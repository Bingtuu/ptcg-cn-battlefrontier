"""task 050 WP1：M11 特征层（D-M11-2 特征清单 A+B 组，C 组顺延）。

验收口径见 `tasks/task 050.md`：FEATURE_NAMES 键序钉死 / 全字段确定性 /
A 组因子与重构后 evaluate 对拍（内联重构前逻辑作 oracle）/ 代表性视图手算
数值断言 / 对手隐藏信息只出 count 特征（信息纪律）。
"""

from helpers import basic, in_play, inst, main_state, stage1

from battlefrontier.agent.features import FEATURE_NAMES, feature_vector
from battlefrontier.agent.heuristic import HeuristicParams, evaluate, pokemon_score
from battlefrontier.engine.state import GameState, PlayerState, SpecialCondition


def _pre_refactor_evaluate(view, params: HeuristicParams) -> float:
    """重构前 heuristic.evaluate（task 018 内联版）的逐行复刻——对拍 oracle。"""
    own, opp = view.own, view.opponent
    own_in = ([own.active] if own.active else []) + list(own.bench)
    opp_in = ([opp.active] if opp.active else []) + list(opp.bench)
    board_own = sum(pokemon_score(p, params) for p in own_in)
    board_opp = sum(pokemon_score(p, params) for p in opp_in)
    energy_own = sum(len(p.attached_energy) for p in own_in)
    energy_opp = sum(len(p.attached_energy) for p in opp_in)
    return (
        params.w_prize_diff * (own.prizes_count - opp.prizes_count)
        + params.w_board * (board_own - board_opp)
        + params.w_hand * (len(own.hand) - opp.hand_count)
        + params.w_energy_ready * (energy_own - energy_opp)
        + params.w_deck * (own.deck_count - opp.deck_count)
    )


def _rich_view():
    """非全零的代表性视图（turn=7 main 阶段，p0 视角）：

    p0：active 妙蛙种子（2 能）；bench 妙蛙草（stage1，1 能）+ 小火龙（0 能）；
    手牌 3（小火龙/能量/妙蛙草）；energy_attached=True；evolved_this_turn={4}。
    p1：active 小火龙（1 能，中毒+灼伤）；bench 绿毛虫（0 能）；手牌 0。
    """
    state = main_state(p0_active_energies=2,
                       p0_extra_hand=(inst(52, stage1("妙蛙草", "妙蛙种子")),),
                       p1_bench=(in_play(3, basic("绿毛虫"), 0),))
    p0 = state.players[0].model_copy(update={
        "bench": (in_play(4, stage1("妙蛙草", "妙蛙种子"), 1),
                  in_play(5, basic("小火龙"), 0)),
        "energy_attached_this_turn": True,
        "evolved_this_turn": frozenset({4}),
    })
    p1 = state.players[1].model_copy(update={
        "active": state.players[1].active.model_copy(update={
            "conditions": frozenset({SpecialCondition.POISONED, SpecialCondition.BURNED})}),
    })
    state = state.model_copy(update={"players": (p0, p1), "turn": 7})
    return state.visible_state(0)


# 手算期望值（pokemon_score 默认参数 w_hp=1/w_damage=5/w_retreat=-10：
# 妙蛙种子 70+100-10=160；妙蛙草 90+200-0=290；小火龙/绿毛虫=160）
RICH_EXPECTED = {
    # A 组（五因子原值）
    "prize_diff": 0.0,                    # 6 - 6
    "board_score_diff": 610.0 - 320.0,    # (160+290+160) - (160+160)
    "hand_diff": 3.0,                     # 3 - 0
    "energy_ready_diff": 2.0,             # (2+1+0) - (1+0)
    "deck_diff": 0.0,                     # 10 - 10
    # B 组（结构量）
    "turn_norm": 7 / 50,
    "own_bench_count": 2.0,
    "opp_bench_count": 1.0,
    "own_deck_count": 10.0,
    "opp_deck_count": 10.0,
    "own_hand_count": 3.0,
    "opp_hand_count": 0.0,
    "stadium_in_play": 0.0,
    "own_active_conditions_count": 0.0,
    "opp_active_conditions_count": 2.0,   # 中毒 + 灼伤
    "own_stage0_count": 2.0,              # 妙蛙种子 + 小火龙
    "own_stage1_count": 1.0,              # 妙蛙草
    "own_stage2_count": 0.0,
    "opp_stage0_count": 2.0,              # 小火龙 + 绿毛虫
    "opp_stage1_count": 0.0,
    "opp_stage2_count": 0.0,
    "face_down_pokemon": 0.0,             # main 阶段无背面布阵
    "flag_energy_attached": 1.0,
    "flag_supporter_played": 0.0,
    "flag_retreated": 0.0,
    "flag_stadium_played": 0.0,
    "flag_stadium_used": 0.0,
    "flag_entered_play": 0.0,
    "flag_evolved": 1.0,                  # evolved_this_turn={4}
    "flag_ability_used": 0.0,
}


def test_FEATURE_NAMES_键序钉死且唯一():
    assert isinstance(FEATURE_NAMES, tuple)
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))
    assert all(isinstance(n, str) and n for n in FEATURE_NAMES)
    # 与手算期望表同集合（防漏防飘）
    assert set(FEATURE_NAMES) == set(RICH_EXPECTED)


def test_feature_vector_键序等于_FEATURE_NAMES():
    view = _rich_view()
    assert tuple(feature_vector(view)) == FEATURE_NAMES


def test_feature_vector_确定性_同视图两次全等():
    view = _rich_view()
    assert feature_vector(view) == feature_vector(view)


def test_feature_vector_全字段为float():
    for name, value in feature_vector(_rich_view()).items():
        assert isinstance(value, float), f"{name} 不是 float: {value!r}"


def test_feature_vector_代表性视图手算数值断言():
    assert feature_vector(_rich_view()) == RICH_EXPECTED


def test_A组因子与evaluate重构对拍():
    """重构后 evaluate == 重构前内联 oracle（逐值全等，多参数组 × 多视图）。"""
    views = [main_state().visible_state(0), _rich_view(),
             main_state(p0_active_energies=0, p1_bench=(in_play(3, basic("绿毛虫")),))
             .visible_state(1)]
    params_list = [HeuristicParams(),
                   HeuristicParams(w_damage=0.1, w_prize_diff=3.0),
                   HeuristicParams(w_retreat=0.0, w_deck=1.0, w_hand=0.0)]
    for view in views:
        for params in params_list:
            assert evaluate(view, params) == _pre_refactor_evaluate(view, params)


def test_A组特征等于因子原值_不带权重():
    """A 组特征 = 因子分解量原值；加权重构即 evaluate（w 非 1 时原值 != 贡献）。"""
    view = _rich_view()
    params = HeuristicParams()
    feats = feature_vector(view)
    recomposed = (
        params.w_prize_diff * feats["prize_diff"]
        + params.w_board * feats["board_score_diff"]
        + params.w_hand * feats["hand_diff"]
        + params.w_energy_ready * feats["energy_ready_diff"]
        + params.w_deck * feats["deck_diff"]
    )
    assert recomposed == evaluate(view, params) == 295.5


def test_对手隐藏信息只出count特征():
    """信息纪律（D-M11-2）：对手侧特征只允许计数/标记类，无手牌内容字段。"""
    opp_features = sorted(n for n in FEATURE_NAMES if n.startswith("opp_"))
    assert opp_features == [
        "opp_active_conditions_count",
        "opp_bench_count",
        "opp_deck_count",
        "opp_hand_count",
        "opp_stage0_count",
        "opp_stage1_count",
        "opp_stage2_count",
    ]
    assert not any("hand" in n and "count" not in n and "diff" not in n
                   for n in FEATURE_NAMES if n.startswith("opp_"))


def test_feature_vector_接受对手视角():
    """visible_state(1) 视角：own/opp 互换，数值随视角翻转。"""
    state = main_state()
    v0, v1 = state.visible_state(0), state.visible_state(1)
    f0, f1 = feature_vector(v0), feature_vector(v1)
    assert f0["hand_diff"] == -f1["hand_diff"]
    assert f0["own_hand_count"] == f1["opp_hand_count"]


def test_feature_vector_turn超归一化上限_截断():
    """turn_norm 口径：min(turn, 50)/50（回合上限 200，超 50 截断防爆量纲）。"""
    state = main_state().model_copy(update={"turn": 120})
    assert feature_vector(state.visible_state(0))["turn_norm"] == 1.0


def test_feature_vector_setup阶段_face_down计数():
    """布阵阶段对手背面放置：face_down_pokemon 计数，active/bench 不可见归零。"""
    p0 = PlayerState(hand=(inst(10, basic("妙蛙种子")),),
                     deck=tuple(inst(100 + i, basic("垫牌")) for i in range(10)))
    p1 = PlayerState(deck=tuple(inst(300 + i, basic("对手垫牌")) for i in range(10)),
                     active=in_play(2, basic("小火龙")),
                     bench=(in_play(3, basic("绿毛虫")),))
    state = GameState(players=(p0, p1), current_player=0, phase="setup_bench")
    feats = feature_vector(state.visible_state(0))
    assert feats["face_down_pokemon"] == 2.0       # 对手 1 active + 1 bench 背面
    assert feats["opp_bench_count"] == 0.0         # 背面期间不可见
    assert feats["opp_stage0_count"] == 0.0
