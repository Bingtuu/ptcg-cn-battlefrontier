"""规则引擎核心：阶段机 + 合法行动枚举 + 白板推进（PRD §6.2 / §6.4）。

规则事实源：docs/rules-manual.md（简中官网规则页整理）+ docs/rules-reference.md
（落点速查 + 决议日志），逐条在代码注释标注出处。
白板范围：不执行任何卡面效果，宝可梦只有 HP / 固定伤害招式 / 撤退费用。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from battlefrontier.dsl import ExecutionContext, run_effect
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action, IllegalActionError
from battlefrontier.engine.events import GameEvent
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    GameState,
    InPlayPokemon,
    PlayerState,
    SpecialCondition,
    Supertype,
)

if TYPE_CHECKING:
    from battlefrontier.dsl.schema import CardEffectDoc


class DeckConfigError(Exception):
    """卡组不满足开局条件（无基础宝可梦 / 张数不足），明确报错而非死循环。"""


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
    weakness: str | None = None,
) -> int:
    """伤害计算顺序（rules-manual §6）：基准（≤0 终止）→ 弱点 ×2 → 抗性 -30 → 下限 0。

    白板期无攻/防修饰，修饰插入点见注释；备战区伤害不计算弱点抗性（贯穿规则，
    铺伤原语落地时走 to_bench=True）。weakness = 有效弱点覆盖（task 017）。
    """
    dmg = attack.damage or 0
    if dmg <= 0:
        return 0
    # 插入点：攻击方身上附加的增伤效果（task 009+ 修饰原语）
    if not to_bench:
        dmg = _weakness_resistance(atk_card, defender, dmg, weakness=weakness)
    # 插入点：防御方身上附加的减伤效果（task 009+）
    return max(dmg, 0)


class GameEngine:
    """持有随机源与事件流；状态本身不可变，apply/new_game 产出新 GameState。

    card_effects：name_group（本期 = 卡名）→ DSL 文档；引擎对卡牌内容零硬编码，
    无文档的训练家卡不可使用。
    """

    def __init__(
        self, rng: RandomSource, card_effects: Mapping[str, CardEffectDoc] | None = None
    ) -> None:
        self.rng = rng
        self.card_effects = dict(card_effects or {})
        self.events: list[GameEvent] = []
        self.state: GameState

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

        # 放置基础宝可梦到备战区：不限次，≤5（规则书·行动阶段）
        if len(p.bench) < 5:
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

        # 撤退：每回合 1 次机会（pokemon.cn basic_rules05）；弃撤退费用数量的能量，与备战区对换
        if (
            p.active
            and p.bench
            and not p.retreated_this_turn
            and len(p.active.attached_energy) >= p.active.current.card.retreat_cost
        ):
            for i in range(len(p.bench)):
                actions.append(Action(kind="retreat", bench_index=i))

        # 攻击：能量满足 且（有伤害 或 有 on_attack DSL 绑定）的招式各一条行动
        # （rules-manual §6 能量需求；纯效果招式经 DSL 结算，task 012）；
        # 先攻方第一回合不能攻击（规则书·回合的进行）。
        # 授予招式（task 016）：attached_tool 的招式接在自身招式后枚举，能量由持有者
        # 附着能量支付，DSL 绑定取道具文档；无绑定的授予招式不枚举（task 015 纪律）。
        first_turn_ban = s.turn == 1 and player == s.first_player
        if p.active and not first_turn_ban:
            own_attacks = p.active.current.card.attacks
            own_doc = self.card_effects.get(p.active.current.card.name)
            tool = p.active.attached_tool
            combined = [(a, own_doc) for a in own_attacks]
            if tool is not None:
                tool_doc = self.card_effects.get(tool.card.name)
                combined += [(a, tool_doc) for a in tool.card.attacks]
            for i, (attack, doc) in enumerate(combined):
                if not _energy_satisfied(p.active.attached_energy, attack.cost):
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
            doc = self.card_effects.get(c.card.name)
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
            if not playable_feasible(effect, p, bench_full=len(p.bench) >= 5,
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
            sdoc = self.card_effects.get(s.stadium.card.name)
            seffect = next(
                (e for e in sdoc.effects if e.trigger == "stadium_grant"), None,
            ) if sdoc else None
            if seffect is not None and playable_feasible(
                seffect, p, bench_full=len(p.bench) >= 5,
                opponent=s.players[1 - player], first_turn=s.turn == 1,
            ):
                actions.append(Action(kind="use_stadium"))

        # 特性（ability_manual）：场上宝可梦每回合按 DSL limit 发动（rules-manual 特性节）；
        # 限次强制 + 条件门（task 017：condition 不满足不枚举）+ 可行性门（池为空不枚举；
        # 门未覆盖的形式 DslError 不猜）
        for t in in_play:
            top = t.current
            doc = self.card_effects.get(top.card.name)
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

    def _do_place_bench(self, player: int, action: Action) -> None:
        """【规则出处·游戏准备】备战区可放任意只基础宝可梦（≤5）。"""
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        self._set_player(player, p.model_copy(update={
            "bench": p.bench + (InPlayPokemon(stack=(card,)),),
            "entered_play_this_turn": p.entered_play_this_turn | {card.iid},
        }))
        self._emit("place_bench", player, iid=card.iid, name=card.card.name)

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
        """【规则书·进化】手牌进化卡覆盖到对应宝可梦上，特殊状态恢复，伤害保留。"""
        p, card = self._take_from_hand(self.state.players[player], action.iid)  # type: ignore[arg-type]
        slot, idx, target = self._find_in_play(p, action.target_iid)  # type: ignore[arg-type]
        evolved = target.model_copy(update={
            "stack": target.stack + (card,),
            "conditions": frozenset(),
        })
        p = self._replace_in_play(p, slot, idx, evolved)
        self._set_player(player, p.model_copy(update={
            "evolved_this_turn": p.evolved_this_turn | {card.iid},
        }))
        self._emit("evolve", player, iid=card.iid, name=card.card.name, onto=target.current.card.name)

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

    def _do_use_stadium(self, player: int, action: Action) -> None:
        """stadium_grant 行动（task 017）：以当前玩家为 ctx 跑竞技场 DSL 效果块，
        可挂起（chooser）；完成后标记本回合已用。"""
        stadium = self.state.stadium
        assert stadium is not None  # legal_actions 已保证
        p = self.state.players[player]
        self._set_player(player, p.model_copy(update={"stadium_used_this_turn": True}))
        self._emit("use_stadium", player, name=stadium.card.name)
        doc = self.card_effects[stadium.card.name]
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
            doc = self.card_effects.get(tool.card.name)
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
        标记只保留到自己回合结束）。"""
        self._discard_turn_end_tools(player)
        p = self.state.players[player]
        if p.own_ko_during_opponent_turn:
            self._set_player(player, p.model_copy(update={
                "own_ko_during_opponent_turn": False,
            }))

    def _do_retreat(self, player: int, action: Action) -> None:
        """【规则书·撤退】弃撤退费用数量的能量，与备战区对换，撤退方特殊状态恢复。"""
        p = self.state.players[player]
        active = p.active
        cost = active.current.card.retreat_cost
        discarded = active.attached_energy[:cost]
        retreated = active.model_copy(update={
            "attached_energy": active.attached_energy[cost:],
            "conditions": frozenset(),
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
        """
        s = self.state
        atk = s.players[player].active
        # 授予招式（task 016）：attack_index 越过自身招式数时取 attached_tool 的招式，
        # DSL 文档与效果源均为道具卡（如招式学习器 进化的「进化」）
        own_attacks = atk.current.card.attacks
        tool = atk.attached_tool
        if action.attack_index < len(own_attacks):
            attack = own_attacks[action.attack_index]
            doc = self.card_effects.get(atk.current.card.name)
            source = atk.current
        else:
            assert tool is not None  # legal_actions 已保证索引合法
            attack = tool.card.attacks[action.attack_index - len(own_attacks)]
            doc = self.card_effects.get(tool.card.name)
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
                self._begin_turn(1 - player)
                return
            # 正面：继续正常结算（混乱不解除）
        effect_index = next(
            (i for i, e in enumerate(doc.effects)
             if e.trigger == "on_attack" and e.attack == attack.name),
            None,
        ) if doc else None
        if effect_index is not None:
            self._emit("attack", player, name=atk.current.card.name, attack=attack.name)
            self._run_or_suspend(player, source, effect_index, start=0,
                                 completion="attack")
            return
        defender = 1 - player
        d = s.players[defender]
        dmg = _attack_damage(attack, atk.current.card, d.active,
                             weakness=self._effective_weakness(player, d.active))
        target = d.active.model_copy(update={"damage": d.active.damage + dmg})
        self._set_player(defender, d.model_copy(update={"active": target}))
        self._emit("attack", player, name=atk.current.card.name, attack=attack.name,
                   damage=dmg, target=target.current.card.name)
        self.check_knockouts()
        if self.state.phase in ("game_over", "promote"):
            return  # 游戏已结束或等待换上
        self._on_turn_end(player)
        self._begin_turn(defender)

    def _effective_hp(self, mon: InPlayPokemon, player: int) -> int:
        """最大 HP 含道具常驻修正（rules-manual §8 昏厥判定的 HP 基准）。

        引擎对卡牌内容零硬编码：修正值读道具 DSL 文档 passive_static 的
        modify_hp 声明（condition 如 holder_is_basic 在求值点判定）。
        """
        hp = mon.current.card.hp or 0
        tool = mon.attached_tool
        if tool is None:
            return hp
        doc = self.card_effects.get(tool.card.name)
        if doc is None:
            return hp
        from battlefrontier.dsl.chooser import condition_met

        for effect in doc.effects:
            if effect.trigger != "passive_static":
                continue
            if not condition_met(effect.condition, self, player, mon):
                continue
            for node in effect.actions:
                if node.action == "modify_hp":
                    hp += node.args["amount"]
        return hp

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
            doc = self.card_effects.get(m.current.card.name)
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

    def check_knockouts(self) -> None:
        """任意伤害来源后的统一昏厥检查入口（rules-manual §8；§7.2 检查后结算同源）。

        扫描双方备战区与战斗场，伤害 ≥ 最大 HP（含道具修正，_effective_hp）即昏厥：
        整叠（进化链+能量+道具）进弃牌堆、对手按规则盒拿取奖赏；战斗场昏厥进换上
        （promote）流程，备战昏厥无需换上。
        双方同时多只昏厥的结算顺序见 rules-manual 附录待核清单（当前伤害源为单体
        招式，不会触发）。
        """
        for player in (0, 1):
            p = self.state.players[player]
            # 备战区昏厥
            kept = []
            for b in p.bench:
                if b.damage >= self._effective_hp(b, player):
                    if self._knockout_one(player, b):
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
                if self._knockout_one(player, active):
                    return
                d = self.state.players[player]
                if not d.bench:
                    # 【rules-manual §8 胜利条件②】战斗场昏厥且备战区无可换上
                    self._game_over(winner=1 - player, reason="no_pokemon")
                    return
                self.state = self.state.model_copy(update={
                    "phase": "promote", "current_player": player,
                })
                return

    def _knockout_one(self, player: int, knocked_mon: InPlayPokemon) -> bool:
        """结算一只昏厥：整叠（进化链 + 能量 + 道具）进弃牌堆，对手按规则盒拿奖赏
        （rules-manual §1.4/§8，不看正面；任意顺序拿取暂以固定取顶实现，统计等价）。

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
        # 跨回合标记（task 017 化危为吉）：「上一个对手的回合」内我方宝可梦昏厥——
        # 昏厥归属方不是当前回合方时置位，其回合结束时清除（_on_turn_end）
        if player != self.state.current_player:
            owner = self.state.players[player]
            self._set_player(player, owner.model_copy(update={
                "own_ko_during_opponent_turn": True,
            }))
        taker_idx = 1 - player
        taker = self.state.players[taker_idx]
        n = PRIZE_BY_RULE_BOX.get(knocked_mon.current.card.rule_box or "", 1)
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
        # 换上后回合权：默认换上方回合（普通昏厥）；turn_after_promote 置位时给指定方
        # （混乱反面自我昏厥：攻击已消耗，回合权给对手——D1 决议 task 013）
        nxt = self.state.turn_after_promote
        if nxt is not None:
            self.state = self.state.model_copy(update={"turn_after_promote": None})
        self._begin_turn(nxt if nxt is not None else player)

    def _do_end_turn(self, player: int, action: Action) -> None:
        self._emit("end_turn", player)
        self._on_turn_end(player)
        self._begin_turn(1 - player)

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
        doc = self.card_effects[card.card.name]
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
        doc = self.card_effects[mon.current.card.name]
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
    ) -> None:
        """跑效果或挂起：NeedChoice → phase="choice" + pending_choice；完成 → 按 completion 收尾。"""
        from battlefrontier.dsl.chooser import build_pending

        doc = self.card_effects[card.card.name]
        effect = doc.effects[effect_index]
        ctx = ExecutionContext(
            engine=self, player=player, source=card,
            effect_id=f"{card.card.name}[{card.iid}]:{effect.trigger}", trigger=effect.trigger,
        )
        need = run_effect(ctx, effect, start=start, choice=choice, carry=carry)
        if need is not None:
            pending = build_pending(self, player, card, effect_index, need.cursor, need,
                                    completion=completion)
            self.state = self.state.model_copy(update={
                "phase": "choice", "current_player": player, "pending_choice": pending,
            })
            return
        # 效果完成：训练家卡本体进弃牌区（规则书·训练家卡）；特性不弃置；
        # 攻击结算完毕推进对手回合（rules-manual §6：攻击后回合结束）。
        # 效果内若已触发换上/终局（check_knockouts），不覆盖其阶段。
        if completion == "trainer":
            p = self.state.players[player]
            self._set_player(player, p.model_copy(update={"discard": p.discard + (card,)}))
        if self.state.phase in ("main", "choice"):
            if completion == "attack":
                self.state = self.state.model_copy(update={"pending_choice": None})
                self._on_turn_end(player)
                self._begin_turn(1 - player)
            else:
                self.state = self.state.model_copy(update={
                    "phase": "main", "pending_choice": None,
                })
        else:
            self.state = self.state.model_copy(update={"pending_choice": None})

    def _do_choose(self, player: int, action: Action) -> None:
        """chooser 恢复：带选择结果从挂起游标续跑效果（PRD §5.2）。"""
        pc = self.state.pending_choice
        assert pc is not None  # legal_actions 已保证 phase="choice" 才有 choose
        self.state = self.state.model_copy(update={"pending_choice": None})
        self._run_or_suspend(player, pc.source, pc.effect_index,
                             start=pc.cursor, choice=action.choices,
                             carry=pc.payload, completion=pc.completion)

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
        })
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
        })
        self._emit("game_over", winner, reason=reason, is_draw=is_draw)

    def force_draw(self, reason: str) -> None:
        """死循环保护等强制判平入口（上限值由调用方配置）。"""
        self._emit(reason, None)
        self._game_over(winner=None, reason=reason, is_draw=True)
