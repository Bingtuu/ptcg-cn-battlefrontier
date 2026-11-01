from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from dataclasses import dataclass

from battlefrontier.report.winrate import Z_95
from battlefrontier.runner.results_db import ResultsDB


@dataclass(frozen=True)
class PairedImprovement:
    n: int
    heuristic_wr: float
    mcts_wr: float
    real_wr: float
    effect: float
    ci_low: float
    ci_high: float

    @property
    def significant_improvement(self) -> bool:
        return self.ci_low > 0

    @property
    def significant_deterioration(self) -> bool:
        return self.ci_high < 0


def _decided_games(db: ResultsDB, experiment_id: int) -> dict[int, int]:
    rows = db.games(experiment_id)
    decided: dict[int, int] = {}
    for row in rows:
        seed = int(row["seed"])
        if seed in decided:
            raise ValueError(f"实验 #{experiment_id} 种子 {seed} 重复")
        if row["error"] is not None:
            raise ValueError(f"实验 #{experiment_id} 种子 {seed} 存在失败局")
        if row["is_draw"] or row["winner"] not in (0, 1):
            raise ValueError(f"实验 #{experiment_id} 种子 {seed} 存在平局或非决定局")
        decided[seed] = int(row["winner"])
    return decided


def paired_outcomes(
    heuristic_db: ResultsDB,
    heuristic_id: int,
    mcts_db: ResultsDB,
    mcts_id: int,
) -> tuple[tuple[int, int, int], ...]:
    heuristic = _decided_games(heuristic_db, heuristic_id)
    mcts = _decided_games(mcts_db, mcts_id)
    if not heuristic or set(heuristic) != set(mcts):
        raise ValueError("CRN 实验种子集合不一致或为空")
    return tuple((seed, heuristic[seed], mcts[seed]) for seed in sorted(heuristic))


def paired_improvement(
    outcomes: Iterable[tuple[int, int, int]], *, real_wr: float
) -> PairedImprovement:
    rows = tuple(outcomes)
    if len(rows) < 2:
        raise ValueError("CRN 至少需要两局")
    if len({seed for seed, _, _ in rows}) != len(rows):
        raise ValueError("CRN 种子重复")
    if not 0 <= real_wr <= 1:
        raise ValueError("real_wr 必须在 [0,1] 内")
    if any(heuristic not in (0, 1) or mcts not in (0, 1) for _, heuristic, mcts in rows):
        raise ValueError("CRN 只接受决定局胜负 0/1")

    n = len(rows)
    heuristic_wr = sum(1 for _, heuristic, _ in rows if heuristic == 0) / n
    mcts_wr = sum(1 for _, _, mcts in rows if mcts == 0) / n
    direction = (real_wr > heuristic_wr) - (real_wr < heuristic_wr)
    if direction == 0:
        raise ValueError("启发式与真实胜率相等，改善方向不可用")
    effects = [
        direction * ((mcts == 0) - (heuristic == 0))
        for _, heuristic, mcts in rows
    ]
    effect = statistics.mean(effects)
    se = statistics.stdev(effects) / math.sqrt(n)
    margin = Z_95 * se
    return PairedImprovement(
        n=n,
        heuristic_wr=heuristic_wr,
        mcts_wr=mcts_wr,
        real_wr=real_wr,
        effect=effect,
        ci_low=effect - margin,
        ci_high=effect + margin,
    )
