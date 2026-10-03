"""通用启发式 Agent（PRD §7.2，task 018）。

局面评估函数（奖赏差/场面战力/手牌质量/能量就绪度/牌库资源，线性加权）+
决策规则（开局布阵优先级、行动排序「特性→进化→能量→物品→支援者→攻击」、
斩杀检测）。D10：不做单卡组定制——评分只用通用字段（HP/招式伤害/撤退费/
进化链/卡片类别），不按卡名分支。

确定性纪律：不消费引擎随机源，一切 tie-break 用 iid/下标升序；
参数全部收敛到 HeuristicParams，默认值即 PRD 通用启发式。
评估函数与决策规则拆成纯函数（`evaluate` / `pokemon_score`），为 MCTS
rollout 预留（PRD §7.3）。
"""

from __future__ import annotations

from dataclasses import dataclass

from battlefrontier.agent.dsl_estimate import (
    attack_has_draw,
    card_has_draw,
    damage_formula,
    estimate_attack_damage,
    has_hand_ammo_pattern,
    pending_damage_link,
)
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import _energy_satisfied
from battlefrontier.engine.state import (
    CardDef,
    CardInstance,
    InPlayPokemon,
    PendingChoice,
    Supertype,
    VisibleGameState,
)

__all__ = ["HeuristicAgent", "HeuristicParams", "evaluate", "pokemon_score"]

# 抗性减伤（rules-manual §6：抗性 -30）
RESISTANCE_AMOUNT = 30


@dataclass(frozen=True)
class HeuristicParams:
    """启发式参数（PRD §7.2：参数全暴露进实验定义）。默认值=通用启发式。"""

    # 宝可梦评分权重（布阵/推备/能量目标/检索选择共用）
    w_hp: float = 1.0
    w_damage: float = 5.0
    w_retreat: float = -10.0
    # 局面评估函数五因子权重（评估/报告/后续 MCTS rollout 用）
    w_prize_diff: float = 10.0
    w_board: float = 1.0
    w_hand: float = 0.5
    w_energy_ready: float = 2.0
    w_deck: float = 0.1
    # 决策开关
    use_abilities: bool = True
    max_bench_setup: int = 3       # 开局布阵最多放置的备战区数量
    play_items: bool = True
    play_supporters: bool = True
    play_stadiums: bool = True
    attach_tools: bool = True
    retreat_when_powerless: bool = True  # 战斗场无可支付招式且备战区有就绪打手时撤退
    # 牌库资源管理（task 032 WP2，D-032-6）：牌库余量 ≤ deck_low_threshold 时
    # 抑制含 draw 节点的训练家、攻击选择排除含 draw 的招式（有其他攻击可选时）；
    # 默认值即新行为，旧实验 YAML 无参兼容
    deck_protect: bool = True
    deck_low_threshold: int = 6


def _card_of(poke: InPlayPokemon | CardInstance):
    return poke.current.card if isinstance(poke, InPlayPokemon) else poke.card


def pokemon_score(poke: InPlayPokemon | CardInstance, params: HeuristicParams) -> float:
    """通用战力分：HP + 最大招式伤害 + 撤退费惩罚（D10：只用通用字段）。"""
    card = _card_of(poke)
    max_damage = max((a.damage or 0 for a in card.attacks), default=0)
    return (
        params.w_hp * (card.hp or 0)
        + params.w_damage * max_damage
        + params.w_retreat * card.retreat_cost
    )


def _in_play(active: InPlayPokemon | None, bench: tuple[InPlayPokemon, ...]) -> list[InPlayPokemon]:
    return ([active] if active else []) + list(bench)


def evaluate(view: VisibleGameState, params: HeuristicParams) -> float:
    """局面评估函数（PRD §7.2 五因子，线性加权；从 current_player 视角）。"""
    own, opp = view.own, view.opponent
    own_in, opp_in = _in_play(own.active, own.bench), _in_play(opp.active, opp.bench)
    board_own = sum(pokemon_score(p, params) for p in own_in)
    board_opp = sum(pokemon_score(p, params) for p in opp_in)
    energy_own = sum(len(p.attached_energy) for p in own_in)
    energy_opp = sum(len(p.attached_energy) for p in opp_in)
    return (
        params.w_prize_diff * (own.prizes_count - opp.prizes_count)  # 对手奖赏剩得少=我方领先
        + params.w_board * (board_own - board_opp)
        + params.w_hand * (len(own.hand) - opp.hand_count)
        + params.w_energy_ready * (energy_own - energy_opp)
        + params.w_deck * (own.deck_count - opp.deck_count)
    )


class HeuristicAgent:
    """通用启发式 Agent：只读 VisibleGameState，决策确定（无随机源）。

    card_effects（task 032 WP2，D-032-2）：可选 DSL 文档库（公开卡面信息，
    不违反可见视图纪律），供变量伤害估算 / 囤能例外 / 牌库保护读取；
    None 时全部行为回退静态基值现状。
    """

    def __init__(self, params: HeuristicParams | None = None, card_effects=None) -> None:
        self.params = params or HeuristicParams()
        self.card_effects = card_effects

    def observe(self, view: VisibleGameState, legal_actions: list[Action]) -> Action:
        if not legal_actions:
            raise ValueError("无合法行动可选")
        by_kind: dict[str, list[Action]] = {}
        for a in legal_actions:
            by_kind.setdefault(a.kind, []).append(a)

        if acts := by_kind.get("place_active"):
            return self._pick_place(view, acts)
        if "confirm_setup" in by_kind:
            return self._decide_setup_bench(view, by_kind)
        if acts := by_kind.get("promote"):
            return self._pick_promote(view, acts)
        if acts := by_kind.get("choose"):
            return self._pick_choose(view, acts)
        return self._decide_main(view, by_kind)

    # ── 开局布阵 / 推备 ─────────────────────────────────

    def _pick_place(self, view: VisibleGameState, acts: list[Action]) -> Action:
        hand = {c.iid: c for c in view.own.hand}
        return min(acts, key=lambda a: (-pokemon_score(hand[a.iid], self.params), a.iid))

    def _decide_setup_bench(self, view: VisibleGameState, by_kind: dict[str, list[Action]]) -> Action:
        acts = by_kind.get("place_bench", [])
        if acts and len(view.own.bench) < self.params.max_bench_setup:
            return self._pick_place(view, acts)
        return next(a for a in by_kind["confirm_setup"])

    def _pick_promote(self, view: VisibleGameState, acts: list[Action]) -> Action:
        return min(
            acts,
            key=lambda a: (-pokemon_score(view.own.bench[a.bench_index], self.params), a.bench_index),
        )

    # ── chooser 选择 ────────────────────────────────────

    def _pick_choose(self, view: VisibleGameState, acts: list[Action]) -> Action:
        pool = {c.iid: c for c in view.pending_pool or ()}
        # 池在公开区域（手牌/弃牌堆/场上）时 pending_pool 为 None，从可见视图补
        for c in (*view.own.hand, *view.own.discard):
            pool.setdefault(c.iid, c)
        for p in _in_play(view.own.active, view.own.bench):
            for c in (*p.stack, *p.attached_energy):
                pool.setdefault(c.iid, c)
        # 对手场上宝可梦（opponent_pokemon_any 类池，如复制招式的目标选择）
        for p in _in_play(view.opponent.active, view.opponent.bench):
            pool.setdefault(p.current.iid, p.current)

        def score(a: Action) -> float:
            total = 0.0
            for iid in a.choices:
                card = pool.get(iid)
                if card is None:
                    continue
                if card.card.supertype == Supertype.POKEMON:
                    total += pokemon_score(card, self.params)
                elif card.card.supertype == Supertype.ENERGY:
                    total += 1.0
                else:
                    total += 0.5
            return total

        pc = view.pending_choice
        # 伤害关联 any_count discard（task 032 WP2，D-032-4）：淘金潮/极雷轰型——
        # 弃得越多伤害越高，是「收益」不是「代价」，优先于 cost/actions 评分方向：
        # 能斩杀选达到斩杀的最小张数（省弹药），不能斩杀全选倾泻
        if pc is not None:
            linked = self._pick_damage_linked_discard(view, acts, pc)
            if linked is not None:
                return linked
        # cost 段（代价支付，task 032 WP1，D-032-1）取最低评分——不弃高分宝可梦；
        # actions 段（收益选择）与无挂起帧防御路径维持最高评分。tie-break 均为
        # choices 升序（确定性）
        if pc is not None and pc.step_phase == "cost":
            return min(acts, key=lambda a: (score(a), a.choices))
        return min(acts, key=lambda a: (-score(a), a.choices))

    def _pick_damage_linked_discard(
        self, view: VisibleGameState, acts: list[Action], pc: PendingChoice
    ) -> Action | None:
        """D-032-4：any_count discard 后续 damage count=discarded_this_effect 时，
        按斩杀需求定量弃置；非伤害关联返回 None（回退评分方向）。"""
        node = pending_damage_link(pc, self.card_effects)
        if node is None:
            return None
        opp = view.opponent.active
        if opp is None:
            return None
        remaining = (opp.current.card.hp or 0) - opp.damage
        target: int | None = None
        for n in range(pc.min_choose, pc.max_choose + 1):
            dmg = damage_formula(node, n)
            if dmg is None:
                return None
            if dmg >= remaining:
                target = n  # 能斩杀 → 达到斩杀的最小张数
                break
        if target is None:
            target = pc.max_choose  # 不能斩杀 → 倾泻全选
        candidates = [a for a in acts if len(a.choices) == target]
        if not candidates:
            return None
        return min(candidates, key=lambda a: a.choices)  # tie-break choices 升序

    # ── 主阶段行动排序 ──────────────────────────────────

    def _decide_main(self, view: VisibleGameState, by_kind: dict[str, list[Action]]) -> Action:
        hand = {c.iid: c for c in view.own.hand}
        deck_low = self._deck_low(view)
        if self.params.use_abilities and (acts := by_kind.get("use_ability")):
            return min(acts, key=lambda a: a.iid)
        if acts := by_kind.get("evolve"):
            return min(
                acts,
                key=lambda a: (-pokemon_score(hand[a.iid], self.params), a.iid, a.target_iid or 0),
            )
        if acts := by_kind.get("attach_energy"):
            picked = self._pick_energy_attach(view, acts)
            if picked is not None:
                return picked
        if acts := by_kind.get("attack"):
            lethal = self._lethal_attack(view, acts)
            if lethal is not None:  # 斩杀优先于物品/支援者（PRD §7.2 斩杀检测）
                return lethal
        if self.params.attach_tools and (acts := by_kind.get("attach_tool")):
            active_iid = view.own.active.current.iid if view.own.active else None
            return min(acts, key=lambda a: (a.target_iid != active_iid, a.target_iid or 0, a.iid))
        if self.params.retreat_when_powerless and (acts := by_kind.get("retreat")):
            picked = self._pick_retreat(view, acts)
            if picked is not None:
                return picked
        if self.params.play_items:
            items = [a for a in by_kind.get("play_trainer", [])
                     if hand[a.iid].card.trainer_subtype == "物品"]
            if deck_low:  # D-032-6：含 draw 节点物品抑制（跳过该卡，继续排序）
                items = [a for a in items
                         if not card_has_draw(hand[a.iid].card, self.card_effects)]
            if items:
                return min(items, key=lambda a: a.iid)
        if self.params.play_supporters:
            supporters = [a for a in by_kind.get("play_trainer", [])
                          if hand[a.iid].card.trainer_subtype == "支援者"]
            if deck_low:  # D-032-6：含 draw 节点支援者抑制
                supporters = [a for a in supporters
                              if not card_has_draw(hand[a.iid].card, self.card_effects)]
            if supporters:
                return min(supporters, key=lambda a: a.iid)
        if self.params.play_stadiums and (acts := by_kind.get("play_stadium")):
            return min(acts, key=lambda a: a.iid)
        if acts := by_kind.get("use_stadium"):
            return acts[0]
        if acts := by_kind.get("attack"):
            return self._pick_attack(view, acts)
        fallback = by_kind.get("end_turn")
        return fallback[0] if fallback else min(
            (a for acts in by_kind.values() for a in acts),
            key=lambda a: (a.kind, a.iid or 0, a.target_iid or 0),
        )

    def _deck_low(self, view: VisibleGameState) -> bool:
        """D-032-6：牌库余量触及保护线（deck_protect 关闭时恒 False）。"""
        return (
            self.params.deck_protect
            and view.own.deck_count <= self.params.deck_low_threshold
        )

    def _pick_energy_attach(self, view: VisibleGameState, acts: list[Action]) -> Action | None:
        """能量目标：仍有付不起的招式才补能（全就绪则不浪费每回合 1 次的附着）。

        战斗场未就绪优先补给；否则补给备战区未就绪最高分者；全都就绪返回 None 跳过。
        A3 囤能例外（task 032 WP2，D-032-5 修订）：主动宝可梦为手牌弹药型（on_attack
        含 discard own_hand + 后续 damage count=discarded_this_effect）且已能开打
        （任一招式费用已满足）时不附着——能量留手牌作弹药；尚不能开打时照常补费
        （M8b 复校准实证：无条件跳过会让未充能的主战手永久卡死）；无 DSL 文档时
        现状不变。
        """
        active = view.own.active
        hand_ammo = active is not None and has_hand_ammo_pattern(
            active.current.card, self.card_effects
        )

        def needs_energy(poke: InPlayPokemon) -> bool:
            return any(
                not _energy_satisfied(poke.attached_energy, atk.cost)
                for atk in poke.current.card.attacks
            )

        if active is not None and needs_energy(active):
            target_iid = active.current.iid
        elif hand_ammo:
            return None
        else:
            candidates = [b for b in view.own.bench if needs_energy(b)]
            if not candidates:
                return None
            best = min(candidates, key=lambda b: (-pokemon_score(b, self.params), b.current.iid))
            target_iid = best.current.iid
        targeted = [a for a in acts if a.target_iid == target_iid]
        return min(targeted or acts, key=lambda a: (a.target_iid or 0, a.iid))

    def _pick_retreat(self, view: VisibleGameState, acts: list[Action]) -> Action | None:
        """保守撤退：仅当战斗场无可支付招式且备战区有已就绪打手时撤退。"""
        active = view.own.active
        if active is None:
            return None
        can_attack = any(
            _energy_satisfied(active.attached_energy, atk.cost)
            for atk in active.current.card.attacks
        )
        if can_attack:
            return None
        ready = [
            a for a in acts
            if any(
                _energy_satisfied(view.own.bench[a.bench_index].attached_energy, atk.cost)
                for atk in view.own.bench[a.bench_index].current.card.attacks
            )
        ]
        if not ready:
            return None
        return min(
            ready,
            key=lambda a: (-pokemon_score(view.own.bench[a.bench_index], self.params), a.bench_index),
        )

    def _attack_sources(self, view: VisibleGameState) -> tuple[list, list[CardDef]]:
        """各招式（含道具授予招式，core.py 同序）与其来源卡（本体 / 附着道具）。"""
        active = view.own.active
        assert active is not None
        attacks = list(active.current.card.attacks)
        sources = [active.current.card] * len(attacks)
        if active.attached_tool is not None:
            tool_attacks = list(active.attached_tool.card.attacks)
            attacks += tool_attacks
            sources += [active.attached_tool.card] * len(tool_attacks)
        return attacks, sources

    def _attack_table(self, view: VisibleGameState) -> list[tuple[int, bool]]:
        """各招式对对手战斗场的（有效伤害， 可参与斩杀判定）。

        每招先查 DSL 变量伤害估算器（task 032 WP2，D-032-3：淘金潮 50×手牌弃能
        等不再被看成静态基值）；估算 None 回退 atk.damage 现状路径。
        弱点 ×2 / 抗性 -30（rules-manual §6）维持既有后处理；纯效果招式记 0。
        lethal_ok=False（效果 condition 不可判 / 不满足）的招式基值仍入表、
        不参与斩杀判定。
        """
        opp = view.opponent.active
        attacks, sources = self._attack_sources(view)
        table: list[tuple[int, bool]] = []
        for atk, src in zip(attacks, sources, strict=True):
            est = estimate_attack_damage(view, atk.name, atk.damage, src, self.card_effects)
            if est is None:
                dmg, lethal_ok = atk.damage or 0, True
            else:
                dmg, lethal_ok = est.amount, est.lethal_ok
            if opp is not None and dmg:
                own_type = view.own.active.current.card.energy_type
                if opp.current.card.weakness and own_type == opp.current.card.weakness:
                    dmg *= 2
                if opp.current.card.resistance and own_type == opp.current.card.resistance:
                    dmg = max(0, dmg - RESISTANCE_AMOUNT)
            table.append((dmg, lethal_ok))
        return table

    def _attack_damage_table(self, view: VisibleGameState) -> list[int]:
        """各招式对对手战斗场的有效伤害（_attack_table 的伤害投影）。"""
        return [dmg for dmg, _ in self._attack_table(view)]

    def _lethal_attack(self, view: VisibleGameState, acts: list[Action]) -> Action | None:
        """斩杀检测：能直接昏厥对手战斗场且可参与斩杀判定的招式，取有效伤害最高者
        （tie 取下标小者）。"""
        opp = view.opponent.active
        if opp is None:
            return None
        table = self._attack_table(view)
        remaining = (opp.current.card.hp or 0) - opp.damage
        lethal = [
            a for a in acts
            if table[a.attack_index][1] and table[a.attack_index][0] >= remaining
        ]
        if not lethal:
            return None
        return max(lethal, key=lambda a: (table[a.attack_index][0], -a.attack_index))

    def _pick_attack(self, view: VisibleGameState, acts: list[Action]) -> Action:
        """无斩杀时取有效伤害最高的招式（tie 取下标小者）。

        D-032-6：牌库余量触及保护线时排除含 draw 节点的招式（有其他攻击可选时）。
        """
        table = self._attack_table(view)
        candidates = acts
        if self._deck_low(view):
            attacks, sources = self._attack_sources(view)
            non_draw = [
                a for a in acts
                if not attack_has_draw(
                    sources[a.attack_index], attacks[a.attack_index].name, self.card_effects
                )
            ]
            if non_draw:
                candidates = non_draw
        return max(candidates, key=lambda a: (table[a.attack_index][0], -a.attack_index))
