"""M13：赛事级开发/验证切分与报告。"""

from __future__ import annotations

import sqlite3

import pytest
import yaml

from battlefrontier.data.pairings import pairing_contrast
from battlefrontier.data.validation import tournament_time_split


def _tournament_db(tmp_path):
    path = tmp_path / "validation.db"
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
        "INSERT INTO v_tournament_weights VALUES (?, ?, ?, ?)",
        [
            ("t1", "2025-01-01", "master", "intl_aligned"),
            ("t2", "2025-01-02", "master", "intl_aligned"),
            ("t3", "2025-01-02", "master", "intl_aligned"),
            ("t4", "2025-01-03", "master", "intl_aligned"),
            ("t5", "2025-01-04", "master", "intl_aligned"),
            ("t6", "2025-01-05", "senior", "intl_aligned"),
            ("t7", "2025-01-06", "master", "cn"),
        ],
    )
    conn.executemany(
        "INSERT INTO v_pairing_players VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("t1", 1, 1, 1, "Alpha", "Beta", 1),
            ("t2", 1, 1, 1, "Alpha", "Beta", 2),
            ("t3", 1, 1, 1, "Alpha", "Beta", 0),
            ("t4", 1, 1, 1, "Alpha", "Beta", 1),
            ("t5", 1, 1, 1, "Alpha", "Beta", 2),
        ],
    )
    conn.commit()
    conn.close()
    return path


def test_time_split_uses_ordered_ids_across_same_date_boundary(tmp_path):
    split = tournament_time_split(
        _tournament_db(tmp_path), date_from="2025-01-01", date_to="2025-12-31",
        basis="intl_aligned", division="master",
    )
    assert split.development_ids == ("t1", "t2", "t3")
    assert split.validation_ids == ("t4", "t5")
    assert split.meta["development_last"] == "t3"
    assert split.meta["validation_first"] == "t4"


def test_time_split_rejects_empty_tournament_set(tmp_path):
    with pytest.raises(ValueError, match="赛事为空"):
        tournament_time_split(
            _tournament_db(tmp_path), date_from="2030-01-01", date_to="2030-12-31",
            basis="intl_aligned", division="master",
        )


def test_time_split_rejects_invalid_fraction(tmp_path):
    with pytest.raises(ValueError, match="development_fraction"):
        tournament_time_split(
            _tournament_db(tmp_path), date_from="2025-01-01", date_to="2025-12-31",
            basis="intl_aligned", division="master", development_fraction=1.0,
        )


def test_time_split_rejects_empty_side_from_small_cut(tmp_path):
    with pytest.raises(ValueError, match="切分两侧均须非空"):
        tournament_time_split(
            _tournament_db(tmp_path), date_from="2025-01-01", date_to="2025-01-02",
            basis="intl_aligned", division="master", development_fraction=0.1,
        )


def test_time_split_wraps_unreadable_tournament_view(tmp_path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    with pytest.raises(ValueError, match="赛事视图不可读"):
        tournament_time_split(
            path, date_from="2025-01-01", date_to="2025-12-31",
            basis="intl_aligned", division="master",
        )


def test_frozen_protocol_counts_and_boundary():
    with open("config/m13-validation-v1.yml", encoding="utf-8") as fh:
        protocol = yaml.safe_load(fh)
    assert protocol["method"] == "time-70-30"
    assert protocol["development_fraction"] == 0.7
    assert protocol["tournament_count"] == 409
    assert protocol["development_count"] == 286
    assert protocol["validation_count"] == 123
    assert protocol["development_last"] == "limitless:687aa6f4164bc0b13840661e"
    assert protocol["validation_first"] == "limitless:687ec868164bc0b138408fc9"


def test_contrast_can_filter_exact_tournament_ids(tmp_path):
    path = _tournament_db(tmp_path)
    selected = pairing_contrast(
        path, ["Alpha", "Beta"], date_from="2025-01-01",
        date_to="2025-12-31", basis="intl_aligned", tournament_ids=("t1", "t2"),
    )
    by = {(c.archetype, c.opponent): c for c in selected.cells}
    assert by[("Alpha", "Beta")].n == 2
    assert by[("Alpha", "Beta")].wins == 1
    assert selected.sample_total == 2
    empty = pairing_contrast(
        path, ["Alpha", "Beta"], date_from="2025-01-01",
        date_to="2025-12-31", basis="intl_aligned", tournament_ids=("not-present",),
    )
    assert empty.cells == () and empty.sample_total == 0


def test_contrast_rejects_empty_explicit_tournament_ids(tmp_path):
    with pytest.raises(ValueError, match="tournament_ids 为空"):
        pairing_contrast(
            _tournament_db(tmp_path), ["Alpha", "Beta"], date_from="2025-01-01",
            date_to="2025-12-31", basis="intl_aligned", tournament_ids=(),
        )
