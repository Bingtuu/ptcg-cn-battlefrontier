"""M13：真实赛事的开发/验证切分（只读、确定性）。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TournamentSplit:
    development_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    meta: dict


def tournament_time_split(
    db_path: str | Path,
    *,
    date_from: str,
    date_to: str,
    basis: str,
    division: str = "master",
    development_fraction: float = 0.7,
) -> TournamentSplit:
    """按 (date, tournament_id) 排序后取前 70% 开发，其余验证。"""
    if not 0 < development_fraction < 1:
        raise ValueError("development_fraction 必须在 (0,1) 内")
    path = Path(db_path).resolve()
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        try:
            rows = conn.execute(
                "SELECT tournament_id, date FROM v_tournament_weights "
                "WHERE date BETWEEN ? AND ? AND basis = ? "
                "AND (division = ? OR division IS NULL) "
                "ORDER BY date, tournament_id",
                (date_from, date_to, basis, division),
            ).fetchall()
        except sqlite3.Error as e:
            raise ValueError(f"赛事视图不可读：{e}") from e
    finally:
        conn.close()
    if len(rows) < 2:
        raise ValueError("赛事为空或不足以切分")
    cut = int(len(rows) * development_fraction)
    if not 1 <= cut < len(rows):
        raise ValueError("切分两侧均须非空")
    development = tuple(str(row[0]) for row in rows[:cut])
    validation = tuple(str(row[0]) for row in rows[cut:])
    meta = {
        "method": "time-70-30",
        "development_fraction": development_fraction,
        "tournament_count": len(rows),
        "development_count": len(development),
        "validation_count": len(validation),
        "development_last": development[-1],
        "validation_first": validation[0],
        "development_date_last": rows[cut - 1][1],
        "validation_date_first": rows[cut][1],
    }
    return TournamentSplit(development, validation, meta)
