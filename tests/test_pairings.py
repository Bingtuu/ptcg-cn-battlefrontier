"""task 073：只读对阵对照。临时库，不填正式数字。"""

import json
import sqlite3

from battlefrontier.cli import main
from battlefrontier.data.pairings import pairing_contrast
from battlefrontier.report.pairing_pack import (
    format_pairing_contrast,
    write_pairing_pack,
)

POOL = """
version: 9
locked_at: "2026-10-28"
query:
  window: "2025-04-11..2025-08-31"
  division: master
  basis: intl_aligned
  min_n: 1
  n_tournaments: 1
  snapshot: standard-2026-09-16
  name_group_rules_hash: abc
decks:
  - {archetype: 甲, en_archetype: Alpha, wur: 0.6, n: 10, deck_id: "mik_moe:1"}
  - {archetype: 乙, en_archetype: Beta, wur: 0.4, n: 10, deck_id: "mik_moe:2"}
"""


def _db(tmp_path):
    path = tmp_path / "p.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE v_tournament_weights (
          tournament_id TEXT, date TEXT, division TEXT, basis TEXT
        );
        CREATE TABLE v_pairing_players (
          tournament_id TEXT, phase INT, round INT, table_no INT,
          archetype_name_1 TEXT, archetype_name_2 TEXT, winner_side INT
        );
        """
    )
    conn.executemany(
        "INSERT INTO v_tournament_weights VALUES (?,?,?,?)",
        [
            ("t1", "2025-05-01", "master", "intl_aligned"),
            ("t2", "2024-01-01", "master", "intl_aligned"),
            ("t3", "2025-06-01", "senior", "intl_aligned"),
            ("t4", "2025-06-01", "master", "cn"),
        ],
    )
    conn.executemany(
        "INSERT INTO v_pairing_players VALUES (?,?,?,?,?,?,?)",
        [
            ("t1", 1, 1, 1, "Alpha", "Beta", 1),
            ("t1", 1, 1, 2, "Alpha", "Beta", 2),
            ("t1", 1, 1, 3, "Alpha", "Alpha", 1),
            ("t1", 1, 1, 4, "Alpha", "Beta", 0),
            ("t2", 1, 1, 1, "Alpha", "Beta", 1),
            ("t3", 1, 1, 1, "Alpha", "Beta", 1),
            ("t4", 1, 1, 1, "Alpha", "Beta", 1),
            ("t1", 1, 2, 1, "Gamma", "Beta", 1),
        ],
    )
    conn.commit()
    conn.close()
    return path


def test_contrast_keeps_only_in_pool_decided_games(tmp_path) -> None:
    rep = pairing_contrast(
        _db(tmp_path), ["Alpha", "Beta"],
        date_from="2025-04-11", date_to="2025-08-31", basis="intl_aligned",
    )
    by = {(c.archetype, c.opponent): c for c in rep.cells}
    assert by[("Alpha", "Beta")].n == 2
    assert by[("Alpha", "Beta")].wins == 1
    assert by[("Beta", "Alpha")].wins == 1
    assert rep.sample_total == 3
    assert [row.winner_side for row in rep.sample] == [1, 2, 0]
    assert all(row.archetype_1 != row.archetype_2 for row in rep.sample)


def test_readonly_refuses_insert(tmp_path) -> None:
    path = _db(tmp_path)
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        try:
            conn.execute("INSERT INTO v_pairing_players VALUES ('x',1,1,1,'A','B',1)")
        except sqlite3.OperationalError:
            return
        raise AssertionError("只读连接不应写入")
    finally:
        conn.close()


def test_pack_shares_cell_numbers(tmp_path) -> None:
    rep = pairing_contrast(
        _db(tmp_path), ["Alpha", "Beta"],
        date_from="2025-04-11", date_to="2025-08-31", basis="intl_aligned",
        sample_limit=1,
    )
    paths = write_pairing_pack(tmp_path / "pack", rep)
    text = format_pairing_contrast(rep)
    assert text in paths["md"].read_text(encoding="utf-8")
    assert "Alpha vs Beta" in paths["html"].read_text(encoding="utf-8")
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["cells"][0]["n"] == rep.cells[0].n
    assert payload["cells"][0]["wins"] == rep.cells[0].wins
    assert payload["cells"][0]["winrate"] == rep.cells[0].winrate
    assert payload["sample_total"] == 3
    assert len(payload["sample"]) == 1


def test_cli_pairings_writes_pack(tmp_path, capsys) -> None:
    pool = tmp_path / "pool.yml"
    pool.write_text(POOL, encoding="utf-8")
    out = tmp_path / "out"
    rc = main([
        "pairings", "--pool", str(pool), "--db", str(_db(tmp_path)),
        "--date-from", "2025-04-11", "--date-to", "2025-08-31",
        "--basis", "intl_aligned", "--out", str(out),
    ])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "n=2" in captured and "对阵包：" in captured
    assert (out / "pairings.csv").is_file()
    assert (out / "pairings.md").is_file()
