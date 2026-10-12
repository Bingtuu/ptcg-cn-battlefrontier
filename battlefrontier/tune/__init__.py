"""启发式参数自调优（task 045，设计：docs/superpowers/specs/2026-10-11-heuristic-tuning-design.md）。

space（参数空间）/ fitness（评估协议）/ search（坐标下降 + 编排）/
trajectory（JSONL 轨迹）/ defn（TuneDef 强校验）。
"""

from battlefrontier.tune.defn import TuneDef, load_tune
from battlefrontier.tune.fitness import (
    EvalResult,
    PairAssignment,
    PairSplit,
    aggregate,
    execute_plan,
    pair_seed_range,
    prepare_pairs,
    select_pairs,
    split_pairs,
)
from battlefrontier.tune.search import SearchResult, coordinate_descent, run_tune
from battlefrontier.tune.space import default_vector, params_from_vector, search_space
from battlefrontier.tune.trajectory import TrajectoryWriter, read_trajectory

__all__ = [
    "EvalResult",
    "PairAssignment",
    "PairSplit",
    "SearchResult",
    "TrajectoryWriter",
    "TuneDef",
    "aggregate",
    "coordinate_descent",
    "default_vector",
    "execute_plan",
    "load_tune",
    "pair_seed_range",
    "params_from_vector",
    "prepare_pairs",
    "read_trajectory",
    "run_tune",
    "search_space",
    "select_pairs",
    "split_pairs",
]
