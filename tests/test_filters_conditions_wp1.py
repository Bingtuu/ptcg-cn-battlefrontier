"""task 026 WP1：filters / conditions 高频解锁项注册测试（红→绿）。

filters 求值点 = dsl/chooser.py `_match_one`（卡维度）/ `_match_in_play`（场上维度）；
conditions 求值点 = `condition_met`。未知词 / 畸形参数 = DslError（不猜）。
测试函数中文名（b1 起库内惯例）。
"""

import pytest
from helpers import basic, energy, engine_at, in_play, inst, main_state, stage1

from battlefrontier.dsl.chooser import (
    condition_met,
    matches,
    matches_in_play,
)
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.state import CardDef


def named_pokemon(name: str, owner: str | None = None, rule_box: str | None = None,
                  labels: tuple[str, ...] = (), is_tera: bool = False) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=100, stage=0, rule_box=rule_box, owner=owner, labels=labels,
        is_tera=is_tera,
    )


# ── filters：卡维度 ─────────────────────────────────────────────────────


def test_name_filter_按卡名匹配() -> None:
    夜巡灵 = inst(1, named_pokemon("夜巡灵"))
    其他 = inst(2, named_pokemon("彷徨夜灵"))
    assert matches(夜巡灵, ("name:夜巡灵",))
    assert not matches(其他, ("name:夜巡灵",))


def test_owner_pokemon_filter_主人与卡种双约束() -> None:
    玛俐宝可梦 = inst(1, named_pokemon("玛俐的捣蛋小妖", owner="玛俐"))
    其他宝可梦 = inst(2, named_pokemon("小火龙"))
    玛俐训练家 = inst(3, CardDef(
        card_id="stub-玛俐的骄傲", name="玛俐的骄傲", supertype="trainer",
        trainer_subtype="支援者", owner="玛俐",
    ))
    assert matches(玛俐宝可梦, ("owner_pokemon:玛俐",))
    assert not matches(其他宝可梦, ("owner_pokemon:玛俐",))
    assert not matches(玛俐训练家, ("owner_pokemon:玛俐",))  # 训练家不算「玛俐的宝可梦」


def test_energy_属性_filter_参数化() -> None:
    草能量 = inst(1, energy("基本草能量", "草"))
    特殊恶能量 = inst(2, CardDef(
        card_id="stub-恶能", name="特殊恶能量", supertype="energy", energy_type="恶",
    ))
    超宝可梦 = inst(3, CardDef(
        card_id="stub-超兽", name="超兽", supertype="pokemon", hp=60, energy_type="超",
    ))
    assert matches(草能量, ("energy_草",))
    assert matches(特殊恶能量, ("energy_恶",))  # 不绑定 is_basic_energy（基本约束用组合词）
    assert not matches(超宝可梦, ("energy_超",))  # 宝可梦属性不算能量卡
    # 旧字面词 energy_超 行为回归（泛化为前缀机制后不变）
    assert matches(inst(4, energy("基本超能量", "超")), ("energy_超",))


def test_pokemon_no_rule_or_basic_energy_filter() -> None:
    基础 = inst(1, basic("小拉达"))
    一阶 = inst(2, stage1("妙蛙草", "妙蛙种子"))
    ex = inst(3, named_pokemon("假面兽ex", rule_box="ex"))
    基本能量 = inst(4, energy("基本能量", "超"))
    特殊能量 = inst(5, CardDef(
        card_id="stub-特能", name="特殊能量", supertype="energy", energy_type="无",
    ))
    训练家 = inst(6, CardDef(
        card_id="stub-物品", name="物品", supertype="trainer", trainer_subtype="物品",
    ))
    f = ("pokemon_no_rule_or_basic_energy",)
    assert matches(基础, f) and matches(一阶, f) and matches(基本能量, f)
    assert not matches(ex, f)  # 拥有规则的宝可梦除外
    assert not matches(特殊能量, f) and not matches(训练家, f)


def test_trait_filter_卡维度() -> None:
    古代 = inst(1, named_pokemon("吼叫尾", labels=("古代",)))
    普通 = inst(2, named_pokemon("胖丁"))
    assert matches(古代, ("trait:古代",))
    assert not matches(普通, ("trait:古代",))
    assert not matches(古代, ("trait:未来",))


# ── filters：场上维度 ────────────────────────────────────────────────────


def test_basic_pokemon_in_play_filter() -> None:
    mon = in_play(1, basic("妙蛙种子"))
    evolved = in_play(2, stage1("妙蛙草", "妙蛙种子"))
    assert matches_in_play(mon, ("basic_pokemon",))
    assert not matches_in_play(evolved, ("basic_pokemon",))


def test_trait_filter_场上维度() -> None:
    mon = in_play(1, named_pokemon("吼叫尾", labels=("古代",)))
    other = in_play(2, basic("胖丁"))
    assert matches_in_play(mon, ("trait:古代",))
    assert not matches_in_play(other, ("trait:古代",))


def test_未知filter词_DslError() -> None:
    with pytest.raises(DslError):
        matches(inst(1, basic("小拉达")), ("namee:小拉达",))
    with pytest.raises(DslError):
        matches_in_play(in_play(1, basic("小拉达")), ("basicc_pokemon",))


# ── conditions ──────────────────────────────────────────────────────────


def _engine_with(active_card: CardDef | None = None, bench_cards: tuple = (),
                 turn: int = 2, p1_prizes: int = 6):
    """main 阶段引擎：p0 战斗场/备战/回合数/对手奖赏数可调。"""
    from battlefrontier.engine.state import CardInstance

    state = main_state()
    p0 = state.players[0]
    if active_card is not None:
        p0 = p0.model_copy(update={"active": in_play(1, active_card)})
    if bench_cards:
        p0 = p0.model_copy(update={
            "bench": tuple(in_play(10 + i, c) for i, c in enumerate(bench_cards)),
        })
    p1 = state.players[1].model_copy(update={
        "prizes": tuple(
            CardInstance(iid=400 + i, card=basic("小火龙")) for i in range(p1_prizes)
        ),
    })
    s = state.model_copy(update={"players": (p0, p1), "turn": turn})
    return engine_at(s)


def test_self_is_active与holder_is_active() -> None:
    e = _engine_with(active_card=named_pokemon("赛富豪ex"))
    active_mon = e.state.players[0].active
    bench_mon = in_play(99, basic("喵喵"))
    for cond in ("self_is_active", "holder_is_active"):
        assert condition_met(cond, e, 0, active_mon)
        assert not condition_met(cond, e, 0, bench_mon)
        assert not condition_met(cond, e, 0, None)


def test_first_own_turn() -> None:
    assert condition_met("first_own_turn", _engine_with(turn=1), 0)
    assert not condition_met("first_own_turn", _engine_with(turn=2), 0)


def test_own_tera_in_play() -> None:
    e = _engine_with(active_card=named_pokemon("普通兽"),
                     bench_cards=(named_pokemon("太晶兽ex", is_tera=True),))
    assert condition_met("own_tera_in_play", e, 0)
    e2 = _engine_with(active_card=named_pokemon("普通兽"))
    assert not condition_met("own_tera_in_play", e2, 0)


def test_opponent_prizes_eq与in() -> None:
    e = _engine_with(p1_prizes=4)
    assert condition_met("opponent_prizes_eq:4", e, 0)
    assert not condition_met("opponent_prizes_eq:2", e, 0)
    assert condition_met("opponent_prizes_in:[4,3]", e, 0)
    assert not condition_met("opponent_prizes_in:[2,1]", e, 0)


def test_holder_hp_le() -> None:
    mon = in_play(1, basic("妙蛙种子", hp=70))
    mon = mon.model_copy(update={"damage": 40})  # 剩余 30
    e = _engine_with()
    assert condition_met("holder_hp_le:30", e, 0, mon)
    assert not condition_met("holder_hp_le:20", e, 0, mon)
    assert not condition_met("holder_hp_le:30", e, 0, None)


def test_未知condition词_DslError() -> None:
    e = _engine_with()
    with pytest.raises(DslError):
        condition_met("self_is_bench", e, 0)
    with pytest.raises(DslError):
        condition_met("opponent_prizes_eq:abc", e, 0)
    with pytest.raises(DslError):
        condition_met("opponent_prizes_in:4,3", e, 0)  # 缺方括号 = 畸形参数
