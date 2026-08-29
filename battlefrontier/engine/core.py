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


def _attack_damage(
    attack: AttackDef, atk_card: CardDef, defender: InPlayPokemon, *, to_bench: bool = False
) -> int:
    """伤害计算顺序（rules-manual §6）：基准（≤0 终止）→ 弱点 ×2 → 抗性 -30 → 下限 0。

    白板期无攻/防修饰，修饰插入点见注释；备战区伤害不计算弱点抗性（贯穿规则，
    铺伤原语落地时走 to_bench=True）。
    """
    dmg = attack.damage or 0
    if dmg <= 0:
        return 0
    # 插入点：攻击方身上附加的增伤效果（task 009+ 修饰原语）
    if not to_bench:
        if defender.current.card.weakness is not None and defender.current.card.weakness == atk_card.energy_type:
            dmg *= 2
        if defender.current.card.resistance is not None and defender.current.card.resistance == atk_card.energy_type:
            dmg -= 30  # 现行规则抗性恒 -30（rules-manual §6）
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

        # 撤退：每回合 1 次机会（pokemon.cn basic_rules05）；弃撤退费用数量的能量，与备战区对换
        if (
            p.active
            and p.bench
            and not p.retreated_this_turn
            and len(p.active.attached_energy) >= p.active.current.card.retreat_cost
        ):
            for i in range(len(p.bench)):
                actions.append(Action(kind="retreat", bench_index=i))

        # 攻击：每个有伤害且能量满足的招式一条行动（rules-manual §6 能量需求）；
        # 先攻方第一回合不能攻击（规则书·回合的进行）
        first_turn_ban = s.turn == 1 and player == s.first_player
        if p.active and not first_turn_ban:
            for i, attack in enumerate(p.active.current.card.attacks):
                if attack.damage is not None and _energy_satisfied(
                    p.active.attached_energy, attack.cost
                ):
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
            # 成本可行性门（chooser task 009）：成本无法支付/无合法落点则不枚举
            from battlefrontier.dsl.chooser import playable_feasible
            effect = next(e for e in doc.effects if e.trigger == "on_play")
            if not playable_feasible(effect, p, bench_full=len(p.bench) >= 5):
                continue
            actions.append(Action(kind="play_trainer", iid=c.iid))

        # 特性（ability_manual）：场上宝可梦每回合按 DSL limit 发动（rules-manual 特性节）；
        # 限次强制 + 可行性门（池为空不枚举；门未覆盖的形式 DslError 不猜）
        from battlefrontier.dsl.chooser import ability_feasible
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
            if not ability_feasible(effect, p):
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
        """【rules-manual §6】按 attack_index 选招式，伤害经 _attack_damage 结算；
        攻击后回合结束。昏厥统一走 check_knockouts。"""
        s = self.state
        atk = s.players[player].active
        attack = atk.current.card.attacks[action.attack_index]
        defender = 1 - player
        d = s.players[defender]
        dmg = _attack_damage(attack, atk.current.card, d.active)
        target = d.active.model_copy(update={"damage": d.active.damage + dmg})
        self._set_player(defender, d.model_copy(update={"active": target}))
        self._emit("attack", player, name=atk.current.card.name, attack=attack.name,
                   damage=dmg, target=target.current.card.name)
        self.check_knockouts()
        if self.state.phase in ("game_over", "promote"):
            return  # 游戏已结束或等待换上
        self._begin_turn(defender)

    def check_knockouts(self) -> None:
        """任意伤害来源后的统一昏厥检查入口（rules-manual §8；§7.2 检查后结算同源）。

        扫描双方备战区与战斗场，伤害 ≥ HP 即昏厥：整叠（进化链+能量）进弃牌堆、
        对手按规则盒拿取奖赏；战斗场昏厥进换上（promote）流程，备战昏厥无需换上。
        双方同时多只昏厥的结算顺序见 rules-manual 附录待核清单（当前伤害源为单体
        招式，不会触发）。
        """
        for player in (0, 1):
            p = self.state.players[player]
            # 备战区昏厥
            kept = []
            for b in p.bench:
                if b.damage >= (b.current.card.hp or 0):
                    if self._knockout_one(player, b):
                        return  # 对手拿完奖赏，立即获胜
                else:
                    kept.append(b)
            if len(kept) != len(p.bench):
                p = self.state.players[player]
                self._set_player(player, p.model_copy(update={"bench": tuple(kept)}))
            # 战斗场昏厥
            p = self.state.players[player]
            if p.active and p.active.damage >= (p.active.current.card.hp or 0):
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
        """结算一只昏厥：整叠进弃牌堆，对手按规则盒拿奖赏（rules-manual §1.4/§8，
        不看正面；任意顺序拿取暂以固定取顶实现，统计等价）。

        返回 True 表示对手拿完奖赏立即获胜（胜利条件①，调用方停止后续结算）。
        """
        p = self.state.players[player]
        self._set_player(player, p.model_copy(update={
            "discard": p.discard + knocked_mon.stack + knocked_mon.attached_energy,
        }))
        self._emit("knockout", player, name=knocked_mon.current.card.name)
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
        self._begin_turn(player)

    def _do_end_turn(self, player: int, action: Action) -> None:
        self._emit("end_turn", player)
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
        # 效果完成：训练家卡本体进弃牌区（规则书·训练家卡）；特性不弃置。
        # 效果内若已触发换上/终局（check_knockouts），不覆盖其阶段。
        if completion == "trainer":
            p = self.state.players[player]
            self._set_player(player, p.model_copy(update={"discard": p.discard + (card,)}))
        if self.state.phase in ("main", "choice"):
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
