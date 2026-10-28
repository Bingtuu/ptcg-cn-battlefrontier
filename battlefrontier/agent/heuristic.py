"""通用启发式 Agent（PRD §7.2，task 018）。

局面评估函数（奖赏差/场面战力/手牌质量/能量就绪度/牌库资源，线性加权）+
决策规则（开局布阵优先级、行动排序「特性→进化→能量→物品→支援者→攻击」、
斩杀检测）。特性不再无条件取最小 iid（task 077）：交易类弃抽与弃牌区附能
加伤按效果形态估价值，其余特性仍优先于进化。D10：不做单卡组定制——评分只用
通用字段（HP/招式伤害/撤退费/进化链/卡片类别）与效果形态，不按卡名分支。

确定性纪律：不消费引擎随机源，一切 tie-break 用 iid/下标升序；
参数全部收敛到 HeuristicParams，默认值即 PRD 通用启发式。
评估函数与决策规则拆成纯函数（`evaluate` / `pokemon_score`），为 MCTS
rollout 预留（PRD §7.3）；evaluate 五因子进一步拆为模块级因子函数
（`factor_*`，task 050 M11 WP1：特征层 A 组取因子原值）。
"""

from __future__ import annotations

from dataclasses import dataclass

from battlefrontier.agent.dsl_estimate import (
    attack_has_draw,
    card_has_draw,
    damage_formula,
    doc_for,
    estimate_attack_damage,
    has_hand_ammo_pattern,
    pending_damage_link,
)
from battlefrontier.dsl.chooser import matches_in_play
from battlefrontier.dsl.interpreter import flatten_steps
from battlefrontier.dsl.loader import DslError
from battlefrontier.dsl.schema import ActionNode, Effect
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import _energy_satisfied, resolve_tool_attacks
from battlefrontier.engine.state import (
    CardDef,
    CardInstance,
    InPlayPokemon,
    PendingChoice,
    Supertype,
    VisibleGameState,
)

__all__ = [
    "HeuristicAgent",
    "HeuristicParams",
    "evaluate",
    "factor_board_score",
    "factor_deck_diff",
    "factor_energy_ready_diff",
    "factor_hand_diff",
    "factor_prize_diff",
    "pokemon_score",
]

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
    # 特性质量门控（task 077，D-077-1~4）。False = 消融回「有特性就 min(iid)」。
    # 三个阈值可进实验 YAML；不进 tune 搜索空间。默认是第一刀，不是已拍板最优。
    ability_quality_gate: bool = True
    # 交易类（弃少量手牌再抽）牌库地板：余量 ≤ 此值拒用。每发固定抽 2 且可每回合
    # 重复，所以高于训练家用的 deck_low_threshold。
    ability_cycle_deck_floor: int = 12
    # 手牌张数高于此值拒交易类（同回合多只连刷会把牌库磨穿）。
    ability_cycle_hand_max: int = 4
    # 手牌最低保留分 ≤ 此值才算有垫牌可弃。能量=1、训练家=3、宝可梦=pokemon_score。
    # 默认 2：只有能量算垫牌（没有能量可弃 = 手牌差，拒交易类）。
    ability_cycle_discard_ceiling: float = 2.0


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


def factor_prize_diff(view: VisibleGameState) -> float:
    """五因子之一：奖赏差（对手奖赏剩得少 = 我方领先）。M11 WP1 特征层共享。"""
    return float(view.own.prizes_count - view.opponent.prizes_count)


def factor_board_score(view: VisibleGameState, params: HeuristicParams) -> float:
    """五因子之一：场面战力差（双方场上宝可梦 pokemon_score 合计之差）。"""
    own_in = _in_play(view.own.active, view.own.bench)
    opp_in = _in_play(view.opponent.active, view.opponent.bench)
    return (sum(pokemon_score(p, params) for p in own_in)
            - sum(pokemon_score(p, params) for p in opp_in))


def factor_hand_diff(view: VisibleGameState) -> float:
    """五因子之一：手牌质量差（我方手牌数 - 对手手牌数——对手只出 count）。"""
    return float(len(view.own.hand) - view.opponent.hand_count)


def factor_energy_ready_diff(view: VisibleGameState) -> float:
    """五因子之一：能量就绪度差（双方场上附着能量总数之差）。"""
    own_in = _in_play(view.own.active, view.own.bench)
    opp_in = _in_play(view.opponent.active, view.opponent.bench)
    return float(sum(len(p.attached_energy) for p in own_in)
                 - sum(len(p.attached_energy) for p in opp_in))


def factor_deck_diff(view: VisibleGameState) -> float:
    """五因子之一：牌库资源差（双方牌库余量之差）。"""
    return float(view.own.deck_count - view.opponent.deck_count)


def evaluate(view: VisibleGameState, params: HeuristicParams) -> float:
    """局面评估函数（PRD §7.2 五因子，线性加权；从 current_player 视角）。

    task 050（M11 WP1）：五因子拆为模块级纯函数（特征层 A 组取因子原值），
    evaluate = 因子加权和——行为零变化（test_features 对拍钉死）。
    """
    return (
        params.w_prize_diff * factor_prize_diff(view)
        + params.w_board * factor_board_score(view, params)
        + params.w_hand * factor_hand_diff(view)
        + params.w_energy_ready * factor_energy_ready_diff(view)
        + params.w_deck * factor_deck_diff(view)
    )


# 特性价值（task 077）。未归类 / 读不到文档 = 通用正价值（仍会用，只是不压过更高的）。
_GENERIC_ABILITY_VALUE = 10.0
_CYCLE_ABILITY_VALUE = 8.0
_ATTACH_PROGRESS_VALUE = 18.0
_ATTACH_ENABLE_VALUE = 30.0
_ACTIVE_ATTACH_BONUS = 5.0
_ENERGY_KEEP_SCORE = 1.0
_TRAINER_KEEP_SCORE = 3.0


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _is_cycle_discard_draw(effect: Effect) -> bool:
    """交易类：弃少量手牌（choose=N）再抽牌。整手刷新（count=all）与带伤害的弃牌不算。"""
    steps = flatten_steps(effect)
    discards = [n for _, n in steps if n.action == "discard" and n.selector == "own_hand"]
    if not discards or not any(n.action == "draw" for _, n in steps):
        return False
    if any(n.action == "damage" for _, n in steps):
        return False
    return all(
        n.count != "all" and _positive_int(n.choose) is not None
        for n in discards
    )


def _damage_attach_node(effect: Effect) -> ActionNode | None:
    """弃牌区附能并放置伤害指示物（精神拥抱形态）。"""
    for _, node in flatten_steps(effect):
        counters = _positive_int(node.args.get("damage_counters", 0))
        if node.action == "attach_energy" and node.selector == "own_discard" and counters:
            return node
    return None


def _energy_symbol(node: ActionNode) -> str | None:
    for word in node.filters:
        if word.startswith("energy_"):
            return word.split("_", 1)[1]
    return None


def _cost_satisfied(types: list[str | None], cost: tuple[str, ...]) -> bool:
    """与引擎 _energy_satisfied 同口径，但吃属性列表（便于模拟「再附 1 张」）。"""
    remaining = list(types)
    for sym in cost:
        if sym == "无":
            continue
        if sym in remaining:
            remaining.remove(sym)
        else:
            return False
    colorless = sum(1 for s in cost if s == "无")
    return len(remaining) >= colorless


def _energy_role(types: list[str | None], cost: tuple[str, ...], add: str | None) -> str:
    """none / progress / enable。add=None 表示过滤里没有属性，只当无色垫。"""
    if _cost_satisfied(types, cost):
        return "none"
    if _cost_satisfied([*types, add], cost):
        return "enable"
    colored = [s for s in cost if s != "无"]
    if add is not None and colored.count(add) > types.count(add):
        return "progress"
    colored_paid = all(types.count(s) >= colored.count(s) for s in set(colored))
    if colored_paid and len(types) < len(cost):
        return "progress"
    return "none"


def _mon_energy_role(mon: InPlayPokemon, add: str | None) -> int:
    """0=再附一张就付清某招，1=只推进缺口，2=帮不上。"""
    types = [e.card.energy_type for e in mon.attached_energy]
    best = 2
    for atk in mon.current.card.attacks:
        role = _energy_role(types, atk.cost, add)
        if role == "enable":
            return 0
        if role == "progress":
            best = 1
    return best


def _mon_by_iid(view: VisibleGameState, iid: int) -> InPlayPokemon | None:
    for mon in _in_play(view.own.active, view.own.bench):
        if mon.current.iid == iid:
            return mon
    return None


def _attach_targets(
    view: VisibleGameState, holder: InPlayPokemon, node: ActionNode,
) -> list[InPlayPokemon]:
    pool = node.args.get("target_pool", "own_pokemon_in_play")
    if pool == "self":
        mons = [holder]
    elif pool == "own_bench":
        mons = list(view.own.bench)
    else:
        mons = _in_play(view.own.active, view.own.bench)
    filters = tuple(node.args.get("target_filters", ()))
    counters = _positive_int(node.args.get("damage_counters", 0)) or 0
    kept: list[InPlayPokemon] = []
    for mon in mons:
        if filters:
            try:
                if not matches_in_play(mon, filters):
                    continue
            except DslError:
                continue
        hp = mon.current.card.hp or 0
        if mon.damage + counters * 10 >= hp:
            continue
        kept.append(mon)
    return kept


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
        # D-077-2：弃牌区附能并放指示物时，优先还没付清招式的目标（再回落原评分）
        bias = self._damage_attach_choice_node(view)
        if bias is not None:
            add = _energy_symbol(bias)

            def rank(a: Action) -> tuple:
                role_rank = 2
                for iid in a.choices:
                    mon = _mon_by_iid(view, iid)
                    if mon is None:
                        continue
                    role_rank = min(role_rank, _mon_energy_role(mon, add))
                return (role_rank, -score(a), a.choices)

            return min(acts, key=rank)
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
            picked = self._pick_ability(view, acts)
            if picked is not None:
                return picked
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

    def _pick_ability(self, view: VisibleGameState, acts: list[Action]) -> Action | None:
        """D-077-3：按价值选特性；全 ≤0 返回 None（本步不发，继续后续排序）。

        ability_quality_gate=False 时恢复 min(iid)（D-077-4 消融）。
        """
        if not self.params.ability_quality_gate:
            return min(acts, key=lambda a: a.iid if a.iid is not None else 0)
        positive = [(self._ability_value(view, a), a) for a in acts]
        positive = [(v, a) for v, a in positive if v > 0]
        if not positive:
            return None
        return max(positive, key=lambda va: (va[0], -(va[1].iid or 0)))[1]

    def _ability_value(self, view: VisibleGameState, action: Action) -> float:
        if action.iid is None:
            return _GENERIC_ABILITY_VALUE
        holder = _mon_by_iid(view, action.iid)
        if holder is None:
            return _GENERIC_ABILITY_VALUE
        effect = self._manual_effect(holder.current.card)
        if effect is None:
            return _GENERIC_ABILITY_VALUE
        if _is_cycle_discard_draw(effect):
            return _CYCLE_ABILITY_VALUE if self._cycle_allowed(view) else 0.0
        node = _damage_attach_node(effect)
        if node is not None:
            return self._attach_damage_value(view, holder, node)
        return _GENERIC_ABILITY_VALUE

    def _manual_effect(self, card: CardDef) -> Effect | None:
        if self.card_effects is None:
            return None
        doc = doc_for(self.card_effects, card)
        if doc is None:
            return None
        return next((e for e in doc.effects if e.trigger == "ability_manual"), None)

    def _keep_score(self, card: CardInstance) -> float:
        """弃牌代价：能量最便宜，训练家次之，宝可梦走通用战力分。"""
        if card.card.supertype == Supertype.ENERGY:
            return _ENERGY_KEEP_SCORE
        if card.card.supertype == Supertype.TRAINER:
            return _TRAINER_KEEP_SCORE
        return pokemon_score(card, self.params)

    def _cycle_allowed(self, view: VisibleGameState) -> bool:
        """D-077-1：牌库厚、手牌还没够用、且有垫牌可弃。"""
        if view.own.deck_count <= self.params.ability_cycle_deck_floor:
            return False
        if len(view.own.hand) > self.params.ability_cycle_hand_max:
            return False
        if not view.own.hand:
            return False
        worst = min(self._keep_score(c) for c in view.own.hand)
        return worst <= self.params.ability_cycle_discard_ceiling

    def _attach_damage_value(
        self, view: VisibleGameState, holder: InPlayPokemon, node: ActionNode,
    ) -> float:
        """D-077-2：有「放上指示物仍活着、且能量推进未付清招式」的目标才有价值。"""
        add = _energy_symbol(node)
        active_iid = view.own.active.current.iid if view.own.active else None
        best = 0.0
        for mon in _attach_targets(view, holder, node):
            role = _mon_energy_role(mon, add)
            if role == 2:
                continue
            value = _ATTACH_ENABLE_VALUE if role == 0 else _ATTACH_PROGRESS_VALUE
            if mon.current.iid == active_iid:
                value += _ACTIVE_ATTACH_BONUS
            best = max(best, value)
        return best

    def _damage_attach_choice_node(self, view: VisibleGameState) -> ActionNode | None:
        """挂起帧正落在附伤类的目标步时返回该节点，否则 None。"""
        if not self.params.ability_quality_gate or self.card_effects is None:
            return None
        pc = view.pending_choice
        if pc is None or pc.step_phase == "cost":
            return None
        if pc.pool not in ("own_pokemon_in_play", "own_bench"):
            return None
        doc = doc_for(self.card_effects, pc.source.card)
        if doc is None or not (0 <= pc.effect_index < len(doc.effects)):
            return None
        steps = flatten_steps(doc.effects[pc.effect_index])
        if not (0 <= pc.cursor < len(steps)):
            return None
        node = steps[pc.cursor][1]
        if _positive_int(node.args.get("damage_counters", 0)) is None:
            return None
        if node.action != "attach_energy" or node.selector != "own_discard":
            return None
        return node

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
            # 与引擎枚举同一份授予招式（含卡面为空时的 grant_attack 合成）
            tool_attacks = list(resolve_tool_attacks(
                active.attached_tool, self.card_effects,
            ))
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
