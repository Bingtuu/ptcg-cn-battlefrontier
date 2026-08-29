"""测试共用 fixture 助手：stub 卡定义与引擎驱动。"""

from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    GameState,
    InPlayPokemon,
    PlayerState,
)


def _attacks(damage: int | None, cost: int) -> tuple[AttackDef, ...]:
    """白板 stub：单个固定伤害招式，成本为 cost 个无色能量。"""
    if damage is None:
        return ()
    return (AttackDef(name="打击", cost=("无",) * cost, damage=damage),)


def basic(name: str, hp: int = 70, damage: int = 20, cost: int = 1, retreat: int = 1) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, attacks=_attacks(damage, cost), retreat_cost=retreat,
    )


def stage1(name: str, evolves_from: str, hp: int = 90, damage: int = 40, cost: int = 2) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=1, evolves_from=evolves_from, attacks=_attacks(damage, cost),
    )


def energy(name: str = "基本能量", energy_type: str | None = None) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="energy",
        energy_type=energy_type, is_basic_energy=True,
    )


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


def inst(iid: int, card: CardDef) -> CardInstance:
    return CardInstance(iid=iid, card=card)


def in_play(iid: int, card: CardDef, energies: int = 0) -> InPlayPokemon:
    return InPlayPokemon(
        stack=(inst(iid, card),),
        attached_energy=tuple(inst(9000 + iid * 10 + j, energy()) for j in range(energies)),
    )


def main_state(
    p0_active_energies: int = 1,
    p1_active_energies: int = 1,
    p0_extra_hand: tuple[CardInstance, ...] = (),
    p1_bench: tuple[InPlayPokemon, ...] = (),
) -> GameState:
    """直接构造 main 阶段局面（绕过开局，战斗/主阶段规则测试用）。"""
    a0 = in_play(1, basic("妙蛙种子"), p0_active_energies)
    a1 = in_play(2, basic("小火龙"), p1_active_energies)
    p0 = PlayerState(
        deck=tuple(inst(100 + i, basic("妙蛙种子")) for i in range(10)),
        hand=(inst(50, basic("小火龙")), inst(51, energy())) + p0_extra_hand,
        prizes=tuple(inst(200 + i, basic("妙蛙种子")) for i in range(6)),
        active=a0,
    )
    p1 = PlayerState(
        deck=tuple(inst(300 + i, basic("小火龙")) for i in range(10)),
        prizes=tuple(inst(400 + i, basic("小火龙")) for i in range(6)),
        active=a1,
        bench=p1_bench,
    )
    return GameState(
        players=(p0, p1), turn=2, current_player=0, phase="main", first_player=0,
    )


def engine_at(state: GameState) -> GameEngine:
    e = GameEngine(RandomSource(0))
    e.state = state
    return e
