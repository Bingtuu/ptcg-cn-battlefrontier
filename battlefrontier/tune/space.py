"""启发式参数搜索空间声明（D-T1，task 045）——纯数据，无行为。

10 维进搜索：8 连续权重走乘法网格（尺度无关，对正负号权重一致适用；
0 = 关闭该因子），2 整数维走枚举网格。网格点不含默认值——默认值即坐标下降
起点，不重复评估。布尔开关不进空间（M8a 后「开」均为已验证修复行为，
固定全开，见设计文档 §2；task 077 的 ability_quality_gate、task 078 的
board_quality_gate、task 079 的 energy_target_gate、task 080 的
attack_quality_gate、task 083 的 ko_prize_lookahead_gate、task 085 的
copy_conversion_gate、task 086 的 prize_race_gate、task 093 的
convert_timing_hybrid_gate 同样固定默认开，不进这 10 维）。
"""

from __future__ import annotations

from dataclasses import dataclass

from battlefrontier.agent.heuristic import HeuristicParams

__all__ = [
    "CONTINUOUS_DIMS",
    "CONTINUOUS_MULTIPLIERS",
    "INTEGER_DIMS",
    "ParamDim",
    "default_vector",
    "params_from_vector",
    "search_space",
]

# 连续维乘法网格倍率（D-T1）：{0, ×0.25, ×0.5, ×2, ×4}；×1 = 默认值本身不入格
CONTINUOUS_MULTIPLIERS: tuple[float, ...] = (0.0, 0.25, 0.5, 2.0, 4.0)

CONTINUOUS_DIMS: tuple[str, ...] = (
    "w_hp", "w_damage", "w_retreat", "w_prize_diff",
    "w_board", "w_hand", "w_energy_ready", "w_deck",
)

INTEGER_DIMS: tuple[str, ...] = ("max_bench_setup", "deck_low_threshold")

# 整数维完整枚举（含默认值；网格生成时剔除）
INTEGER_ENUM: dict[str, tuple[int, ...]] = {
    "max_bench_setup": (1, 2, 3, 4, 5),          # 1..5 步 1
    "deck_low_threshold": (0, 3, 6, 9, 12),
}


@dataclass(frozen=True)
class ParamDim:
    """单维参数：字段名 / 类别 / 默认值 / 网格点（不含默认值）。"""

    name: str
    kind: str  # "continuous" / "integer"
    default: float | int
    grid: tuple[float | int, ...]


def search_space() -> tuple[ParamDim, ...]:
    """10 维搜索空间（固定序：8 连续维 D-T1 表序 + 2 整数维）。"""
    defaults = HeuristicParams()
    dims: list[ParamDim] = []
    for name in CONTINUOUS_DIMS:
        default = getattr(defaults, name)
        grid = tuple(default * m for m in CONTINUOUS_MULTIPLIERS)
        dims.append(ParamDim(name=name, kind="continuous", default=default, grid=grid))
    for name in INTEGER_DIMS:
        default = getattr(defaults, name)
        grid = tuple(v for v in INTEGER_ENUM[name] if v != default)
        dims.append(ParamDim(name=name, kind="integer", default=default, grid=grid))
    return tuple(dims)


def default_vector() -> dict[str, float | int]:
    """搜索起点的参数向量（= HeuristicParams 全部默认值的 10 维投影）。"""
    return {dim.name: dim.default for dim in search_space()}


def params_from_vector(vector: dict[str, float | int]) -> HeuristicParams:
    """参数向量 → HeuristicParams。键集合须恰为 10 搜索维（缺/多/未知显式报错，不猜）；
    未进空间的布尔开关取默认（全开，含 ability_quality_gate / board_quality_gate /
    energy_target_gate / attack_quality_gate / ko_prize_lookahead_gate /
    copy_conversion_gate / prize_race_gate / convert_timing_hybrid_gate）。"""
    names = {dim.name for dim in search_space()}
    missing = names - set(vector)
    unknown = set(vector) - names
    if missing:
        raise ValueError(f"参数向量缺维（不猜）: {sorted(missing)}")
    if unknown:
        raise ValueError(f"参数向量含未知维（不猜）: {sorted(unknown)}")
    return HeuristicParams(**vector)
