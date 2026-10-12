"""坐标下降搜索器（D-T3，task 045）+ 调优执行编排（``run_tune``）。

坐标下降：从默认参数出发逐维试全部网格点，该维最优点 Δfitness 严格大于噪声
门槛才采纳；单维全不采纳则保持原值；整轮无改进即停；最多 3 轮。副产品 =
逐维敏感性记录（``trials``：每维各点 Δfitness），直接进 task 046 敏感性报告。

搜索循环 ``coordinate_descent`` 为纯逻辑（evaluate 注入，不打真局也可单测）；
同参数重评同分（CRN 种子钉死）保证搜索过程本身确定。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.tune.defn import TuneDef
from battlefrontier.tune.fitness import (
    PairSplit,
    execute_plan,
    prepare_pairs,
    select_pairs,
    split_pairs,
)
from battlefrontier.tune.space import ParamDim, default_vector, search_space
from battlefrontier.tune.trajectory import TrajectoryWriter, trajectory_row

__all__ = ["DimTrial", "SearchResult", "coordinate_descent", "run_tune"]


@dataclass(frozen=True)
class DimTrial:
    """一次网格点试投（敏感性记录单元）：delta = 相对采纳前当前 fitness 的变化。"""

    round: int
    dim: str
    value: float | int
    fitness: float
    delta: float
    adopted: bool


@dataclass(frozen=True)
class SearchResult:
    best_vector: dict[str, float | int]
    best_fitness: float
    baseline_fitness: float
    rounds_run: int
    stop_reason: str          # "no_improvement" / "max_rounds"
    n_evaluations: int        # 含基线评估
    trials: tuple[DimTrial, ...]


def coordinate_descent(evaluate: Callable[[dict[str, float | int]], float],
                       *, space: tuple[ParamDim, ...],
                       start: dict[str, float | int],
                       noise_threshold: float,
                       max_rounds: int) -> SearchResult:
    """坐标下降主循环。evaluate = 参数向量 → fitness（须确定性：同向量同分）。"""
    names = {d.name for d in space}
    missing = names - set(start)
    unknown = set(start) - names
    if missing:
        raise ValueError(f"起始向量缺维（不猜）: {sorted(missing)}")
    if unknown:
        raise ValueError(f"起始向量含未知维（不猜）: {sorted(unknown)}")

    current = dict(start)
    current_fitness = evaluate(dict(current))
    baseline_fitness = current_fitness
    n_evaluations = 1
    trials: list[DimTrial] = []
    rounds_run = 0
    stop_reason = "max_rounds"

    for round_no in range(1, max_rounds + 1):
        rounds_run = round_no
        improved = False
        for dim in space:
            # 当前值不重复评估（默认值不入网格；已采纳的新值同样跳过）
            points = [p for p in dim.grid if p != current[dim.name]]
            scored: list[tuple[float, float | int]] = []
            pending: list[DimTrial] = []
            for point in points:
                vector = dict(current)
                vector[dim.name] = point
                fitness = evaluate(vector)
                n_evaluations += 1
                scored.append((fitness, point))
                pending.append(DimTrial(round=round_no, dim=dim.name, value=point,
                                        fitness=fitness,
                                        delta=fitness - current_fitness,
                                        adopted=False))
            # 采纳该维最优点（grid 序首个最优，确定性 tie-break）——Δ 严格大于
            # 噪声门槛才采纳（D-T2 噪声纪律）；全不采纳则保持原值
            best_fitness, best_point = scored[0]
            for fitness, point in scored[1:]:
                if fitness > best_fitness:
                    best_fitness, best_point = fitness, point
            if best_fitness - current_fitness > noise_threshold:
                adopted_trial = DimTrial(round=round_no, dim=dim.name,
                                         value=best_point, fitness=best_fitness,
                                         delta=best_fitness - current_fitness,
                                         adopted=True)
                pending = [adopted_trial if t.value == best_point else t
                           for t in pending]
                current[dim.name] = best_point
                current_fitness = best_fitness
                improved = True
            trials.extend(pending)
        if not improved:
            stop_reason = "no_improvement"
            break

    return SearchResult(best_vector=current, best_fitness=current_fitness,
                        baseline_fitness=baseline_fitness, rounds_run=rounds_run,
                        stop_reason=stop_reason, n_evaluations=n_evaluations,
                        trials=tuple(trials))


# ── 调优执行编排（CLI 入口）───────────────────────────────

def run_tune(defn: TuneDef, db_path: str, *,
             workers: int = 1,
             cards_dir: str | Path = "cards",
             output_path: str | Path,
             progress: Callable[[str], None] | None = None) -> tuple[SearchResult, PairSplit]:
    """装载卡池与卡组 → 划分/子集 → 坐标下降（每次评估写一行轨迹 JSONL）。

    返回 (搜索结果, 配对划分)；holdout 复评属 task 046，这里只跑训练集。
    """
    from battlefrontier.data.pool import load_target_pool

    pool = load_target_pool(defn.pool)
    if defn.pairs is not None:
        split = select_pairs(pool, defn.pairs)
    else:
        split = split_pairs(pool, defn.split_seed, defn.holdout_size)
    prepared = prepare_pairs(split.train, db_path, cards_dir)
    for pp in prepared:
        for w in pp.warnings:
            if progress is not None:
                progress(f"[装载告警] [{pp.assignment.archetype_a}×"
                         f"{pp.assignment.archetype_b}] {w}")

    writer = TrajectoryWriter(output_path)
    counter = {"n": 0}
    try:
        def evaluate(vector: dict[str, float | int]) -> float:
            result = execute_plan(prepared, vector, defn.games_per_pair,
                                  workers=workers)
            writer.append(trajectory_row(counter["n"], result))
            counter["n"] += 1
            if progress is not None:
                progress(f"评估 #{counter['n'] - 1}: fitness={result.fitness:.4f}"
                         f"（{wall_fmt(result.wall_seconds)}）")
            return result.fitness

        result = coordinate_descent(evaluate, space=search_space(),
                                    start=default_vector(),
                                    noise_threshold=defn.noise_threshold,
                                    max_rounds=defn.max_rounds)
    finally:
        writer.close()
    return result, split


def wall_fmt(seconds: float) -> str:
    """墙钟秒 → 短可读串（CLI 进度行用）。"""
    return f"{seconds:.1f}s" if seconds < 60 else f"{seconds / 60:.1f}min"
