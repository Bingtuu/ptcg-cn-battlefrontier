"""精简对局日志（task 074）。

数据只来自结果库 `games` 与 `game_events`。不新造事件，不编造理由，
不列出每步合法行动。回放走 `render_log`，只抽完成局里种子最小的若干局。
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.engine.events import GameEvent
from battlefrontier.report.deviation_pack import deviation_html
from battlefrontier.report.render import render_log
from battlefrontier.report.winrate import (
    WinrateReport,
    format_report,
    wilson_ci,
    winrate_report,
)
from battlefrontier.runner.results_db import ResultsDB

MAIN_PHASE_KINDS = frozenset({
    "attack", "retreat", "play_trainer", "play_stadium",
    "evolve", "attach_energy", "end_turn",
})
DEFAULT_REPLAY_SAMPLE = 3


@dataclass(frozen=True)
class GameSummaryRow:
    game_id: int
    seed: int
    first_player: int
    winner: int | None
    is_draw: bool
    turns: int
    error: str | None


@dataclass(frozen=True)
class ActionStat:
    side: int
    kind: str
    label: str
    occurrences: int
    games: int
    wins: int
    winrate: float
    ci: tuple[float, float]


@dataclass(frozen=True)
class ReplaySample:
    experiment_id: int
    game_id: int
    seed: int
    text: str


@dataclass(frozen=True)
class BattleLogReport:
    winrate: WinrateReport
    summaries: tuple[GameSummaryRow, ...]
    actions: tuple[ActionStat, ...]
    replays: tuple[ReplaySample, ...]


def action_label(kind: str, detail: dict) -> str:
    """主阶段事件的可读标签。不用模型补全缺失字段。"""
    if kind == "attack":
        name = str(detail.get("name") or "")
        attack = str(detail.get("attack") or "")
        if name and attack:
            return f"{name}：{attack}"
        return attack or name or kind
    if kind == "retreat":
        return f"{detail.get('out', '')}→{detail.get('into', '')}"
    if kind == "evolve":
        return f"{detail.get('onto', '')}→{detail.get('name', '')}"
    if kind == "attach_energy":
        return str(detail.get("target") or kind)
    if kind in ("play_trainer", "play_stadium"):
        return str(detail.get("name") or kind)
    if kind == "end_turn":
        return "end_turn"
    return kind


def _events(db: ResultsDB, game_id: int) -> list[GameEvent]:
    loaded: list[GameEvent] = []
    for row in db.game_events(game_id):
        loaded.append(GameEvent.model_validate(json.loads(row["event_json"])))
    return loaded


def _summaries(rows: list[dict]) -> tuple[GameSummaryRow, ...]:
    return tuple(
        GameSummaryRow(
            game_id=int(g["id"]), seed=int(g["seed"]),
            first_player=int(g["first_player"]),
            winner=None if g["winner"] is None else int(g["winner"]),
            is_draw=bool(g["is_draw"]), turns=int(g["turns"]),
            error=g["error"],
        )
        for g in rows
    )


def _actions(db: ResultsDB, rows: list[dict]) -> tuple[ActionStat, ...]:
    occurrences: dict[tuple, int] = {}
    covered: dict[tuple, set[int]] = {}
    wins: dict[tuple, set[int]] = {}
    for game in rows:
        if game["error"]:
            continue
        gid = int(game["id"])
        decided = not game["is_draw"]
        winner = game["winner"]
        for ev in _events(db, gid):
            if ev.kind not in MAIN_PHASE_KINDS or ev.player is None:
                continue
            label = action_label(ev.kind, ev.detail)
            key = (int(ev.player), ev.kind, label)
            occurrences[key] = occurrences.get(key, 0) + 1
            if not decided:
                continue
            covered.setdefault(key, set()).add(gid)
            if winner == ev.player:
                wins.setdefault(key, set()).add(gid)
    stats: list[ActionStat] = []
    for side, kind, label in sorted(occurrences, key=lambda k: (k[0], k[1], k[2])):
        games_n = len(covered.get((side, kind, label), set()))
        wins_n = len(wins.get((side, kind, label), set()))
        stats.append(ActionStat(
            side=side, kind=kind, label=label,
            occurrences=occurrences[(side, kind, label)],
            games=games_n, wins=wins_n,
            winrate=wins_n / games_n if games_n else 0.0,
            ci=wilson_ci(wins_n, games_n),
        ))
    stats.sort(key=lambda s: (s.side, s.kind, -s.occurrences, s.label))
    return tuple(stats)


def sample_replays(db: ResultsDB, experiment_id: int, sample_n: int) -> tuple[ReplaySample, ...]:
    """完成局按 (seed, id) 取前 sample_n 局。sample_n=0 返回空。"""
    if sample_n < 0:
        raise ValueError("sample_n 不能为负")
    played = [g for g in db.games(experiment_id) if not g["error"]]
    played.sort(key=lambda g: (int(g["seed"]), int(g["id"])))
    picked = played[:sample_n]
    out: list[ReplaySample] = []
    for game in picked:
        text = render_log(_events(db, int(game["id"])))
        out.append(ReplaySample(
            experiment_id=experiment_id, game_id=int(game["id"]),
            seed=int(game["seed"]), text=text,
        ))
    return tuple(out)


def battle_log_report(db: ResultsDB, experiment_id: int, *,
                      sample_n: int = DEFAULT_REPLAY_SAMPLE) -> BattleLogReport:
    rows = db.games(experiment_id)
    return BattleLogReport(
        winrate=winrate_report(db, experiment_id),
        summaries=_summaries(rows),
        actions=_actions(db, rows),
        replays=sample_replays(db, experiment_id, sample_n),
    )


def format_game_summaries(rep: BattleLogReport) -> str:
    lines = ["每局汇总（默认开，一行一局）",
             "game_id | seed | first | winner | draw | turns | error"]
    for row in rep.summaries:
        winner = "" if row.winner is None else str(row.winner)
        err = row.error or ""
        lines.append(
            f"{row.game_id} | {row.seed} | {row.first_player} | {winner}"
            f" | {int(row.is_draw)} | {row.turns} | {err}"
        )
    return "\n".join(lines)


def format_main_actions(rep: BattleLogReport) -> str:
    lines = ["主阶段行动 × 胜率（决定局为分母；平局计次数不计胜率）"]
    if not rep.actions:
        lines.append("（无主阶段行动事件）")
        return "\n".join(lines)
    side_name = {0: "A", 1: "B"}
    for stat in rep.actions:
        who = side_name.get(stat.side, str(stat.side))
        lines.append(
            f"{who} {stat.kind} {stat.label}："
            f"{stat.occurrences} 次 / {stat.games} 局 "
            f"胜率 {stat.winrate * 100:.1f}%"
            f"（CI {stat.ci[0] * 100:.1f}..{stat.ci[1] * 100:.1f}）"
        )
    return "\n".join(lines)


def format_replays(rep: BattleLogReport) -> str:
    if not rep.replays:
        return "抽样回放：无（完成局为 0，或 sample 为 0）"
    lines = [f"抽样回放：{len(rep.replays)} 局（完成局按种子升序，不渲染全部）"]
    for replay in rep.replays:
        lines.append(f"## 实验 #{replay.experiment_id} 种子 {replay.seed} 局 #{replay.game_id}")
        lines.append(replay.text or "（空事件流）")
    return "\n".join(lines)


def battle_log_markdown(rep: BattleLogReport) -> str:
    name = rep.winrate.name
    return (
        f"# 对局日志：{name}\n\n"
        "以下三段与命令行打印的格式化原文相同，不另算数字。\n\n"
        "## 胜率\n\n```\n"
        f"{format_report(rep.winrate)}\n"
        "```\n\n## 汇总\n\n```\n"
        f"{format_game_summaries(rep)}\n"
        "```\n\n## 主阶段行动\n\n```\n"
        f"{format_main_actions(rep)}\n"
        "```\n\n## 回放\n\n```\n"
        f"{format_replays(rep)}\n"
        "```\n"
    )


def _summary_dict(row: GameSummaryRow) -> dict[str, object]:
    return {
        "game_id": row.game_id, "seed": row.seed,
        "first_player": row.first_player, "winner": row.winner,
        "is_draw": row.is_draw, "turns": row.turns, "error": row.error,
    }


def _action_dict(stat: ActionStat) -> dict[str, object]:
    return {
        "side": stat.side, "kind": stat.kind, "label": stat.label,
        "occurrences": stat.occurrences, "games": stat.games, "wins": stat.wins,
        "winrate": stat.winrate, "ci_low": stat.ci[0], "ci_high": stat.ci[1],
    }


def write_battle_log_pack(directory: str | Path, rep: BattleLogReport) -> dict[str, Path]:
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    markdown = battle_log_markdown(rep)
    paths = {
        "md": out / "log.md",
        "html": out / "log.html",
        "summary_csv": out / "summary.csv",
        "actions_csv": out / "actions.csv",
        "json": out / "log.json",
    }
    paths["md"].write_text(markdown, encoding="utf-8")
    paths["html"].write_text(deviation_html(markdown), encoding="utf-8")
    summaries = [_summary_dict(row) for row in rep.summaries]
    actions = [_action_dict(stat) for stat in rep.actions]
    summary_fields = [
        "game_id", "seed", "first_player", "winner", "is_draw", "turns", "error",
    ]
    _write_csv(paths["summary_csv"], summaries, summary_fields)
    action_fields = [
        "side", "kind", "label", "occurrences", "games", "wins",
        "winrate", "ci_low", "ci_high",
    ]
    _write_csv(paths["actions_csv"], actions, action_fields)
    payload = {
        "experiment_id": rep.winrate.experiment_id,
        "name": rep.winrate.name,
        "wr_a": rep.winrate.wr_a,
        "summaries": summaries,
        "actions": actions,
        "replays": [
            {"experiment_id": r.experiment_id, "game_id": r.game_id,
             "seed": r.seed, "text": r.text}
            for r in rep.replays
        ],
    }
    paths["json"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return paths


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if row.get(k) is None else row.get(k) for k in fields})
