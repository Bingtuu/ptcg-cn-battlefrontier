"""评估协议（D-T2，task 045）：配对分层划分 + CRN 种子派生 + 批量跑局聚合。

- **划分**：池内 36 无向配对 → 训练 24 / holdout 12，分层抽样（9 个 archetype
  双侧覆盖，不满足显式报错不猜）；抽样走注入 RandomSource（split_seed 钉死在
  调优定义）。冒烟/调试可经 ``select_pairs`` 显式指定训练配对子集（holdout 空）。
- **CRN 降方差**：所有候选在同一配对上使用同一固定种子区间
  （pair i → 种子 200000+i×1000 起 N 局）——确定性同时为公共随机数降方差手段。
- **fitness**：候选参数（固定侧 A）vs 默认参数（侧 B），训练集平均胜率
  （分母=决定局，平局/失败局剔分母，对齐 report/winrate 口径）。

批量跑局复用 runner 的多进程 worker（``_run_one_experiment``：worker 内按同一种子
重建 Agent，串行与并行同一条代码路径）；聚合 ``aggregate`` 为纯函数，注入
模拟结果即可单测，不打真局。搜索过程局不落结果库（D-T4：轨迹 JSONL 即锚点）。
"""

from __future__ import annotations

import multiprocessing as mp
import time
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.data.deck import load_deck
from battlefrontier.data.pool import TargetPool
from battlefrontier.dsl import CardLibrary, load_card_dir
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef
from battlefrontier.runner.experiment import (
    AgentCfg,
    AgentSides,
    _run_one_experiment,
    _unique_docs,
    assemble_card_effects,
)

__all__ = [
    "SEED_BASE",
    "SEED_STRIDE",
    "EvalResult",
    "GameOutcome",
    "PairAssignment",
    "PairOutcome",
    "PairSplit",
    "PreparedPair",
    "aggregate",
    "check_coverage",
    "execute_plan",
    "pair_seed_range",
    "prepare_pairs",
    "select_pairs",
    "split_pairs",
]

# CRN 种子锚点（D-T2）：pair i → [200000+i×1000, +N)；STRIDE 即每配对局数上限
SEED_BASE = 200000
SEED_STRIDE = 1000


# ── 配对划分 ─────────────────────────────────────────────

@dataclass(frozen=True)
class PairAssignment:
    """一个无向配对：index = pool.matchup_pairs() 序（CRN 种子派生锚点）。"""

    index: int
    archetype_a: str
    archetype_b: str
    deck_id_a: str
    deck_id_b: str


@dataclass(frozen=True)
class PairSplit:
    train: tuple[PairAssignment, ...]
    holdout: tuple[PairAssignment, ...]


def _assignments(pool: TargetPool) -> list[PairAssignment]:
    return [
        PairAssignment(index=i, archetype_a=a.archetype, archetype_b=b.archetype,
                       deck_id_a=a.deck_id, deck_id_b=b.deck_id)
        for i, (a, b) in enumerate(pool.matchup_pairs())
    ]


def check_coverage(split: PairSplit, archetypes: set[str]) -> None:
    """分层校验：每个 archetype 在训练集与 holdout 各自至少出现于一个配对；
    不满足显式报错（不猜——调用方应更换 split_seed）。"""
    for label, side in (("训练集", split.train), ("holdout", split.holdout)):
        covered = {p.archetype_a for p in side} | {p.archetype_b for p in side}
        missing = sorted(archetypes - covered)
        if missing:
            raise ValueError(
                f"{label}未覆盖 archetype（不猜，请更换 split_seed）: {missing}")


def split_pairs(pool: TargetPool, split_seed: int, holdout_size: int) -> PairSplit:
    """36 无向配对 → 训练/holdout 分层划分（同 split_seed 同划分）。

    划分比例可行性（两侧配对数 ×2 须足以覆盖全部 archetype）不满足显式报错。
    """
    all_pairs = _assignments(pool)
    n = len(all_pairs)
    m = len({d.archetype for d in pool.decks})
    if not (1 <= holdout_size < n) or holdout_size * 2 < m or (n - holdout_size) * 2 < m:
        raise ValueError(
            f"划分比例非法（不猜）：holdout_size={holdout_size}，配对总数 {n}，"
            f"archetype 数 {m}——须 1 ≤ holdout < {n} 且两侧配对数×2 ≥ {m}")
    rng = RandomSource(split_seed)
    order = rng.shuffle(range(n))
    holdout_idx = frozenset(order[:holdout_size])
    split = PairSplit(
        train=tuple(p for p in all_pairs if p.index not in holdout_idx),
        holdout=tuple(p for p in all_pairs if p.index in holdout_idx),
    )
    check_coverage(split, {d.archetype for d in pool.decks})
    return split


def select_pairs(pool: TargetPool, pairs: list[tuple[str, str]]) -> PairSplit:
    """显式训练配对子集（冒烟/调试）：train = 所选（池序），holdout 空；
    index 保留池序（CRN 锚点不变）。未知 archetype / 镜像对显式报错（不猜）。"""
    all_pairs = {frozenset((p.archetype_a, p.archetype_b)): p for p in _assignments(pool)}
    names = {d.archetype for d in pool.decks}
    selected: list[PairAssignment] = []
    for a, b in pairs:
        for name in (a, b):
            if name not in names:
                raise ValueError(f"卡池中不存在 archetype（不猜）: {name}")
        if a == b:
            raise ValueError(f"镜像对不进配对（不猜）: {a}")
        pair = all_pairs.get(frozenset((a, b)))
        assert pair is not None  # 两 archetype 均在池则配对必存在
        selected.append(pair)
    return PairSplit(train=tuple(sorted(selected, key=lambda p: p.index)), holdout=())


# ── CRN 种子派生 ─────────────────────────────────────────

def pair_seed_range(pair_index: int, games: int) -> range:
    """pair i → 种子区间 [200000+i×1000, +N)。N > 1000 会与相邻配对撞区间（不猜）。"""
    if games > SEED_STRIDE:
        raise ValueError(
            f"games_per_pair={games} 超过 CRN 种子区间宽 {SEED_STRIDE}（不猜）")
    start = SEED_BASE + pair_index * SEED_STRIDE
    return range(start, start + games)


# ── 聚合（纯函数，注入模拟结果即可单测）────────────────────

@dataclass(frozen=True)
class GameOutcome:
    """单局结局（winner 视角：0 = 候选侧 A）。"""

    pair_index: int
    seed: int
    winner: int | None
    is_draw: bool
    failed: bool


@dataclass(frozen=True)
class PairOutcome:
    pair_index: int
    archetype_a: str
    archetype_b: str
    seed_start: int
    seed_end: int          # 含端点
    games: int
    decided: int
    wins_a: int
    draws: int
    failed: int
    winrate: float         # wins_a / decided（decided=0 → 0.0，同 winrate 口径）


@dataclass(frozen=True)
class EvalResult:
    """一次候选评估：参数向量 + fitness（训练集平均胜率）+ 各配对明细 + 墙钟秒。"""

    vector: dict[str, float | int]
    fitness: float
    pairs: tuple[PairOutcome, ...]
    wall_seconds: float


def aggregate(vector: dict[str, float | int],
              assignments: tuple[PairAssignment, ...] | list[PairAssignment],
              games_per_pair: int,
              outcomes: list[GameOutcome] | tuple[GameOutcome, ...],
              wall_seconds: float) -> EvalResult:
    """局结局 → 评估结果。局数/种子与 CRN 派生区间不符显式报错（不猜）。"""
    by_pair: dict[int, list[GameOutcome]] = {}
    for o in outcomes:
        by_pair.setdefault(o.pair_index, []).append(o)
    pair_results: list[PairOutcome] = []
    for a in assignments:
        games = by_pair.get(a.index, [])
        expected = set(pair_seed_range(a.index, games_per_pair))
        seeds = {o.seed for o in games}
        if len(games) < games_per_pair:
            raise ValueError(
                f"配对 {a.index} 缺局（不猜）：{len(games)}/{games_per_pair}")
        if len(games) > games_per_pair:
            raise ValueError(
                f"配对 {a.index} 多局（不猜）：{len(games)}/{games_per_pair}")
        if seeds != expected:
            raise ValueError(
                f"配对 {a.index} 种子与 CRN 区间不符（不猜）："
                f"期望 {min(expected)}..{max(expected)}")
        played = [o for o in games if not o.failed]
        decided = [o for o in played if not o.is_draw]
        wins_a = sum(1 for o in decided if o.winner == 0)
        winrate = wins_a / len(decided) if decided else 0.0
        rng = pair_seed_range(a.index, games_per_pair)
        pair_results.append(PairOutcome(
            pair_index=a.index, archetype_a=a.archetype_a, archetype_b=a.archetype_b,
            seed_start=rng.start, seed_end=rng.stop - 1,
            games=len(games), decided=len(decided), wins_a=wins_a,
            draws=len(played) - len(decided), failed=len(games) - len(played),
            winrate=winrate))
    if not pair_results:
        raise ValueError("训练配对集为空（不猜）")
    fitness = sum(p.winrate for p in pair_results) / len(pair_results)
    return EvalResult(vector=dict(vector), fitness=fitness,
                      pairs=tuple(pair_results), wall_seconds=wall_seconds)


# ── 批量跑局（复用 runner worker 多进程设施）────────────────

@dataclass(frozen=True)
class PreparedPair:
    """单个配对的装载结果：双方卡组 + 按 card_id 精确挂载的 DSL 文档 + 汇集告警。"""

    assignment: PairAssignment
    deck_a: list[CardDef]
    deck_b: list[CardDef]
    card_effects: CardLibrary
    warnings: tuple[str, ...] = ()


def prepare_pairs(assignments: tuple[PairAssignment, ...] | list[PairAssignment],
                  db_path: str,
                  cards_dir: str | Path = "cards") -> list[PreparedPair]:
    """装载全部训练配对（deck_id 缓存——同 archetype 跨配对只装一次）。"""
    library = load_card_dir(cards_dir)
    decks: dict[str, tuple[list[CardDef], list[str]]] = {}

    def deck(deck_id: str) -> tuple[list[CardDef], list[str]]:
        if deck_id not in decks:
            loaded = load_deck(db_path, deck_id)
            decks[deck_id] = (loaded.cards, loaded.warnings)
        return decks[deck_id]

    prepared: list[PreparedPair] = []
    for a in assignments:
        deck_a, wa = deck(a.deck_id_a)
        deck_b, wb = deck(a.deck_id_b)
        effects, we = assemble_card_effects([deck_a, deck_b], library)
        warnings = tuple(dict.fromkeys([*wa, *wb, *we]))
        prepared.append(PreparedPair(assignment=a, deck_a=deck_a, deck_b=deck_b,
                                     card_effects=effects, warnings=warnings))
    return prepared


def execute_plan(prepared: list[PreparedPair] | tuple[PreparedPair, ...],
                 vector: dict[str, float | int],
                 games_per_pair: int, *, workers: int = 1) -> EvalResult:
    """候选参数（侧 A）vs 默认参数（侧 B）在全部配对 × CRN 种子区间上批量跑局。

    串行与多进程同走 ``_run_one_experiment``（worker 内按同一种子重建 Agent），
    imap 保序回收——并行与串行结果逐局一致（§8.4 纪律延伸）。
    """
    agents = AgentSides(a=AgentCfg(type="heuristic", params=dict(vector)),
                        b=AgentCfg(type="heuristic"))
    agents_payload = agents.model_dump(mode="json")
    payloads: list[dict] = []
    seed_to_pair: dict[int, int] = {}
    for pp in prepared:
        card_effects = [d.model_dump(mode="json")
                        for d in _unique_docs(pp.card_effects.values())]
        deck_a = [c.model_dump(mode="json") for c in pp.deck_a]
        deck_b = [c.model_dump(mode="json") for c in pp.deck_b]
        for seed in pair_seed_range(pp.assignment.index, games_per_pair):
            seed_to_pair[seed] = pp.assignment.index
            payloads.append({"deck_a": deck_a, "deck_b": deck_b,
                             "card_effects": card_effects,
                             "agents": agents_payload, "seed": seed})

    t0 = time.perf_counter()
    outcomes: list[GameOutcome] = []
    if workers > 1:
        ctx = mp.get_context("spawn")
        with ctx.Pool(workers) as pool:
            results = pool.imap(_run_one_experiment, payloads)
            for seed, result, error in results:
                outcomes.append(_to_outcome(seed_to_pair, seed, result, error))
    else:
        for payload in payloads:
            seed, result, error = _run_one_experiment(payload)
            outcomes.append(_to_outcome(seed_to_pair, seed, result, error))
    wall = time.perf_counter() - t0
    return aggregate(vector, [pp.assignment for pp in prepared],
                     games_per_pair, outcomes, wall)


def _to_outcome(seed_to_pair: dict[int, int], seed: int, result, error) -> GameOutcome:
    """worker 三元组 → GameOutcome；失败局记 failed（剔决定局分母，不拖垮评估）。"""
    return GameOutcome(
        pair_index=seed_to_pair[seed], seed=seed,
        winner=result.winner if result is not None else None,
        is_draw=result.is_draw if result is not None else False,
        failed=error is not None)
