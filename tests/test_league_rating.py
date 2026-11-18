"""task 127：BT-MLE 评级主估计子（Bradley-Terry MM 迭代）。

解析锚：双人情形 MLE log-strength 差 = 得分比 log-odds ln(s/(n−s))；
平局 0.5 计分；零均值；交换对称（a/b 互换 → strength 取反）；
确定性（同输入两次完全一致）；Elo 标度换算单调。
"""

import math

import pytest

from battlefrontier.report.league import bt_mle, elo_scale

LN10 = math.log(10.0)


def _diff(strengths, a, b):
    return strengths[a] - strengths[b]


def test_two_player_logodds_analytic():
    """3 胜 1 负 → α_A − α_B = ln(3/1)（MLE 解析解，MM 须收敛到它）。"""
    games = [("A", "B", 1.0)] * 3 + [("A", "B", 0.0)]
    s = bt_mle(games, ["A", "B"])
    assert _diff(s, "A", "B") == pytest.approx(math.log(3.0), abs=1e-8)


def test_two_player_all_draws_equal():
    games = [("A", "B", 0.5)] * 4
    s = bt_mle(games, ["A", "B"])
    assert _diff(s, "A", "B") == pytest.approx(0.0, abs=1e-10)


def test_zero_mean():
    games = [("A", "B", 1.0), ("B", "C", 1.0), ("A", "C", 0.0)]
    s = bt_mle(games, ["A", "B", "C"])
    assert sum(s.values()) == pytest.approx(0.0, abs=1e-10)


def test_cycle_symmetry_equal_strengths():
    """A>B、B>C、C>A 各一局的循环 → 任何排序都被对称性否定，MLE = 全等。"""
    games = [("A", "B", 1.0), ("B", "C", 1.0), ("C", "A", 1.0)]
    s = bt_mle(games, ["A", "B", "C"])
    for v in s.values():
        assert v == pytest.approx(0.0, abs=1e-10)


def test_invert_scores_negates_strength():
    """结果取反（胜↔负，平局不变）→ 强度取反——BT 对称性。"""
    games = [("A", "B", 1.0)] * 3 + [("A", "B", 0.0)]
    s1 = bt_mle(games, ["A", "B"])
    s2 = bt_mle([(a, b, 1.0 - sc) for a, b, sc in games], ["A", "B"])
    assert s1["A"] == pytest.approx(-s2["A"], abs=1e-10)
    assert s1["B"] == pytest.approx(-s2["B"], abs=1e-10)


def test_deterministic_same_input():
    games = [("A", "B", 1.0), ("A", "C", 0.5), ("B", "C", 0.0)] * 7
    s1 = bt_mle(games, ["A", "B", "C"])
    s2 = bt_mle(list(games), ["A", "B", "C"])
    assert s1 == s2


def test_draws_count_half_in_two_player():
    """1 胜 1 平 1 负 → 得分 1.5/3 → log-odds ln(1.5/1.5) = 0。"""
    games = [("A", "B", 1.0), ("A", "B", 0.5), ("A", "B", 0.0)]
    s = bt_mle(games, ["A", "B"])
    assert _diff(s, "A", "B") == pytest.approx(0.0, abs=1e-10)


def test_elo_scale_monotone_and_zero_anchor():
    """零均值下 log-strength 0 → Elo 1500；差 ln10 → 400 分（标度定义）。"""
    assert elo_scale(0.0) == pytest.approx(1500.0)
    assert elo_scale(LN10) - elo_scale(0.0) == pytest.approx(400.0)
    assert elo_scale(math.log(3.0)) > elo_scale(0.0)


def test_unknown_entity_raises():
    with pytest.raises((ValueError, KeyError)):
        bt_mle([("A", "B", 1.0)], ["A"])
