"""task 045：搜索轨迹 JSONL（D-T4）——每次评估一行，可重放、可对拍。"""

import json

import pytest

from battlefrontier.tune.fitness import (
    EvalResult,
    PairOutcome,
    aggregate,
)
from battlefrontier.tune.space import default_vector
from battlefrontier.tune.trajectory import (
    TrajectoryWriter,
    read_trajectory,
    rows_equivalent,
    trajectory_row,
)


def _eval_result() -> EvalResult:
    pairs = (
        PairOutcome(pair_index=0, archetype_a="宝0", archetype_b="宝1",
                    seed_start=200000, seed_end=200019,
                    games=20, decided=19, wins_a=11, draws=1, failed=0,
                    winrate=11 / 19),
        PairOutcome(pair_index=17, archetype_a="宝2", archetype_b="宝5",
                    seed_start=217000, seed_end=217019,
                    games=20, decided=20, wins_a=9, draws=0, failed=0,
                    winrate=0.45),
    )
    return EvalResult(vector=default_vector(), fitness=(11 / 19 + 0.45) / 2,
                      pairs=pairs, wall_seconds=3.25)


def test_轨迹行结构_全要素():
    row = trajectory_row(7, _eval_result())
    assert row["evaluation"] == 7
    assert row["vector"] == default_vector()
    assert row["score"] == pytest.approx((11 / 19 + 0.45) / 2)
    # 各配对种子区间（CRN 锚点）
    assert row["seed_ranges"] == [
        {"pair_index": 0, "seed_start": 200000, "seed_end": 200019},
        {"pair_index": 17, "seed_start": 217000, "seed_end": 217019},
    ]
    # 各配对明细
    assert row["pairs"] == [
        {"pair_index": 0, "archetype_a": "宝0", "archetype_b": "宝1",
         "games": 20, "decided": 19, "wins_a": 11, "draws": 1, "failed": 0,
         "winrate": 11 / 19},
        {"pair_index": 17, "archetype_a": "宝2", "archetype_b": "宝5",
         "games": 20, "decided": 20, "wins_a": 9, "draws": 0, "failed": 0,
         "winrate": 0.45},
    ]
    assert row["wall_seconds"] == 3.25


def test_写入读出_可重放(tmp_path):
    path = tmp_path / "traj.jsonl"
    with TrajectoryWriter(path) as w:
        w.append(trajectory_row(0, _eval_result()))
        w.append(trajectory_row(1, _eval_result()))
    # 每评估一行、合法 JSON、UTF-8 中文不转义
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(json.loads(line) for line in lines)
    assert "宝0" in lines[0]
    rows = read_trajectory(path)
    assert len(rows) == 2
    assert rows[0] == trajectory_row(0, _eval_result())
    assert rows[1]["evaluation"] == 1


def test_rows_equivalent_忽略墙钟():
    """确定性对拍口径：wall_seconds 非确定量，逐行一致比较排除它。"""
    a = trajectory_row(0, _eval_result())
    b = dict(a, wall_seconds=999.0)
    assert rows_equivalent(a, b)
    c = dict(a, score=0.1)
    assert not rows_equivalent(a, c)
    d = dict(a, vector={**a["vector"], "w_hp": 2.0})
    assert not rows_equivalent(a, d)


def test_聚合到轨迹_端到端字段衔接():
    """aggregate 产出直接进 trajectory_row：字段齐全（回归守卫）。"""
    from test_tune_fitness import _assignments, _outcomes_10

    pairs = _assignments()
    outcomes = _outcomes_10(0, [0] * 10) + _outcomes_10(5, [1] * 10)
    result = aggregate(default_vector(), pairs, 10, outcomes, 0.5)
    row = trajectory_row(0, result)
    assert row["seed_ranges"][1] == {"pair_index": 5, "seed_start": 205000,
                                     "seed_end": 205009}
    assert row["pairs"][0]["wins_a"] == 10
    assert row["pairs"][1]["wins_a"] == 0
    assert row["score"] == pytest.approx(0.5)
