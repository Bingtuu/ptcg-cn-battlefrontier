"""M11 学得评估器特征层（task 050 WP1，D-M11-2 特征清单 A+B 组；C 组 dsl_estimate
衍生特征顺延后续 WP）。

纯函数 `feature_vector(view) -> dict[str, float]`：零随机、零引擎调用——只读
VisibleGameState（视图天然隐藏对手手牌/牌库/奖赏内容，特征层不绕过此纪律，
对手侧只有 count/标记特征）。键序由 `FEATURE_NAMES` 钉死（训练/推理同一份
清单，模型资产锚点）。

- **A 组（五因子原值）**：heuristic.evaluate 的因子分解量原值（不带权重），
  共享 `heuristic.factor_*` 纯函数；board_score 内部宝可梦评分用默认
  HeuristicParams（w_hp=1/w_damage=5/w_retreat=-10）。
- **B 组（结构量）**：口径见各特征注释。
"""

from __future__ import annotations

from battlefrontier.agent.heuristic import (
    HeuristicParams,
    factor_board_score,
    factor_deck_diff,
    factor_energy_ready_diff,
    factor_hand_diff,
    factor_prize_diff,
)
from battlefrontier.engine.state import InPlayPokemon, VisibleGameState

__all__ = ["FEATURE_NAMES", "TURN_NORM_CAP", "feature_vector"]

# turn 归一化口径：min(turn, TURN_NORM_CAP) / TURN_NORM_CAP
# （对局回合上限 200，但绝大多数对局 50 回合内结束；截断防爆量纲）
TURN_NORM_CAP = 50

# 特征清单 v1（键序钉死——训练/推理/模型资产共用此序）：
# A 组：prize_diff / board_score_diff / hand_diff / energy_ready_diff / deck_diff
# B 组：turn_norm（min(turn,50)/50）/ 双方 bench 占用 / 双方 deck_count /
#   双方 hand 数（对手只 count）/ 竞技场在场 0-1 / 双方 active 特殊状态计数 /
#   双方场上进化阶段分布（当前形态 stage：0=basic，1=stage1，≥2 归 stage2 桶，
#   计数口径）/ face_down_pokemon（布阵阶段对手背面放置数）/ 回合规则标记
#   8 个布尔转 0-1（能量已附着/支援者已用/已撤退/竞技场已打出/竞技场已用过/
#   有登场/有进化/已用特性——后三者由 entered_play/evolved/abilities（含共享）
#   集合非空投影）。
FEATURE_NAMES: tuple[str, ...] = (
    # A 组（五因子原值）
    "prize_diff",
    "board_score_diff",
    "hand_diff",
    "energy_ready_diff",
    "deck_diff",
    # B 组（结构量）
    "turn_norm",
    "own_bench_count",
    "opp_bench_count",
    "own_deck_count",
    "opp_deck_count",
    "own_hand_count",
    "opp_hand_count",
    "stadium_in_play",
    "own_active_conditions_count",
    "opp_active_conditions_count",
    "own_stage0_count",
    "own_stage1_count",
    "own_stage2_count",
    "opp_stage0_count",
    "opp_stage1_count",
    "opp_stage2_count",
    "face_down_pokemon",
    "flag_energy_attached",
    "flag_supporter_played",
    "flag_retreated",
    "flag_stadium_played",
    "flag_stadium_used",
    "flag_entered_play",
    "flag_evolved",
    "flag_ability_used",
)


def _in_play(active: InPlayPokemon | None, bench: tuple[InPlayPokemon, ...]) -> list[InPlayPokemon]:
    return ([active] if active else []) + list(bench)


def _stage_counts(pokes: list[InPlayPokemon]) -> tuple[float, float, float]:
    """当前形态 stage 分布计数：0 = basic / 1 = stage1 / ≥2 归 stage2 桶。"""
    basic_n = sum(1 for p in pokes if p.current.card.stage <= 0)
    stage1_n = sum(1 for p in pokes if p.current.card.stage == 1)
    stage2_n = sum(1 for p in pokes if p.current.card.stage >= 2)
    return float(basic_n), float(stage1_n), float(stage2_n)


def feature_vector(view: VisibleGameState) -> dict[str, float]:
    """可见视图 → 特征向量（键序 = FEATURE_NAMES；全字段 float，全确定）。"""
    own, opp = view.own, view.opponent
    own_in = _in_play(own.active, own.bench)
    opp_in = _in_play(opp.active, opp.bench)
    own_s0, own_s1, own_s2 = _stage_counts(own_in)
    opp_s0, opp_s1, opp_s2 = _stage_counts(opp_in)
    return {
        # A 组（五因子原值，不带权重；board_score 内部用默认 HeuristicParams）
        "prize_diff": float(factor_prize_diff(view)),
        "board_score_diff": float(factor_board_score(view, HeuristicParams())),
        "hand_diff": float(factor_hand_diff(view)),
        "energy_ready_diff": float(factor_energy_ready_diff(view)),
        "deck_diff": float(factor_deck_diff(view)),
        # B 组（结构量）
        "turn_norm": float(min(view.turn, TURN_NORM_CAP)) / TURN_NORM_CAP,
        "own_bench_count": float(len(own.bench)),
        "opp_bench_count": float(len(opp.bench)),
        "own_deck_count": float(own.deck_count),
        "opp_deck_count": float(opp.deck_count),
        "own_hand_count": float(len(own.hand)),
        "opp_hand_count": float(opp.hand_count),
        "stadium_in_play": float(view.stadium is not None),
        "own_active_conditions_count": (
            float(len(own.active.conditions)) if own.active else 0.0),
        "opp_active_conditions_count": (
            float(len(opp.active.conditions)) if opp.active else 0.0),
        "own_stage0_count": own_s0,
        "own_stage1_count": own_s1,
        "own_stage2_count": own_s2,
        "opp_stage0_count": opp_s0,
        "opp_stage1_count": opp_s1,
        "opp_stage2_count": opp_s2,
        "face_down_pokemon": float(opp.face_down_pokemon),
        "flag_energy_attached": float(own.energy_attached_this_turn),
        "flag_supporter_played": float(own.supporter_played_this_turn),
        "flag_retreated": float(own.retreated_this_turn),
        "flag_stadium_played": float(own.stadium_played_this_turn),
        "flag_stadium_used": float(own.stadium_used_this_turn),
        "flag_entered_play": float(bool(own.entered_play_this_turn)),
        "flag_evolved": float(bool(own.evolved_this_turn)),
        "flag_ability_used": float(
            bool(own.abilities_used_this_turn or own.shared_abilities_used_this_turn)),
    }
