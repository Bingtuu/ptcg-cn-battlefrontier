"""败局解剖分节（task 124）：终局类型 × 死亡回合分桶 + 每桶抽样回放。

数据只读结果库 `games` / `game_events`（game_over 的 detail.reason 与 knockout
事件 turn），不改事件流产生逻辑。仅统计决定局（平局与失败局不计）。
回放复用 task 120 对局包导出路径（render_log + deviation_html）。

死亡回合口径（写进分节头注）：败方最后一只宝可梦昏厥所在回合（kind=knockout
且 player=败方事件的最大 turn）；deck_out 类取 game_over 事件 turn。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.engine.events import GameEvent
from battlefrontier.report import SIM_INTERPRETATION_NOTE
from battlefrontier.report.deviation_pack import deviation_html
from battlefrontier.report.render import render_log
from battlefrontier.runner.results_db import ResultsDB

DEATH_BUCKETS = ("≤6", "7–9", "10–12", "13–15", ">15")
REASON_ROWS = ("prizes", "no_pokemon", "deck_out", "其他")
KNOWN_REASONS = frozenset(REASON_ROWS[:-1])


@dataclass(frozen=True)
class AutopsySample:
    game_id: int
    seed: int
    death_turn: int


@dataclass(frozen=True)
class AutopsyCell:
    loser: int            # 0 = A 负，1 = B 负
    reason: str
    bucket: int
    count: int
    samples: tuple[AutopsySample, ...]


@dataclass(frozen=True)
class AutopsyReport:
    experiment_id: int
    name: str
    decided: int
    wins_a: int
    wins_b: int
    cells: tuple[AutopsyCell, ...]

    def cell(self, loser: int, reason: str, bucket: int) -> AutopsyCell:
        for c in self.cells:
            if c.loser == loser and c.reason == reason and c.bucket == bucket:
                return c
        raise KeyError((loser, reason, bucket))

    def count(self, loser: int, reason: str, bucket: int) -> int:
        return self.cell(loser, reason, bucket).count


def death_bucket(turn: int) -> int:
    if turn <= 6:
        return 0
    if turn <= 9:
        return 1
    if turn <= 12:
        return 2
    if turn <= 15:
        return 3
    return 4


def _events(db: ResultsDB, game_id: int) -> list[GameEvent]:
    loaded: list[GameEvent] = []
    for row in db.game_events(game_id):
        loaded.append(GameEvent.model_validate(json.loads(row["event_json"])))
    return loaded


def autopsy_report(db: ResultsDB, experiment_id: int, *,
                   sample_n: int = 1) -> AutopsyReport:
    """终局类型 × 死亡回合分桶矩阵；每桶按 (seed, id) 升序抽 sample_n 局。"""
    if sample_n < 0:
        raise ValueError("sample_n 不能为负")
    exp = db.experiment(experiment_id)
    pool: dict[tuple[int, str, int], list[tuple[int, int, int]]] = {}
    decided = wins_a = wins_b = 0
    for g in db.games(experiment_id):
        if g["error"] or g["is_draw"] or g["winner"] is None:
            continue
        decided += 1
        winner = int(g["winner"])
        loser = 1 - winner
        if winner == 0:
            wins_a += 1
        else:
            wins_b += 1
        over_turn: int | None = None
        reason = "其他"
        ko_turns: list[int] = []
        for ev in _events(db, int(g["id"])):
            if ev.kind == "knockout" and ev.player == loser:
                ko_turns.append(ev.turn)
            elif ev.kind == "game_over":
                r = str(ev.detail.get("reason") or "")
                reason = r if r in KNOWN_REASONS else "其他"
                over_turn = ev.turn
        if over_turn is None:
            continue
        if reason == "deck_out":
            death_turn = over_turn
        else:
            death_turn = max(ko_turns) if ko_turns else over_turn
        key = (loser, reason, death_bucket(death_turn))
        pool.setdefault(key, []).append((int(g["seed"]), int(g["id"]), death_turn))
    cells: list[AutopsyCell] = []
    for loser in (0, 1):
        for reason in REASON_ROWS:
            for bucket in range(len(DEATH_BUCKETS)):
                games = sorted(pool.get((loser, reason, bucket), []))
                samples = tuple(
                    AutopsySample(game_id=gid, seed=seed, death_turn=death)
                    for seed, gid, death in games[:sample_n]
                )
                cells.append(AutopsyCell(loser=loser, reason=reason,
                                         bucket=bucket, count=len(games),
                                         samples=samples))
    return AutopsyReport(experiment_id=exp["id"], name=exp["name"],
                         decided=decided, wins_a=wins_a, wins_b=wins_b,
                         cells=tuple(cells))


def write_autopsy_packs(directory: str | Path, rep: AutopsyReport,
                        db: ResultsDB) -> dict[int, dict[str, Path]]:
    """抽样局每局一个对局包子目录（log.md / log.html，task 120 渲染路径）。"""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[int, dict[str, Path]] = {}
    for cell in rep.cells:
        for sample in cell.samples:
            if sample.game_id in paths:
                continue
            text = render_log(_events(db, sample.game_id))
            gdir = out / f"game-{sample.game_id}"
            gdir.mkdir(parents=True, exist_ok=True)
            markdown = (
                f"# 对局包：实验 #{rep.experiment_id}「{rep.name}」"
                f"局 #{sample.game_id}（种子 {sample.seed}）\n\n"
                f"终局类型 {cell.reason}，死亡回合 {sample.death_turn}。\n\n"
                "```\n" + (text or "（空事件流）") + "\n```\n"
            )
            md_path = gdir / "log.md"
            html_path = gdir / "log.html"
            md_path.write_text(markdown, encoding="utf-8")
            html_path.write_text(deviation_html(markdown), encoding="utf-8")
            paths[sample.game_id] = {"md": md_path, "html": html_path}
    return paths


def format_autopsy(rep: AutopsyReport,
                   paths: dict[int, dict[str, Path]] | None = None) -> str:
    lines = [
        "败局解剖（task 124）：仅决定局（平局与失败局不计）",
        ("死亡回合口径：败方最后一只宝可梦昏厥所在回合（kind=knockout 且 "
         "player=败方事件的最大 turn）；deck_out 类取 game_over 事件 turn"),
    ]
    for loser, who in ((0, "A"), (1, "B")):
        side_losses = sum(
            rep.count(loser, reason, bucket)
            for reason in REASON_ROWS for bucket in range(len(DEATH_BUCKETS))
        )
        opp_wr = rep.wins_b / rep.decided if loser == 0 else rep.wins_a / rep.decided
        lines.append(
            f"{who} 负：{side_losses} 局 / 决定局 {rep.decided} 局"
            f"（对方胜率 {opp_wr * 100:.1f}%）"
        )
        lines.append("终局类型 \\ 死亡回合 | " + " | ".join(DEATH_BUCKETS))
        for reason in REASON_ROWS:
            row = [reason]
            for bucket in range(len(DEATH_BUCKETS)):
                row.append(str(rep.count(loser, reason, bucket)))
            lines.append(" | ".join(row))
        for reason in REASON_ROWS:
            for bucket in range(len(DEATH_BUCKETS)):
                cell = rep.cell(loser, reason, bucket)
                for sample in cell.samples:
                    tail = ""
                    if paths and sample.game_id in paths:
                        tail = " → " + " ".join(
                            str(p) for p in paths[sample.game_id].values())
                    lines.append(
                        f"  样本 {who}负 {reason} × {DEATH_BUCKETS[bucket]}："
                        f"局 #{sample.game_id}（种子 {sample.seed}，"
                        f"死亡回合 {sample.death_turn}）{tail}"
                    )
    lines.append(SIM_INTERPRETATION_NOTE)
    return "\n".join(lines)
