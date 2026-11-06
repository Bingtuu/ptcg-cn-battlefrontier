"""task 106：报告层诚实化 —— sim 解释限定语（红测先行）.

claims register（docs/claims-register.md）使用守则 1/3 的落地：
format_report / format_calibration 输出必须携带「自对局模拟结果，不构成真实
胜率预测」限定语；校准表另带「真实窗与卡快照可能不同代、|Δ| 非精度指标」。
"""

from __future__ import annotations

import pytest

from battlefrontier.report import (
    CALIBRATION_EXTRA_NOTE,
    SIM_INTERPRETATION_NOTE,
)
from battlefrontier.report.calibration import format_calibration
from battlefrontier.report.winrate import format_report, winrate_report
from battlefrontier.runner.play import GameResult
from battlefrontier.runner.results_db import ResultsDB
from tests.test_calibration import _real, _report, _seed_pair_ab


def _result(winner, is_draw, turns):
    return GameResult(winner=winner, is_draw=is_draw, turns=turns, phase="game_over")


@pytest.fixture()
def synth_db(tmp_path):
    """最小 3 局完成实验（构造同 tests/test_winrate.py synth_db 先例）。"""
    db = ResultsDB(tmp_path / "r.db")
    exp_id = db.start_experiment(name="synth-note", definition_yaml="name: x\n",
                                 code_version="cv", data_version="d")
    for i, (seed, winner) in enumerate(((100, 0), (101, 1), (102, 0))):
        db.record_game(exp_id, seed=seed, first_player=0,
                       result=_result(winner, False, turns=8 + i),
                       deck_a_id="a", deck_b_id="b")
    db.finish_experiment(exp_id)
    yield db, exp_id
    db.close()


def test_常量非空且含核心语义():
    assert "自对局模拟结果" in SIM_INTERPRETATION_NOTE
    assert "不构成真实胜率预测" in SIM_INTERPRETATION_NOTE
    assert "不同代" in CALIBRATION_EXTRA_NOTE
    assert "精度指标" in CALIBRATION_EXTRA_NOTE


def test_format_report_带_sim_限定语(synth_db):
    db, exp_id = synth_db
    text = format_report(winrate_report(db, exp_id))
    assert SIM_INTERPRETATION_NOTE in text


def test_format_calibration_带两条限定语(tmp_path):
    db_path = tmp_path / "r.db"
    db = ResultsDB(db_path)
    _seed_pair_ab(db)
    db.close()
    rep = _report(db_path, [_real("Alpha", "Beta", 100, 0.60)])
    text = format_calibration(rep)
    assert SIM_INTERPRETATION_NOTE in text
    assert CALIBRATION_EXTRA_NOTE in text
