"""task 127：联赛评级与报告。

bt_mle = Bradley-Terry MLE（MM 迭代，确定性）——联赛评级**主估计子**。
task 148 教训：固定大步长顺序 Elo 未收敛至自身数据的 BT-MLE，故顺序 Elo
不交付。Elo 标度换算仅作展示锚。
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from battlefrontier.report import SIM_INTERPRETATION_NOTE
from battlefrontier.runner.results_db import ResultsDB

_LN10 = math.log(10.0)


def bt_mle(games: list[tuple[str, str, float]], entities: list[str], *,
           tol: float = 1e-10, max_iters: int = 500) -> dict[str, float]:
    """Bradley-Terry 强度 MLE（MM 迭代）。

    games: (entity_a, entity_b, score_a)，score ∈ {1.0, 0.5, 0.0}（平局 0.5）。
    返回零均值 log-strength。聚合按 (x, y) 对计 [得分, 局数]，迭代确定性。
    """
    unknown = {a for a, _, _ in games} | {b for _, b, _ in games}
    unknown -= set(entities)
    if unknown:
        raise ValueError(f"对局含未注册 entity（不猜）: {sorted(unknown)}")

    obs: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for a, b, score in games:
        key = (a, b) if (a, b) in obs or (b, a) not in obs else (b, a)
        s = score if key == (a, b) else 1.0 - score
        obs[key][0] += s
        obs[key][1] += 1.0

    alpha = {e: 0.0 for e in entities}
    for _ in range(max_iters):
        step = {}
        for e in entities:
            o = x = 0.0
            for (p, q), (score, n) in obs.items():
                if p == e or q == e:
                    pe = 1.0 / (1.0 + math.exp(alpha[q] - alpha[p]))
                    o += score if p == e else n - score
                    x += n * (pe if p == e else 1.0 - pe)
            step[e] = math.log(max(o, 1e-12) / x) if x > 0 else 0.0
        m = sum(step.values()) / len(entities)
        delta = max(abs(step[e] - m) for e in entities)
        for e in entities:
            alpha[e] += step[e] - m
        if delta < tol:
            break
    return alpha


def elo_scale(log_strength: float) -> float:
    """log-strength → 传统 Elo 标度（仅展示锚：差 ln10 = 400 分）。"""
    return 1500.0 + 400.0 * log_strength / _LN10


@dataclass(frozen=True)
class RatingRow:
    agent: str
    log_strength: float
    elo: float


@dataclass(frozen=True)
class CellRecord:
    """(row, col) 视角：row agent 对 col agent 的胜/局（双向合并）。"""

    wins: int = 0
    games: int = 0


@dataclass
class LeagueReport:
    name: str
    ratings: list[RatingRow]                 # 按 log_strength 降序
    matrix: dict[tuple[str, str], CellRecord]
    registry_sha256: str
    games_total: int
    code_version: str
    data_version: str
    agents: list[str] = field(default_factory=list)

    def format_text(self) -> str:
        lines = [SIM_INTERPRETATION_NOTE, ""]
        lines.append(f"联赛：{self.name}　registry_sha256={self.registry_sha256}")
        lines.append(f"meta：局数 {self.games_total} / 代码 {self.code_version}"
                     f" / 数据 {self.data_version}")
        lines.append("")
        lines.append("BT-MLE 评级（主估计子；平局 0.5；零均值 log-strength）")
        for r in self.ratings:
            lines.append(f"  {r.agent:<20} {r.elo:8.1f}　(log={r.log_strength:+.4f})")
        lines.append("")
        lines.append("成对净胜率（行 vs 列，双向合并）")
        agents = self.agents
        lines.append("  " + " ".join(f"{c:>10}" for c in agents))
        for row in agents:
            cells = []
            for col in agents:
                rec = self.matrix.get((row, col))
                cells.append(f"{rec.wins}/{rec.games}" if rec else "-")
            lines.append(f"  {row:<4}" + " ".join(f"{c:>10}" for c in cells))
        return "\n".join(lines)


def league_report(results_path: str | Path, league_name: str) -> LeagueReport:
    """按 group_name 回收联赛细胞 → 评级 + 矩阵（error 局剔除，不猜）。"""
    db = ResultsDB(results_path)
    try:
        exps = db.experiments_by_group(league_name)
        if not exps:
            raise ValueError(f"结果库中无联赛「{league_name}」的细胞（不猜）")

        games: list[tuple[str, str, float]] = []
        matrix: dict[tuple[str, str], CellRecord] = {}
        registry_sha = ""
        agents: list[str] = []
        code_version = data_version = ""
        games_total = 0

        def rec(row: str, col: str) -> CellRecord:
            if (row, col) not in matrix:
                matrix[(row, col)] = CellRecord()
            return matrix[(row, col)]

        for e in exps:
            meta = yaml.safe_load(e["definition_yaml"]).get("league", {})
            a_id = meta["agents"]["a"]
            b_id = meta["agents"]["b"]
            for agent in (a_id, b_id):
                if agent not in agents:
                    agents.append(agent)
            registry_sha = registry_sha or meta.get("registry_sha256", "")
            code_version = code_version or e["code_version"]
            data_version = data_version or e["data_version"]
            for g in db.games(e["id"]):
                if g["error"] is not None or g["winner"] is None:
                    continue
                score = 0.5 if g["is_draw"] else (1.0 if g["winner"] == 0 else 0.0)
                games.append((a_id, b_id, score))
                r = rec(a_id, b_id)
                matrix[(a_id, b_id)] = CellRecord(
                    wins=r.wins + (1 if score == 1.0 else 0),
                    games=r.games + 1)
                r2 = rec(b_id, a_id)
                matrix[(b_id, a_id)] = CellRecord(
                    wins=r2.wins + (1 if score == 0.0 else 0),
                    games=r2.games + 1)
                games_total += 1

        strengths = bt_mle(games, agents)
        ratings = sorted(
            (RatingRow(a, strengths[a], elo_scale(strengths[a])) for a in agents),
            key=lambda r: -r.log_strength)
        return LeagueReport(
            name=league_name, ratings=ratings, matrix=matrix,
            registry_sha256=registry_sha, games_total=games_total,
            code_version=code_version, data_version=data_version,
            agents=agents)
    finally:
        db.close()
