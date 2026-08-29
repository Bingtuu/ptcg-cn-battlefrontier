"""task 002：GameState 数据模型测试（PRD §6.1 / §6.3）。"""

import json

import pytest
from pydantic import ValidationError

from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    GameState,
    InPlayPokemon,
    PlayerState,
    SpecialCondition,
)


def _pokemon(name: str, hp: int = 70, damage: int = 20, stage: int = 0) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}",
        name=name,
        supertype="pokemon",
        hp=hp,
        stage=stage,
        attacks=(AttackDef(name="打击", cost=("无",), damage=damage),),
    )


def _energy(name: str = "基本斗能量") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy")


def _inst(iid: int, card: CardDef) -> CardInstance:
    return CardInstance(iid=iid, card=card)


def _sample_state() -> GameState:
    basic = _pokemon("stub-妙蛙种子")
    energy = _energy()
    active = InPlayPokemon(
        stack=(_inst(1, basic),),
        attached_energy=(_inst(2, energy),),
        damage=20,
        conditions=frozenset({SpecialCondition.POISONED}),
    )
    p0 = PlayerState(
        deck=tuple(_inst(10 + i, basic) for i in range(50)),
        hand=(_inst(3, basic), _inst(4, energy)),
        prizes=tuple(_inst(100 + i, basic) for i in range(6)),
        active=active,
    )
    p1 = PlayerState(
        deck=tuple(_inst(200 + i, basic) for i in range(52)),
        prizes=tuple(_inst(300 + i, basic) for i in range(6)),
        active=InPlayPokemon(stack=(_inst(5, basic),)),
        bench=(InPlayPokemon(stack=(_inst(6, basic),)),),
    )
    return GameState(players=(p0, p1), turn=3, current_player=1, phase="main")


def test_card_instance_separated_from_definition() -> None:
    inst = _inst(1, _pokemon("小火龙"))
    assert inst.iid == 1
    assert inst.card.card_id == "stub-小火龙"
    # 同一卡定义可有多个实例（同名卡 4 张进卡组）
    assert _inst(2, inst.card).card is inst.card


def test_inplay_pokemon_carries_board_state() -> None:
    basic, evo = _pokemon("stub-波波"), _pokemon("stub-比比鸟", stage=1)
    p = InPlayPokemon(
        stack=(_inst(1, basic), _inst(2, evo)),
        attached_energy=(_inst(3, _energy()),),
        damage=30,
        conditions=frozenset({SpecialCondition.ASLEEP, SpecialCondition.BURNED}),
    )
    assert p.stack[-1].card.name == "stub-比比鸟"  # 栈顶为当前形态
    assert p.damage == 30 and len(p.attached_energy) == 1
    assert p.conditions == {SpecialCondition.ASLEEP, SpecialCondition.BURNED}


def test_serialization_roundtrip() -> None:
    state = _sample_state()
    payload = json.dumps(state.model_dump(mode="json"), ensure_ascii=False)
    assert GameState.model_validate(json.loads(payload)) == state


def test_state_is_immutable() -> None:
    state = _sample_state()
    with pytest.raises(ValidationError):
        state.turn = 99  # type: ignore[misc]


def test_bench_limit_five() -> None:
    basic = _pokemon("stub-小拉达")
    six = tuple(InPlayPokemon(stack=(_inst(i, basic),)) for i in range(6))
    with pytest.raises(ValidationError):
        PlayerState(bench=six)


def test_prizes_limit_six() -> None:
    basic = _pokemon("stub-超音蝠")
    seven = tuple(_inst(i, basic) for i in range(7))
    with pytest.raises(ValidationError):
        PlayerState(prizes=seven)


def test_visible_state_hides_opponent_hidden_zones() -> None:
    state = _sample_state()
    view = state.visible_state(0)
    # 自己：手牌全量可见
    assert [c.iid for c in view.own.hand] == [3, 4]
    # 对手：手牌/牌库/奖赏只剩数量，弃牌堆与场上公开
    assert view.opponent.hand_count == 0
    assert view.opponent.deck_count == 52
    assert view.opponent.prizes_count == 6
    assert not hasattr(view.opponent, "hand")
    assert view.opponent.active is not None
    assert len(view.opponent.bench) == 1


def test_visible_state_hides_own_deck_order_and_prizes() -> None:
    """PRD §6.3：牌库内容对 Agent 隐藏；奖赏卡背面放置，双方均不可见内容。

    自己侧可见：手牌（全量）、牌库/奖赏数量、弃牌堆、场上、回合规则标记。
    """
    state = _sample_state()
    view = state.visible_state(0)
    assert "deck" not in type(view.own).model_fields
    assert "prizes" not in type(view.own).model_fields
    assert view.own.deck_count == len(state.players[0].deck)
    assert view.own.prizes_count == 6
    assert [c.iid for c in view.own.hand] == [3, 4]
    # 决策所需的回合标记保留可见
    assert view.own.energy_attached_this_turn is False
    assert view.own.supporter_played_this_turn is False


def test_visible_state_is_serializable_for_agent() -> None:
    state = _sample_state()
    view = state.visible_state(1)
    payload = json.dumps(view.model_dump(mode="json"), ensure_ascii=False)
    assert json.loads(payload)["opponent"]["deck_count"] == 50
