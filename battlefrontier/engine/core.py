"""规则引擎核心：阶段机 + 合法行动枚举 + 白板推进（PRD §6.2 / §6.4）。

规则事实源：docs/rules-manual.md（简中官网规则页整理）+ docs/rules-reference.md
（落点速查 + 决议日志），逐条在代码注释标注出处。
白板范围：不执行任何卡面效果，宝可梦只有 HP / 固定伤害招式 / 撤退费用。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from battlefrontier.dsl import ExecutionContext, run_effect
from battlefrontier.dsl.loader import CardLibrary, DslError
from battlefrontier.engine.actions import Action, IllegalActionError
from battlefrontier.engine.events import GameEvent
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    GameState,
    InPlayPokemon,
    PendingChoice,
    PlayerState,
    SpecialCondition,
    Supertype,
)

if TYPE_CHECKING:
    from battlefrontier.dsl.schema import CardEffectDoc


class DeckConfigError(Exception):
    """卡组不满足开局条件（无基础宝可梦 / 张数不足），明确报错而非死循环。"""


def effect_doc_by_ref(
    effects: Mapping[str, CardEffectDoc], card_id: str, name: str
) -> CardEffectDoc | None:
    """按卡身份解析 DSL 文档。

    CardLibrary（装载键 = card_id 精确挂载，2026-09-06 决议）：仅按 card_id 取，
    无名字兜底——card_id 未覆盖但同名有文档时返回 None（防同名异文本静默错挂，
    彷徨夜灵 D 标顶替 H 标事故回归）。朴素 dict = 存量测试兼容路径，按卡名取。
    """
    if isinstance(effects, CardLibrary):
        return effects.get(card_id)
    return effects.get(name)


def effect_doc(
    effects: Mapping[str, CardEffectDoc], card: CardDef
) -> CardEffectDoc | None:
    """effect_doc_by_ref 的 CardDef 便捷封装（引擎全部 card_effects 查询点走此助手）。"""
    return effect_doc_by_ref(effects, card.card_id, card.name)


# 规则盒宝可梦昏厥时对手拿取的奖赏张数（rules-manual §1.4/§8；开放词表，
# 新规则盒在此登记；无规则盒 / 未知规则盒恒 1；V-UNION 一期不实现）
PRIZE_BY_RULE_BOX = {"ex": 2, "V": 2, "VSTAR": 2, "VMAX": 3}


def _energy_satisfied(attached: tuple[CardInstance, ...], cost: tuple[str, ...]) -> bool:
    """招式能量需求（rules-manual §6）：指定属性逐个匹配，无色（"无"）需求任意属性可抵。"""
    remaining = [e.card.energy_type for e in attached]
    for sym in cost:
        if sym == "无":
            continue
        if sym in remaining:
            remaining.remove(sym)
        else:
            return False
    colorless = sum(1 for s in cost if s == "无")
    return len(remaining) >= colorless


def _weakness_resistance(
    atk_card: CardDef, defender: InPlayPokemon, dmg: int, *, weakness: str | None = None,
) -> int:
    """弱点 ×2 / 抗性 -30（rules-manual §6；仅战斗场目标结算，备战目标不计算）。

    weakness：有效弱点覆盖（task 017 妖精领域等弱点改写，由引擎
    _effective_weakness 计算传入）；None = 用防守方卡面弱点。
    """
    wk = weakness if weakness is not None else defender.current.card.weakness
    if wk is not None and wk == atk_card.energy_type:
        dmg *= 2
    if defender.current.card.resistance is not None and defender.current.card.resistance == atk_card.energy_type:
        dmg -= 30  # 现行规则抗性恒 -30（rules-manual §6）
    return max(dmg, 0)


def _attack_damage(
    attack: AttackDef, atk_card: CardDef, defender: InPlayPokemon, *, to_bench: bool = False,
    weakness: str | None = None, damage_mod: int = 0,
) -> int:
    """伤害计算顺序（rules-manual §6）：基准（≤0 终止）→ 攻方修饰 → 弱点 ×2 → 抗性 -30 → 下限 0。

    damage_mod：攻击方持有者身上的声明式伤害修正（task 025 modify_damage，
    引擎 _effective_damage_modifier 求和传入；§6 顺序 2，在弱点抗性前）。
    备战区伤害不计算弱点抗性（贯穿规则，铺伤原语落地时走 to_bench=True）。
    weakness = 有效弱点覆盖（task 017）。
    """
    dmg = attack.damage or 0
    if dmg <= 0:
        return 0
    dmg += damage_mod
    if not to_bench:
        dmg = _weakness_resistance(atk_card, defender, dmg, weakness=weakness)
    # 插入点：防御方身上附加的减伤效果（task 009+）
    return max(dmg, 0)


class GameEngine:
    """持有随机源与事件流；状态本身不可变，apply/new_game 产出新 GameState。

    card_effects：CardLibrary（键 = card_id 精确挂载）或卡名键朴素 dict（存量测试
    兼容路径）；引擎对卡牌内容零硬编码，无文档的训练家卡不可使用。
    """

    def __init__(
        self, rng: RandomSource, card_effects: Mapping[str, CardEffectDoc] | None = None
    ) -> None:
        self.rng = rng
        # CardLibrary 保类型（dict() 会退化为朴素 dict，解析口径从 card_id 滑回卡名）
        self.card_effects = (
            card_effects if isinstance(card_effects, CardLibrary)
            else dict(card_effects or {})
        )
        self.events: list[GameEvent] = []
        self.state: GameState
        # 效果执行中标记（task 026 WP2）：run_effect 期间置位——效果内造成的昏厥
        # 只入 promote_queue 不翻阶段（换上推迟到效果完成后由完成路径统一进行，D-WP2-1）
        self._in_effect = False
        # 招式伤害落点瞬时记录（task 026 WP5 白蕾雅，D-WP5-2；WP6 扩为三元组）：
        # (攻方, 攻方是否太晶, 攻方栈顶 iid)，由攻击伤害路径（on_attack 的 damage
        # 节点，战斗场/备战落点均置位——WP7 F1 归正）在 check_knockouts 前置位；
        # check_knockouts 进入即取走并清空（consume-on-read，防残留串到后续非招式伤害
        # 路径）；iid 供 own_ko_by_attack 触发解析攻击方（task 026 WP6，D-WP6-6）
        self._attack_damage_active: tuple[int, bool, int | None] | None = None

    # ── 事件 ─────────────────────────────────────────────

    def _emit(self, kind: str, player: int | None = None, **detail: object) -> None:
        self.events.append(
            GameEvent(
                seq=len(self.events),
                turn=self.state.turn,
                phase=self.state.phase,
                player=player,
                kind=kind,
                detail=detail,
            )
        )

    # ── 开局（规则书「游戏的准备」）─────────────────────────

    def new_game(self, deck_a: list[CardDef], deck_b: list[CardDef]) -> GameState:
        """掷币定先后手 → 洗牌 → 起手 7 → mulligan → 布阵 → （双方完成后）奖赏 6。

        【规则出处·游戏准备】掷币胜方先攻（白板简化：胜方固定先攻，
        让先选择权留待 Agent 层）；双方起手 7 张，无基础宝可梦须展示手牌、
        洗回重抽（mulligan），对手可按 mulligan 次数抽牌（白板自动化，
        选择权留待 Agent 层）；奖赏卡 6 张。
        """
        self.events = []
        for cards in (deck_a, deck_b):
            basics = [c for c in cards if c.supertype == Supertype.POKEMON and c.stage == 0]
            if not basics:
                raise DeckConfigError("卡组无基础宝可梦，无法开局")
            if len(cards) < 13:
                raise DeckConfigError("卡组张数不足以开局（需 ≥13：起手 7 + 奖赏 6）")
        decks: list[tuple[CardInstance, ...]] = []
        for cards in (deck_a, deck_b):
            base = len(decks) * 10000  # 双方实例 id 区间隔离
            instances = tuple(CardInstance(iid=base + i, card=c) for i, c in enumerate(cards))
            decks.append(self.rng.shuffle(instances))

        first = 0 if self.rng.flip_coin() else 1
        players = [PlayerState(deck=decks[0]), PlayerState(deck=decks[1])]
        self.state = GameState(
            players=(players[0], players[1]), turn=0, current_player=0,
            phase="setup", first_player=first,
        )
        self._emit("coin_flip", None, first_player=first)

        # 起手 7 + mulligan（规则书·游戏准备；rules-reference §1 已核：mulligan 时对方按次数多抽）
        hands: list[tuple[CardInstance, ...]] = []
        mulligan_counts = [0, 0]
        for idx in range(2):
            hand = players[idx].deck[:7]
            deck = players[idx].deck[7:]
            while not any(c.card.supertype == Supertype.POKEMON and c.card.stage == 0 for c in hand):
                mulligan_counts[idx] += 1
                self._emit("mulligan", idx, hand=[c.card.name for c in hand])  # 给对手看过
                deck = self.rng.shuffle(deck + hand)
                hand, deck = deck[:7], deck[7:]
            hands.append(hand)
            players[idx] = players[idx].model_copy(update={"deck": deck, "hand": hand})

        # 对手按 mulligan 次数抽牌（白板自动化：默认抽）
        for idx in range(2):
            bonus = mulligan_counts[1 - idx]
            if bonus:
                p = players[idx]
                players[idx] = p.model_copy(update={
                    "hand": p.hand + p.deck[:bonus],
                    "deck": p.deck[bonus:],
                })
                self._emit("mulligan_bonus_draw", idx, count=bonus)

        # 奖赏卡 6 张在双方战斗场放置完成后设置（rules-reference §1 已核）→ 见 _do_confirm_setup
        self.state = self.state.model_copy(update={"players": (players[0], players[1])})
        self._emit("setup_ready", None)
        self.state = self.state.model_copy(update={"phase": "setup_active", "current_player": 0})
        return self.state

    # ── 合法行动枚举（PRD §6.2）────────────────────────────

    def legal_actions(self, player: int) -> list[Action]:
        s = self.state
        if s.phase == "game_over" or player != s.current_player:
            return []
        p = s.players[player]
        if s.phase == "setup_active":
            return [
                Action(kind="place_active", iid=c.iid)
                for c in p.hand
                if c.card.supertype == Supertype.POKEMON and c.card.stage == 0
            ]
        if s.phase == "setup_bench":
            actions = [
                Action(kind="place_bench", iid=c.iid)
                for c in p.hand
                if c.card.supertype == Supertype.POKEMON and c.card.stage == 0
            ] if len(p.bench) < 5 else []
            return actions + [Action(kind="confirm_setup")]
        if s.phase == "promote":
            # 【规则书·昏厥】战斗场昏厥后须从备战区换上 1 只
            return [Action(kind="promote", bench_index=i) for i in range(len(p.bench))]
        if s.phase == "bench_shrink":
            # 备战区失效缩减（task 026 WP6 零之大空洞，D-WP6-2）：超容方逐只自选弃置
            return [Action(kind="shrink_bench", choices=(m.current.iid,)) for m in p.bench]
        if s.phase == "choice":
            # chooser 挂起：仅挂起方可行动，枚举合法选择（PRD §5.2）
            pc = s.pending_choice
            if pc is None or player != pc.player:
                return []
            from battlefrontier.dsl.chooser import enumerate_choices
            return enumerate_choices(pc)
        if s.phase == "main":
            return self._main_actions(player)
        return []

    def _main_actions(self, player: int) -> list[Action]:
        from battlefrontier.dsl.chooser import (
            ability_feasible,
            condition_met,
            playable_feasible,
        )

        s = self.state
        p = s.players[player]
        actions: list[Action] = []
        in_play: list[InPlayPokemon] = ([p.active] if p.active else []) + list(p.bench)

        # 放置基础宝可梦到备战区：不限次，容量按有效备战上限（规则书·行动阶段；
        # task 026 WP6 零之大空洞 bench_size 声明式覆写，_bench_size 读声明）
        if len(p.bench) < self._bench_size(player):
            for c in p.hand:
                if c.card.supertype == Supertype.POKEMON and c.card.stage == 0:
                    actions.append(Action(kind="place_bench", iid=c.iid))

        # 进化：每只每回合限 1 次；登场/已进化当回合不可再进化（规则书·进化）
        for c in p.hand:
            if c.card.supertype == Supertype.POKEMON and c.card.stage >= 1:
                for t in in_play:
                    top = t.current
                    if (
                        c.card.evolves_from == top.card.name
                        and top.iid not in p.entered_play_this_turn
                        and top.iid not in p.evolved_this_turn
                    ):
                        actions.append(Action(kind="evolve", iid=c.iid, target_iid=top.iid))

        # 能量：每回合限附着 1 张（规则书·能量）
        if not p.energy_attached_this_turn:
            for c in p.hand:
                if c.card.supertype == Supertype.ENERGY:
                    for t in in_play:
                        actions.append(
                            Action(kind="attach_energy", iid=c.iid, target_iid=t.current.iid)
                        )

        # 宝可梦道具：每只限 1 个、不限次（rules-manual §5；attach 是规则行动，
        # 道具效果由 DSL passive_static/grant_attack 声明驱动）
        for c in p.hand:
            if c.card.supertype == Supertype.TRAINER and c.card.trainer_subtype == "宝可梦道具":
                for t in in_play:
                    if t.attached_tool is None:
                        actions.append(
                            Action(kind="attach_tool", iid=c.iid, target_iid=t.current.iid)
                        )

        # 撤退：每回合 1 次机会（pokemon.cn basic_rules05）；弃撤退费用数量的能量，与备战区对换；
        # 有效撤退费含常驻修正（task 026 WP4，_effective_retreat_cost 读 DSL 声明）；
        # 撤退锁（task 026 WP6 沙铃仙人掌 穷追不舍，D-WP6-6）：被锁战斗宝可梦不枚举撤退；
        # 睡眠/麻痹不可撤退（task 026 WP7，D-WP7-2，rules-manual §7.2；混乱不影响撤退）
        if (
            p.active
            and not p.active.retreat_lock
            and not (
                p.active.conditions
                & {SpecialCondition.ASLEEP, SpecialCondition.PARALYZED}
            )
            and p.bench
            and not p.retreated_this_turn
            and len(p.active.attached_energy) >= self._effective_retreat_cost(p.active, player)
        ):
            for i in range(len(p.bench)):
                actions.append(Action(kind="retreat", bench_index=i))

        # 攻击：能量满足 且（有伤害 或 有 on_attack DSL 绑定）的招式各一条行动
        # （rules-manual §6 能量需求；纯效果招式经 DSL 结算，task 012）；
        # 先攻方第一回合不能攻击（规则书·回合的进行）。
        # 睡眠/麻痹不可用招式（task 026 WP7，D-WP7-2，rules-manual §7.2；
        # 混乱照常枚举——攻击时掷币判定，D1 决议）。
        # 授予招式（task 016）：attached_tool 的招式接在自身招式后枚举，能量由持有者
        # 附着能量支付，DSL 绑定取道具文档；无绑定的授予招式不枚举（task 015 纪律）。
        first_turn_ban = s.turn == 1 and player == s.first_player
        status_ban = p.active is not None and bool(
            p.active.conditions & {SpecialCondition.ASLEEP, SpecialCondition.PARALYZED}
        )
        if p.active and not first_turn_ban and not status_ban:
            own_attacks = p.active.current.card.attacks
            own_doc = effect_doc(self.card_effects, p.active.current.card)
            tool = p.active.attached_tool
            combined = [(a, own_doc) for a in own_attacks]
            if tool is not None:
                tool_doc = effect_doc(self.card_effects, tool.card)
                combined += [(a, tool_doc) for a in tool.card.attacks]
            for i, (attack, doc) in enumerate(combined):
                # 攻击冷却锁（task 026 WP4 裁决 2，lock_attack）：被锁招式不枚举
                if attack.name in p.active.attack_locks:
                    continue
                # 有效招式费（task 026 WP5，D-WP5-4）：_effective_attack_cost 读 DSL
                # modify_attack_cost 声明（月月熊 老练招式）；枚举与执行共用求值点
                if not _energy_satisfied(
                    p.active.attached_energy,
                    self._effective_attack_cost(p.active, player, attack),
                ):
                    continue
                has_dsl = doc is not None and any(
                    e.trigger == "on_attack" and e.attack == attack.name
                    for e in doc.effects
                )
                if attack.damage is not None or has_dsl:
                    actions.append(Action(kind="attack", attack_index=i))

        # 训练家卡：物品每回合不限次数；支援者每回合限 1 张且先攻方首回合禁用
        # （PRD §6.6 / 规则书·训练家卡）；效果经 DSL 解释器执行，无文档不可使用
        for c in p.hand:
            if c.card.supertype != Supertype.TRAINER:
                continue
            if c.card.trainer_subtype not in ("物品", "支援者"):
                continue  # 宝可梦道具 / 竞技场的使用骨架随机制落地（task 008+）
            doc = effect_doc(self.card_effects, c.card)
            if doc is None or not any(e.trigger == "on_play" for e in doc.effects):
                continue
            if c.card.trainer_subtype == "支援者" and (
                p.supporter_played_this_turn or first_turn_ban
            ):
                continue
            # 条件门（task 014：「只有…时才可使用」）+ 成本可行性门（chooser task 009）：
            # 条件不满足 / 成本无法支付 / 无合法落点则不枚举
            effect = next(e for e in doc.effects if e.trigger == "on_play")
            if not condition_met(effect.condition, self, player):
                continue
            if not playable_feasible(effect, p, bench_full=len(p.bench) >= self._bench_size(player),
                                     opponent=s.players[1 - player],
                                     first_turn=s.turn == 1):
                continue
            actions.append(Action(kind="play_trainer", iid=c.iid))

        # 竞技场（task 017，rules-manual §5）：每回合限打出 1 张；与场上同名不可打出
        for c in p.hand:
            if c.card.supertype != Supertype.TRAINER or c.card.trainer_subtype != "竞技场":
                continue
            if p.stadium_played_this_turn:
                continue
            if s.stadium is not None and s.stadium.card.name == c.card.name:
                continue
            actions.append(Action(kind="play_stadium", iid=c.iid))

        # stadium_grant：场上竞技场赋予的每方每回合 1 次行动（无 DSL 文档不可发动）；
        # 落点可行性门（search_deck destination=bench 备战满不枚举——无效果不可使用）
        if s.stadium is not None and not p.stadium_used_this_turn:
            sdoc = effect_doc(self.card_effects, s.stadium.card)
            seffect = next(
                (e for e in sdoc.effects if e.trigger == "stadium_grant"), None,
            ) if sdoc else None
            if seffect is not None and playable_feasible(
                seffect, p, bench_full=len(p.bench) >= self._bench_size(player),
                opponent=s.players[1 - player], first_turn=s.turn == 1,
            ):
                actions.append(Action(kind="use_stadium"))

        # 特性（ability_manual）：场上宝可梦每回合按 DSL limit 发动（rules-manual 特性节）；
        # 限次强制 + 条件门（task 017：condition 不满足不枚举）+ 可行性门（池为空不枚举；
        # 门未覆盖的形式 DslError 不猜）
        for t in in_play:
            top = t.current
            doc = effect_doc(self.card_effects, top.card)
            if doc is None:
                continue
            effect = next((e for e in doc.effects if e.trigger == "ability_manual"), None)
            if effect is None:
                continue
            if effect.limit is None:
                raise DslError(f"{top.card.name} 特性未声明 limit（不猜；请在 DSL 补 limit）")
            if effect.limit == "once_per_turn" and top.iid in p.abilities_used_this_turn:
                continue
            if (
                effect.limit == "once_per_turn_shared"
                and top.card.name in p.shared_abilities_used_this_turn
            ):
                continue
            if not condition_met(effect.condition, self, player, t):
                continue
            if not ability_feasible(effect, self, player):
                continue
            actions.append(Action(kind="use_ability", iid=top.iid))

        actions.append(Action(kind="end_turn"))
        return actions

    # ── 推进 ─────────────────────────────────────────────

    def apply(self, player: int, action: Action) -> GameState:
        legal = self.legal_actions(player)
        if action not in legal:
            raise IllegalActionError(f"{action} 不在合法行动列表中")
        handler = getattr(self, f"_do_{action.kind}")
        handler(player, action)
        return self.state

    def _set_player(self, idx: int, p: PlayerState) -> None:
        players = list(self.state.players)
        players[idx] = p
        self.state = self.state.model_copy(update={"players": (players[0], players[1])})

    def _take_from_hand(self, p: PlayerState, iid: int) -> tuple[PlayerState, CardInstance]:
        card = next(c for c in p.hand if c.iid == iid)
        return p.model_copy(update={"hand": tuple(c for c in p.hand if c.iid != iid)}), card

    def _do_place_active(self, player: int, action: Action) -> None:
        """【规则出处·游戏准备】起手必须选择 1 只基础宝可梦放战斗场。"""
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        active = InPlayPokemon(stack=(card,))
        self._set_player(player, p.model_copy(update={
            "active": active,
            "entered_play_this_turn": p.entered_play_this_turn | {card.iid},
        }))
        self._emit("place_active", player, iid=card.iid, name=card.card.name)
        self.state = self.state.model_copy(update={"phase": "setup_bench"})

    def _queue_event_trigger(self, player: int, iid: int, event: str) -> None:
        """事件触发请求入队（task 026 WP3，pending_event_triggers；FIFO）。"""
        self.state = self.state.model_copy(update={
            "pending_event_triggers": self.state.pending_event_triggers
            + ((player, iid, event),),
        })

    def _fire_trigger_on_event(
        self, player: int, source: CardInstance, holder: InPlayPokemon | None,
        event: str, attacker_iid: int | None = None,
    ) -> bool:
        """trigger_on_event 分发公共点（task 026 WP2/WP3/WP6）：检索来源卡文档中挂该事件的
        效果，condition 门控后自动发动（「可使用」的放弃选项不建模，D-WP2-3）；
        completion="ability" = 特性卡本体不弃置，完成后回主阶段。
        own_ko_by_attack（WP6）：来源已因昏厥进弃牌堆（holder=None，condition 以
        holder=None 求值）；completion="attack" 且发动前置 turn_after_promote=触发方——
        攻击方的回合已因攻击消耗，触发效果结算与换上完毕后回合权归被攻击方（D-WP6-6）。
        attacker_iid 穿透进 ctx.attacker_iid（opponent_attacker 选择器数据源）。
        同卡多个同事件效果 = DslError（不猜，需要时再扩展顺序分发）。
        返回是否实际发动（排水方据此决定继续排下一条还是交棒给被触发效果）。
        """
        doc = effect_doc(self.card_effects, source.card)
        if doc is None:
            return False
        matched = [
            (i, e) for i, e in enumerate(doc.effects)
            if e.trigger == "trigger_on_event" and e.event == event
        ]
        if len(matched) > 1:
            raise DslError(
                f"{source.card.name}: 一张卡多个同事件 trigger_on_event 效果"
                f"（event={event}；需要时再扩展顺序分发）"
            )
        if not matched:
            return False
        effect_index, effect = matched[0]
        from battlefrontier.dsl.chooser import condition_met

        if not condition_met(effect.condition, self, player, holder):
            return False
        self._emit("trigger_on_event", player, iid=source.iid,
                   name=source.card.name, event=event)
        if event == "own_ko_by_attack":
            # 触发方的换上完成后回合权归被攻击方（=触发方自己；攻击方回合已消耗）
            self.state = self.state.model_copy(update={
                "turn_after_promote": player,
            })
            self._run_or_suspend(player, source, effect_index, start=0,
                                 completion="attack", attacker_iid=attacker_iid)
        else:
            self._run_or_suspend(player, source, effect_index, start=0,
                                 completion="ability")
        return True

    def _drain_event_triggers(self) -> bool:
        """事件触发队列共享排水（task 026 WP3/WP6）：先排 pending_event_triggers
        （own_evolve_from_hand 等），再排 pending_ko_triggers（own_ko_by_attack）。
        来源已不在场上时——own_ko_by_attack 从该玩家弃牌堆按 iid 找回来源（昏厥离场
        后仍可发动，holder=None）；其余事件离场即失效，跳过排下一条。
        返回是否实际发动了某条（发动则交棒给被触发效果的执行/挂起）。
        """
        while self.state.pending_event_triggers:
            tp, tiid, tevent = self.state.pending_event_triggers[0]
            self.state = self.state.model_copy(update={
                "pending_event_triggers": self.state.pending_event_triggers[1:],
            })
            try:
                _, _, holder = self._find_in_play(self.state.players[tp], tiid)
            except IllegalActionError:
                continue  # 来源已不在场上：离场即失效，跳过
            if self._fire_trigger_on_event(tp, holder.current, holder, tevent):
                return True
        while self.state.pending_ko_triggers:
            tp, tiid, tattacker = self.state.pending_ko_triggers[0]
            self.state = self.state.model_copy(update={
                "pending_ko_triggers": self.state.pending_ko_triggers[1:],
            })
            holder: InPlayPokemon | None = None
            try:
                _, _, holder = self._find_in_play(self.state.players[tp], tiid)
                source = holder.current
            except IllegalActionError:
                # 昏厥离场：从弃牌堆按 iid 找回来源卡（整叠进弃牌堆，必然在）
                source = next(
                    (c for c in self.state.players[tp].discard if c.iid == tiid),
                    None,
                )
                if source is None:
                    continue
            if self._fire_trigger_on_event(tp, source, holder,
                                           "own_ko_by_attack",
                                           attacker_iid=tattacker):
                return True
        return False

    def _do_place_bench(self, player: int, action: Action) -> None:
        """【规则出处·游戏准备】备战区可放任意只基础宝可梦（≤5）。

        trigger_on_event 分发（task 026 WP2）：仅当进入时 phase=="main"（自己的回合
        从手牌使出放于备战区）；setup 阶段的放置不触发，DSL search_deck
        destination=bench 不经本行动（天然不触发）。
        """
        entered_phase = self.state.phase
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        self._set_player(player, p.model_copy(update={
            "bench": p.bench + (InPlayPokemon(stack=(card,)),),
            "entered_play_this_turn": p.entered_play_this_turn | {card.iid},
        }))
        self._emit("place_bench", player, iid=card.iid, name=card.card.name)
        if entered_phase != "main":
            return
        placed = self.state.players[player].bench[-1]  # 刚放置的宝可梦（bench 末尾）
        self._fire_trigger_on_event(player, placed.current, placed,
                                    "own_play_from_hand_to_bench")

    def _do_confirm_setup(self, player: int, action: Action) -> None:
        if player == 0:
            self.state = self.state.model_copy(update={"phase": "setup_active", "current_player": 1})
        else:
            # 双方战斗场放置完成 → 设置奖赏卡 6 张（rules-reference §1 已核顺序）→ 翻开开局
            for idx in range(2):
                p = self.state.players[idx]
                self._set_player(idx, p.model_copy(update={
                    "prizes": p.deck[:6],
                    "deck": p.deck[6:],
                }))
            self._emit("set_prizes", None)
            self._begin_turn(self.state.first_player, first_turn=True)

    # ── 主阶段行动（规则书「回合的进行」）────────────────────

    def _find_in_play(self, p: PlayerState, top_iid: int) -> tuple[str, int, InPlayPokemon]:
        """按栈顶 iid 定位场上宝可梦：返回 (位置, bench 下标, 对象)。"""
        if p.active and p.active.current.iid == top_iid:
            return "active", -1, p.active
        for i, b in enumerate(p.bench):
            if b.current.iid == top_iid:
                return "bench", i, b
        raise IllegalActionError(f"场上不存在栈顶 iid={top_iid} 的宝可梦")

    def _replace_in_play(self, p: PlayerState, slot: str, idx: int, new: InPlayPokemon) -> PlayerState:
        if slot == "active":
            return p.model_copy(update={"active": new})
        bench = list(p.bench)
        bench[idx] = new
        return p.model_copy(update={"bench": tuple(bench)})

    def _do_evolve(self, player: int, action: Action) -> None:
        """【规则书·进化】手牌进化卡覆盖到对应宝可梦上，特殊状态恢复，伤害保留。

        trigger_on_event 分发（task 026 WP3，own_evolve_from_hand）：本行动直发
        （不入队）；DSL evolve 原语路径按用户裁决（2026-09-07）分流——zone="hand"
        （神奇糖果跳阶）经 _apply_evolution 入队 pending_event_triggers 效果完成后
        排水，zone="deck"（招式学习器「进化」）不触发；setup 阶段无进化行动，
        天然不触发。
        """
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        slot, idx, target = self._find_in_play(p, action.target_iid)  # type: ignore[arg-type]
        evolved = target.model_copy(update={
            "stack": target.stack + (card,),
            "conditions": frozenset(),
            # 撤退锁随进化解除（task 026 WP6，D-WP6-6）
            "retreat_lock": False,
            # 麻痹施加标记随状态恢复清除（task 026 WP7，D-WP7-2）
            "paralyzed_mark": None,
        })
        p = self._replace_in_play(p, slot, idx, evolved)
        self._set_player(player, p.model_copy(update={
            "evolved_this_turn": p.evolved_this_turn | {card.iid},
        }))
        self._emit("evolve", player, iid=card.iid, name=card.card.name, onto=target.current.card.name)
        _, _, holder = self._find_in_play(self.state.players[player], card.iid)
        self._fire_trigger_on_event(player, card, holder, "own_evolve_from_hand")

    def _do_attach_energy(self, player: int, action: Action) -> None:
        """【规则书·能量】每回合限 1 张，从手牌附着到场上宝可梦。"""
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        slot, idx, target = self._find_in_play(p, action.target_iid)  # type: ignore[arg-type]
        p = self._replace_in_play(p, slot, idx, target.model_copy(update={
            "attached_energy": target.attached_energy + (card,),
        }))
        self._set_player(player, p.model_copy(update={"energy_attached_this_turn": True}))
        self._emit("attach_energy", player, iid=card.iid, target=target.current.card.name)

    def _do_attach_tool(self, player: int, action: Action) -> None:
        """【rules-manual §5】宝可梦道具从手牌放到场上宝可梦身上（每只限 1 个）。"""
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        slot, idx, target = self._find_in_play(p, action.target_iid)  # type: ignore[arg-type]
        p = self._replace_in_play(p, slot, idx, target.model_copy(update={
            "attached_tool": card,
        }))
        self._set_player(player, p)
        self._emit("attach_tool", player, iid=card.iid, name=card.card.name,
                   target=target.current.card.name)

    def _do_play_stadium(self, player: int, action: Action) -> None:
        """【rules-manual §5】竞技场：手牌打出放公共场地；旧场进其放置方
        （stadium_owner）弃牌区；每回合限 1 张、同名不可打出（枚举层已拦截）。"""
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        old, old_owner = self.state.stadium, self.state.stadium_owner
        self._set_player(player, p.model_copy(update={"stadium_played_this_turn": True}))
        self.state = self.state.model_copy(update={
            "stadium": card, "stadium_owner": player,
        })
        if old is not None and old_owner is not None:
            owner = self.state.players[old_owner]
            self._set_player(old_owner, owner.model_copy(update={
                "discard": owner.discard + (old,),
            }))
        self._emit("play_stadium", player, iid=card.iid, name=card.card.name,
                   replaced=old.card.name if old else None)
        # 备战区失效缩减（task 026 WP6 零之大空洞，D-WP6-2）：旧竞技场离场后超容方
        # 逐只自选弃置，双方同缩由旧场持有者先执行；缩减完成后回出牌方主阶段
        self._check_bench_shrink(first=old_owner, resume=(player, "main"))

    def _do_use_stadium(self, player: int, action: Action) -> None:
        """stadium_grant 行动（task 017）：以当前玩家为 ctx 跑竞技场 DSL 效果块，
        可挂起（chooser）；完成后标记本回合已用。"""
        stadium = self.state.stadium
        assert stadium is not None  # legal_actions 已保证
        p = self.state.players[player]
        self._set_player(player, p.model_copy(update={"stadium_used_this_turn": True}))
        self._emit("use_stadium", player, name=stadium.card.name)
        doc = effect_doc(self.card_effects, stadium.card)
        assert doc is not None  # legal_actions 已保证竞技场有 DSL 文档
        effect_index = next(
            i for i, e in enumerate(doc.effects) if e.trigger == "stadium_grant"
        )
        self._run_or_suspend(player, stadium, effect_index, start=0,
                             completion="stadium")

    def _discard_turn_end_tools(self, player: int) -> None:
        """回合结束弃置：DSL grant_attack args.discard_at_turn_end 声明的道具
        （招式学习器 进化原文：「将在自己的回合结束时被放于弃牌区」）。"""
        p = self.state.players[player]

        def strip(mon: InPlayPokemon) -> tuple[InPlayPokemon, CardInstance | None]:
            tool = mon.attached_tool
            if tool is None:
                return mon, None
            doc = effect_doc(self.card_effects, tool.card)
            flagged = doc is not None and any(
                node.action == "grant_attack" and node.args.get("discard_at_turn_end")
                for e in doc.effects for node in e.actions
            )
            if flagged:
                return mon.model_copy(update={"attached_tool": None}), tool
            return mon, None

        discarded: list[CardInstance] = []
        new_active, t = (strip(p.active) if p.active else (None, None))
        if t:
            discarded.append(t)
        new_bench = []
        for m in p.bench:
            m2, t = strip(m)
            new_bench.append(m2)
            if t:
                discarded.append(t)
        if discarded:
            self._set_player(player, p.model_copy(update={
                "active": new_active, "bench": tuple(new_bench),
                "discard": p.discard + tuple(discarded),
            }))
            for c in discarded:
                self._emit("discard_tool", player, iid=c.iid, name=c.card.name)

    def _on_turn_end(self, player: int) -> None:
        """回合结束统一收尾（所有回合结束路径必经）：道具回合末弃置（task 015）
        + 跨回合 KO 标记清除（task 017 化危为吉「上一个对手的回合」语义：
        标记只保留到自己回合结束）+ 回合级奖赏加成标记清除（task 026 WP5 白蕾雅，
        D-WP5-2 turn scoped）+ 撤退锁解除（task 026 WP6 穷追不舍「下个对手的回合」，
        D-WP6-6：被锁目标自己的回合结束解除）+ 回合级伤害修正标记与精确口径昏厥
        标记清除（task 026 WP7，D-WP7-3/D-WP7-7）。"""
        self._discard_turn_end_tools(player)
        p = self.state.players[player]
        if any(m.retreat_lock for m in ([p.active] if p.active else []) + list(p.bench)):
            def _unlock(mon: InPlayPokemon) -> InPlayPokemon:
                return mon.model_copy(update={"retreat_lock": False}) if mon.retreat_lock else mon

            p = p.model_copy(update={
                "active": _unlock(p.active) if p.active else None,
                "bench": tuple(_unlock(m) for m in p.bench),
            })
            self._set_player(player, p)
        update: dict[str, object] = {}
        if p.own_ko_during_opponent_turn:
            update["own_ko_during_opponent_turn"] = False
        if p.extra_prize_tera_ko:
            update["extra_prize_tera_ko"] = False
        # task 026 WP7：回合级伤害修正标记（D-WP7-3 空手道王的修炼）与精确口径
        # 昏厥标记（D-WP7-7 古玉鱼）同样在持有者回合结束清除
        if p.turn_damage_mods:
            update["turn_damage_mods"] = ()
        if p.own_ko_by_attack_during_opponent_turn:
            update["own_ko_by_attack_during_opponent_turn"] = False
        if update:
            self._set_player(player, p.model_copy(update=update))

    # ── 宝可梦检查（task 026 WP7，D-WP7-1/2；rules-manual §7.2）──────────────

    # 检查阶段状态结算固定序（D-WP7-1）：毒→灼→眠→麻；混乱不在本阶段结算
    # （攻击时掷币，D1 决议 task 013）
    _CHECK_STATUS_ORDER = (
        SpecialCondition.POISONED, SpecialCondition.BURNED,
        SpecialCondition.ASLEEP, SpecialCondition.PARALYZED,
    )

    def _start_pokemon_check(self, ended_player: int) -> None:
        """宝可梦检查（task 026 WP7，D-WP7-1；rules-manual §7.2）：所有回合结束路径
        统一接入（end_turn / 攻击结算完毕 / 攻击致昏厥换上后）。

        同步结算（无选择）：回合持有者方先、双方场上宝可梦各按固定序——毒 +10；
        灼 +20 后持有者掷币，正面恢复反面保持；眠掷币正面恢复反面保持；麻按施加
        标记恢复（D-WP7-2：持有者回合结束且非施加当回合才恢复）。随后分发现场
        pokemon_check 事件触发（雪妖女 冻结帷幕；离场即失效由排水点语义保证），
        全部处理结束后统一 check_knockouts + 奖赏 + 换上（§7.2 末注），再开下一回合。
        """
        # 回合结束统一收尾（task 026 WP7 复核 M1）：攻击致昏厥→换上路径不经
        # _on_turn_end——检查入口统一补调（retreat_lock / extra_prize_tera_ko /
        # own_ko_during_opponent_turn / discard_at_turn_end 道具自弃四项防陈旧
        # 泄漏）；end_turn / 攻击完成路径已调过一次，四处职责幂等，重复调用无害
        self._on_turn_end(ended_player)
        nxt = 1 - ended_player
        self.state = self.state.model_copy(update={
            "phase": "pokemon_check", "pokemon_check_next": nxt,
        })
        self._emit("pokemon_check", None, next_player=nxt)
        for owner in (ended_player, nxt):  # 回合持有者方先
            self._settle_conditions(owner, holder_turn_ended=owner == ended_player)
        # pokemon_check 事件触发入队（双方场上声明该事件的宝可梦；FIFO 排水）
        for owner in (ended_player, nxt):
            pl = self.state.players[owner]
            for mon in ([pl.active] if pl.active else []) + list(pl.bench):
                doc = effect_doc(self.card_effects, mon.current.card)
                if doc is not None and any(
                    e.trigger == "trigger_on_event" and e.event == "pokemon_check"
                    for e in doc.effects
                ):
                    self._queue_event_trigger(owner, mon.current.iid, "pokemon_check")
        self._advance_pokemon_check()

    def _settle_conditions(self, owner: int, *, holder_turn_ended: bool) -> None:
        """单方场上宝可梦的检查阶段状态结算（毒→灼→眠→麻固定序；逐只发 check_status）。"""
        p = self.state.players[owner]
        positions = ([("active", -1)] if p.active else []) + [
            ("bench", i) for i in range(len(p.bench))
        ]
        for slot, idx in positions:
            for status in self._CHECK_STATUS_ORDER:
                p = self.state.players[owner]
                mon = p.active if slot == "active" else p.bench[idx]
                if status not in mon.conditions:
                    continue
                name = mon.current.card.name
                if status == SpecialCondition.POISONED:
                    # 中毒：放 1 个伤害指示物（不自动恢复，rules-manual §7.2）
                    mon = mon.model_copy(update={"damage": mon.damage + 10})
                    self._set_player(owner, self._replace_in_play(p, slot, idx, mon))
                    self._emit("check_status", owner, name=name,
                               status="poisoned", damage=10)
                elif status == SpecialCondition.BURNED:
                    # 灼伤：放 2 个指示物后掷币，正面恢复反面保持（§7.2）
                    heads = self.rng.flip_coin()
                    update: dict[str, object] = {"damage": mon.damage + 20}
                    if heads:
                        update["conditions"] = mon.conditions - {status}
                    mon = mon.model_copy(update=update)
                    self._set_player(owner, self._replace_in_play(p, slot, idx, mon))
                    self._emit("check_status", owner, name=name, status="burned",
                               damage=20, flip="heads" if heads else "tails",
                               recovered=heads)
                elif status == SpecialCondition.ASLEEP:
                    # 睡眠：掷币正面恢复反面保持（§7.2；不放伤害指示物）
                    heads = self.rng.flip_coin()
                    if heads:
                        mon = mon.model_copy(update={
                            "conditions": mon.conditions - {status},
                        })
                        self._set_player(owner, self._replace_in_play(p, slot, idx, mon))
                    self._emit("check_status", owner, name=name, status="asleep",
                               flip="heads" if heads else "tails", recovered=heads)
                else:
                    # 麻痹：持有者回合结束且非施加当回合才恢复（D-WP7-2 施加标记）；
                    # 无标记（直接构造入场等）= 持有者回合结束即恢复
                    recover = holder_turn_ended and (
                        mon.paralyzed_mark is None
                        or mon.paralyzed_mark != (self.state.turn, owner)
                    )
                    if recover:
                        mon = mon.model_copy(update={
                            "conditions": mon.conditions - {status},
                            "paralyzed_mark": None,
                        })
                        self._set_player(owner, self._replace_in_play(p, slot, idx, mon))
                    self._emit("check_status", owner, name=name,
                               status="paralyzed", recovered=recover)

    def _advance_pokemon_check(self) -> None:
        """检查推进（D-WP7-1）：事件触发排水（挂起时交棒——恢复后经
        _run_or_suspend 完成路径的检查拦截回本函数）→ 统一 check_knockouts +
        奖赏（§7.2 末注）→ 战斗场昏厥换上（预置 turn_after_promote=检查后回合方）
        → 失效缩减复查 → 开下一回合。"""
        if self.state.phase == "game_over":
            return
        if self._drain_event_triggers():
            return  # 交棒被触发效果；其完成路径回本函数继续推进
        self.check_knockouts()
        if self.state.phase == "game_over":
            return
        nxt = self.state.pokemon_check_next
        assert nxt is not None  # 仅检查进行中进入本函数
        if self.state.phase == "choice":
            # 防卫（task 026 WP7 复核 m2）：check_knockouts 内排水昏厥触发器
            # （own_ko_by_attack）可能挂起选择——不得穿透到 _begin_turn；
            # 恢复后经 _run_or_suspend 完成路径的检查拦截回本函数
            return
        if self.state.phase == "promote":
            # 战斗场昏厥换上完成后进检查后回合（换上路径 _proceed_after_turn_end
            # 读 pokemon_check_next 直接开回合，不重入检查）
            self.state = self.state.model_copy(update={"turn_after_promote": nxt})
            return
        # 失效缩减复查（承接原攻击完成路径的 D-WP6-2 触点：检查内触发的离场
        # 效果同样可能造成超容；缩减完成后经 _proceed_after_turn_end 开回合）
        if self._check_bench_shrink(first=None, resume=(nxt, "begin_turn")):
            return
        self.state = self.state.model_copy(update={"pokemon_check_next": None})
        self._begin_turn(nxt)

    def _proceed_after_turn_end(self, next_player: int) -> None:
        """回合权交接统一出口（task 026 WP7）：换上/缩减完成后的回合推进——
        检查进行中（pokemon_check_next 非 None = 检查收尾的换上/缩减路径）直接
        开检查后回合（防重入）；否则插入宝可梦检查（D-WP7-1：所有回合结束路径
        必经）。next_player = 常规回合权归属（=检查后开回合方，ended=1−该值）。"""
        pending = self.state.pokemon_check_next
        if pending is not None:
            self.state = self.state.model_copy(update={"pokemon_check_next": None})
            self._begin_turn(pending)
            return
        self._start_pokemon_check(1 - next_player)

    def _do_retreat(self, player: int, action: Action) -> None:
        """【规则书·撤退】弃撤退费用数量的能量，与备战区对换，撤退方特殊状态恢复。
        有效撤退费含常驻修正（task 026 WP4，_effective_retreat_cost 读 DSL 声明）。"""
        p = self.state.players[player]
        active = p.active
        cost = self._effective_retreat_cost(active, player)
        discarded = active.attached_energy[:cost]
        retreated = active.model_copy(update={
            "attached_energy": active.attached_energy[cost:],
            "conditions": frozenset(),
            # 攻击冷却锁随撤退清除（task 026 WP4 裁决 2，同特殊状态恢复口径）
            "attack_locks": (),
            "attack_lock_turn": None,
            # 麻痹施加标记随状态恢复清除（task 026 WP7，D-WP7-2）
            "paralyzed_mark": None,
        })
        new_active = p.bench[action.bench_index]  # type: ignore[index]
        bench = list(p.bench)
        bench[action.bench_index] = retreated  # type: ignore[index]
        self._set_player(player, p.model_copy(update={
            "active": new_active,
            "bench": tuple(bench),
            "discard": p.discard + discarded,
            "retreated_this_turn": True,
        }))
        self._emit("retreat", player, out=retreated.current.card.name,
                   into=new_active.current.card.name, paid=cost)

    def _do_attack(self, player: int, action: Action) -> None:
        """【rules-manual §6】按 attack_index 选招式；攻击后回合结束。昏厥统一走 check_knockouts。

        招式有 on_attack DSL 绑定时（task 012）：伤害与附加效果全部由 DSL 结算
        （damage 原语负责伤害与目标，AttackDef.damage 不重复结算），可挂起（chooser），
        完成且无昏厥分支时推进对手回合（completion="attack"）。
        回合结束统一进宝可梦检查（task 026 WP7，D-WP7-1：_start_pokemon_check），
        检查完毕才开下一回合。
        """
        s = self.state
        atk = s.players[player].active
        # 授予招式（task 016）：attack_index 越过自身招式数时取 attached_tool 的招式，
        # DSL 文档与效果源均为道具卡（如招式学习器 进化的「进化」）
        own_attacks = atk.current.card.attacks
        tool = atk.attached_tool
        if action.attack_index < len(own_attacks):
            attack = own_attacks[action.attack_index]
            doc = effect_doc(self.card_effects, atk.current.card)
            source = atk.current
        else:
            assert tool is not None  # legal_actions 已保证索引合法
            attack = tool.card.attacks[action.attack_index - len(own_attacks)]
            doc = effect_doc(self.card_effects, tool.card)
            source = tool
        # 混乱（D1 决议，rules-reference 附录 A）：战斗宝可梦决定使用招式时掷 1 次硬币——
        # 正面招式正常发动（混乱不解除）；反面招式完全失败 + 自身 3 个伤害指示物。
        if SpecialCondition.CONFUSED in atk.conditions:
            heads = self.rng.flip_coin()
            self._emit("confusion_check", player, name=atk.current.card.name,
                       attack=attack.name, result="heads" if heads else "tails")
            if not heads:
                p = self.state.players[player]
                hurt = atk.model_copy(update={"damage": atk.damage + 30})
                self._set_player(player, self._replace_in_play(p, "active", -1, hurt))
                self._emit("confusion_self_damage", player,
                           name=atk.current.card.name, damage=30)
                self.check_knockouts()
                if self.state.phase == "game_over":
                    return
                if self.state.phase == "promote":
                    # 自我昏厥：攻击方换上后回合权给对手（攻击已消耗）
                    self.state = self.state.model_copy(update={
                        "turn_after_promote": 1 - player,
                    })
                    return
                self._on_turn_end(player)
                self._start_pokemon_check(player)
                return
            # 正面：继续正常结算（混乱不解除）
        effect_index = next(
            (i for i, e in enumerate(doc.effects)
             if e.trigger == "on_attack" and e.attack == attack.name),
            None,
        ) if doc else None
        if effect_index is not None:
            effect = doc.effects[effect_index]
            # on_attack 效果级 condition（task 026 WP1，赫普的古月鸟「则这个招式失败」）：
            # 条件不满足 → 招式失败，不结算伤害/效果，回合照常结束（攻击已消耗）
            if effect.condition is not None:
                from battlefrontier.dsl.chooser import condition_met

                if not condition_met(effect.condition, self, player, atk):
                    self._emit("attack", player, name=atk.current.card.name,
                               attack=attack.name, failed=True,
                               condition=effect.condition)
                    self._on_turn_end(player)
                    self._start_pokemon_check(player)
                    return
            self._emit("attack", player, name=atk.current.card.name, attack=attack.name)
            self._run_or_suspend(player, source, effect_index, start=0,
                                 completion="attack")
            return
        defender = 1 - player
        d = s.players[defender]
        dmg = _attack_damage(attack, atk.current.card, d.active,
                             weakness=self._effective_weakness(player, d.active),
                             damage_mod=self._effective_damage_modifier(
                                 atk, player,
                                 target_rule_box=d.active.current.card.rule_box))
        target = d.active.model_copy(update={"damage": d.active.damage + dmg})
        self._set_player(defender, d.model_copy(update={"active": target}))
        self._emit("attack", player, name=atk.current.card.name, attack=attack.name,
                   damage=dmg, target=target.current.card.name)
        # 白蕾雅奖赏加成（task 026 WP5，D-WP5-2）：招式伤害落点对手战斗场 → 置瞬时记录，
        # check_knockouts → _knockout_one 的 take_prize 触点读取（仅 final>0 才算
        # 「招式的伤害导致」）；效果/指示物路径永不置位
        if dmg > 0:
            self._attack_damage_active = (player, atk.current.card.is_tera, atk.current.iid)
        self.check_knockouts()
        if self.state.phase in ("game_over", "promote", "choice"):
            # 游戏已结束 / 等待换上 / 昏厥触发器挂起选择（own_ko_by_attack，task 026 WP6
            # ——挂起的选择属于被触发效果，其恢复路径自行收尾，本层不推进回合）
            return
        self._on_turn_end(player)
        self._start_pokemon_check(player)

    def _effective_hp(self, mon: InPlayPokemon, player: int) -> int:
        """最大 HP 含道具常驻修正（rules-manual §8 昏厥判定的 HP 基准）。

        引擎对卡牌内容零硬编码：修正值读道具 DSL 文档 passive_static 的
        modify_hp 声明（condition 如 holder_is_basic 在求值点判定）。
        """
        hp = mon.current.card.hp or 0
        tool = mon.attached_tool
        if tool is None:
            return hp
        doc = effect_doc(self.card_effects, tool.card)
        if doc is None:
            return hp
        from battlefrontier.dsl.chooser import condition_met

        for effect in doc.effects:
            if effect.trigger != "passive_static":
                continue
            # 仅对含 modify_hp 声明的效果求 condition（task 026 WP4：紧急滑板同卡
            # holder_hp_le 条件读有效 HP——不加此前置过滤会经 condition_met 递归回
            # 本方法；无关效果的 condition 本就不影响 HP 求和）
            if not any(node.action == "modify_hp" for node in effect.actions):
                continue
            if not condition_met(effect.condition, self, player, mon):
                continue
            for node in effect.actions:
                if node.action == "modify_hp":
                    hp += node.args["amount"]
        return hp

    def _effective_damage_modifier(
        self, mon: InPlayPokemon, player: int, target_rule_box: str | None = None
    ) -> int:
        """攻方招式伤害修正求和（task 025 不服输头带；task 026 WP7 泛化四来源，D-WP7-3）。

        引擎对卡牌内容零硬编码：修正值读 DSL 声明——
        ① 持有者道具 passive_static modify_damage（既有口径；scope 须无）；
        ② 场上竞技场 passive_static modify_damage（scope 须无；化朗镇）；
        ③ 自己全场宝可梦 aura（args.scope="own_field" 必须，否则 DslError 不猜；
        同名来源卡去重只加一次；卡比兽）；
        ④ 回合级标记 PlayerState.turn_damage_mods（on_play modify_damage 写入，
        如空手道王的修炼；回合结束清除）。
        所有来源的 condition 一律对攻击方持有者（mon）求值；节点
        args.target_rule_box 非 None 且不等于 target_rule_box（防守方规则盒）
        则跳过。仅由调用方在「给对手的战斗宝可梦造成的伤害」落点接入（卡面口径）。
        来源离场 / 道具被弃 / 竞技场被顶即失效（求值点实时读声明，天然满足）。
        """
        from battlefrontier.dsl.chooser import condition_met

        mod = 0

        def scan(doc, *, source_kind: str) -> None:
            nonlocal mod
            for effect in doc.effects:
                if effect.trigger != "passive_static":
                    continue
                nodes = [n for n in effect.actions if n.action == "modify_damage"]
                if not nodes:
                    continue
                if not condition_met(effect.condition, self, player, mon):
                    continue
                for node in nodes:
                    trb = node.args.get("target_rule_box")
                    if trb is not None and trb != target_rule_box:
                        continue
                    scope = node.args.get("scope")
                    if source_kind == "aura":
                        if scope != "own_field":
                            raise DslError(
                                f"宝可梦 aura modify_damage 的 args.scope 须为 own_field"
                                f"（收到 {scope!r}；不猜）"
                            )
                    elif scope is not None:
                        raise DslError(
                            f"{source_kind}挂载的 modify_damage 不支持 scope"
                            f"（收到 {scope!r}；aura 请挂宝可梦卡并声明 own_field）"
                        )
                    amount = node.args.get("amount")
                    if not isinstance(amount, int) or isinstance(amount, bool):
                        raise DslError(
                            f"modify_damage 的 amount 须为 int（收到 {amount!r}）"
                        )
                    mod += amount

        # ① 持有者道具
        tool = mon.attached_tool
        if tool is not None:
            doc = effect_doc(self.card_effects, tool.card)
            if doc is not None:
                scan(doc, source_kind="道具")
        # ② 场上竞技场
        stadium = self.state.stadium
        if stadium is not None:
            doc = effect_doc(self.card_effects, stadium.card)
            if doc is not None:
                scan(doc, source_kind="竞技场")
        # ③ 自己全场宝可梦 aura（scope=own_field；同名来源卡去重）
        p = self.state.players[player]
        seen: set[str] = set()
        for m in ([p.active] if p.active else []) + list(p.bench):
            if m.current.card.name in seen:
                continue
            doc = effect_doc(self.card_effects, m.current.card)
            if doc is None:
                continue
            if not any(
                node.action == "modify_damage" and node.args.get("scope") is not None
                for effect in doc.effects
                if effect.trigger == "passive_static"
                for node in effect.actions
            ):
                continue  # 无 aura 声明的卡文档不逐节点校验（同撤退费口径）
            seen.add(m.current.card.name)
            scan(doc, source_kind="aura")
        # ④ 回合级标记（on_play modify_damage 写入；target_rule_box 过滤在求和点）
        for amount, trb in p.turn_damage_mods:
            if trb is None or trb == target_rule_box:
                mod += amount
        return mod

    def _effective_retreat_cost(self, mon: InPlayPokemon, player: int) -> int:
        """撤退费用含常驻修正（task 026 WP4，D-WP4-1/D-WP4-2，🔲 待核；仿 _effective_hp）。

        引擎对卡牌内容零硬编码：修正读 DSL 声明——
        ① 持有者道具的 passive_static modify_retreat_cost（holder 口径，无 scope 键；
        condition 如 holder_hp_le:30 在求值点判定，紧急滑板「剩余HP≤30 则全免」）；
        ② 自己全场宝可梦卡的 passive_static modify_retreat_cost + args.scope=
        own_basic_all（拉帝亚斯ex 天际线：仅作用自己 stage==0 宝可梦；对手场不扫）。
        规约：value=非负 int 减少量加总后 clamp 下限 0，"all" 直接归零（无顺序依赖，
        可交换）；非法 value / 未知 scope = DslError（不猜）。
        来源离场 / 道具被弃 / 进化换栈顶即失效（求值点实时读声明，天然满足）。
        """
        from battlefrontier.dsl.chooser import condition_met
        from battlefrontier.dsl.loader import DslError

        reduction = 0
        zeroed = False

        def apply(node) -> None:
            nonlocal reduction, zeroed
            v = node.args.get("value")
            if v == "all":
                zeroed = True
            elif isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                reduction += v
            else:
                raise DslError(
                    f'modify_retreat_cost 的 value 须为非负 int 或 "all"（收到 {v!r}）'
                )

        def scan(doc, holder: InPlayPokemon, *, expect_scope: str | None) -> None:
            for effect in doc.effects:
                if effect.trigger != "passive_static":
                    continue
                if not condition_met(effect.condition, self, player, holder):
                    continue
                for node in effect.actions:
                    if node.action != "modify_retreat_cost":
                        continue
                    scope = node.args.get("scope")
                    if scope != expect_scope:
                        raise DslError(
                            f"modify_retreat_cost 的 scope={scope!r} 在该挂载点未支持"
                            f"（期望 {expect_scope!r}；不猜）"
                        )
                    apply(node)

        # ① 持有者道具（holder 口径：道具文档不声明 scope）
        tool = mon.attached_tool
        if tool is not None:
            doc = effect_doc(self.card_effects, tool.card)
            if doc is not None:
                scan(doc, mon, expect_scope=None)
        # ② 自己全场特性卡 scope=own_basic_all：仅作用【基础】宝可梦（stage==0）
        if mon.current.card.stage == 0:
            p = self.state.players[player]
            for m in ([p.active] if p.active else []) + list(p.bench):
                doc = effect_doc(self.card_effects, m.current.card)
                if doc is None:
                    continue
                if not any(
                    node.action == "modify_retreat_cost"
                    and node.args.get("scope") is not None
                    for effect in doc.effects
                    if effect.trigger == "passive_static"
                    for node in effect.actions
                ):
                    continue  # 无 scope 声明的卡文档不逐节点校验（holder 口径不由本路径读取）
                scan(doc, m, expect_scope="own_basic_all")
        if zeroed:
            return 0
        return max(0, mon.current.card.retreat_cost - reduction)

    def _effective_attack_cost(
        self, mon: InPlayPokemon, player: int, attack: AttackDef
    ) -> tuple[str, ...]:
        """招式有效费用含常驻修正（task 026 WP5，D-WP5-4，🔲 待核；仿 _effective_retreat_cost）。

        引擎对卡牌内容零硬编码：修正读 DSL 声明——① 持有者自身卡文档
        passive_static modify_attack_cost（月月熊 赫月ex 老练招式「血月费用减对手
        已拿奖赏数×【无】」；attack=招式名必填严格匹配）；② 持有者道具文档同原语
        （task 026 WP7 赫普的讲究头带，D-WP7-4；attack 可缺省=全招式）。
        condition 在求值点判定。args：attack=招式名、
        value=非负 int 或 counters 计数词（如 opponent_taken_prizes，求值走
        interpreter._eval_counter 单一点）。
        规约：只减【无】部分、下限 0（费用不可为负，减免超过无色部分 clamp）；
        非法 value / 未知计数词 = DslError（不猜）。来源离场/进化换栈顶即失效
        （求值点实时读声明，天然满足）。攻击枚举与执行共用本求值点。
        """
        from battlefrontier.dsl.chooser import condition_met

        cost = list(attack.cost)

        def apply_node(node, *, attack_required: bool) -> None:
            declared = node.args.get("attack")
            if attack_required:
                # 自身卡分支保持严格：attack 必须显式匹配招式名（月月熊口径）
                if declared != attack.name:
                    return
            elif declared is not None and declared != attack.name:
                return  # 道具分支：attack 可缺省（=全招式），声明则须匹配
            v = node.args.get("value")
            if isinstance(v, bool):
                raise DslError(
                    f"modify_attack_cost 的 value 须为非负 int 或计数表达式"
                    f"（收到 {v!r}）"
                )
            if isinstance(v, str):
                from battlefrontier.dsl.primitives import _eval_counter

                ctx = ExecutionContext(
                    engine=self, player=player, source=mon.current,
                    effect_id="passive:modify_attack_cost", trigger="passive_static",
                )
                reduce_n = _eval_counter(ctx, v)
            elif isinstance(v, int) and v >= 0:
                reduce_n = v
            else:
                raise DslError(
                    f"modify_attack_cost 的 value 须为非负 int 或计数表达式"
                    f"（收到 {v!r}）"
                )
            # 只减【无】部分，clamp 下限 0（D-WP5-4）
            remove = min(reduce_n, cost.count("无"))
            for _ in range(remove):
                cost.remove("无")

        def scan(doc, *, attack_required: bool) -> None:
            for effect in doc.effects:
                if effect.trigger != "passive_static":
                    continue
                nodes = [n for n in effect.actions if n.action == "modify_attack_cost"]
                if not nodes:
                    continue
                if not condition_met(effect.condition, self, player, mon):
                    continue
                for node in nodes:
                    apply_node(node, attack_required=attack_required)

        doc = effect_doc(self.card_effects, mon.current.card)
        if doc is not None:
            scan(doc, attack_required=True)
        # 道具分支（task 026 WP7 赫普的讲究头带，D-WP7-4）：attached_tool 文档的
        # passive_static modify_attack_cost，condition 对持有者求值；道具离场即失效
        tool = mon.attached_tool
        if tool is not None:
            tdoc = effect_doc(self.card_effects, tool.card)
            if tdoc is not None:
                scan(tdoc, attack_required=False)
        return tuple(cost)

    def _effective_weakness(self, attacker: int, defender: InPlayPokemon) -> str | None:
        """防守方有效弱点（task 017 妖精领域）：攻方场上有 passive_static 的
        modify_weakness 声明且防守栈顶属性命中 target_type → 弱点视为 becomes
        （含龙等卡面无弱点属性的弱点赋予）。引擎对卡牌内容零硬编码：
        目标属性/改写结果全部读 DSL 声明。
        """
        declared = None
        atk_p = self.state.players[attacker]
        mons = ([atk_p.active] if atk_p.active else []) + list(atk_p.bench)
        for m in mons:
            doc = effect_doc(self.card_effects, m.current.card)
            if doc is None:
                continue
            for effect in doc.effects:
                if effect.trigger != "passive_static":
                    continue
                for node in effect.actions:
                    if node.action == "modify_weakness":
                        declared = node.args
        if declared is None:
            return defender.current.card.weakness
        if defender.current.card.energy_type == declared.get("target_type"):
            return declared.get("becomes")
        return defender.current.card.weakness

    def _bench_size(self, player: int) -> int:
        """有效备战区容量（task 026 WP6 零之大空洞，D-WP6-2，🔲 待核；仿 _effective_hp）。

        引擎对卡牌内容零硬编码：覆写读场上竞技场 DSL 文档 passive_static 的
        bench_size 声明（condition 如 own_tera_in_play 逐玩家在求值点判定——
        双方各看自己场上是否有太晶）；无竞技场 / 条件不成立 → 5；多条取 max。
        value 须为 5..8 的 int，否则 DslError（求值点不猜）。竞技场离场即无声明可读，
        失效由求值点语义天然保证（缩减结算走 _check_bench_shrink）。
        """
        stadium = self.state.stadium
        if stadium is None:
            return 5
        doc = effect_doc(self.card_effects, stadium.card)
        if doc is None:
            return 5
        from battlefrontier.dsl.chooser import condition_met

        size = 5
        for effect in doc.effects:
            if effect.trigger != "passive_static":
                continue
            nodes = [n for n in effect.actions if n.action == "bench_size"]
            if not nodes:
                continue
            if not condition_met(effect.condition, self, player):
                continue
            for node in nodes:
                v = node.args.get("value")
                if not isinstance(v, int) or isinstance(v, bool) or v < 5 or v > 8:
                    raise DslError(f"bench_size 的 value 须为 5..8 的 int（收到 {v!r}）")
                size = max(size, v)
        return size

    def _check_bench_shrink(self, *, first: int | None, resume: tuple[int, str]) -> bool:
        """备战区失效缩减检查（task 026 WP6，D-WP6-2）：任一玩家备战数超有效容量
        → 进 bench_shrink 阶段，超容方按队列逐只自选弃置；双方同缩由 first
        （旧竞技场持有者）先执行。缩减完成后按 resume 恢复（("main") 回出牌方
        主阶段 / ("begin_turn") 开始该方回合）。返回是否进入了缩减阶段。
        """
        overflow = [
            i for i in (0, 1)
            if len(self.state.players[i].bench) > self._bench_size(i)
        ]
        if not overflow:
            return False
        if first is not None and first in overflow:
            overflow = [first] + [i for i in overflow if i != first]
        self.state = self.state.model_copy(update={
            "phase": "bench_shrink", "current_player": overflow[0],
            "bench_shrink_queue": tuple(overflow), "bench_shrink_resume": resume,
        })
        return True

    def _do_shrink_bench(self, player: int, action: Action) -> None:
        """失效缩减执行（D-WP6-2）：所选备战宝可梦整叠（进化链+能量+道具）进弃牌区
        ——非昏厥（无奖赏、不进换上队列、不触发昏厥事件）；缩减至不超容后推进队列，
        队列空则按 bench_shrink_resume 恢复。"""
        p = self.state.players[player]
        iid = action.choices[0]
        idx = next(i for i, m in enumerate(p.bench) if m.current.iid == iid)
        mon = p.bench[idx]
        pile = mon.stack + mon.attached_energy + (
            (mon.attached_tool,) if mon.attached_tool is not None else ()
        )
        self._set_player(player, p.model_copy(update={
            "bench": p.bench[:idx] + p.bench[idx + 1:],
            "discard": p.discard + pile,
        }))
        self._emit("bench_shrink", player, iid=iid, name=mon.current.card.name)
        if len(self.state.players[player].bench) > self._bench_size(player):
            return  # 仍超容：同一玩家继续逐只弃置
        queue = self.state.bench_shrink_queue[1:]
        self.state = self.state.model_copy(update={"bench_shrink_queue": queue})
        if queue:
            self.state = self.state.model_copy(update={
                "phase": "bench_shrink", "current_player": queue[0],
            })
            return
        resume = self.state.bench_shrink_resume
        assert resume is not None  # 进入 bench_shrink 阶段时必已设置
        self.state = self.state.model_copy(update={"bench_shrink_resume": None})
        if resume[1] == "begin_turn":
            # task 026 WP7：检查进行中直接开检查后回合，否则插入宝可梦检查
            self._proceed_after_turn_end(resume[0])
        else:
            self.state = self.state.model_copy(update={
                "phase": "main", "current_player": resume[0],
            })

    def _protected_from_attack_effects(self, mon: InPlayPokemon, owner: int) -> bool:
        """招式附加效果免疫判定（task 026 WP6 火恐龙 闪焰之幕，D-WP6-7，🔲 待核）。

        引擎对卡牌内容零硬编码：读持有者卡文档 passive_static 的 protection 声明
        （scope=opponent_attack_effects；未知 scope = DslError 求值点不猜），
        condition 在求值点判定。由效果落点（place_damage_counters / apply_status）
        在 ctx.trigger == "on_attack" 时调用——训练家卡效果不经本判定（不受保护），
        伤害本体也不经本判定（不免疫）。
        scope=opponent_attack_damage_to_bench（task 026 WP7 谢米，D-WP7-5）是
        伤害免疫，不归本守卫管——跳过（求值点 = _protected_bench_from_attack_damage）。
        一期守卫落点清单：apply_status / place_damage_counters / lock_retreat /
        devolve——新增攻击效果落点须显式评估是否接入本守卫（不接 = 不受保护，不猜）。
        """
        doc = effect_doc(self.card_effects, mon.current.card)
        if doc is None:
            return False
        from battlefrontier.dsl.chooser import condition_met

        declared = False
        for effect in doc.effects:
            if effect.trigger != "passive_static":
                continue
            nodes = [n for n in effect.actions if n.action == "protection"]
            if not nodes:
                continue
            for node in nodes:
                scope = node.args.get("scope")
                if scope == "opponent_attack_damage_to_bench":
                    continue  # 伤害免疫 scope：非本守卫职责（D-WP7-5）
                if scope != "opponent_attack_effects":
                    raise DslError(
                        f"protection 的 scope 暂仅支持 opponent_attack_effects/"
                        f"opponent_attack_damage_to_bench（收到 {scope!r}；不猜）"
                    )
            if not condition_met(effect.condition, self, owner, mon):
                continue
            declared = True
        return declared

    def _protected_bench_from_attack_damage(self, mon: InPlayPokemon, owner: int) -> bool:
        """备战伤害免疫判定（task 026 WP7 谢米，D-WP7-5，🔲 待核）：「对手的招式
        对自己备战区宝可梦的伤害」免疫。

        引擎对卡牌内容零硬编码：扫 owner 全场宝可梦卡文档 passive_static 的
        protection scope=opponent_attack_damage_to_bench 声明；args.target_filters
        （如 no_rule_box）对受保护目标（mon）求值收敛保护面；condition 对来源
        持有者求值。来源离场即失效（求值点实时扫场，天然满足）。
        接入点 = damage 原语的备战落点且 ctx.trigger=="on_attack"（招式伤害才免疫；
        训练家卡伤害与伤害指示物不受此保护——指示物不是伤害，rules-manual §6）。
        """
        from battlefrontier.dsl.chooser import condition_met, matches_in_play

        p = self.state.players[owner]
        for m in ([p.active] if p.active else []) + list(p.bench):
            doc = effect_doc(self.card_effects, m.current.card)
            if doc is None:
                continue
            for effect in doc.effects:
                if effect.trigger != "passive_static":
                    continue
                nodes = [
                    n for n in effect.actions
                    if n.action == "protection"
                    and n.args.get("scope") == "opponent_attack_damage_to_bench"
                ]
                if not nodes:
                    continue
                if not condition_met(effect.condition, self, owner, m):
                    continue
                for node in nodes:
                    target_filters = tuple(node.args.get("target_filters", ()))
                    if matches_in_play(mon, target_filters):
                        return True
        return False


    def check_knockouts(self) -> None:
        """任意伤害来源后的统一昏厥检查入口（rules-manual §8；§7.2 检查后结算同源）。

        多昏厥扫描（task 026 WP2）：按 玩家0→1、备战区→战斗场 顺序结算全部昏厥
        （D-WP2-2，🔲 待核）——整叠（进化链+能量+道具）进弃牌堆、对手按规则盒拿取奖赏；
        对手拿完奖赏立即获胜时清空换上队列并终止结算。
        战斗场昏厥：无备战 → 场上无宝可梦判负（§8 胜利条件②）；双方本次扫描后都无
        战斗场且无备战 → 平局（§8 同时胜利口径，🔲 待核）；有备战 → 入 promote_queue
        （不重复入队）。扫描结束后队列非空且不在效果执行中 → 立即进 promote 阶段；
        效果进行中则只入队不翻阶段（由 _run_or_suspend 完成路径翻，D-WP2-1）。
        """
        wiped: list[int] = []  # 本次扫描后场上无宝可梦（战斗场昏厥且备战空）的玩家
        # 白蕾雅奖赏加成（task 026 WP5，D-WP5-2）：取走并清空招式伤害瞬时记录——
        # 本次扫描内的战斗场昏厥若由太晶宝可梦招式伤害导致，take_prize 触点加成
        attack_ctx = self._attack_damage_active
        self._attack_damage_active = None
        for player in (0, 1):
            p = self.state.players[player]
            # 备战区昏厥（attack_ctx 同样传入：古玉鱼精确标记 F1 归正——备战被招式
            # 伤害昏厥也置位；白蕾雅加成 / own_ko_by_attack 触发器在 _knockout_one
            # 内由 active_ko 门拦截，不受备战落点影响）
            kept = []
            for b in p.bench:
                if b.damage >= self._effective_hp(b, player):
                    if self._knockout_one(player, b, attack_ctx=attack_ctx):
                        self.state = self.state.model_copy(update={"promote_queue": ()})
                        return  # 对手拿完奖赏，立即获胜
                else:
                    kept.append(b)
            if len(kept) != len(p.bench):
                p = self.state.players[player]
                self._set_player(player, p.model_copy(update={"bench": tuple(kept)}))
            # 战斗场昏厥
            p = self.state.players[player]
            if p.active and p.active.damage >= self._effective_hp(p.active, player):
                active = p.active
                self._set_player(player, p.model_copy(update={"active": None}))
                if self._knockout_one(player, active, active_ko=True,
                                      attack_ctx=attack_ctx):
                    self.state = self.state.model_copy(update={"promote_queue": ()})
                    return
                d = self.state.players[player]
                if not d.bench:
                    wiped.append(player)  # 战斗场昏厥且备战区无可换上
                elif player not in self.state.promote_queue:
                    self.state = self.state.model_copy(update={
                        "promote_queue": self.state.promote_queue + (player,),
                    })
        if len(wiped) == 2:
            # 【rules-manual §8 同时胜利口径】双方同时无场上宝可梦 → 平局（🔲 待核）
            self._game_over(winner=None, reason="no_pokemon", is_draw=True)
            return
        if wiped:
            # 【rules-manual §8 胜利条件②】战斗场昏厥且备战区无可换上
            self._game_over(winner=1 - wiped[0], reason="no_pokemon")
            return
        # 招式昏厥触发器排水（task 026 WP6，own_ko_by_attack）：先于 promote 翻阶段——
        # 被昏厥方场上的触发效果（如仙人掌反伤）在其宝可梦换上之前结算；被触发效果
        # 以 completion="attack" 发动且发动前置 turn_after_promote=被攻击方，其完成
        # 路径统一翻 promote，换上后回合权归被攻击方（D-WP6-6）。
        if (
            self.state.pending_ko_triggers
            and not self._in_effect
            and self._drain_event_triggers()
        ):
            return
        if self.state.promote_queue and not self._in_effect:
            self.state = self.state.model_copy(update={
                "phase": "promote", "current_player": self.state.promote_queue[0],
            })

    def _knockout_one(
        self, player: int, knocked_mon: InPlayPokemon, *, active_ko: bool = False,
        attack_ctx: tuple[int, bool, int | None] | None = None,
    ) -> bool:
        """结算一只昏厥：整叠（进化链 + 能量 + 道具）进弃牌堆，对手按规则盒拿奖赏
        （rules-manual §1.4/§8，不看正面；任意顺序拿取暂以固定取顶实现，统计等价）。

        白蕾雅奖赏加成（task 026 WP5，D-WP5-2 🔲 待核）：take_prize 触点——
        拿取方 extra_prize_tera_ko 回合标记在 且 本昏厥为战斗场（active_ko）且
        由拿取方太晶宝可梦招式伤害导致（attack_ctx）→ 多拿 1 张；奖赏不足按剩余
        拿取（拿完即胜，由下方 prizes 空判定承接）。
        返回 True 表示对手拿完奖赏立即获胜（胜利条件①，调用方停止后续结算）。
        """
        p = self.state.players[player]
        pile = knocked_mon.stack + knocked_mon.attached_energy + (
            (knocked_mon.attached_tool,) if knocked_mon.attached_tool else ()
        )
        self._set_player(player, p.model_copy(update={
            "discard": p.discard + pile,
        }))
        self._emit("knockout", player, name=knocked_mon.current.card.name)
        # 招式昏厥触发器入队（task 026 WP6，own_ko_by_attack）：战斗场被对手招式伤害
        # 昏厥 → 记录（被昏厥方, 被昏厥栈顶 iid, 攻击方栈顶 iid）；分发在
        # check_knockouts 扫描结束后 / _run_or_suspend 完成路径统一进行（离场即失效）
        if (
            active_ko
            and attack_ctx is not None
            and attack_ctx[0] == 1 - player
            and attack_ctx[2] is not None
        ):
            self.state = self.state.model_copy(update={
                "pending_ko_triggers": self.state.pending_ko_triggers
                + ((player, knocked_mon.current.iid, attack_ctx[2]),),
            })
        # 跨回合标记（task 017 化危为吉）：「上一个对手的回合」内我方宝可梦昏厥——
        # 昏厥归属方不是当前回合方时置位，其回合结束时清除（_on_turn_end）
        if player != self.state.current_player:
            owner = self.state.players[player]
            self._set_player(player, owner.model_copy(update={
                "own_ko_during_opponent_turn": True,
            }))
        # 精确口径标记（task 026 WP7 古玉鱼 嫉妒业火，D-WP7-7 + F1 复核归正）：
        # 仅「因对手招式伤害」昏厥才置位（attack_ctx 非空 = 本次扫描有对手招式伤害
        # 落点记录；效果/指示物致昏厥不置位）——战斗场与备战区昏厥均置位
        # （F1：卡面「自己的宝可梦【昏厥】」无战斗场限定，备战狙击致昏厥同属）；
        # 清除口径同宽标记（_on_turn_end / 检查阶段入口双清）
        if (
            attack_ctx is not None
            and attack_ctx[0] == 1 - player
            and player != self.state.current_player
        ):
            owner = self.state.players[player]
            self._set_player(player, owner.model_copy(update={
                "own_ko_by_attack_during_opponent_turn": True,
            }))
        taker_idx = 1 - player
        taker = self.state.players[taker_idx]
        n = PRIZE_BY_RULE_BOX.get(knocked_mon.current.card.rule_box or "", 1)
        if (
            active_ko
            and attack_ctx is not None
            and attack_ctx[0] == taker_idx
            and attack_ctx[1]
            and taker.extra_prize_tera_ko
        ):
            n += 1  # 白蕾雅：太晶宝可梦招式伤害昏厥对手战斗场 → 多拿 1 张
            self._emit("prize_bonus", taker_idx, source="extra_prize_tera_ko")
        taken = taker.prizes[:n]
        self._set_player(taker_idx, taker.model_copy(update={
            "hand": taker.hand + taken, "prizes": taker.prizes[len(taken):],
        }))
        for c in taken:  # 每张一条事件（回放保真）
            self._emit("take_prize", taker_idx, iid=c.iid, name=c.card.name,
                       left=len(self.state.players[taker_idx].prizes))
        if not self.state.players[taker_idx].prizes:
            self._game_over(winner=taker_idx, reason="prizes")
            return True
        return False

    def _do_promote(self, player: int, action: Action) -> None:
        p = self.state.players[player]
        new_active = p.bench[action.bench_index]  # type: ignore[index]
        bench = p.bench[: action.bench_index] + p.bench[action.bench_index + 1 :]  # type: ignore[index]
        self._set_player(player, p.model_copy(update={"active": new_active, "bench": bench}))
        self._emit("promote", player, name=new_active.current.card.name)
        # 多昏厥换上队列（task 026 WP2，D-WP2-2）：逐条弹出，未空则继续下一位换上
        queue = self.state.promote_queue
        if queue:
            queue = queue[1:]
            self.state = self.state.model_copy(update={"promote_queue": queue})
        if queue:
            self.state = self.state.model_copy(update={
                "phase": "promote", "current_player": queue[0],
            })
            return
        # 效果内昏厥/bounce 的换上：队列清空后回效果方主阶段（D-WP2-1；
        # D-WP2-4 归并 task 025 promote_to_main）——不推进回合、不抽牌
        resume = self.state.resume_after_promotes
        if resume is not None:
            self.state = self.state.model_copy(update={
                "resume_after_promotes": None,
                "phase": resume[1], "current_player": resume[0],
            })
            # 失效缩减复查（task 026 WP6，D-WP6-2）：bounce 战斗场唯一太晶后换上
            # 完成时太晶已离场——恢复主阶段前复查超容（resume 原样传递）
            self._check_bench_shrink(first=None, resume=resume)
            return
        # 换上后回合权：默认换上方回合（普通昏厥）；turn_after_promote 置位时给指定方
        # （混乱反面自我昏厥：攻击已消耗，回合权给对手——D1 决议 task 013）
        nxt = self.state.turn_after_promote
        if nxt is not None:
            self.state = self.state.model_copy(update={"turn_after_promote": None})
        target = nxt if nxt is not None else player
        # 备战区缩编复查（task 026 WP6，零之大空洞）：昏厥/换上后竞技场可能已被顶掉，
        # 超容方按 shrink_bench 阶段逐个弃置，全部完成后才开回合（D-WP6-2）
        if self._check_bench_shrink(first=None, resume=(target, "begin_turn")):
            return
        # 回合权交接（task 026 WP7）：检查进行中直接开检查后回合，否则插入宝可梦检查
        self._proceed_after_turn_end(target)

    def _do_end_turn(self, player: int, action: Action) -> None:
        self._emit("end_turn", player)
        self._on_turn_end(player)
        # 宝可梦检查（task 026 WP7，D-WP7-1）：回合结束统一插入，检查完毕后开下一回合
        self._start_pokemon_check(player)

    def _do_play_trainer(self, player: int, action: Action) -> None:
        """【规则书·训练家卡】物品/支援者从手牌使用，效果经 DSL 解释器结算后放于弃牌区。

        chooser（task 009）：效果执行遇选择节点即挂起（phase="choice" +
        pending_choice），Agent 选择后经 _do_choose 恢复；支援者标记在打出时置位，
        本体在效果完成后进弃牌区。
        """
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        self._set_player(player, p.model_copy(update={
            "supporter_played_this_turn": p.supporter_played_this_turn
            or card.card.trainer_subtype == "支援者",
        }))
        self._emit("play_trainer", player, iid=card.iid, name=card.card.name,
                   subtype=card.card.trainer_subtype)
        doc = effect_doc(self.card_effects, card.card)
        assert doc is not None  # legal_actions 已保证训练家卡有 DSL 文档
        effect_index = next(i for i, e in enumerate(doc.effects) if e.trigger == "on_play")
        self._run_or_suspend(player, card, effect_index, start=0)

    def _do_use_ability(self, player: int, action: Action) -> None:
        """【rules-manual 特性】自己回合按 DSL limit 发动场上宝可梦的特性。

        限次标记在发动时置位（once_per_turn 按栈顶 iid / once_per_turn_shared 按卡名）；
        效果经 DSL 解释器结算，可挂起（chooser），完成后不进弃牌区（completion="ability"）。
        """
        p = self.state.players[player]
        iid = action.iid  # type: ignore[attr-defined]
        in_play: list[InPlayPokemon] = ([p.active] if p.active else []) + list(p.bench)
        mon = next(m for m in in_play if m.current.iid == iid)
        doc = effect_doc(self.card_effects, mon.current.card)
        assert doc is not None  # legal_actions 已保证特性卡有 DSL 文档
        effect_index = next(i for i, e in enumerate(doc.effects) if e.trigger == "ability_manual")
        effect = doc.effects[effect_index]
        update: dict[str, object] = {}
        if effect.limit == "once_per_turn":
            update["abilities_used_this_turn"] = p.abilities_used_this_turn | {iid}
        elif effect.limit == "once_per_turn_shared":
            update["shared_abilities_used_this_turn"] = (
                p.shared_abilities_used_this_turn | {mon.current.card.name}
            )
        if update:
            self._set_player(player, p.model_copy(update=update))
        self._emit("use_ability", player, iid=iid, name=mon.current.card.name, limit=effect.limit)
        self._run_or_suspend(player, mon.current, effect_index, start=0, completion="ability")

    def _run_or_suspend(
        self, player: int, card: CardInstance, effect_index: int,
        start: int, choice: tuple[int, ...] | None = None,
        carry: tuple[int, ...] = (), completion: str = "trainer",
        *, inner: tuple[str, str, str] | None = None, outer_cursor: int = -1,
        outer_choice: tuple[int, ...] = (), inner_done: bool = False,
        flip: bool | None = None,
        cost_discarded: tuple[int, ...] = (),
        discarded_count: int = 0,
        attacker_iid: int | None = None,
    ) -> None:
        """跑效果或挂起：NeedChoice → phase="choice" + pending_choice；完成 → 按 completion 收尾。

        嵌套帧（task 020 copy_attack）：inner 非空时按 inner 定位内层效果续跑；
        内层完成 → 带 inner_done 恢复外层 copy 节点（不重复执行内层）；
        内层再传播 inner → 嵌套层级 >1，显式 DslError（不猜）。
        flip（task 025）：挂起冻结的掷币结果，恢复时穿透进 ctx.last_flip；
        嵌套帧内层完成恢复外层时不穿透（外层 copy 节点后接掷币门控节点的组合
        会在解释器显式 DslError——不猜，需要时再扩展多级冻结）。
        cost_discarded（task 026 WP4）：挂起冻结的 cost 段弃置 iid，恢复时穿透进
        ctx.cost_discarded_iids（同 flip 口径，嵌套帧不穿透）。
        discarded_count（task 026 WP5）：挂起冻结的前序弃置张数，恢复时穿透进
        ctx.discarded_this_effect（同 flip 口径，嵌套帧不穿透）。
        宝可梦检查（task 026 WP7，D-WP7-1）：完成路径在排水后、promote/main 恢复
        逻辑前检查拦截——pokemon_check_next 非 None 且 phase 为 pokemon_check/
        choice 时回 _advance_pokemon_check 继续检查推进（检查触发的效果完成不
        直接开回合/回主阶段）。
        """
        from battlefrontier.dsl.chooser import build_pending

        if inner is not None and not inner_done:
            # inner = (card_id, 卡名, 招式名)：CardLibrary 按 card_id 取，朴素 dict 按名取
            doc = effect_doc_by_ref(self.card_effects, inner[0], inner[1])
            if doc is None:
                raise DslError(f"copy_attack 内层文档缺失：{inner[1]}（{inner[0]}）未挂载（不猜）")
            effect = next(e for e in doc.effects
                          if e.trigger == "on_attack" and e.attack == inner[2])
            effect_id = f"{card.card.name}[{card.iid}]:copy>{inner[1]}.{inner[2]}"
        else:
            doc = effect_doc(self.card_effects, card.card)
            assert doc is not None  # 调用方（trainer/ability/attack）已保证文档存在
            effect = doc.effects[effect_index]
            effect_id = f"{card.card.name}[{card.iid}]:{effect.trigger}"
        ctx = ExecutionContext(
            engine=self, player=player, source=card,
            effect_id=effect_id, trigger=effect.trigger,
        )
        ctx.inner_done = inner_done
        ctx.attacker_iid = attacker_iid
        self._in_effect = True
        try:
            need = run_effect(ctx, effect, start=start, choice=choice, carry=carry,
                              flip=flip, cost_discarded=cost_discarded,
                              discarded_count=discarded_count)
        finally:
            self._in_effect = False
        if need is not None:
            if need.inner is not None:
                if inner is not None:
                    raise DslError(
                        f"copy_attack 嵌套层级 >1 未支持（不猜）：内层 {inner} "
                        f"又传播 {need.inner}（需要时扩展 chooser 多级帧）"
                    )
                # 外层 copy 节点首次传播：建立嵌套帧（cursor/outer_cursor 分层记录）
                pending = build_pending(
                    self, player, card, effect_index, need.inner_cursor, need,
                    completion=completion, inner=need.inner,
                    outer_cursor=need.cursor, outer_choice=choice or (),
                )
            else:
                pending = build_pending(
                    self, player, card, effect_index, need.cursor, need,
                    completion=completion, inner=inner,
                    outer_cursor=outer_cursor, outer_choice=outer_choice,
                )
            self.state = self.state.model_copy(update={
                "phase": "choice", "current_player": player, "pending_choice": pending,
            })
            return
        if inner is not None and not inner_done:
            # 内层完成 → 带 inner_done 恢复外层 copy 节点（外层后续节点照常执行）
            self._run_or_suspend(player, card, effect_index, start=outer_cursor,
                                 choice=outer_choice, completion=completion,
                                 inner_done=True)
            return
        # 效果完成：训练家卡本体进弃牌区（规则书·训练家卡）；特性不弃置；
        # 攻击结算完毕推进对手回合（rules-manual §6：攻击后回合结束）。
        if completion == "trainer":
            p = self.state.players[player]
            self._set_player(player, p.model_copy(update={"discard": p.discard + (card,)}))
        # 事件触发队列排水（task 026 WP3/WP6，用户裁决 2026-09-07）：DSL 进化路径
        # （神奇糖果 skip_stage zone="hand"）入队的 own_evolve_from_hand 与招式昏厥
        # 入队的 own_ko_by_attack 在效果全部结算完毕后统一分发——先于 promote 翻阶段；
        # 来源已不在场上 / condition 不满足则跳过排下一条（own_evolve 离场即失效；
        # own_ko_by_attack 从弃牌堆找回来源）；实际发动则交棒（被触发效果的自身完成
        # 路径递归排剩余队列 / 翻 promote / 回主阶段，本层不再执行后续收尾）
        if self.state.phase != "game_over" and self._drain_event_triggers():
            return
        # 宝可梦检查内拦截（task 026 WP7，D-WP7-1）：检查阶段触发的效果
        # （雪妖女 冻结帷幕等）完成/挂起恢复后回到检查推进（排水→统一昏厥结算
        # →下一回合），不走下方 promote/main 恢复逻辑
        if (
            self.state.pokemon_check_next is not None
            and self.state.phase in ("pokemon_check", "choice")
        ):
            self.state = self.state.model_copy(update={
                "pending_choice": None, "phase": "pokemon_check",
            })
            self._advance_pokemon_check()
            return
        # 效果内昏厥的推迟换上（task 026 WP2，D-WP2-1/2）：队列非空 → 统一进 promote
        # 阶段；ability/trainer/stadium 完成后回效果方主阶段（resume_after_promotes），
        # attack 不设 resume——置 turn_after_promote=防守方（攻击已消耗回合；
        # 普通昏厥换上=防守方与默认口径一致；自我昏厥换上后回合权归对手——
        # 2026-09-19 主会话复核批准口径，无独立 D 编号）
        if self.state.phase != "game_over" and self.state.promote_queue:
            update: dict[str, object] = {
                "phase": "promote",
                "current_player": self.state.promote_queue[0],
                "pending_choice": None,
            }
            if completion in ("ability", "trainer", "stadium"):
                update["resume_after_promotes"] = (player, "main")
            elif completion == "attack" and self.state.turn_after_promote is None:
                # 攻击已消耗回合：换上后回合权归防守方（普通昏厥换上=防守方与默认
                # 口径一致；自我昏厥换上后归对手——2026-09-19 主会话复核批准口径）；
                # own_ko_by_attack 触发路径发动时已预置（D-WP6-6 归被攻击方）——不覆盖
                update["turn_after_promote"] = 1 - player
            self.state = self.state.model_copy(update=update)
            return
        # 效果内若已终局（game_over）或翻上换阶段（bounce 直接翻），不覆盖其阶段。
        if self.state.phase in ("main", "choice"):
            if completion == "attack":
                self.state = self.state.model_copy(update={"pending_choice": None})
                self._on_turn_end(player)
                # 失效缩减复查（task 026 WP6 零之大空洞，D-WP6-2 触点②③：
                # transform/bounce/昏厥等离场在效果结算完毕后统一复查——沿用
                # bench_shrink 挂起-恢复机制；check_knockouts 触点①经本路径覆盖，
                # 效果中途不翻阶段）——超容方缩减完成后进宝可梦检查再开对手回合
                if self._check_bench_shrink(first=None, resume=(1 - player, "begin_turn")):
                    return
                # 宝可梦检查（task 026 WP7，D-WP7-1）：攻击后回合结束统一插入
                self._start_pokemon_check(player)
            else:
                self.state = self.state.model_copy(update={"pending_choice": None})
                # 同上（D-WP6-2）：trainer/ability/stadium 完成后回效果方主阶段前复查
                if self._check_bench_shrink(first=None, resume=(player, "main")):
                    return
                self.state = self.state.model_copy(update={"phase": "main"})
        else:
            self.state = self.state.model_copy(update={"pending_choice": None})

    def _resolve_choose_names(self, pc: PendingChoice, choices: tuple[int, ...]) -> list[str]:
        """choose 事件的选中项名称解析（task 022 决策聚合数据源）。

        卡 iid 扫描双方全区域；opponent_active_attack 池的元素是招式索引，
        解析为对手战斗场招式名（rules：复制招式选择公开信息）。
        """
        if pc.pool == "opponent_active_attack":
            opp_active = self.state.players[1 - pc.player].active
            attacks = opp_active.current.card.attacks if opp_active else ()
            return [attacks[i].name for i in choices if i < len(attacks)]
        names: dict[int, str] = {}
        for p in self.state.players:
            for c in (*p.deck, *p.hand, *p.discard, *p.prizes):
                names[c.iid] = c.card.name
            for mon in ([p.active] if p.active else []) + list(p.bench):
                for c in (*mon.stack, *mon.attached_energy):
                    names[c.iid] = c.card.name
                if mon.attached_tool is not None:
                    names[mon.attached_tool.iid] = mon.attached_tool.card.name
        return [names.get(i, f"#{i}") for i in choices]

    def _do_choose(self, player: int, action: Action) -> None:
        """chooser 恢复：带选择结果从挂起游标续跑效果（PRD §5.2；嵌套帧 task 020）。

        恢复前落 choose 决策事件（task 022，PRD §5.4/§9 决策聚合数据源）：
        effect_id / 来源卡 / 池 / 选中 iids + 名称；嵌套帧 effect_id 含 copy> 标注。
        """
        pc = self.state.pending_choice
        assert pc is not None  # legal_actions 已保证 phase="choice" 才有 choose
        if pc.inner is not None:
            effect_id = f"{pc.source.card.name}[{pc.source.iid}]:copy>{pc.inner[1]}.{pc.inner[2]}"
        else:
            doc = effect_doc(self.card_effects, pc.source.card)
            assert doc is not None  # 挂起时文档存在（同一对局内库不变）
            trigger = doc.effects[pc.effect_index].trigger
            effect_id = f"{pc.source.card.name}[{pc.source.iid}]:{trigger}"
        self._emit("choose", player, effect_id=effect_id, card=pc.source.card.name,
                   pool=pc.pool, chosen=list(action.choices),
                   chosen_names=self._resolve_choose_names(pc, action.choices))
        self.state = self.state.model_copy(update={"pending_choice": None})
        self._run_or_suspend(player, pc.source, pc.effect_index,
                             start=pc.cursor, choice=action.choices,
                             carry=pc.payload, completion=pc.completion,
                             inner=pc.inner, outer_cursor=pc.outer_cursor,
                             outer_choice=pc.outer_choice, flip=pc.flip_result,
                             cost_discarded=pc.cost_discarded,
                             discarded_count=pc.discarded_count,
                             attacker_iid=pc.attacker_iid)

    def _begin_turn(self, player: int, first_turn: bool = False) -> None:
        """回合开始：重置回合标记 → 抽牌（牌库空判负，规则书·胜负判定）。

        【rules-manual §1.1】登场/进化锁定在各自第一回合不清除：setup 放置的
        宝可梦视为刚登场，双方第一回合（turn==1）均不可进化，第二回合起解锁。
        """
        turn = 1 if first_turn else self.state.turn + (1 if player == self.state.first_player else 0)
        p = self.state.players[player]
        p = p.model_copy(update={
            "energy_attached_this_turn": False,
            "supporter_played_this_turn": False,
            "retreated_this_turn": False,
            "stadium_played_this_turn": False,
            "stadium_used_this_turn": False,
            "abilities_used_this_turn": frozenset(),
            "shared_abilities_used_this_turn": frozenset(),
            **({} if turn == 1 else {
                "entered_play_this_turn": frozenset(),
                "evolved_this_turn": frozenset(),
            }),
        })
        self._set_player(player, p)
        self.state = self.state.model_copy(update={
            "turn": turn, "current_player": player, "phase": "draw",
            # 检查进行中标记清零（task 026 WP7：正常路径进本函数前已清；
            # 此处兜底防泄漏——回合开始即无未完结检查）
            "pokemon_check_next": None,
        })
        # 攻击冷却解禁（task 026 WP4 裁决 2）：攻击于 turn N → 下个自己回合（N+1）
        # 仍锁 → N+2 回合开始解禁（turn 仅在先攻方回合开始递增）
        p = self.state.players[player]
        if any(
            m.attack_lock_turn is not None and turn - m.attack_lock_turn >= 2
            for m in ([p.active] if p.active else []) + list(p.bench)
        ):
            def _unlock(mon: InPlayPokemon) -> InPlayPokemon:
                if mon.attack_lock_turn is not None and turn - mon.attack_lock_turn >= 2:
                    return mon.model_copy(update={
                        "attack_locks": (), "attack_lock_turn": None,
                    })
                return mon

            self._set_player(player, p.model_copy(update={
                "active": _unlock(p.active) if p.active else None,
                "bench": tuple(_unlock(m) for m in p.bench),
            }))
        if not p.deck:
            self._emit("deck_out", player)
            self._game_over(winner=1 - player, reason="deck_out")
            return
        p = self.state.players[player]
        self._set_player(player, p.model_copy(update={
            "hand": p.hand + p.deck[:1], "deck": p.deck[1:],
        }))
        self._emit("draw", player, iid=p.deck[0].iid, name=p.deck[0].card.name)
        self.state = self.state.model_copy(update={"phase": "main"})

    def _game_over(self, winner: int | None, reason: str, is_draw: bool = False) -> None:
        self.state = self.state.model_copy(update={
            "phase": "game_over", "winner": winner, "is_draw": is_draw,
            # 检查进行中标记清零（task 026 WP7：终局即无未完结检查）
            "pokemon_check_next": None,
        })
        self._emit("game_over", winner, reason=reason, is_draw=is_draw)

    def force_draw(self, reason: str) -> None:
        """死循环保护等强制判平入口（上限值由调用方配置）。"""
        self._emit(reason, None)
        self._game_over(winner=None, reason=reason, is_draw=True)
