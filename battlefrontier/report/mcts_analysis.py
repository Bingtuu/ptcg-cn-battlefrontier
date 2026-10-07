"""MCTS 决策分析报告（task 042，D-042-4）：mcts_consider 事件 → 三件套。

数据源 = 结果库 game_events 层的 mcts_consider 事件（task 042 起落流，
MCTSAgent 根统计外化；heuristic/random 对局无此类事件）。

三件套口径：
① 按 action kind 聚合的访问份额（Σvisits/Σtotal——强 Agent 注意力分布）；
② 高熵决策点 top N（归一化熵 H/Hmax，Hmax=ln(候选数)——访问最分散 =
   关键抉择点，列 turn/phase/分布）；
③ 选中行动访问份额分桶（果断 >80% / 50-80% / 纠结 <50%）× 选择方最终胜率
   ——games/wins 只统计决定局（平局不进分母，同 decisions 报告口径），
   Wilson 95% CI 复用 report.winrate。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from battlefrontier.report.winrate import wilson_ci
from battlefrontier.runner.results_db import ResultsDB

TOP_ENTROPY_N = 20  # 高熵决策点展示条数（D-042-4②）

# 选中行动访问份额分桶（D-042-4③）：share>0.8 果断 / 0.5≤share≤0.8 居中 / <0.5 纠结
BUCKETS: tuple[str, ...] = ("果断（>80%）", "50-80%", "纠结（<50%）")


@dataclass(frozen=True)
class KindShare:
    kind: str
    visits: int
    share: float        # Σvisits(kind) / Σtotal_visits


@dataclass(frozen=True)
class EntropyPoint:
    seed: int
    side: int           # 决策方（0 = A 卡组侧）
    turn: int
    phase: str
    entropy: float      # 归一化熵 H/Hmax ∈ [0,1]
    distribution: tuple[tuple[str, int], ...]  # (action 标签, visits)，降序


@dataclass(frozen=True)
class BucketStat:
    label: str
    decisions: int      # 决策点数（完成局全部事件）
    games: int          # 覆盖的不同决定局数
    wins: int           # 其中选择方最终获胜局数
    winrate: float
    ci: tuple[float, float]


@dataclass(frozen=True)
class MctsReport:
    experiment_id: int
    name: str
    games_analyzed: int     # 完成局数
    decision_points: int    # mcts_consider 事件总数
    kind_shares: tuple[KindShare, ...]
    entropy_top: tuple[EntropyPoint, ...]
    buckets: tuple[BucketStat, ...]


def _normalized_entropy(visits: list[int]) -> float:
    """归一化熵 H/Hmax（自然对数；候选 ≤1 时熵 0——无分散可言）。"""
    total = sum(visits)
    if total <= 0 or len(visits) <= 1:
        return 0.0
    h = -sum((v / total) * math.log(v / total) for v in visits if v > 0)
    return h / math.log(len(visits))


def _bucket_label(share: float) -> str:
    if share > 0.8:
        return BUCKETS[0]
    if share >= 0.5:
        return BUCKETS[1]
    return BUCKETS[2]


def mcts_report(db: ResultsDB, experiment_id: int) -> MctsReport:
    exp = db.experiment(experiment_id)
    rows = [g for g in db.games(experiment_id) if not g["error"]]
    visits_by_kind: dict[str, int] = {}
    total_visits = 0
    points: list[EntropyPoint] = []
    decisions = {label: 0 for label in BUCKETS}
    covered: dict[str, set[int]] = {}   # 桶 → 决定局 id
    wins: dict[str, set[int]] = {}      # 桶 → 选择方获胜局 id
    n_events = 0

    for g in rows:
        gid, winner, decided = g["id"], g["winner"], not g["is_draw"]
        for row in db.game_events(gid):
            ev = json.loads(row["event_json"])
            if ev["kind"] != "mcts_consider":
                continue
            n_events += 1
            d = ev["detail"]
            considered = [(c["action"], c["kind"], c["visits"]) for c in d["considered"]]
            for _, kind, v in considered:
                visits_by_kind[kind] = visits_by_kind.get(kind, 0) + v
            total_visits += d["total_visits"]
            points.append(EntropyPoint(
                seed=g["seed"], side=ev["player"], turn=ev["turn"], phase=ev["phase"],
                entropy=_normalized_entropy([v for _, _, v in considered]),
                distribution=tuple((a, v) for a, _, v in considered),
            ))
            share = d["chosen_visits"] / d["total_visits"] if d["total_visits"] else 0.0
            label = _bucket_label(share)
            decisions[label] += 1
            if not decided:
                continue  # 平局不进胜率分母（决策数仍计，同 decisions 口径）
            covered.setdefault(label, set()).add(gid)
            if winner == ev["player"]:
                wins.setdefault(label, set()).add(gid)

    kind_shares = tuple(sorted(
        (KindShare(kind=k, visits=v,
                   share=v / total_visits if total_visits else 0.0)
         for k, v in visits_by_kind.items()),
        key=lambda k: (-k.share, k.kind),
    ))
    entropy_top = tuple(sorted(
        points, key=lambda p: (-p.entropy, p.seed, p.turn),
    )[:TOP_ENTROPY_N])
    buckets = tuple(
        BucketStat(
            label=label, decisions=decisions[label],
            games=len(covered.get(label, set())), wins=len(wins.get(label, set())),
            winrate=(len(wins.get(label, set())) / len(covered.get(label, set()))
                     if covered.get(label) else 0.0),
            ci=wilson_ci(len(wins.get(label, set())), len(covered.get(label, set()))),
        )
        for label in BUCKETS
    )
    return MctsReport(experiment_id=exp["id"], name=exp["name"],
                      games_analyzed=len(rows), decision_points=n_events,
                      kind_shares=kind_shares, entropy_top=entropy_top, buckets=buckets)


def format_mcts_report(r: MctsReport) -> str:
    """文本报告：访问份额 → 高熵决策点 top N → 分桶胜率。"""
    lines = [
        (f"实验 #{r.experiment_id}「{r.name}」MCTS 决策分析"
         f"（完成局 {r.games_analyzed}，决策点 {r.decision_points}）"),
    ]
    if r.decision_points == 0:
        lines.append("（无 mcts_consider 事件——该实验非 MCTS 对局或早于 task 042）")
        return "\n".join(lines)
    lines.append("── 行动类别访问份额 ──")
    for k in r.kind_shares:
        lines.append(f"  {k.kind}：{k.share * 100:.1f}%（{k.visits} 次访问）")
    lines.append(f"── 高熵决策点 top {len(r.entropy_top)}（归一化熵 H/Hmax）──")
    for i, p in enumerate(r.entropy_top, 1):
        dist = " / ".join(f"{a} {v}" for a, v in p.distribution)
        lines.append(
            f"  #{i} 种子{p.seed} 回合{p.turn} {p.phase}（玩家{p.side}）"
            f" H={p.entropy:.2f}：{dist}")
    lines.append("── 选中行动访问份额 × 胜率（分母 = 决定局）──")
    for b in r.buckets:
        lines.append(
            f"  {b.label}：{b.decisions} 决策 / {b.games} 局 "
            f"胜率 {b.winrate * 100:.1f}%（CI {b.ci[0] * 100:.1f}..{b.ci[1] * 100:.1f}）")
    return "\n".join(lines)
