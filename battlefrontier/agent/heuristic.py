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

from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import _energy_satisfied
from battlefrontier.engine.state import (
    CardInstance,
    InPlayPokemon,
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
    """通用启发式 Agent：只读 VisibleGameState，决策确定（无随机源）。"""

    def __init__(self, params: HeuristicParams | None = None) -> None:
        self.params = params or HeuristicParams()

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

        return min(acts, key=lambda a: (-score(a), a.choices))

    # ── 主阶段行动排序 ──────────────────────────────────

    def _decide_main(self, view: VisibleGameState, by_kind: dict[str, list[Action]]) -> Action:
        hand = {c.iid: c for c in view.own.hand}
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
            if items:
                return min(items, key=lambda a: a.iid)
        if self.params.play_supporters:
            supporters = [a for a in by_kind.get("play_trainer", [])
                          if hand[a.iid].card.trainer_subtype == "支援者"]
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

    def _pick_energy_attach(self, view: VisibleGameState, acts: list[Action]) -> Action | None:
        """能量目标：仍有付不起的招式才补能（全就绪则不浪费每回合 1 次的附着）。

        战斗场未就绪优先补给；否则补给备战区未就绪最高分者；全都就绪返回 None 跳过。
        """

        def needs_energy(poke: InPlayPokemon) -> bool:
            return any(
                not _energy_satisfied(poke.attached_energy, atk.cost)
                for atk in poke.current.card.attacks
            )

        active = view.own.active
        if active is not None and needs_energy(active):
            target_iid = active.current.iid
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

    def _attack_damage_table(self, view: VisibleGameState) -> list[int]:
        """各招式（含道具授予招式，core.py 同序）对对手战斗场的有效伤害。

        弱点 ×2 / 抗性 -30（rules-manual §6）；纯效果招式记 0，不参与斩杀判定。
        """
        active = view.own.active
        opp = view.opponent.active
        assert active is not None
        attacks = list(active.current.card.attacks)
        if active.attached_tool is not None:
            attacks += active.attached_tool.card.attacks
        table: list[int] = []
        for atk in attacks:
            dmg = atk.damage
            if dmg is None:
                table.append(0)
                continue
            if opp is not None:
                own_type = active.current.card.energy_type
                if opp.current.card.weakness and own_type == opp.current.card.weakness:
                    dmg *= 2
                if opp.current.card.resistance and own_type == opp.current.card.resistance:
                    dmg = max(0, dmg - RESISTANCE_AMOUNT)
            table.append(dmg)
        return table

    def _lethal_attack(self, view: VisibleGameState, acts: list[Action]) -> Action | None:
        """斩杀检测：能直接昏厥对手战斗场的招式，取有效伤害最高者（tie 取下标小者）。"""
        opp = view.opponent.active
        if opp is None:
            return None
        table = self._attack_damage_table(view)
        remaining = (opp.current.card.hp or 0) - opp.damage
        lethal = [a for a in acts if table[a.attack_index] >= remaining]
        if not lethal:
            return None
        return max(lethal, key=lambda a: (table[a.attack_index], -a.attack_index))

    def _pick_attack(self, view: VisibleGameState, acts: list[Action]) -> Action:
        """无斩杀时取有效伤害最高的招式（tie 取下标小者）。"""
        table = self._attack_damage_table(view)
        return max(acts, key=lambda a: (table[a.attack_index], -a.attack_index))
