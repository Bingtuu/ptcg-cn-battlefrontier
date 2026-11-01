from __future__ import annotations

import json
import sqlite3

import pytest

from battlefrontier.report.m14_decision import (
    BatchData,
    DecisionRecord,
    PatternSpec,
    discover_patterns,
    evaluate_pattern,
    load_action_records,
    load_decision_records,
    turn_bucket,
)


def _event(kind: str, player: int, turn: int, *, chosen: str | None = None,
           detail: dict | None = None) -> str:
    payload = {"kind": kind, "player": player, "turn": turn,
               "phase": "main", "detail": detail or {}}
    if chosen is not None:
        payload["detail"] = {"chosen": chosen, "chosen_visits": 50,
                             "total_visits": 100, "considered": []}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _db(path, rows: dict[int, list[str]]) -> str:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE games (
          id INTEGER PRIMARY KEY, experiment_id INTEGER NOT NULL, seed INTEGER NOT NULL,
          first_player INTEGER NOT NULL, winner INTEGER, is_draw INTEGER NOT NULL,
          turns INTEGER NOT NULL, events_hash TEXT NOT NULL, deck_a_id TEXT NOT NULL,
          deck_b_id TEXT NOT NULL, error TEXT
        );
        CREATE TABLE game_events (
          game_id INTEGER NOT NULL, seq INTEGER NOT NULL, event_json TEXT NOT NULL,
          PRIMARY KEY (game_id, seq)
        );
        """
    )
    for gid, (seed, events) in enumerate(rows.items(), start=1):
        con.execute(
            "INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (gid, 1, seed, 0, 0, 0, 8, "h", "a", "b", None),
        )
        con.executemany(
            "INSERT INTO game_events VALUES (?,?,?)",
            [(gid, seq, event) for seq, event in enumerate(events)],
        )
    con.commit()
    con.close()
    return str(path)


def test_turn_bucket_is_deterministic():
    assert turn_bucket(0, "setup_active") == "setup"
    assert turn_bucket(2, "main") == "early"
    assert turn_bucket(6, "main") == "mid"
    assert turn_bucket(12, "main") == "late"


def test_load_decision_records_parses_chosen_kind(tmp_path):
    path = _db(tmp_path / "decisions.db", {
        101: [_event("mcts_consider", 0, 2, chosen="retreat：多龙巴鲁托ex")],
        102: [_event("mcts_consider", 1, 4, chosen="attack：喷射头击"),
              _event("mcts_consider", 0, 5, chosen="use_ability：望月")],
    })
    records = load_decision_records(path, side=0)
    assert records == (
        DecisionRecord(seed=101, side=0, turn=2, phase="main",
                       kind="retreat", action="retreat：多龙巴鲁托ex"),
        DecisionRecord(seed=102, side=0, turn=5, phase="main",
                       kind="use_ability", action="use_ability：望月"),
    )


def test_load_action_records_reads_executed_actions(tmp_path):
    path = _db(tmp_path / "actions.db", {
        201: [_event("retreat", 0, 2, detail={"into": "多龙巴鲁托ex"}),
              _event("attack", 1, 3, detail={"attack": "喷射头击"})],
    })
    records = load_action_records(path, side=0)
    assert len(records) == 1
    assert records[0].kind == "retreat"
    assert records[0].turn == 2


def test_discover_patterns_is_sorted_and_deterministic():
    records = (
        DecisionRecord(1, 0, 2, "main", "retreat", "retreat：多龙巴鲁托ex"),
        DecisionRecord(2, 0, 3, "main", "retreat", "retreat：多龙巴鲁托ex"),
        DecisionRecord(3, 0, 4, "main", "attack", "attack：喷射头击"),
        DecisionRecord(4, 0, 6, "main", "attack", "attack：多龙巴鲁托ex"),
    )
    first = discover_patterns(records, max_candidates=32)
    second = discover_patterns(records, max_candidates=32)
    assert first == second
    assert first == tuple(sorted(first, key=lambda p: p.name))
    assert PatternSpec(name="attack@mid", kind="attack", bucket="mid") in first
    assert PatternSpec(name="retreat@early", kind="retreat", bucket="early") in first


def _batch(label: str, *, seeds: tuple[int, ...] = tuple(range(1, 9)),
           pattern_seeds: tuple[int, ...] | None = None,
           pattern_wins: tuple[int, ...] | None = None,
           heuristic_wins: tuple[int, ...] | None = None,
           real_wr: float = 0.504) -> BatchData:
    pattern_seeds = tuple(seeds[:5]) if pattern_seeds is None else pattern_seeds
    wins = set(pattern_seeds if pattern_wins is None else pattern_wins)
    heuristic_wins = set(seeds if heuristic_wins is None else heuristic_wins)
    decisions = tuple(
        DecisionRecord(seed=s, side=0, turn=2, phase="main", kind="retreat",
                       action="retreat：多龙巴鲁托ex")
        for s in pattern_seeds for _ in range(4)
    )
    return BatchData(
        label=label,
        real_wr=real_wr,
        decisions=decisions,
        mcts_outcomes={s: (1 if s in wins else 0) for s in seeds},
        heuristic_outcomes={s: (0 if s in heuristic_wins else 1) for s in seeds},
    )


def test_evaluate_pattern_passes_stable_batches():
    spec = PatternSpec(name="retreat@early", kind="retreat", bucket="early")
    result = evaluate_pattern(spec, (_batch("b1"), _batch("b2", seeds=tuple(range(9, 17)))))
    assert result.batch_stats[0].points == 20
    assert result.batch_stats[0].games == 5
    assert result.batch_stats[1].points == 20
    assert result.combined_effect == pytest.approx(1.0)
    assert result.combined_ci_low == pytest.approx(1.0)
    assert result.combined_ci_high == pytest.approx(1.0)
    assert result.passes


def test_evaluate_pattern_rejects_unstable_direction():
    spec = PatternSpec(name="retreat@early", kind="retreat", bucket="early")
    stable = _batch("b1")
    unstable = _batch("b2", seeds=tuple(range(9, 17)),
                      pattern_wins=(9, 10, 11, 12, 13),
                      heuristic_wins=(9, 10, 11, 12, 13),
                      real_wr=0.80)
    result = evaluate_pattern(spec, (stable, unstable))
    assert result.batch_stats[1].effect == pytest.approx(-1.0)
    assert not result.passes


def test_evaluate_pattern_rejects_low_coverage():
    spec = PatternSpec(name="retreat@early", kind="retreat", bucket="early")
    low = _batch("b1", pattern_seeds=(1,))
    full = _batch("b2", seeds=tuple(range(9, 17)))
    result = evaluate_pattern(spec, (low, full))
    assert result.batch_stats[0].points == 4
    assert result.batch_stats[0].games == 1
    assert not result.passes
