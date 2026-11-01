from __future__ import annotations

import pytest

from battlefrontier.report.paired import paired_improvement, paired_outcomes
from battlefrontier.runner.play import GameResult
from battlefrontier.runner.results_db import ResultsDB


def test_paired_improvement_uses_direction_toward_real():
    outcomes = [(seed, 1, 0) for seed in range(100)]
    result = paired_improvement(outcomes, real_wr=0.30)
    assert result.heuristic_wr == 0.0
    assert result.mcts_wr == 1.0
    assert result.effect == 1.0
    assert result.ci_low == result.ci_high == 1.0
    assert result.significant_improvement
    assert not result.significant_deterioration


def test_paired_improvement_detects_significant_deterioration():
    outcomes = [
        (seed, int(seed < 20), int(seed < 10)) for seed in range(100)
    ]
    result = paired_improvement(outcomes, real_wr=0.30)
    assert result.heuristic_wr == 0.8
    assert result.mcts_wr == 0.9
    assert result.effect == pytest.approx(-0.1)
    assert result.ci_high < 0
    assert result.significant_deterioration


def test_paired_improvement_zero_variance_is_not_significant():
    outcomes = [(seed, seed % 2, seed % 2) for seed in range(100)]
    result = paired_improvement(outcomes, real_wr=0.30)
    assert result.effect == 0.0
    assert result.ci_low == result.ci_high == 0.0
    assert not result.significant_improvement
    assert not result.significant_deterioration


def test_paired_improvement_reference_ci():
    outcomes = [(seed, 1, int(seed % 2 == 0)) for seed in range(100)]
    result = paired_improvement(outcomes, real_wr=0.70)
    assert result.heuristic_wr == 0.0
    assert result.mcts_wr == 0.5
    assert result.effect == pytest.approx(0.5)
    assert result.ci_low == pytest.approx(0.402, abs=0.001)
    assert result.ci_high == pytest.approx(0.598, abs=0.001)


def test_paired_improvement_rejects_duplicate_seed_and_zero_direction():
    with pytest.raises(ValueError, match="种子"):
        paired_improvement([(1, 0, 0), (1, 0, 0)], real_wr=0.30)
    with pytest.raises(ValueError, match="方向"):
        paired_improvement([(1, 1, 1), (2, 1, 1)], real_wr=0.0)


def _experiment(db: ResultsDB, name: str, rows: list[tuple]) -> int:
    exp_id = db.start_experiment(
        name=name, definition_yaml="y", code_version="c", data_version="d"
    )
    for seed, winner, is_draw, error in rows:
        if error is not None:
            db.record_error(exp_id, seed=seed, deck_a_id="a", deck_b_id="b", error=error)
        else:
            result = GameResult(
                winner=winner, is_draw=is_draw, turns=8, phase="main", first_player=0
            )
            db.record_game(
                exp_id, seed=seed, first_player=0, result=result,
                deck_a_id="a", deck_b_id="b",
            )
    db.finish_experiment(exp_id)
    return exp_id


def test_paired_outcomes_aligns_seed_and_a_wins(tmp_path):
    db = ResultsDB(tmp_path / "paired.db")
    try:
        heuristic = _experiment(db, "h", [(2, 0, False, None), (1, 1, False, None)])
        mcts = _experiment(db, "m", [(1, 0, False, None), (2, 1, False, None)])
        assert paired_outcomes(db, heuristic, db, mcts) == ((1, 1, 0), (2, 0, 1))
    finally:
        db.close()


@pytest.mark.parametrize(
    ("heuristic_rows", "mcts_rows", "match"),
    [
        ([(1, 0, False, None)], [(2, 0, False, None)], "种子"),
        ([(1, None, True, None)], [(1, 0, False, None)], "平局"),
        ([(1, None, False, "boom")], [(1, 0, False, None)], "失败"),
        ([(1, 0, False, None)], [(1, None, True, None)], "平局"),
        ([(1, 0, False, None)], [(1, None, False, "boom")], "失败"),
    ],
)
def test_paired_outcomes_rejects_unusable_games(tmp_path, heuristic_rows, mcts_rows, match):
    db = ResultsDB(tmp_path / "paired-errors.db")
    try:
        heuristic = _experiment(db, "h", heuristic_rows)
        mcts = _experiment(db, "m", mcts_rows)
        with pytest.raises(ValueError, match=match):
            paired_outcomes(db, heuristic, db, mcts)
    finally:
        db.close()
