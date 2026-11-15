"""task 125：matchup 快照导出器（bfsim matchup-snap，四期 M14 gate 操作包）。

验收对拍：snap 文件逐格 == assemble_matrix 输出（共享装配函数）；
meta 带窗口/数据版本/限定语；快照可回喂 field-pick --matrix-snap。
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from battlefrontier.cli import main
from battlefrontier.report.field_pick import (
    QUALIFIER_HEADER,
    assemble_matrix,
    export_matchup_snapshot,
    intl_cells_from_db,
    load_matrix_snapshot,
)

POOL_YML = """
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
  - {archetype: 丙, en_archetype: Gamma, wur: 0.1, n: 5, deck_id: "mik_moe:3"}
"""

DATE_FROM = "2025-04-11"
DATE_TO = "2025-08-31"


def _intl_db(tmp_path):
    """最小 intl 对阵库：Alpha/Beta 有对局（含一小样本对），Gamma 无。"""
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
        [("t1", "2025-05-01", "master", "intl_aligned")],
    )
    conn.executemany(
        "INSERT INTO v_pairing_players VALUES (?,?,?,?,?,?,?)",
        [
            ("t1", 1, 1, 1, "Alpha", "Beta", 1),
            ("t1", 1, 1, 2, "Alpha", "Beta", 1),
            ("t1", 1, 1, 3, "Alpha", "Beta", 2),
            ("t1", 1, 1, 4, "Beta", "Gamma", 1),
            ("t1", 1, 1, 5, "Beta", "Gamma", 1),
        ],
    )
    conn.commit()
    conn.close()
    return path


def _pool(tmp_path):
    p = tmp_path / "pool.yml"
    p.write_text(POOL_YML, encoding="utf-8")
    return p


def _field(tmp_path):
    p = tmp_path / "field.json"
    p.write_text(json.dumps({"decks": [
        {"display_name": "甲", "value": 2.0},
        {"display_name": "乙", "value": 1.0},
    ]}), encoding="utf-8")
    return p


EN_NAMES = ["Alpha", "Beta", "Gamma"]


def _snap_meta():
    return {
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "basis": "intl_aligned",
        "division": "master",
        "data_version": 9,
        "qualifier": QUALIFIER_HEADER,
    }


# ── 验收 2：逐格一致（共享装配函数）─────────────────────────


def test_snap_逐格等于_assemble_matrix(tmp_path):
    db = _intl_db(tmp_path)
    intl_cells = intl_cells_from_db(db, EN_NAMES, DATE_FROM, DATE_TO)
    snap = export_matchup_snapshot(intl_cells, [], EN_NAMES, _snap_meta())
    ref = assemble_matrix(intl_cells, [], EN_NAMES)

    by_pair = {(c["a"], c["b"]): c for c in snap["cells"]}
    assert by_pair.keys() == ref.keys()
    for pair, cell in ref.items():
        got = by_pair[pair]
        assert got["winrate"] == pytest.approx(cell.wr_a)
        assert got["n"] == cell.n
        assert got["source"] == cell.source
        assert got["shrunk"] == cell.shrunk
        assert got["low_confidence"] == (cell.source == "missing")


def test_intl_cells_from_db_与内联装配同源(tmp_path):
    """共享函数 == CLI 原内联逻辑（pairing_contrast + intl_cells_from_contrast）。"""
    from battlefrontier.data.pairings import pairing_contrast
    from battlefrontier.report.field_pick import intl_cells_from_contrast

    db = _intl_db(tmp_path)
    inline = intl_cells_from_contrast(pairing_contrast(
        db, EN_NAMES, date_from=DATE_FROM, date_to=DATE_TO,
        basis="intl_aligned", division="master"))
    assert intl_cells_from_db(db, EN_NAMES, DATE_FROM, DATE_TO) == inline


# ── 验收 1：schema / meta / 收缩与 low_confidence 标注 ──────


def test_snap_meta_窗口数据版本限定语(tmp_path):
    db = _intl_db(tmp_path)
    snap = export_matchup_snapshot(
        intl_cells_from_db(db, EN_NAMES, DATE_FROM, DATE_TO), [],
        EN_NAMES, _snap_meta())
    assert snap["meta"]["date_from"] == DATE_FROM
    assert snap["meta"]["date_to"] == DATE_TO
    assert snap["meta"]["data_version"] == 9
    assert "弱参照" in snap["meta"]["qualifier"]
    assert "同模拟器内" in snap["meta"]["qualifier"]
    assert snap["schema_version"] >= 1


def test_snap_收缩与缺格标注(tmp_path):
    """小样本真实格 shrunk=True 且胜率向 50% 收；无数据格 low_confidence=True。"""
    db = _intl_db(tmp_path)
    intl_cells = intl_cells_from_db(db, EN_NAMES, DATE_FROM, DATE_TO)
    by_pair = {(c.a, c.b): c for c in intl_cells}
    assert by_pair[("Beta", "Gamma")].n == 2  # < PAIR_MIN_N → 收缩

    snap = export_matchup_snapshot(intl_cells, [], EN_NAMES, _snap_meta())
    cells = {(c["a"], c["b"]): c for c in snap["cells"]}
    shrunk_cell = cells[("Beta", "Gamma")]
    assert shrunk_cell["shrunk"] and shrunk_cell["n"] == 2
    assert shrunk_cell["winrate"] == pytest.approx((2 * 1.0 + 10) / 22)
    mirror = cells[("Gamma", "Beta")]
    assert mirror["source"] == "intl" and mirror["shrunk"]
    assert mirror["winrate"] == pytest.approx(1 - shrunk_cell["winrate"])
    assert cells[("Alpha", "Gamma")]["low_confidence"]
    assert cells[("Alpha", "Gamma")]["winrate"] == 0.5


def test_load_matrix_snapshot_回读(tmp_path):
    db = _intl_db(tmp_path)
    snap = export_matchup_snapshot(
        intl_cells_from_db(db, EN_NAMES, DATE_FROM, DATE_TO), [],
        EN_NAMES, _snap_meta())
    p = tmp_path / "snap.json"
    p.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    cells, meta = load_matrix_snapshot(p)
    assert meta["date_from"] == DATE_FROM
    by_pair = {(c.a, c.b): c for c in cells}
    assert by_pair[("Beta", "Gamma")].shrunk  # 收缩标记回读保留
    assert by_pair[("Alpha", "Gamma")].source == "missing"


# ── CLI：matchup-snap 落盘 + field-pick 回喂 ────────────────


def test_matchup_snap_CLI_落盘(tmp_path, capsys):
    db = _intl_db(tmp_path)
    pool = _pool(tmp_path)
    out = tmp_path / "snap.json"
    rc = main(["matchup-snap", "--pool", str(pool), "--intl-db", str(db),
               "--from", DATE_FROM, "--to", DATE_TO, "--out", str(out)])
    assert rc == 0 and out.exists()
    snap = json.loads(out.read_text(encoding="utf-8"))
    assert snap["meta"]["date_from"] == DATE_FROM
    assert snap["meta"]["data_version"] == 9  # 池版本进 meta
    assert len(snap["cells"]) == 9  # 3 池：3×2 非镜像全有向格 + 3 镜像默认格（v0.3/task 140）


def test_field_pick_matrix_snap_回喂与内联一致(tmp_path, capsys):
    """验收 3：快照直接喂 field-pick，输出与 intl-db 内联装配逐字一致。"""
    db = _intl_db(tmp_path)
    pool = _pool(tmp_path)
    field = _field(tmp_path)
    out = tmp_path / "snap.json"
    main(["matchup-snap", "--pool", str(pool), "--intl-db", str(db),
          "--from", DATE_FROM, "--to", DATE_TO, "--out", str(out)])
    capsys.readouterr()  # 消费导出回显，避免污染后续对拍

    base_args = ["field-pick", "--field", str(field), "--pool", str(pool),
                 "--n-sim", "50"]
    main(base_args + ["--intl-db", str(db), "--from", DATE_FROM,
                      "--to", DATE_TO])
    inline_text = capsys.readouterr().out

    main(base_args + ["--matrix-snap", str(out)])
    snap_text = capsys.readouterr().out
    assert snap_text == inline_text


def test_field_pick_matrix_snap_与_intl_db_冲突(tmp_path, capsys):
    db = _intl_db(tmp_path)
    pool = _pool(tmp_path)
    field = _field(tmp_path)
    out = tmp_path / "snap.json"
    main(["matchup-snap", "--pool", str(pool), "--intl-db", str(db),
          "--from", DATE_FROM, "--to", DATE_TO, "--out", str(out)])
    rc = main(["field-pick", "--field", str(field), "--pool", str(pool),
               "--intl-db", str(db), "--matrix-snap", str(out)])
    assert rc == 1
    assert "冲突" in capsys.readouterr().out
