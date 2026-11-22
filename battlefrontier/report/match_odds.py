"""task 159：赛制口径解析换算——单局胜率 → Bo3 比赛胜率 → 瑞士轮出线概率。

纯解析派生，零模拟成本：Bo3 假设单局独立同 p；瑞士轮 = 二项尾概率，
简化口径（无 tiebreak / 配对小分 / 对手强度漂移）。输出仍是 sim 口径
数字的解析翻译，不构成真实胜率预测（claims register 守则 1）。
"""

from __future__ import annotations

from math import comb


def bo3_match_prob(p: float) -> float:
    """单局胜率 p → Bo3 比赛胜率 = p²(3−2p)（2-0 或 2-1 取胜）。"""
    return p * p * (3.0 - 2.0 * p)


def cut_prob(p: float, rounds: int, min_wins: int) -> float:
    """瑞士轮 rounds 轮中 ≥min_wins 胜的概率（二项尾，简化口径）。"""
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"cut_prob：p 须在 [0,1]（got {p!r}）")
    return sum(comb(rounds, k) * p ** k * (1.0 - p) ** (rounds - k)
               for k in range(min_wins, rounds + 1))


def format_match_odds(base_p: float, mod_p: float, *, rounds: int = 6,
                      min_wins: int = 4) -> str:
    """人读赛制口径段：基线/改表两栏的 Bo3 换算 + 瑞士轮出线概率。"""
    note = (f"赛制口径换算（解析派生：Bo3 假设单局独立同 p；瑞士轮 {rounds} 轮 "
            f"≥{min_wins} 胜出线为简化口径，无 tiebreak/配对小分；仍是 sim 口径"
            f"数字，不构成真实胜率预测）")
    bo3 = (f"Bo3 比赛胜率：基线 {bo3_match_prob(base_p) * 100:.1f}% / "
           f"改表 {bo3_match_prob(mod_p) * 100:.1f}%")
    cut = (f"{rounds} 轮 ≥{min_wins} 胜出线概率：基线 "
           f"{cut_prob(base_p, rounds, min_wins) * 100:.1f}% / "
           f"改表 {cut_prob(mod_p, rounds, min_wins) * 100:.1f}%")
    return f"{note}\n{bo3}\n{cut}"
