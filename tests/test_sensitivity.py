"""换卡敏感性统计与报告测试（task 023，PRD §9）。

统计参考值手算对拍（不引 scipy，正确性靠已知值锚定）：
65/100 vs 35/100 → 合并 p=0.5，SE=√0.005≈0.0707107，z≈4.24264，
双侧 p≈2.21e-5（标准正态表 z=4.24 单尾 1.11e-5）；
非合并 SE=√0.00455≈0.0674537，ΔCI = 0.30 ± 1.959964×0.0674537 ≈ (0.1678, 0.4322)。
"""

from __future__ import annotations

import pytest

from battlefrontier.report.sensitivity import (
    diff_ci,
    format_sensitivity,
    normal_cdf,
    sensitivity_report,
    two_proportion_z,
)
from battlefrontier.runner.play import GameResult
from battlefrontier.runner.results_db import ResultsDB

# ── 统计原语 ─────────────────────────────────────────────

def test_normal_cdf_reference():
    """Φ 参考值：Φ(0)=0.5，Φ(1.96)≈0.9750021，Φ(-1.96)≈0.0249979。"""
    assert normal_cdf(0.0) == pytest.approx(0.5)
    assert normal_cdf(1.96) == pytest.approx(0.9750021, abs=1e-6)
    assert normal_cdf(-1.96) == pytest.approx(0.0249979, abs=1e-6)


def test_two_proportion_z_reference():
    z, p = two_proportion_z(65, 100, 35, 100)
    assert z == pytest.approx(4.2426406871, rel=1e-6)
    assert p == pytest.approx(2.21e-5, rel=1e-2)


def test_two_proportion_z_zero_denominator():
    """n=0 不除零：返回 (None, None) 由报告层标注。"""
    assert two_proportion_z(0, 0, 35, 100) == (None, None)
    assert two_proportion_z(65, 100, 0, 0) == (None, None)


def test_diff_ci_reference():
    lo, hi = diff_ci(65, 100, 35, 100)
    assert lo == pytest.approx(0.1678, abs=1e-3)
    assert hi == pytest.approx(0.4322, abs=1e-3)
    assert diff_ci(0, 0, 35, 100) is None


def test_same_proportion_not_significant():
    z, p = two_proportion_z(50, 100, 50, 100)
    assert z == pytest.approx(0.0)
    assert p == pytest.approx(1.0)


# ── 报告（合成结果库端到端）──────────────────────────────

def _seed_db(tmp_path, base_wr: int, variant_wr: int, n: int = 100,
             variant_games: int | None = None):
    """造 base/variant 两个实验：各 n 局决定局，A 胜指定场数。"""
    if variant_games is None:
        variant_games = n
    db = ResultsDB(tmp_path / "r.db")
    ids = []
    for variant, wins, games in (("", base_wr, n), ("v1", variant_wr, variant_games)):
        exp_id = db.start_experiment(name="grp", definition_yaml="y",
                                     code_version="c", data_version="d",
                                     group_name="grp", variant=variant)
        for seed in range(games):
            res = GameResult(winner=0 if seed < wins else 1, is_draw=False,
                             turns=8, phase="main", first_player=seed % 2)
            db.record_game(exp_id, seed=seed, first_player=res.first_player,
                           result=res, deck_a_id="a", deck_b_id="b")
        db.finish_experiment(exp_id)
        ids.append(exp_id)
    db.close()
    return ids


def test_sensitivity_report_numbers(tmp_path):
    base_id, var_id = _seed_db(tmp_path, 65, 35)
    db = ResultsDB(tmp_path / "r.db")
    try:
        rep = sensitivity_report(db, base_id, [var_id])
    finally:
        db.close()
    assert rep.base.experiment_id == base_id
    assert rep.base.decided == 100 and rep.base.wins_a == 65
    (comp,) = rep.variants
    assert comp.variant == "v1"
    assert comp.wr_a == pytest.approx(0.35)
    assert comp.d_wr == pytest.approx(-0.30)
    assert comp.z == pytest.approx(-4.2426406871, rel=1e-6)
    assert comp.p == pytest.approx(2.21e-5, rel=1e-2)
    assert comp.d_ci[0] == pytest.approx(-0.4322, abs=1e-3)


def test_format_sensitivity_meta_and_table(tmp_path):
    base_id, var_id = _seed_db(tmp_path, 65, 35)
    db = ResultsDB(tmp_path / "r.db")
    try:
        text = format_sensitivity(sensitivity_report(db, base_id, [var_id]))
    finally:
        db.close()
    assert f"#{base_id}" in text and f"#{var_id}" in text
    assert "v1" in text and "种子" in text and "ΔWR" in text
    assert "65.0%" in text and "35.0%" in text and "-30.0%" in text


def test_format_sensitivity_zero_decided(tmp_path):
    """变体 0 局：不崩，显著性标注为不可用。"""
    base_id, var_id = _seed_db(tmp_path, 50, 0, variant_games=0)
    db = ResultsDB(tmp_path / "r.db")
    try:
        text = format_sensitivity(sensitivity_report(db, base_id, [var_id]))
    finally:
        db.close()
    assert "不可用" in text or "n=0" in text
