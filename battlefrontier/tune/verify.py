"""top-3 复评 + 双门槛 holdout 验证 + 敏感性报告（task 046 WP1，D-046-1/2/4）。

- **轨迹重建式验证（D-046-2）**：``reconstruct_search`` 从轨迹 JSONL 行逐行重建
  坐标下降搜索过程，内嵌采纳规则 / 扫维顺序 / 网格点序列一致性校验——重建不出
  即轨迹被篡改或损坏，显式报错不猜（不新增 summary 文件，轨迹 JSONL 维持唯一
  锚点 D-T4）。
- **双门槛（D-046-1）**：候选采纳回写须同时 ①复评训练集胜率 > 0.5（严格）
  ②holdout 集胜率 ≥ 0.5（含平）；过线者中取 holdout 最高（tie → 训练 → 轨迹
  先见序）；零过线结论「默认参数即局部最优」，如实落账不强行回写。
- 复评跑局复用 ``fitness.execute_plan``（CRN 种子派生不变；games 100→500 为
  区间前缀扩展，D-046-4）。``execute`` 可注入（测试 stub，默认真跑）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from battlefrontier.tune.fitness import EvalResult, PreparedPair, execute_plan
from battlefrontier.tune.search import DimTrial
from battlefrontier.tune.space import ParamDim, search_space

__all__ = [
    "Candidate",
    "CandidateEval",
    "FinalVerdict",
    "ReconstructedSearch",
    "SensitivityRow",
    "VerifyResult",
    "format_verify",
    "gate_verdict",
    "reconstruct_search",
    "run_verify",
    "select_final",
    "sensitivity_rows",
    "top_candidates",
    "vector_diff",
    "verify_projection",
]


@dataclass(frozen=True)
class ReconstructedSearch:
    """轨迹重建结果：与 SearchResult 同构（无 stop_reason）+ 搜索空间（敏感性用）。"""

    baseline_vector: dict[str, float | int]
    baseline_fitness: float
    best_vector: dict[str, float | int]
    best_fitness: float
    trials: tuple[DimTrial, ...]
    n_evaluations: int        # 含基线评估
    rounds_run: int
    space: tuple[ParamDim, ...]


@dataclass(frozen=True)
class Candidate:
    """top-k 候选：采纳路径 waypoint（adopted trial 结算后的 current 快照）。"""

    vector: dict[str, float | int]
    search_fitness: float     # 搜索期（粗扫）fitness，非复评胜率


@dataclass(frozen=True)
class CandidateEval:
    """候选 + 复评结果（D-046-4：训练/holdout 各 games 局/对）。"""

    candidate_id: int          # top_candidates 输出序（1 起）
    vector: dict[str, float | int]
    search_fitness: float
    train_winrate: float
    holdout_winrate: float
    passed: bool               # gate_verdict 结果


@dataclass(frozen=True)
class FinalVerdict:
    """最终判定：final=None = 默认参数即局部最优（零过线，如实落账）。"""

    final: CandidateEval | None
    reason: str
    passed: tuple[CandidateEval, ...]


@dataclass(frozen=True)
class SensitivityRow:
    """逐维逐网格值聚合：最佳 Δfitness / 试投次数 / 出现轮次（从未试投 best_delta=None）。"""

    dim: str
    value: float | int
    best_delta: float | None
    n_trials: int
    rounds: tuple[int, ...]


@dataclass(frozen=True)
class VerifyResult:
    candidates: tuple[CandidateEval, ...]
    verdict: FinalVerdict
    recon: ReconstructedSearch
    games: int
    noise_threshold: float


# ── 轨迹重建（含完整性校验，D-046-2）────────────────────────

def reconstruct_search(rows: Sequence[dict], noise_threshold: float,
                       space: tuple[ParamDim, ...] = search_space()
                       ) -> ReconstructedSearch:
    """从轨迹 JSONL 行重建坐标下降（行为严格对齐 search.coordinate_descent）。

    校验（任何矛盾显式 ValueError 带行号，不猜）：基线/试投行键集合 = 空间维；
    每行与当前向量差异维数恰为 1；第 i 个 sweep（0 起）试投维 = space[i % N].name；
    试投值序列 = 该维 grid 去掉当前值（grid 序，漏点/重复/离网即矛盾）；
    sweep 总数须为整轮（坐标下降每轮扫完全部 N 维才停）。
    采纳规则：sweep 内最优试投（严格更大才替换，保持行序首个最优）的
    score - cur > noise_threshold 才采纳。
    """
    if not rows:
        raise ValueError("轨迹为空（不猜：无基线评估行）")
    n_dims = len(space)
    names = {d.name for d in space}

    def check_keys(vector: dict, row_no: int) -> None:
        missing = names - set(vector)
        unknown = set(vector) - names
        if missing:
            raise ValueError(
                f"轨迹第 {row_no} 行参数向量缺维（不猜）: {sorted(missing)}")
        if unknown:
            raise ValueError(
                f"轨迹第 {row_no} 行参数向量含未知维（不猜）: {sorted(unknown)}")

    for i, row in enumerate(rows):
        if not isinstance(row, dict) or "vector" not in row or "score" not in row:
            raise ValueError(f"轨迹第 {i} 行缺 vector/score 键（不猜）")

    check_keys(rows[0]["vector"], 0)
    current = dict(rows[0]["vector"])
    cur = float(rows[0]["score"])
    baseline_fitness = cur

    trials: list[DimTrial] = []
    sweep_index = -1
    pending_dim: ParamDim | None = None
    pending: list[tuple[float | int, float]] = []   # (试投值, score)，行序

    def settle() -> None:
        """sweep 结束（换维或行尽）结算：序列完整性校验 + 采纳规则。"""
        nonlocal cur
        if pending_dim is None:
            return
        expected = [p for p in pending_dim.grid if p != current[pending_dim.name]]
        values = [v for v, _ in pending]
        if values != expected:
            raise ValueError(
                f"sweep {sweep_index}（维 '{pending_dim.name}'）试投序列与坐标下降"
                f"应试点序列不符（漏点/重复/乱序，不猜）：实际 {values}，"
                f"期望 {expected}")
        best_value, best_score = pending[0]
        for value, score in pending[1:]:
            if score > best_score:          # 严格更大才替换，保持行序首个最优
                best_value, best_score = value, score
        adopt = best_score - cur > noise_threshold
        for value, score in pending:
            trials.append(DimTrial(
                round=sweep_index // n_dims + 1, dim=pending_dim.name, value=value,
                fitness=score, delta=score - cur, adopted=adopt and value == best_value))
        if adopt:
            current[pending_dim.name] = best_value
            cur = best_score

    for i, row in enumerate(rows[1:], start=1):
        vector = row["vector"]
        score = float(row["score"])
        check_keys(vector, i)
        if pending_dim is not None:
            diff = [k for k in current if vector[k] != current[k]]
            if diff == [pending_dim.name]:
                # 当前 sweep 续行（sweep 内 current 不变，差异恒为试投维）
                value = vector[pending_dim.name]
                if value not in pending_dim.grid:
                    raise ValueError(
                        f"轨迹第 {i} 行试投值 {value!r} 不在维 '{pending_dim.name}'"
                        f" 网格 {list(pending_dim.grid)}（不猜）")
                pending.append((value, score))
                continue
        # 换维（或首个试投行）→ 先结算上一 sweep（采纳生效），再校验本行
        settle()
        sweep_index += 1
        pending_dim = space[sweep_index % n_dims]
        diff = [k for k in current if vector[k] != current[k]]
        if len(diff) != 1:
            raise ValueError(
                f"轨迹第 {i} 行与当前向量差异维数 = {len(diff)}（须恰为 1，不猜）")
        if diff[0] != pending_dim.name:
            raise ValueError(
                f"轨迹第 {i} 行试投维 '{diff[0]}' 与坐标下降扫维顺序不符"
                f"（sweep {sweep_index} 期望 '{pending_dim.name}'，不猜）")
        value = vector[diff[0]]
        if value not in pending_dim.grid:
            raise ValueError(
                f"轨迹第 {i} 行试投值 {value!r} 不在维 '{pending_dim.name}' 网格"
                f" {list(pending_dim.grid)}（不猜）")
        pending = [(value, score)]
    settle()

    n_sweeps = sweep_index + 1
    if n_sweeps % n_dims != 0:
        raise ValueError(
            f"轨迹在 sweep {n_sweeps - 1} 后截断（{n_sweeps} 个 sweep 非完整轮——"
            f"坐标下降每轮须扫完全部 {n_dims} 维，不猜）")
    return ReconstructedSearch(
        baseline_vector=dict(rows[0]["vector"]), baseline_fitness=baseline_fitness,
        best_vector=current, best_fitness=cur, trials=tuple(trials),
        n_evaluations=len(rows), rounds_run=n_sweeps // n_dims, space=space)


# ── top-k 候选（采纳路径 waypoint）───────────────────────────

def top_candidates(recon: ReconstructedSearch, k: int = 3) -> list[Candidate]:
    """采纳路径 waypoint 按搜索 fitness 降序取前 k（tie → 先见序；同向量去重保先见）。"""
    current = dict(recon.baseline_vector)
    seen: set[tuple[tuple[str, float | int], ...]] = set()
    waypoints: list[Candidate] = []
    for t in recon.trials:
        if not t.adopted:
            continue
        current[t.dim] = t.value
        key = tuple(sorted(current.items()))
        if key in seen:
            continue
        seen.add(key)
        waypoints.append(Candidate(vector=dict(current), search_fitness=t.fitness))
    waypoints.sort(key=lambda c: -c.search_fitness)   # 稳定排序：tie 保持先见序
    return waypoints[:k]


# ── 双门槛与最终选择（D-046-1）───────────────────────────────

def gate_verdict(train_winrate: float, holdout_winrate: float) -> bool:
    """D-046-1 双门槛：复评训练集胜率 > 0.5（严格）且 holdout 胜率 ≥ 0.5（含平）。"""
    return train_winrate > 0.5 and holdout_winrate >= 0.5


def select_final(candidates: Sequence[CandidateEval]) -> FinalVerdict:
    """过线者中选 holdout 最高（tie → 训练高 → 先见序）；零过线 = 默认参数即局部最优。"""
    passed = tuple(c for c in candidates
                   if gate_verdict(c.train_winrate, c.holdout_winrate))
    if not passed:
        return FinalVerdict(
            final=None, passed=(),
            reason="默认参数即局部最优（无候选过双门槛），如实落账不强行回写")
    best = passed[0]
    for c in passed[1:]:
        if (c.holdout_winrate, c.train_winrate) > (best.holdout_winrate,
                                                   best.train_winrate):
            best = c
    return FinalVerdict(
        final=best, passed=passed,
        reason=f"采纳候选 #{best.candidate_id}（holdout {best.holdout_winrate:.4f}"
               f" / 训练 {best.train_winrate:.4f}）")


# ── 敏感性聚合 ─────────────────────────────────────────────

def sensitivity_rows(recon: ReconstructedSearch) -> list[SensitivityRow]:
    """逐维聚合 trials：每维每网格值最佳 Δfitness / 试投次数 / 出现轮次。
    输出序 = space 维序 → grid 序（确定性）。"""
    by_dim_value: dict[tuple[str, float | int], list[DimTrial]] = {}
    for t in recon.trials:
        by_dim_value.setdefault((t.dim, t.value), []).append(t)
    rows: list[SensitivityRow] = []
    for dim in recon.space:
        for value in dim.grid:
            ts = by_dim_value.get((dim.name, value), [])
            rows.append(SensitivityRow(
                dim=dim.name, value=value,
                best_delta=max((t.delta for t in ts), default=None),
                n_trials=len(ts),
                rounds=tuple(sorted({t.round for t in ts}))))
    return rows


# ── 编排 ─────────────────────────────────────────────────

def run_verify(*, rows: Sequence[dict], noise_threshold: float,
               train_prepared: Sequence[PreparedPair],
               holdout_prepared: Sequence[PreparedPair],
               games: int,
               execute: Callable[..., EvalResult] | None = None,
               workers: int = 1,
               progress: Callable[[str], None] | None = None) -> VerifyResult:
    """重建 → top-3 → 各候选训练/holdout 复评 → 双门槛 + 最终选择。

    holdout 为空显式报错（不猜——D-046-1 双门槛无从谈起）。
    execute 缺省 = fitness.execute_plan（CRN 种子派生不变，D-046-4）。
    """
    if execute is None:
        execute = execute_plan
    if not holdout_prepared:
        raise ValueError(
            "holdout 配对集为空（不猜）：D-046-1 双门槛需要 holdout 复评——"
            "pairs 显式子集模式（holdout 空）的调优定义不可 tune-verify")
    recon = reconstruct_search(rows, noise_threshold)
    evaluated: list[CandidateEval] = []
    for cid, cand in enumerate(top_candidates(recon, k=3), start=1):
        train_res = execute(train_prepared, cand.vector, games, workers=workers)
        holdout_res = execute(holdout_prepared, cand.vector, games, workers=workers)
        evaluated.append(CandidateEval(
            candidate_id=cid, vector=dict(cand.vector),
            search_fitness=cand.search_fitness,
            train_winrate=train_res.fitness, holdout_winrate=holdout_res.fitness,
            passed=gate_verdict(train_res.fitness, holdout_res.fitness)))
        if progress is not None:
            progress(f"候选 #{cid} 复评：训练 {train_res.fitness:.4f} / "
                     f"holdout {holdout_res.fitness:.4f}（{games} 局/对）")
    return VerifyResult(candidates=tuple(evaluated),
                        verdict=select_final(evaluated), recon=recon,
                        games=games, noise_threshold=noise_threshold)


# ── 报告（文本 + JSON 投影）──────────────────────────────────

def vector_diff(vector: dict[str, float | int],
                baseline: dict[str, float | int]) -> dict[str, tuple[float | int, float | int]]:
    """与基线向量的差异维（键序 = baseline 序 = space 维序，确定性）。"""
    return {k: (baseline[k], vector[k]) for k in baseline if vector[k] != baseline[k]}


def _diff_text(vector: dict[str, float | int],
               baseline: dict[str, float | int]) -> str:
    return "、".join(f"{k} {old}→{new}"
                     for k, (old, new) in vector_diff(vector, baseline).items())


def format_verify(result: VerifyResult, *, name: str) -> str:
    """候选明细 → 最终判定 → 敏感性表（CLI 打印）。"""
    recon = result.recon
    lines = [
        (f"调优验证「{name}」：{len(result.candidates)} 个候选 × 复评 {result.games} 局/对"
         f"（双门槛 D-046-1：训练 >0.5 且 holdout ≥0.5；"
         f"基线 fitness {recon.baseline_fitness:.4f} → 搜索最优 {recon.best_fitness:.4f}，"
         f"{recon.rounds_run} 轮 / {recon.n_evaluations} 次评估）"),
    ]
    for c in result.candidates:
        lines.append(
            f"候选 #{c.candidate_id}: diff [{_diff_text(c.vector, recon.baseline_vector)}]"
            f" ｜ 搜索 fitness {c.search_fitness:.4f} ｜ 训练 {c.train_winrate:.4f}"
            f" ｜ holdout {c.holdout_winrate:.4f} ｜ 门槛 {'过' if c.passed else '不过'}")
    if result.verdict.final is None:
        lines.append(f"最终判定：{result.verdict.reason}")
    else:
        lines.append(
            f"最终判定：{result.verdict.reason}；与默认参数 diff 全清单："
            f"[{_diff_text(result.verdict.final.vector, recon.baseline_vector)}]")
    lines.append("敏感性（逐维各网格值：最佳 Δfitness / 试投次数 / 出现轮次）：")
    rows = sensitivity_rows(recon)
    idx = 0
    for dim in recon.space:
        cells = []
        for _ in dim.grid:
            r = rows[idx]
            idx += 1
            delta = "—" if r.best_delta is None else f"{r.best_delta:+.4f}"
            rounds = ",".join(str(x) for x in r.rounds) or "—"
            cells.append(f"{r.value}: Δ{delta} (n={r.n_trials}, r{rounds})")
        lines.append(f"  {dim.name}: " + " · ".join(cells))
    return "\n".join(lines)


def verify_projection(result: VerifyResult, *, name: str, split_seed: int) -> dict:
    """VerifyResult 的可序列化投影（结果 JSON 落盘用，含 name/games/seed 锚点）。"""
    recon = result.recon
    verdict = result.verdict
    return {
        "name": name,
        "split_seed": split_seed,
        "games_per_pair": result.games,
        "noise_threshold": result.noise_threshold,
        "baseline": {"vector": recon.baseline_vector,
                     "fitness": recon.baseline_fitness},
        "best": {"vector": recon.best_vector, "fitness": recon.best_fitness},
        "n_evaluations": recon.n_evaluations,
        "rounds_run": recon.rounds_run,
        "candidates": [
            {"candidate_id": c.candidate_id, "vector": c.vector,
             "diff": {k: {"from": old, "to": new}
                      for k, (old, new)
                      in vector_diff(c.vector, recon.baseline_vector).items()},
             "search_fitness": c.search_fitness,
             "train_winrate": c.train_winrate,
             "holdout_winrate": c.holdout_winrate,
             "passed": c.passed}
            for c in result.candidates],
        "verdict": {
            "adopted": verdict.final is not None,
            "candidate_id": verdict.final.candidate_id if verdict.final else None,
            "vector": verdict.final.vector if verdict.final else None,
            "reason": verdict.reason,
        },
        "sensitivity": [
            {"dim": r.dim, "value": r.value, "best_delta": r.best_delta,
             "n_trials": r.n_trials, "rounds": list(r.rounds)}
            for r in sensitivity_rows(recon)],
    }
