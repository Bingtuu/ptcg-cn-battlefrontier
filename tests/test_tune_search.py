"""task 045：坐标下降搜索器（D-T3）——采纳/拒绝/停止规则 + 逐维敏感性记录。

搜索循环单测全部用注入的 fake evaluate（不打真局）；搜索级确定性用 stub 卡组
真实 play_game 小预算端到端对拍（同起点两次跑 trials 逐项一致）。
"""

import pytest

from battlefrontier.tune.search import (
    DimTrial,
    coordinate_descent,
)
from battlefrontier.tune.space import default_vector, search_space

SPACE = search_space()
START = default_vector()


def _run(evaluate, **kw):
    args = {"space": SPACE, "start": START, "noise_threshold": 0.01, "max_rounds": 3}
    args.update(kw)
    return coordinate_descent(evaluate, **args)


# ── 采纳规则 ─────────────────────────────────────────────

def test_采纳_超过噪声门槛才采纳_取该维最优点():
    """w_damage ×2（默认 5→10）提升 0.02 > 门槛 0.01 → 采纳；其余维不动。"""
    def evaluate(vec):
        return 0.5 + (0.02 if vec["w_damage"] == 10.0 else 0.0)

    result = _run(evaluate)
    assert result.best_vector["w_damage"] == 10.0
    assert result.best_fitness == pytest.approx(0.52)
    assert result.baseline_fitness == pytest.approx(0.5)
    for dim in SPACE:
        if dim.name != "w_damage":
            assert result.best_vector[dim.name] == START[dim.name]
    # 采纳发生在第 1 轮；第 2 轮无改进停止
    assert result.rounds_run == 2 and result.stop_reason == "no_improvement"
    adopted = [t for t in result.trials if t.adopted]
    assert len(adopted) == 1
    assert (adopted[0].dim, adopted[0].value) == ("w_damage", 10.0)
    assert adopted[0].delta == pytest.approx(0.02)


def test_拒绝_提升恰等于门槛不采纳():
    """Δ == 噪声门槛不采纳（严格大于才采纳；用二进制可精确表示的值排除浮点毛刺）。"""
    def evaluate(vec):
        return 0.5 + (0.25 if vec["w_hp"] == 2.0 else 0.0)

    result = _run(evaluate, noise_threshold=0.25)
    assert result.best_vector["w_hp"] == START["w_hp"] == 1.0
    assert result.stop_reason == "no_improvement"
    assert not any(t.adopted for t in result.trials)


def test_单维全不采纳则保持原值():
    """w_hp 各点提升均低于门槛 → 该维保持原值；其他维正常采纳。"""
    def evaluate(vec):
        score = 0.5
        if vec["w_hp"] != 1.0:
            score += 0.005          # 低于门槛 0.01
        if vec["w_damage"] == 20.0:  # ×4
            score += 0.03
        return score

    result = _run(evaluate)
    assert result.best_vector["w_hp"] == 1.0
    assert result.best_vector["w_damage"] == 20.0


def test_整轮无改进_立即停止():
    """恒定 fitness：第 1 轮扫完即停（rounds_run=1，不进入第 2 轮）。"""
    result = _run(lambda vec: 0.5)
    assert result.rounds_run == 1
    assert result.stop_reason == "no_improvement"
    assert result.best_vector == START
    assert result.best_fitness == pytest.approx(0.5)
    # 评估次数 = 1 基线 + 8×5 连续点 + 4+4 整数点
    assert result.n_evaluations == 1 + 8 * 5 + 4 + 4
    assert len(result.trials) == 8 * 5 + 4 + 4


def test_三轮上限_持续改进则止于_max_rounds():
    """每维采纳后下轮仍可改进（fake 递增）→ 恰跑满 3 轮，stop_reason=max_rounds。"""
    counter = {"n": 0}

    def evaluate(vec):
        counter["n"] += 1
        return 0.5 + counter["n"] * 0.02  # 严格递增：每维最末评估点恒被采纳

    result = _run(evaluate, max_rounds=3)
    assert result.rounds_run == 3
    assert result.stop_reason == "max_rounds"
    assert result.n_evaluations == counter["n"]


def test_max_rounds_为1_单轮冒烟配置():
    counter = {"n": 0}

    def evaluate(vec):
        counter["n"] += 1
        return 0.5 + counter["n"] * 0.02

    result = _run(evaluate, max_rounds=1)
    assert result.rounds_run == 1 and result.stop_reason == "max_rounds"
    assert result.n_evaluations == 1 + 8 * 5 + 4 + 4


# ── 敏感性记录 ───────────────────────────────────────────

def test_逐维敏感性记录_每维各点Δfitness():
    """trials 覆盖每维全部试投点，含 round/dim/value/fitness/delta/adopted。"""
    def evaluate(vec):
        return 0.5 + (0.02 if vec["w_damage"] == 10.0 else 0.0)

    result = _run(evaluate)
    r1 = [t for t in result.trials if t.round == 1]
    # 第 1 轮：每维各网格点各一次（默认值不在网格，当前值=默认值 → 全点数）
    for dim in SPACE:
        vals = [t.value for t in r1 if t.dim == dim.name]
        assert vals == list(dim.grid)
    # Δfitness 相对采纳前当前 fitness 记录
    w_hp_zero = next(t for t in r1 if t.dim == "w_hp" and t.value == 0.0)
    assert w_hp_zero.fitness == pytest.approx(0.5)
    assert w_hp_zero.delta == pytest.approx(0.0)
    assert isinstance(w_hp_zero, DimTrial)
    adopted = [t for t in r1 if t.adopted]
    assert [(t.dim, t.value) for t in adopted] == [("w_damage", 10.0)]


def test_坐标下降确定性_同起点同fake_两次一致():
    """搜索过程本身确定：同 fake（纯函数）两次跑 SearchResult 完全一致。"""

    def evaluate(vec):
        return 0.5 + 0.001 * sum(float(v) for v in vec.values())

    r1 = _run(evaluate)
    r2 = _run(evaluate)
    assert r1 == r2


def test_start_键集合校验_不猜():
    with pytest.raises(ValueError, match="缺"):
        _run(lambda v: 0.5, start={k: v for k, v in START.items() if k != "w_hp"})
    with pytest.raises(ValueError, match="未知"):
        _run(lambda v: 0.5, start={**START, "bogus": 1})


def test_搜索级确定性_真实对局两次跑一致():
    """同起点同种子区间（stub 卡组真实 play_game），两次坐标下降：
    SearchResult 逐字段一致，评估函数产出轨迹逐行一致。"""
    from test_tune_fitness import _stub_pair

    from battlefrontier.tune.fitness import execute_plan
    from battlefrontier.tune.trajectory import rows_equivalent, trajectory_row

    prepared = [_stub_pair(0)]

    def run_once():
        rows = []

        def evaluate(vec):
            result = execute_plan(prepared, vec, games_per_pair=4, workers=1)
            rows.append(trajectory_row(len(rows), result))
            return result.fitness

        result = _run(evaluate, max_rounds=1)
        return result, rows

    (result1, rows1), (result2, rows2) = run_once(), run_once()
    assert result1 == result2
    assert len(rows1) == result1.n_evaluations
    assert len(rows1) == len(rows2)
    assert all(rows_equivalent(a, b) for a, b in zip(rows1, rows2, strict=True))
    # 有效性自查：无失败局
    assert all(p["failed"] == 0 for row in rows1 for p in row["pairs"])
