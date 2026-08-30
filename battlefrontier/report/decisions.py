"""决策聚合报告（PRD §9，task 022）：choose 决策事件 × 最终胜率。

数据源 = 结果库 game_events 层的 choose 事件（task 022 起落流）；
observe 锚点（DSL 声明，effect_observe 事件）经 effect_id 同局关联到决策点作展示标签。

口径：只统计完成局；选择分布按（侧, 卡, 池, 选择标签）聚合——occurrences 为决策次数，
games 为覆盖的不同决定局数（同局重复选择只计一局），winrate = 选择方最终获胜局 /
覆盖决定局数 + Wilson 95% CI（复用 report.winrate）。选择标签 = 选中卡名 "+"
连接；空选（up-to 语义不找）= 「（放弃）」。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from battlefrontier.report.winrate import wilson_ci
from battlefrontier.runner.results_db import ResultsDB

ABSTAIN = "（放弃）"


@dataclass(frozen=True)
class ChoiceStat:
    label: str
    occurrences: int
    games: int          # 覆盖的不同决定局数
    wins: int           # 其中选择方最终获胜局数
    winrate: float
    ci: tuple[float, float]


@dataclass(frozen=True)
class DecisionPoint:
    side: int           # 0 = A 卡组侧
    card: str
    pool: str
    anchor: str | None
    choices: tuple[ChoiceStat, ...]


@dataclass(frozen=True)
class DecisionReport:
    experiment_id: int
    name: str
    games_analyzed: int
    points: tuple[DecisionPoint, ...]


def decision_report(db: ResultsDB, experiment_id: int) -> DecisionReport:
    exp = db.experiment(experiment_id)
    rows = [g for g in db.games(experiment_id) if not g["error"]]
    # 逐局聚合：key = (side, card, pool, label)
    occurrences: dict[tuple, int] = {}
    covered: dict[tuple, set[int]] = {}     # 覆盖的决定局 id
    wins: dict[tuple, set[int]] = {}        # 其中选择方获胜局 id
    meta: dict[tuple, tuple[int, str, str]] = {}
    anchors: dict[tuple[int, str, str], str] = {}  # (side, card, pool) → anchor

    for g in rows:
        gid, winner, decided = g["id"], g["winner"], not g["is_draw"]
        anchor_by_eid: dict[str, str] = {}
        events = [json.loads(e["event_json"]) for e in db.game_events(gid)]
        for ev in events:
            if ev["kind"] == "effect_observe":
                anchor_by_eid[ev["detail"]["effect_id"]] = ev["detail"]["anchor"]
        for ev in events:
            if ev["kind"] != "choose":
                continue
            d = ev["detail"]
            side, card, pool = ev["player"], d["card"], d["pool"]
            label = "+".join(d["chosen_names"]) if d["chosen_names"] else ABSTAIN
            key = (side, card, pool, label)
            meta[key] = (side, card, pool)
            occurrences[key] = occurrences.get(key, 0) + 1
            if d["effect_id"] in anchor_by_eid:
                anchors.setdefault((side, card, pool), anchor_by_eid[d["effect_id"]])
            if not decided:
                continue  # 平局不进胜率分母（次数仍计）
            covered.setdefault(key, set()).add(gid)
            if winner == side:
                wins.setdefault(key, set()).add(gid)

    by_point: dict[tuple[int, str, str], list[ChoiceStat]] = {}
    for key, (side, card, pool) in meta.items():
        games_n = len(covered.get(key, set()))
        wins_n = len(wins.get(key, set()))
        stat = ChoiceStat(
            label=key[3], occurrences=occurrences[key], games=games_n, wins=wins_n,
            winrate=wins_n / games_n if games_n else 0.0,
            ci=wilson_ci(wins_n, games_n),
        )
        by_point.setdefault((side, card, pool), []).append(stat)

    points = tuple(
        DecisionPoint(
            side=side, card=card, pool=pool,
            anchor=anchors.get((side, card, pool)),
            choices=tuple(sorted(stats, key=lambda s: (-s.occurrences, s.label))),
        )
        for (side, card, pool), stats in sorted(by_point.items())
    )
    return DecisionReport(experiment_id=exp["id"], name=exp["name"],
                          games_analyzed=len(rows), points=points)


def format_decisions(r: DecisionReport) -> str:
    """文本报告：按侧/卡分节，分布行按次数降序。"""
    lines = [f"实验 #{r.experiment_id}「{r.name}」决策聚合（完成局 {r.games_analyzed}）"]
    side_name = {0: "A", 1: "B"}
    current_side: int | None = None
    for p in r.points:
        if p.side != current_side:
            current_side = p.side
            lines.append(f"── {side_name.get(p.side, p.side)} 侧 ──")
        anchor = f"，锚点 {p.anchor}" if p.anchor else ""
        total = sum(c.occurrences for c in p.choices)
        lines.append(f"{p.card} / {p.pool}（{total} 次决策{anchor}）")
        for c in p.choices:
            lines.append(
                f"  {c.label}：{c.occurrences} 次 / {c.games} 局 "
                f"胜率 {c.winrate * 100:.1f}%（CI {c.ci[0] * 100:.1f}..{c.ci[1] * 100:.1f}）"
            )
    if len(lines) == 1:
        lines.append("（无决策事件——该实验早于 task 022 或无 chooser 对局）")
    return "\n".join(lines)
