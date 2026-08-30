"""胜率报告（PRD §9，task 021）：结果库 → 胜率 + Wilson 95% CI + 先后手拆分。

统计口径（与 tasks/task 021.md 一致，报告文本同步标注）：

- 完成局 = error IS NULL；决定局 = 完成局且非平局；
- 胜率 = 胜场 / 决定局（平局率单独报告）；平均回合数 = 完成局（含平局）平均；
- 先后手拆分 = games.first_player（0 = A 先攻）分组内各自 A 胜率；
- Wilson 95% CI 手写实现（z=1.96；不引 scipy——公式简单，参考值对拍见测试）。

meta 回显：实验 id / 名称 / 种子区间 / 代码+数据版本 / 局数（可复算纪律）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from battlefrontier.runner.results_db import ResultsDB

Z_95 = 1.959964  # 正态 97.5 分位


def wilson_ci(wins: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score 区间。n=0 → (0.0, 0.0)（不除零不猜）。"""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


@dataclass(frozen=True)
class Split:
    """先后手分组：games 完成局数 / decided 决定局数 / A 胜场与胜率。"""

    games: int
    decided: int
    wins_a: int
    wr_a: float
    ci_a: tuple[float, float]


@dataclass(frozen=True)
class WinrateReport:
    experiment_id: int
    name: str
    code_version: str
    data_version: str
    seed_min: int | None
    seed_max: int | None
    games_total: int      # 含失败局
    games_failed: int
    games_played: int     # 完成局（含平局）
    decided: int
    wins_a: int
    wins_b: int
    draws: int
    avg_turns: float
    wr_a: float
    ci_a: tuple[float, float]
    as_first: Split
    as_second: Split


def _split(rows: list[dict], first_player: int) -> Split:
    group = [g for g in rows if g["first_player"] == first_player]
    decided = [g for g in group if not g["is_draw"]]
    wins_a = sum(1 for g in decided if g["winner"] == 0)
    wr = wins_a / len(decided) if decided else 0.0
    return Split(games=len(group), decided=len(decided), wins_a=wins_a,
                 wr_a=wr, ci_a=wilson_ci(wins_a, len(decided)))


def winrate_report(db: ResultsDB, experiment_id: int) -> WinrateReport:
    exp = db.experiment(experiment_id)
    rows = db.games(experiment_id)
    failed = [g for g in rows if g["error"]]
    played = [g for g in rows if not g["error"]]
    decided = [g for g in played if not g["is_draw"]]
    wins_a = sum(1 for g in decided if g["winner"] == 0)
    wins_b = sum(1 for g in decided if g["winner"] == 1)
    seeds = [g["seed"] for g in rows]
    return WinrateReport(
        experiment_id=exp["id"], name=exp["name"],
        code_version=exp["code_version"], data_version=exp["data_version"],
        seed_min=min(seeds) if seeds else None,
        seed_max=max(seeds) if seeds else None,
        games_total=len(rows), games_failed=len(failed), games_played=len(played),
        decided=len(decided), wins_a=wins_a, wins_b=wins_b,
        draws=len(played) - len(decided),
        avg_turns=sum(g["turns"] for g in played) / len(played) if played else 0.0,
        wr_a=wins_a / len(decided) if decided else 0.0,
        ci_a=wilson_ci(wins_a, len(decided)),
        as_first=_split(played, 0),
        as_second=_split(played, 1),
    )


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def format_report(r: WinrateReport) -> str:
    """文本报告：meta 全要素回显 + 胜率/CI/先后手/平局/失败。"""
    seeds = f"{r.seed_min}..{r.seed_max}" if r.seed_min is not None else "（无局）"
    lines = [
        f"实验 #{r.experiment_id}「{r.name}」胜率报告",
        (f"meta：种子区间 {seeds} / 代码 {r.code_version} / 数据 {r.data_version}"
         f" / 局数 {r.games_total}"),
        (f"完成 {r.games_played} 局（决定局 {r.decided}，平 {r.draws}，失败 {r.games_failed}）"
         f"，平均回合 {r.avg_turns:.1f}"),
        (f"A 胜 {r.wins_a} / B 胜 {r.wins_b} —— A 胜率 {_pct(r.wr_a)}"
         f"（Wilson 95% CI {_pct(r.ci_a[0])}..{_pct(r.ci_a[1])}，分母=决定局）"),
        (f"先攻时 A 胜率 {_pct(r.as_first.wr_a)}（{r.as_first.wins_a}/{r.as_first.decided}，"
         f"CI {_pct(r.as_first.ci_a[0])}..{_pct(r.as_first.ci_a[1])}）"),
        (f"后攻时 A 胜率 {_pct(r.as_second.wr_a)}（{r.as_second.wins_a}/{r.as_second.decided}，"
         f"CI {_pct(r.as_second.ci_a[0])}..{_pct(r.as_second.ci_a[1])}）"),
    ]
    return "\n".join(lines)
