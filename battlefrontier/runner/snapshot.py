"""M11 决策一致率快照产线（task 052 WP3，D-M11-5）：教师配置跑局落决策点快照 JSONL。

- **worker** ``_run_one_snapshot``：模块级入口（可 pickle），payload
  （deck_a/deck_b/card_effects/seed/pair_index/teacher params）→ play_game
  （双侧 MCTSAgent 教师 + SnapshotCollector）→ (seed, pair_index, rows, error)；
  失败局 rows=None + 错误文本（对齐 runner/collect 失败局口径：剔除、计数上报）。
- **批量驱动** ``run_collect_snapshots``：配对装载复用 tune.fitness.prepare_pairs
  + runner.collect.pool_assignments；种子协议 = matrix 惯例（pair i →
  [seed_start + i×games_per_pair, +games_per_pair)）；spawn 多进程 imap 保序
  （workers>1）与串行同一条 worker 路径，产物逐行一致。
- **落盘**：``<out>/pair-<index>-<名A>x<名B>.jsonl``（复用 collect.pair_filename），
  首行 header（pair/种子区间/卡组/card_effects——评估侧自包含重建，无需 db），
  其后每行一个快照（record=snapshot；含序列化 GameState + 教师结构化 Action +
  turn/phase/player/action_kind/n_legal/seed）。逐行 JSON（UTF-8 /
  ensure_ascii=False / sort_keys，TrajectoryWriter 惯例）；行内零非确定量。
  快照不落结果库（D-T4 先例：JSONL 侧文件即锚点）。
"""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.agent.mcts import MCTSAgent
from battlefrontier.agent.snapshot import SnapshotCollector
from battlefrontier.data.pool import TargetPool
from battlefrontier.dsl import CardLibrary
from battlefrontier.dsl.schema import CardEffectDoc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef, GameState
from battlefrontier.runner.collect import (
    PairCollectSummary,
    collect_seed_range,
    pair_filename,
    pool_assignments,
)
from battlefrontier.runner.experiment import _unique_docs
from battlefrontier.runner.play import play_game
from battlefrontier.tune.fitness import PreparedPair, prepare_pairs
from battlefrontier.tune.trajectory import TrajectoryWriter, read_trajectory

__all__ = [
    "SNAPSHOT_FORMAT",
    "SnapshotFile",
    "load_snapshot_file",
    "run_collect_snapshots",
    "run_collect_snapshots_pool",
    "snapshot_header",
    "snapshot_state",
    "teacher_action",
]

SNAPSHOT_FORMAT = "bf-m11-snapshot-v1"


def snapshot_header(
    pp: PreparedPair, *, games_per_pair: int, seed_start: int,
    teacher: dict[str, int],
) -> dict:
    """快照文件首行（record=header）：配对 / 种子区间 / 卡组 / card_effects /
    教师预算——评估侧自包含重建引擎与 DSL 库（无需 db）。"""
    a = pp.assignment
    seeds = collect_seed_range(a.index, games_per_pair, seed_start)
    return {
        "record": "header",
        "format": SNAPSHOT_FORMAT,
        "pair_index": a.index,
        "archetype_a": a.archetype_a,
        "archetype_b": a.archetype_b,
        "seed_start": seeds.start,
        "seed_end": seeds.stop - 1,
        "games_per_pair": games_per_pair,
        "teacher": dict(teacher),
        "deck_a": [c.model_dump(mode="json") for c in pp.deck_a],
        "deck_b": [c.model_dump(mode="json") for c in pp.deck_b],
        "card_effects": [d.model_dump(mode="json")
                         for d in _unique_docs(pp.card_effects.values())],
    }


def teacher_action(row: dict) -> Action:
    """快照行 → 教师结构化 Action（choices 经 JSON 退化为 list，重建回 tuple）。"""
    data = dict(row["action"])
    data["choices"] = tuple(data.get("choices") or ())
    return Action(**data)


def snapshot_state(row: dict) -> GameState:
    """快照行 → GameState（model_dump/model_validate 往返，test_state 先例）。"""
    return GameState.model_validate(row["state"])


@dataclass(frozen=True)
class SnapshotFile:
    """载入的快照文件：header + 快照行列表（JSONL 原序）。"""

    header: dict
    rows: list[dict]

    def card_effects(self) -> CardLibrary:
        """header card_effects 重建 DSL 库（挂载键 = card_id 精确挂载）。"""
        return CardLibrary.from_docs(
            ("<snapshot>", CardEffectDoc.model_validate(d))
            for d in self.header["card_effects"])


def load_snapshot_file(path: str | Path) -> SnapshotFile:
    """载入快照 JSONL；首行须为 header（format 校验），其余为 snapshot 行（不猜）。"""
    lines = read_trajectory(path)  # JSONL 逐行 dict（tune 轨迹读侧复用）
    if not lines:
        raise ValueError(f"快照文件为空：{path}")
    header = lines[0]
    if header.get("record") != "header":
        raise ValueError(f"快照文件首行须为 header：{path}（不猜）")
    if header.get("format") != SNAPSHOT_FORMAT:
        raise ValueError(
            f"快照 format 不符：{header.get('format')!r}（期望 {SNAPSHOT_FORMAT}）")
    rows = lines[1:]
    bad = [i for i, r in enumerate(rows) if r.get("record") != "snapshot"]
    if bad:
        raise ValueError(f"快照文件含非 snapshot 行（行号 {bad[:5]}，不猜）")
    return SnapshotFile(header=header, rows=rows)


def _run_one_snapshot(payload: dict) -> tuple[int, int, list[dict] | None, str | None]:
    """多进程 worker 入口（模块级函数，可 pickle）。失败局返回错误文本而非抛出。"""
    try:
        # worker 内重建 CardLibrary（载荷为去重后的文档列表；挂载键 = card_id）
        card_effects = CardLibrary.from_docs(
            ("<worker>", CardEffectDoc.model_validate(d))
            for d in payload["card_effects"])
        t = payload["teacher"]
        # 教师双方同配置 MCTS（预算 + 截断参数经 payload 透传）；rng 走
        # seed+offset 独立流（experiment.build_agents 同口径）
        agents = [
            MCTSAgent(RandomSource(payload["seed"] + 1_000_001),
                      card_effects=card_effects, **t),
            MCTSAgent(RandomSource(payload["seed"] + 2_000_002),
                      card_effects=card_effects, **t),
        ]
        result = play_game(
            deck_a=[CardDef.model_validate(c) for c in payload["deck_a"]],
            deck_b=[CardDef.model_validate(c) for c in payload["deck_b"]],
            seed=payload["seed"],
            card_effects=card_effects,
            agents=agents,
            snapshot_collector=SnapshotCollector(),
        )
        rows = result.snapshot_rows
        assert rows is not None  # snapshot_collector 非 None 则必有（可能为空列表）
        for row in rows:
            row["seed"] = payload["seed"]
        return payload["seed"], payload["pair_index"], rows, None
    except Exception as e:  # noqa: BLE001 — 不猜纪律：失败局剔除并计数，不拖垮产线
        return payload["seed"], payload["pair_index"], None, f"{type(e).__name__}: {e}"


def run_collect_snapshots(
    prepared: list[PreparedPair] | tuple[PreparedPair, ...],
    games_per_pair: int, seed_start: int,
    out_dir: str | Path, *, workers: int = 1,
    teacher: dict[str, int] | None = None,
) -> list[PairCollectSummary]:
    """全部配对 × 种子区间教师配置跑局并落快照 JSONL；返回各配对汇总。

    teacher = MCTS 预算 dict（worlds/iterations/rollout_turn_cap；默认 2×50，
    D-M11-5 基准配置）。串行与多进程同走 ``_run_one_snapshot``（imap 保序回收）。
    """
    teacher = {"worlds": 2, "iterations": 50} if teacher is None else dict(teacher)
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
                             "seed": seed, "pair_index": pp.assignment.index,
                             "teacher": teacher})

    results: list[tuple[int, int, list[dict] | None, str | None]] = []
    if workers > 1:
        ctx = mp.get_context("spawn")
        with ctx.Pool(workers) as pool:
            results.extend(pool.imap(_run_one_snapshot, payloads))
    else:
        for payload in payloads:
            results.append(_run_one_snapshot(payload))

    rows_by_pair: dict[int, list[dict]] = {pp.assignment.index: [] for pp in prepared}
    failed_by_pair: dict[int, int] = {pp.assignment.index: 0 for pp in prepared}
    for _seed, pair_index, rows, error in results:
        if error is not None:
            failed_by_pair[pair_index] += 1  # 失败局剔除（快照整局不落盘）
        else:
            assert rows is not None
            rows_by_pair[pair_index].extend(rows)

    summaries: list[PairCollectSummary] = []
    for pp in prepared:
        a = pp.assignment
        filename = pair_filename(a.index, a.archetype_a, a.archetype_b)
        with TrajectoryWriter(out / filename) as writer:
            writer.append(snapshot_header(
                pp, games_per_pair=games_per_pair, seed_start=seed_start,
                teacher=teacher))
            for row in rows_by_pair[a.index]:
                writer.append({"record": "snapshot", **row})
        summaries.append(PairCollectSummary(
            pair_index=a.index, archetype_a=a.archetype_a, archetype_b=a.archetype_b,
            filename=filename, games=games_per_pair,
            rows=len(rows_by_pair[a.index]), failed=failed_by_pair[a.index]))
    return summaries


def run_collect_snapshots_pool(
    pool_path: str | Path, db_path: str | Path,
    games_per_pair: int, seed_start: int,
    out_dir: str | Path, *, workers: int = 1,
    cards_dir: str | Path = "cards",
    teacher: dict[str, int] | None = None,
) -> tuple[list[PairCollectSummary], list[str]]:
    """卡池装载（tune.fitness.prepare_pairs 复用）+ run_collect_snapshots 一步走。

    返回 (各配对汇总, 装载告警列表)。CLI 入口用。
    """
    from battlefrontier.data.pool import load_target_pool

    pool: TargetPool = load_target_pool(pool_path)
    prepared = prepare_pairs(pool_assignments(pool), str(db_path), cards_dir)
    warnings = [f"[{p.assignment.archetype_a}×{p.assignment.archetype_b}] {w}"
                for p in prepared for w in p.warnings]
    summaries = run_collect_snapshots(prepared, games_per_pair, seed_start, out_dir,
                                      workers=workers, teacher=teacher)
    return summaries, warnings
