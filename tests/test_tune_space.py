"""task 045：参数空间声明（D-T1）——8 连续维乘法网格 + 2 整数维枚举。

网格点不含默认值（默认值即当前点，不重复评估）；布尔开关不进空间（固定全开，
含 task 077 的 ability_quality_gate、task 078 的 board_quality_gate、
task 079 的 energy_target_gate、task 080 的 attack_quality_gate）。
"""

import pytest

from battlefrontier.agent.heuristic import HeuristicParams
from battlefrontier.tune.space import (
    CONTINUOUS_DIMS,
    CONTINUOUS_MULTIPLIERS,
    INTEGER_DIMS,
    ParamDim,
    default_vector,
    params_from_vector,
    search_space,
)


def test_空间维度构成():
    space = search_space()
    assert len(space) == 10
    names = [d.name for d in space]
    # 8 连续维（D-T1 表序）+ 2 整数维
    assert names[:8] == list(CONTINUOUS_DIMS) == [
        "w_hp", "w_damage", "w_retreat", "w_prize_diff",
        "w_board", "w_hand", "w_energy_ready", "w_deck",
    ]
    assert names[8:] == list(INTEGER_DIMS) == ["max_bench_setup", "deck_low_threshold"]
    assert all(d.kind == "continuous" for d in space[:8])
    assert all(d.kind == "integer" for d in space[8:])
    # 布尔开关不进空间（含特性 / 前场 / 能量目标 / 复制招式质量门控）
    bool_fields = {"use_abilities", "play_items", "play_supporters", "play_stadiums",
                   "attach_tools", "retreat_when_powerless", "deck_protect",
                   "ability_quality_gate", "board_quality_gate", "energy_target_gate",
                   "attack_quality_gate"}
    assert not (set(names) & bool_fields)


def test_连续维乘法网格_默认值不重复评估():
    space = {d.name: d for d in search_space()}
    assert CONTINUOUS_MULTIPLIERS == (0.0, 0.25, 0.5, 2.0, 4.0)
    defaults = HeuristicParams()
    for name in CONTINUOUS_DIMS:
        dim = space[name]
        default = getattr(defaults, name)
        assert dim.default == default
        # 网格 = {0, ×0.25, ×0.5, ×2, ×4} × 默认值，不含默认值本身
        assert sorted(dim.grid) == sorted({default * m for m in CONTINUOUS_MULTIPLIERS})
        assert default not in dim.grid
        assert len(dim.grid) == 5
    # 具体对拍：w_hp 默认 1.0
    assert space["w_hp"].grid == (0.0, 0.25, 0.5, 2.0, 4.0)
    # 负权重同样适用（w_retreat 默认 -10.0）
    assert space["w_retreat"].grid == (0.0, -2.5, -5.0, -20.0, -40.0)
    # 小权重（w_deck 默认 0.1）
    assert space["w_deck"].grid == (0.0, 0.025, 0.05, 0.2, 0.4)


def test_整数维枚举网格():
    space = {d.name: d for d in search_space()}
    bench = space["max_bench_setup"]
    assert bench.default == 3
    assert bench.grid == (1, 2, 4, 5)  # 1..5 步 1，不含默认 3
    low = space["deck_low_threshold"]
    assert low.default == 6
    assert low.grid == (0, 3, 9, 12)  # {0,3,6,9,12} 不含默认 6
    assert all(isinstance(v, int) for v in (*bench.grid, *low.grid))


def test_default_vector_即全部默认值():
    vec = default_vector()
    defaults = HeuristicParams()
    assert len(vec) == 10
    for dim in search_space():
        assert vec[dim.name] == getattr(defaults, dim.name)


def test_params_from_vector_合法向量():
    vec = default_vector()
    vec["w_damage"] = 10.0
    vec["max_bench_setup"] = 5
    params = params_from_vector(vec)
    assert isinstance(params, HeuristicParams)
    assert params.w_damage == 10.0 and params.max_bench_setup == 5
    # 未进空间的布尔开关固定全开（默认）
    assert params.use_abilities and params.play_items and params.play_supporters
    assert params.play_stadiums and params.attach_tools
    assert params.retreat_when_powerless and params.deck_protect


def test_params_from_vector_缺键多键_不猜():
    vec = default_vector()
    with pytest.raises(ValueError, match="缺"):
        params_from_vector({k: v for k, v in vec.items() if k != "w_hp"})
    with pytest.raises(ValueError, match="未知"):
        params_from_vector({**vec, "w_hindsight": 1.0})


def test_维度为冻结数据():
    dim = search_space()[0]
    assert isinstance(dim, ParamDim)
    with pytest.raises(AttributeError):
        dim.default = 999  # frozen
