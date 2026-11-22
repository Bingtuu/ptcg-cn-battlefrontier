# task 159：赛制口径解析换算（单局 p → Bo3 比赛胜率 → 瑞士轮出线概率）

from __future__ import annotations

import pytest

from battlefrontier.report.match_odds import (
    bo3_match_prob,
    cut_prob,
    format_match_odds,
)


def test_bo3_match_prob_手算():
    assert bo3_match_prob(0.0) == 0.0
    assert bo3_match_prob(1.0) == 1.0
    assert bo3_match_prob(0.5) == pytest.approx(0.5)
    # p=0.6：0.36×(3−1.2)=0.648（Bo3 赢两局：2-0 或 2-1）
    assert bo3_match_prob(0.6) == pytest.approx(0.648)
    # 单调性：比赛胜率比单局胜率更远离 0.5（放大效应）
    assert bo3_match_prob(0.6) > 0.6
    assert bo3_match_prob(0.4) < 0.4


def test_cut_prob_手算():
    # rounds=6, min_wins=4, p=0.5：(15+6+1)/64 = 22/64
    assert cut_prob(0.5, 6, 4) == pytest.approx(22 / 64)
    # p=0.6：15·0.6⁴0.4² + 6·0.6⁵0.4 + 0.6⁶ = 0.54432
    assert cut_prob(0.6, 6, 4) == pytest.approx(0.54432)
    # 边界：0 胜不可能 / 全胜必然 / min_wins=0 恒 1
    assert cut_prob(0.5, 6, 1) == pytest.approx(1 - 0.5 ** 6)
    assert cut_prob(1.0, 6, 4) == 1.0
    assert cut_prob(0.0, 6, 1) == 0.0
    assert cut_prob(0.5, 6, 0) == 1.0


def test_format_match_odds_赛制段与限定语():
    # base=0.4375 / mod=0.75（沿用 mod_check 手算夹具的期望值）
    text = format_match_odds(0.4375, 0.75)
    # Bo3：0.4375→0.4067（40.7%）；0.75→0.84375（84.4%）
    assert "Bo3" in text
    assert "40.7%" in text and "84.4%" in text
    # 瑞士轮 6 轮 ≥4 胜：0.4375→0.2354（23.5%）；0.75→0.8306（83.1%）
    assert "23.5%" in text and "83.1%" in text
    # 简化口径与 sim 限定语不丢
    assert "tiebreak" in text
    assert "不构成真实胜率预测" in text
    # 基线/改表两栏都在
    assert "基线" in text and "改表" in text
