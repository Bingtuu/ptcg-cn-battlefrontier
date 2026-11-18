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
- **task 155 WP2 采集 v3**（``feature_set="v3"``）：文件首行写 header
  ``{"type":"header","format":"bf-collect-v3","feature_names":[...]}``（名序 =
  ``eval_v3_names(card_vocab)``，词表随池钉进文件自包含）；数据行 features
  为位置对齐 float list。词表经 payload 透传 worker（多进程确定性）；
  ``read_collect_v3`` 读取校验宽度，不符显式 ValueError（不猜）。缺省 v1 =
  现状逐位不动（无 header、dict 行）。
"""

from __future__ import annotations

import json
import multiprocessing as mp
import re
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.agent.collect import FeatureCollector
from battlefrontier.agent.eval_features import eval_v3_names
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
    "read_collect_v3",
    "run_collect",
]

_HEADER_FORMAT_V3 = "bf-collect-v3"

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
        # task 155 WP2：v3 词表随 payload 透传（spawn worker 内重建 collector，
        # 多进程与串行同一条 worker 路径，词表序逐位一致）；缺省 = v1 现状。
        if payload.get("feature_set") == "v3":
            collector: FeatureCollector = FeatureCollector(
                feature_set="v3", card_vocab=tuple(payload["card_vocab"]))
        else:
            collector = FeatureCollector()
        result = play_game(
            deck_a=[CardDef.model_validate(c) for c in payload["deck_a"]],
            deck_b=[CardDef.model_validate(c) for c in payload["deck_b"]],
            seed=payload["seed"],
            card_effects=card_effects,
            agents=agents,
            collector=collector,
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


def _validate_feature_set(feature_set: str, card_vocab: tuple[str, ...] | None) -> None:
    """feature_set 词表校验（不猜纪律）：只认 v1/v3；v3 必须带词表。"""
    if feature_set not in ("v1", "v3"):
        raise ValueError(f"未知 feature_set={feature_set!r}（只支持 v1/v3，不猜）")
    if feature_set == "v3" and card_vocab is None:
        raise ValueError("feature_set='v3' 必须提供 card_vocab（不猜）")


def run_collect(prepared: list[PreparedPair] | tuple[PreparedPair, ...],
                games_per_pair: int, seed_start: int,
                out_dir: str | Path, *, workers: int = 1,
                feature_set: str = "v1",
                card_vocab: tuple[str, ...] | None = None) -> list[PairCollectSummary]:
    """全部配对 × 种子区间批量跑局并落 JSONL；返回各配对汇总。

    串行与多进程同走 ``_run_one_collect``（imap 保序回收），产物逐行一致。
    task 155 WP2：feature_set="v3" 时文件首行写 header（名序 =
    eval_v3_names(card_vocab) 钉进文件），数据行 features 为位置 list；
    词表随 payload 透传 worker。缺省 v1 = 行为逐位不变（无 header、dict 行；
    唯修订 = 结果流式落盘不在内存累积全批——task 155 内存修复，产物字节不变）。
    """
    _validate_feature_set(feature_set, card_vocab)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payloads: list[dict] = []
    for pp in prepared:
        card_effects = [d.model_dump(mode="json")
                        for d in _unique_docs(pp.card_effects.values())]
        deck_a = [c.model_dump(mode="json") for c in pp.deck_a]
        deck_b = [c.model_dump(mode="json") for c in pp.deck_b]
        for seed in collect_seed_range(pp.assignment.index, games_per_pair, seed_start):
            payload: dict = {"deck_a": deck_a, "deck_b": deck_b,
                             "card_effects": card_effects,
                             "seed": seed, "pair_index": pp.assignment.index}
            if feature_set == "v3":
                assert card_vocab is not None
                payload["feature_set"] = "v3"
                payload["card_vocab"] = list(card_vocab)
            payloads.append(payload)

    # task 155 流式修订（主进程内存修复）：imap 结果逐条落盘，不在内存累积
    # 全批结果——v3 行 ≈ 20KB Python 对象内存/行 × ~400 万行 ≈ 80GB 量级，
    # 全批累积直接顶穿内存（worker MemoryError 实证，results/t155-collect.log；
    # 清理期 terminate 竞态的 concurrent send_bytes 为次生噪音）。流式后主进程
    # 内存 = O(单局行)。产物字节与累积版逐字节一致（imap 保序 + 同一
    # TrajectoryWriter 惯例 + 行序 = payload 序）；中途异常时已完成的行保留。
    rows_by_pair: dict[int, int] = {pp.assignment.index: 0 for pp in prepared}
    failed_by_pair: dict[int, int] = {pp.assignment.index: 0 for pp in prepared}
    writers: dict[int, TrajectoryWriter] = {}
    try:
        for pp in prepared:
            a = pp.assignment
            writer = TrajectoryWriter(
                out / pair_filename(a.index, a.archetype_a, a.archetype_b))
            if feature_set == "v3":
                assert card_vocab is not None
                # header 钉清单：词表随池落进文件（自包含，读取端不依赖外部词表）
                writer.append({"type": "header", "format": _HEADER_FORMAT_V3,
                               "feature_names": list(eval_v3_names(card_vocab))})
            writers[a.index] = writer

        def _handle(result: tuple[int, int, list[dict] | None, str | None]) -> None:
            _seed, pair_index, rows, error = result
            if error is not None:
                failed_by_pair[pair_index] += 1  # 失败局剔除（rows 整局不落盘）
                return
            assert rows is not None
            writer = writers[pair_index]
            for row in rows:
                writer.append(row)
            rows_by_pair[pair_index] += len(rows)

        if workers > 1:
            ctx = mp.get_context("spawn")
            pool = ctx.Pool(workers)
            try:
                for result in pool.imap(_run_one_collect, payloads):
                    _handle(result)
            except BaseException:
                # 清理期次生错误（终止竞态 ValueError）不掩盖原始异常
                try:
                    pool.terminate()
                except Exception:  # noqa: BLE001, S110 — 故意吞：终止竞态次生
                    pass           # 噪音不得顶替 worker 原始异常向上抛
                raise
            else:
                pool.close()
            finally:
                pool.join()
        else:
            for payload in payloads:
                _handle(_run_one_collect(payload))
    finally:
        for writer in writers.values():
            writer.close()

    summaries: list[PairCollectSummary] = []
    for pp in prepared:
        a = pp.assignment
        summaries.append(PairCollectSummary(
            pair_index=a.index, archetype_a=a.archetype_a, archetype_b=a.archetype_b,
            filename=pair_filename(a.index, a.archetype_a, a.archetype_b),
            games=games_per_pair,
            rows=rows_by_pair[a.index], failed=failed_by_pair[a.index]))
    return summaries


def read_collect_v3(path: str | Path) -> tuple[tuple[str, ...], list[dict]]:
    """读出 v3 采集文件：首行 header 钉 feature_names，数据行 features 还原为
    名→值 dict（位置对齐）。

    task 155 WP2（不猜纪律）：首行非 bf-collect-v3 header、数据行 features
    宽度 ≠ header 名数，一律显式 ValueError。
    """
    lines = [json.loads(line) for line in Path(path).read_text(encoding="utf-8")
             .splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"{path} 为空文件（无 header 行，不猜）")
    header = lines[0]
    if (not isinstance(header, dict)
            or header.get("type") != "header"
            or header.get("format") != _HEADER_FORMAT_V3):
        raise ValueError(f"{path} 首行非 {_HEADER_FORMAT_V3} header（不猜）")
    names = header["feature_names"]
    rows = []
    for row in lines[1:]:
        features = row["features"]
        if len(features) != len(names):
            raise ValueError(
                f"数据行 features 宽度 {len(features)} 与 header 名数 "
                f"{len(names)} 不符（不猜）")
        rows.append({**row, "features": dict(zip(names, features, strict=True))})
    return tuple(names), rows


def run_collect_pool(pool_path: str | Path, db_path: str | Path,
                     games_per_pair: int, seed_start: int,
                     out_dir: str | Path, *, workers: int = 1,
                     cards_dir: str | Path = "cards",
                     feature_set: str = "v1",
                     card_vocab: tuple[str, ...] | None = None
                     ) -> tuple[list[PairCollectSummary], list[str]]:
    """卡池装载（tune.fitness.prepare_pairs 复用）+ run_collect 一步走（CLI 入口用）。

    task 155 WP2：feature_set/card_vocab 透传 run_collect（v3 词表由 CLI 侧
    ``build_card_vocab`` 算好传入，保多进程确定性）。返回 (各配对汇总, 装载告警列表)。
    """
    from battlefrontier.data.pool import load_target_pool

    _validate_feature_set(feature_set, card_vocab)
    pool = load_target_pool(pool_path)
    prepared = prepare_pairs(pool_assignments(pool), str(db_path), cards_dir)
    warnings = [f"[{p.assignment.archetype_a}×{p.assignment.archetype_b}] {w}"
                for p in prepared for w in p.warnings]
    summaries = run_collect(prepared, games_per_pair, seed_start, out_dir,
                            workers=workers, feature_set=feature_set,
                            card_vocab=card_vocab)
    return summaries, warnings
