"""M11 数据产线（task 050 WP1，D-M11-1）：配对 × 种子区间批量跑局并落特征 JSONL。

- **worker** ``_run_one_collect``：独立模块级入口（不动 ``_run_one_experiment``），
  payload（deck_a/deck_b/card_effects/seed/pair_index）→ play_game（双侧默认
  HeuristicAgent + FeatureCollector）→ (seed, pair_index, rows, error)；
  失败局 rows=None + 错误文本（对齐 fitness._to_outcome 失败局口径：剔除、计数上报）。
- **批量驱动** ``run_collect``：配对装载复用 ``tune.fitness.prepare_pairs``；
  种子协议 = matrix 惯例（pair i → [seed_start + i×games_per_pair, +games_per_pair)，
  不用 tune 的 CRN 区间——其 STRIDE=1000 放不下 2800 局/对）；spawn 多进程
  imap 保序（workers>1）与串行同一条 worker 路径，结果逐行一致。
- **落盘**：按配对聚合写 ``<out>/pair-<index>-<名A>x<名B>.jsonl``（文件名剔除
  路径非法字符），逐行 JSON（UTF-8 / ensure_ascii=False / sort_keys，复用
  tune.trajectory.TrajectoryWriter 惯例）；行内零非确定量（无墙钟/无时间戳）。
  数据不落结果库（D-T4 先例：JSONL 侧文件即锚点）。
"""

from __future__ import annotations

import multiprocessing as mp
import re
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.agent.collect import FeatureCollector
from battlefrontier.agent.heuristic import HeuristicAgent
from battlefrontier.data.pool import TargetPool
from battlefrontier.dsl import CardLibrary
from battlefrontier.dsl.schema import CardEffectDoc
from battlefrontier.engine.state import CardDef
from battlefrontier.runner.experiment import _unique_docs
from battlefrontier.runner.play import play_game
from battlefrontier.tune.fitness import PairAssignment, PreparedPair, prepare_pairs
from battlefrontier.tune.trajectory import TrajectoryWriter

__all__ = [
    "PairCollectSummary",
    "collect_seed_range",
    "pair_filename",
    "pool_assignments",
    "run_collect",
]

_PATH_ILLEGAL = re.compile(r'[\\/:*?"<>|\s]+')


def collect_seed_range(pair_index: int, games_per_pair: int, seed_start: int) -> range:
    """pair i → [seed_start + i×games_per_pair, +games_per_pair)（matrix 惯例）。"""
    start = seed_start + pair_index * games_per_pair
    return range(start, start + games_per_pair)


def pair_filename(pair_index: int, archetype_a: str, archetype_b: str) -> str:
    """``pair-<index>-<名A>x<名B>.jsonl``；archetype 名剔除路径非法字符与空白。"""
    safe_a = _PATH_ILLEGAL.sub("_", archetype_a)
    safe_b = _PATH_ILLEGAL.sub("_", archetype_b)
    return f"pair-{pair_index}-{safe_a}x{safe_b}.jsonl"


def pool_assignments(pool: TargetPool) -> list[PairAssignment]:
    """卡池全部无向配对（pool.matchup_pairs 序；结构同 tune.fitness._assignments）。"""
    return [
        PairAssignment(index=i, archetype_a=a.archetype, archetype_b=b.archetype,
                       deck_id_a=a.deck_id, deck_id_b=b.deck_id)
        for i, (a, b) in enumerate(pool.matchup_pairs())
    ]


def _run_one_collect(payload: dict) -> tuple[int, int, list[dict] | None, str | None]:
    """多进程 worker 入口（模块级函数，可 pickle）。失败局返回错误文本而非抛出。"""
    try:
        # worker 内重建 CardLibrary（载荷为去重后的文档列表；挂载键 = card_id）
        card_effects = CardLibrary.from_docs(
            ("<worker>", CardEffectDoc.model_validate(d))
            for d in payload["card_effects"])
        agents = [HeuristicAgent(card_effects=card_effects),
                  HeuristicAgent(card_effects=card_effects)]
        result = play_game(
            deck_a=[CardDef.model_validate(c) for c in payload["deck_a"]],
            deck_b=[CardDef.model_validate(c) for c in payload["deck_b"]],
            seed=payload["seed"],
            card_effects=card_effects,
            agents=agents,
            collector=FeatureCollector(),
        )
        rows = result.collected_rows
        assert rows is not None  # collector 非 None 则必有（可能为空列表）
        for row in rows:
            row["seed"] = payload["seed"]
            row["pair_index"] = payload["pair_index"]
        return payload["seed"], payload["pair_index"], rows, None
    except Exception as e:  # noqa: BLE001 — 不猜纪律：失败局剔除并计数，不拖垮产线
        return payload["seed"], payload["pair_index"], None, f"{type(e).__name__}: {e}"


@dataclass(frozen=True)
class PairCollectSummary:
    """单配对采集汇总：文件名 / 局数 / 数据行数 / 失败局数（剔除计数上报）。"""

    pair_index: int
    archetype_a: str
    archetype_b: str
    filename: str
    games: int
    rows: int
    failed: int


def run_collect(prepared: list[PreparedPair] | tuple[PreparedPair, ...],
                games_per_pair: int, seed_start: int,
                out_dir: str | Path, *, workers: int = 1) -> list[PairCollectSummary]:
    """全部配对 × 种子区间批量跑局并落 JSONL；返回各配对汇总。

    串行与多进程同走 ``_run_one_collect``（imap 保序回收），产物逐行一致。
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payloads: list[dict] = []
    for pp in prepared:
        card_effects = [d.model_dump(mode="json")
                        for d in _unique_docs(pp.card_effects.values())]
        deck_a = [c.model_dump(mode="json") for c in pp.deck_a]
        deck_b = [c.model_dump(mode="json") for c in pp.deck_b]
        for seed in collect_seed_range(pp.assignment.index, games_per_pair, seed_start):
            payloads.append({"deck_a": deck_a, "deck_b": deck_b,
                             "card_effects": card_effects,
                             "seed": seed, "pair_index": pp.assignment.index})

    results: list[tuple[int, int, list[dict] | None, str | None]] = []
    if workers > 1:
        ctx = mp.get_context("spawn")
        with ctx.Pool(workers) as pool:
            results.extend(pool.imap(_run_one_collect, payloads))
    else:
        for payload in payloads:
            results.append(_run_one_collect(payload))

    rows_by_pair: dict[int, list[dict]] = {pp.assignment.index: [] for pp in prepared}
    failed_by_pair: dict[int, int] = {pp.assignment.index: 0 for pp in prepared}
    for _seed, pair_index, rows, error in results:
        if error is not None:
            failed_by_pair[pair_index] += 1  # 失败局剔除（rows 整局不落盘）
        else:
            assert rows is not None
            rows_by_pair[pair_index].extend(rows)

    summaries: list[PairCollectSummary] = []
    for pp in prepared:
        a = pp.assignment
        filename = pair_filename(a.index, a.archetype_a, a.archetype_b)
        with TrajectoryWriter(out / filename) as writer:
            for row in rows_by_pair[a.index]:
                writer.append(row)
        summaries.append(PairCollectSummary(
            pair_index=a.index, archetype_a=a.archetype_a, archetype_b=a.archetype_b,
            filename=filename, games=games_per_pair,
            rows=len(rows_by_pair[a.index]), failed=failed_by_pair[a.index]))
    return summaries


def run_collect_pool(pool_path: str | Path, db_path: str | Path,
                     games_per_pair: int, seed_start: int,
                     out_dir: str | Path, *, workers: int = 1,
                     cards_dir: str | Path = "cards") -> tuple[list[PairCollectSummary], list[str]]:
    """卡池装载（tune.fitness.prepare_pairs 复用）+ run_collect 一步走（CLI 入口用）。

    返回 (各配对汇总, 装载告警列表)。
    """
    from battlefrontier.data.pool import load_target_pool

    pool = load_target_pool(pool_path)
    prepared = prepare_pairs(pool_assignments(pool), str(db_path), cards_dir)
    warnings = [f"[{p.assignment.archetype_a}×{p.assignment.archetype_b}] {w}"
                for p in prepared for w in p.warnings]
    summaries = run_collect(prepared, games_per_pair, seed_start, out_dir,
                            workers=workers)
    return summaries, warnings
