"""task 021：胜率报告（PRD §9）——Wilson CI 手写实现，参考值对拍锁定正确性。"""

import pytest

from battlefrontier.cli import main
from battlefrontier.report.winrate import format_report, wilson_ci, winrate_report
from battlefrontier.runner.play import GameResult
from battlefrontier.runner.results_db import ResultsDB

# ── Wilson CI 参考值对拍 ─────────────────────────────────

@pytest.mark.parametrize(("x", "n", "lo", "hi"), [
    (63, 100, 0.532, 0.718),   # 经典参考（Wilson 95%）
    (40, 100, 0.310, 0.498),
    (0, 100, 0.0, 0.037),      # 极端：全负
    (100, 100, 0.963, 1.0),    # 极端：全胜
])
def test_wilson_ci_reference(x, n, lo, hi):
    got_lo, got_hi = wilson_ci(x, n)
    assert got_lo == pytest.approx(lo, abs=1e-3)
    assert got_hi == pytest.approx(hi, abs=1e-3)


def test_wilson_ci_zero_games():
    assert wilson_ci(0, 0) == (0.0, 0.0)


# ── 合成结果库对账 ───────────────────────────────────────

def _result(winner, is_draw, turns):
    return GameResult(winner=winner, is_draw=is_draw, turns=turns, phase="game_over")


@pytest.fixture()
def synth_db(tmp_path):
    """11 局：A先攻 5 局（A胜3/B胜1/平1）+ A后攻 5 局（A胜3/B胜2）+ 失败 1。"""
    db = ResultsDB(tmp_path / "r.db")
    exp_id = db.start_experiment(name="synth", definition_yaml="name: synth\n",
                                 code_version="abc1234", data_version="d")
    rows = [  # (seed, first_player, winner, is_draw)
        (100, 0, 0, False), (101, 0, 0, False), (102, 0, 0, False),
        (103, 0, 1, False), (104, 0, None, True),
        (105, 1, 0, False), (106, 1, 0, False), (107, 1, 0, False),
        (108, 1, 1, False), (109, 1, 1, False),
    ]
    for i, (seed, fp, winner, draw) in enumerate(rows):
        db.record_game(exp_id, seed=seed, first_player=fp,
                       result=_result(winner, draw, turns=10 + i),
                       deck_a_id="a", deck_b_id="b")
    db.record_error(exp_id, seed=110, deck_a_id="a", deck_b_id="b", error="模拟失败")
    db.finish_experiment(exp_id)
    yield db, exp_id
    db.close()


def test_report_counts_and_rates(synth_db):
    db, exp_id = synth_db
    r = winrate_report(db, exp_id)
    assert r.games_total == 11 and r.games_failed == 1
    assert r.games_played == 10 and r.decided == 9
    assert (r.wins_a, r.wins_b, r.draws) == (6, 3, 1)
    assert r.wr_a == pytest.approx(6 / 9)
    assert r.ci_a == pytest.approx(wilson_ci(6, 9))
    assert r.avg_turns == pytest.approx(14.5)


def test_report_first_second_split(synth_db):
    db, exp_id = synth_db
    r = winrate_report(db, exp_id)
    assert r.as_first.games == 5 and r.as_first.wins_a == 3 and r.as_first.decided == 4
    assert r.as_first.wr_a == pytest.approx(0.75)
    assert r.as_second.games == 5 and r.as_second.wins_a == 3 and r.as_second.decided == 5
    assert r.as_second.wr_a == pytest.approx(0.6)


def test_report_meta_echo(synth_db):
    db, exp_id = synth_db
    r = winrate_report(db, exp_id)
    assert r.experiment_id == exp_id and r.name == "synth"
    assert r.code_version == "abc1234" and r.data_version == "d"
    assert (r.seed_min, r.seed_max) == (100, 110)


def test_report_empty_experiment(tmp_path):
    db = ResultsDB(tmp_path / "e.db")
    exp_id = db.start_experiment(name="empty", definition_yaml="x",
                                 code_version="v", data_version="d")
    db.finish_experiment(exp_id)
    r = winrate_report(db, exp_id)
    assert r.games_total == 0 and r.wr_a == 0.0 and r.ci_a == (0.0, 0.0)
    assert r.seed_min is None and r.seed_max is None
    db.close()


def test_report_unknown_experiment(tmp_path):
    db = ResultsDB(tmp_path / "u.db")
    with pytest.raises(ValueError, match="999"):
        winrate_report(db, 999)
    db.close()


def test_format_report_contains_meta_and_lines(synth_db):
    db, exp_id = synth_db
    text = format_report(winrate_report(db, exp_id))
    for needle in ("实验 #", "synth", "abc1234", "100", "110",
                   "胜率", "CI", "先攻", "后攻", "平", "失败"):
        assert needle in text


# ── CLI ──────────────────────────────────────────────────

def test_cli_report(synth_db, capsys):
    db, exp_id = synth_db
    path = db._conn.execute("PRAGMA database_list").fetchone()[2]
    db.close()
    rc = main(["report", str(exp_id), "--results", path])
    assert rc == 0
    out = capsys.readouterr().out
    assert "synth" in out and "胜率" in out


def test_cli_report_unknown_id(synth_db, capsys):
    db, _ = synth_db
    path = db._conn.execute("PRAGMA database_list").fetchone()[2]
    db.close()
    rc = main(["report", "999", "--results", path])
    assert rc != 0
    assert "999" in capsys.readouterr().out
