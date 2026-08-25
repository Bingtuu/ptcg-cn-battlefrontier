"""task 003-A：开局布阵与 mulligan（官方规则书·游戏准备）。

规则出处：PTCG 简中官方规则书「游戏的准备」——掷币定先后手、起手 7 张、
无基础宝可梦则 mulligan（展示手牌洗回重抽，对手可按 mulligan 次数抽牌）、
放置战斗场 1 只 + 备战区任意只、奖赏卡 6 张。
"""

from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef


def basic(name: str, hp: int = 70, damage: int = 20, cost: int = 1) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, attack_damage=damage, attack_cost=cost,
    )


def stage1(name: str, evolves_from: str, hp: int = 90, damage: int = 40, cost: int = 2) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=1, evolves_from=evolves_from, attack_damage=damage, attack_cost=cost,
    )


def energy(name: str = "基本能量") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy")


def deck60() -> list[CardDef]:
    return (
        [basic("妙蛙种子")] * 20
        + [stage1("妙蛙草", "妙蛙种子")] * 4
        + [basic("小火龙")] * 20
        + [energy()] * 16
    )


def new_game(seed: int = 42, deck: list[CardDef] | None = None) -> GameEngine:
    d = deck if deck is not None else deck60()
    engine = GameEngine(RandomSource(seed))
    engine.new_game(d, d)
    return engine


def finish_setup(engine: GameEngine) -> None:
    """双方各放 1 战斗场 + 确认（跳过备战区选择）。"""
    for player in (0, 1):
        act = next(a for a in engine.legal_actions(player) if a.kind == "place_active")
        engine.apply(player, act)
        confirm = next(a for a in engine.legal_actions(player) if a.kind == "confirm_setup")
        engine.apply(player, confirm)


def test_new_game_deterministic_same_seed() -> None:
    e1, e2 = new_game(42), new_game(42)
    assert e1.state.model_dump(mode="json") == e2.state.model_dump(mode="json")


def test_new_game_different_seed_differs() -> None:
    assert (
        new_game(1).state.model_dump(mode="json")
        != new_game(2).state.model_dump(mode="json")
    )


def test_setup_deals_seven_hand_and_six_prizes() -> None:
    e = new_game()
    for p in e.state.players:
        assert len(p.hand) == 7
        assert len(p.prizes) == 6
        assert len(p.deck) == 60 - 7 - 6


def test_setup_starts_with_place_active_choices() -> None:
    e = new_game()
    actions = e.legal_actions(0)
    kinds = {a.kind for a in actions}
    assert kinds == {"place_active"}
    # 只能选手牌中的基础宝可梦（本 fixture 起手必有）
    assert all(a.iid is not None for a in actions)


def test_mulligan_reshuffles_until_basic() -> None:
    # 59 能量 + 1 基础：几乎必然多次 mulligan
    deck = [energy()] * 59 + [basic("独角虫")]
    e = new_game(7, deck)
    kinds = [ev.kind for ev in e.events]
    assert "mulligan" in kinds
    # mulligan 后双方起手都必有基础宝可梦
    for p in e.state.players:
        assert any(c.card.supertype.value == "pokemon" and c.card.stage == 0 for c in p.hand)


def test_place_active_and_confirm_setup_enters_main() -> None:
    e = new_game()
    finish_setup(e)
    assert e.state.phase == "main"
    assert e.state.turn == 1
    for p in e.state.players:
        assert p.active is not None
