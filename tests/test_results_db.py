"""task 019：结果库三层表（PRD §8.3，FR-10 契约：独立 SQLite WAL，主库只读）。"""

import json
import sqlite3

import pytest
from helpers import deck60

from battlefrontier.runner.play import play_game
from battlefrontier.runner.results_db import ResultsDB


@pytest.fixture()
def rdb(tmp_path):
    db = ResultsDB(tmp_path / "results.db")
    yield db
    db.close()


def _stub_result(seed: int = 7):
    return play_game(deck60(), deck60(), seed=seed)


def test_schema_three_tables_and_wal(rdb):
    tables = {
        r[0] for r in rdb._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"experiments", "games", "game_events"} <= tables
    assert rdb._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_experiment_lifecycle(rdb):
    exp_id = rdb.start_experiment(
        name="t", definition_yaml="name: t\ngames: 1\n",
        code_version="abc1234", data_version="2026-08-09 (user_version=13)")
    row = rdb._conn.execute(
        "SELECT name, definition_yaml, code_version, data_version, status "
        "FROM experiments WHERE id=?", (exp_id,)).fetchone()
    assert row == ("t", "name: t\ngames: 1\n", "abc1234", "2026-08-09 (user_version=13)", "running")
    rdb.finish_experiment(exp_id)
    assert rdb._conn.execute(
        "SELECT status FROM experiments WHERE id=?", (exp_id,)).fetchone()[0] == "done"


def test_record_game_with_events(rdb):
    exp_id = rdb.start_experiment(
        name="t", definition_yaml="x", code_version="v", data_version="d")
    result = _stub_result()
    game_id = rdb.record_game(
        exp_id, seed=42, first_player=0, result=result,
        deck_a_id="stub-a", deck_b_id="stub-b")
    row = rdb._conn.execute(
        "SELECT experiment_id, seed, first_player, winner, is_draw, turns, events_hash, "
        "deck_a_id, deck_b_id FROM games WHERE id=?", (game_id,)).fetchone()
    assert row == (exp_id, 42, 0, result.winner, int(result.is_draw), result.turns,
                   result.events_hash, "stub-a", "stub-b")
    events = rdb.game_events(game_id)
    assert len(events) == len(result.events)
    assert [e["seq"] for e in events] == list(range(len(result.events)))
    json.loads(events[0]["event_json"])  # 事件流完整可重取


def test_games_query_for_determinism_check(rdb):
    exp_id = rdb.start_experiment(
        name="t", definition_yaml="x", code_version="v", data_version="d")
    for seed in (100, 101):
        rdb.record_game(exp_id, seed=seed, first_player=0, result=_stub_result(seed),
                        deck_a_id="a", deck_b_id="b")
    rows = rdb.games(exp_id)
    assert [r["seed"] for r in rows] == [100, 101]
    assert {"seed", "winner", "is_draw", "turns", "events_hash"} <= set(rows[0])


def test_results_db_is_separate_sqlite(tmp_path):
    """结果库独立落盘（FR-10）：文件可独立打开，不依赖主库。"""
    path = tmp_path / "results.db"
    db = ResultsDB(path)
    db.close()
    conn = sqlite3.connect(path)
    try:
        assert conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] >= 3
    finally:
        conn.close()
