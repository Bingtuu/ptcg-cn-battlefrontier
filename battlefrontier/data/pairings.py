"""池内 archetype 的真实逐桌对阵，只读，供校准对照（task 073）。

读 `v_pairing_players` ⋈ `v_tournament_weights`。不浏览全库：双方 archetype
都必须在调用方给出的集合里。镜像局不进。`winner_side` 为 0（平局或未报，
不猜）不进胜率分母，与 `ptcgdb` 的 `matchup.sql` 一致。连接是 SQLite
`mode=ro`。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PairingCell:
    """一个有向格：视角方 archetype 对 opponent。"""

    archetype: str
    opponent: str
    n: int
    wins: int

    @property
    def winrate(self) -> float:
        return self.wins / self.n if self.n else 0.0


@dataclass(frozen=True)
class PairingSample:
    """过滤后的一行原始对阵。抽样不是胜率分母。"""

    tournament_id: str
    phase: int
    round: int
    table_no: int
    archetype_1: str
    archetype_2: str
    winner_side: int


@dataclass(frozen=True)
class PairingContrast:
    archetypes: tuple[str, ...]
    date_from: str
    date_to: str
    basis: str
    division: str
    cells: tuple[PairingCell, ...]
    sample: tuple[PairingSample, ...]
    sample_total: int


def _connect_ro(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def pairing_contrast(
    db_path: str | Path,
    archetypes: list[str],
    *,
    date_from: str,
    date_to: str,
    basis: str,
    division: str = "master",
    sample_limit: int = 20,
) -> PairingContrast:
    """聚合有向格，并按稳定顺序保留前 sample_limit 行原始对阵。"""
    names = tuple(dict.fromkeys(archetypes))
    if not names:
        raise ValueError("archetypes 为空（不猜）")
    if sample_limit < 0:
        raise ValueError("sample_limit 不能为负")
    marks = ",".join("?" * len(names))
    sql = f"""
        SELECT pp.tournament_id, pp.phase, pp.round, pp.table_no,
               pp.archetype_name_1, pp.archetype_name_2, pp.winner_side
        FROM v_pairing_players pp
        JOIN v_tournament_weights t ON t.tournament_id = pp.tournament_id
        WHERE t.date BETWEEN ? AND ?
          AND t.basis = ?
          AND (t.division = ? OR t.division IS NULL)
          AND pp.archetype_name_1 IN ({marks})
          AND pp.archetype_name_2 IN ({marks})
          AND pp.archetype_name_1 <> pp.archetype_name_2
        ORDER BY pp.tournament_id, pp.phase, pp.round, pp.table_no
    """
    params = (date_from, date_to, basis, division, *names, *names)
    conn = _connect_ro(db_path)
    try:
        try:
            fetched = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as e:
            raise ValueError(
                "对阵视图不可读（需要 v_pairing_players 与 v_tournament_weights）"
                f": {e}"
            ) from e
    finally:
        conn.close()

    rows = [
        PairingSample(
            tournament_id=str(r[0]), phase=int(r[1]), round=int(r[2]),
            table_no=int(r[3]), archetype_1=str(r[4]), archetype_2=str(r[5]),
            winner_side=int(r[6]),
        )
        for r in fetched
    ]
    tallies: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        if row.winner_side not in (1, 2):
            continue
        pairs = (
            (row.archetype_1, row.archetype_2, row.winner_side == 1),
            (row.archetype_2, row.archetype_1, row.winner_side == 2),
        )
        for archetype, opponent, won in pairs:
            bucket = tallies.setdefault((archetype, opponent), [0, 0])
            bucket[1] += 1
            if won:
                bucket[0] += 1
    cells = tuple(
        PairingCell(archetype=key[0], opponent=key[1], wins=wins, n=n)
        for key, (wins, n) in sorted(
            tallies.items(), key=lambda item: (-item[1][1], item[0][0], item[0][1])
        )
    )
    return PairingContrast(
        archetypes=names, date_from=date_from, date_to=date_to, basis=basis,
        division=division, cells=cells, sample=tuple(rows[:sample_limit]),
        sample_total=len(rows),
    )
