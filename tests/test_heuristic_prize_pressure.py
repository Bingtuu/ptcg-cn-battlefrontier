"""task 081：落后抢奖。不改 pokemon_score 公式。"""

from helpers import engine_at, in_play, main_state

from battlefrontier.agent.heuristic import (
    HeuristicAgent,
    HeuristicParams,
    pokemon_score,
)
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef


def decide(engine, params=None):
    agent = HeuristicAgent(params)
    view = engine.state.visible_state(0)
    return agent.observe(view, engine.legal_actions(0))


def poke(name: str, *, hp: int, damage: int, cost: int, retreat: int) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, retreat_cost=retreat,
        attacks=(AttackDef(name="打击", cost=("无",) * cost, damage=damage),),
    )


def _chip_state(*, own_prizes: int, opp_prizes: int):
    """战斗场 30 付得起，备战 120 付得起，对手 200。都打不倒。手里清空，避免附着。"""
    active = poke("低伤", hp=110, damage=30, cost=1, retreat=0)
    bench = poke("高伤", hp=120, damage=120, cost=1, retreat=1)
    opp = poke("靶", hp=200, damage=10, cost=1, retreat=1)
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(3, bench, energies=1),),
        "hand": (),
        "prizes": state.players[0].prizes[:own_prizes],
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, opp, energies=0),
        "prizes": state.players[1].prizes[:opp_prizes],
    })
    return state.model_copy(update={"players": (p0, p1)})


def test_behind_retreats_to_higher_chip_when_nobody_kos():
    """我方奖赏剩 6、对手剩 2（落后）。30 和 120 都打不满 200 → 撤退。"""
    act = decide(engine_at(_chip_state(own_prizes=6, opp_prizes=2)))
    assert act == Action(kind="retreat", bench_index=0)


def test_tied_prizes_do_not_retreat_for_chip():
    """双方都剩 6。未落后 → 不撤，打出 30。"""
    act = decide(engine_at(_chip_state(own_prizes=6, opp_prizes=6)))
    assert act.kind == "attack"


def test_ahead_does_not_retreat_for_chip():
    """我方剩 2、对手剩 6（领先）→ 不撤。"""
    act = decide(engine_at(_chip_state(own_prizes=2, opp_prizes=6)))
    assert act.kind == "attack"


def test_gate_off_keeps_chip_active_even_when_behind():
    """prize_pressure_gate=False：落后也不为了更高的非击杀而撤。"""
    params = HeuristicParams(prize_pressure_gate=False)
    act = decide(engine_at(_chip_state(own_prizes=6, opp_prizes=2)), params)
    assert act.kind != "retreat"


def test_existing_ko_retreat_still_happens_when_tied():
    """未落后，但备战能击杀、战斗场不能：仍是 078 的撤退。"""
    active = poke("低伤", hp=110, damage=30, cost=1, retreat=0)
    bench = poke("杀招", hp=160, damage=190, cost=1, retreat=1)
    opp = poke("靶", hp=150, damage=10, cost=1, retreat=1)
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(3, bench, energies=1),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp, energies=0)})
    act = decide(engine_at(state.model_copy(update={"players": (p0, p1)})))
    assert act == Action(kind="retreat", bench_index=0)


def _promote_state(*, own_prizes: int, opp_prizes: int):
    """墙：HP 800 印面 10，分更高，0 能量。击杀手：HP 70 印面 90，已付 1 能量。

    对手 HP 80。90 能击杀，10 不能。
    pokemon_score 默认 1/5/−10：墙 800+50−10=840，击杀手 70+450−10=510。
    """
    wall = poke("墙", hp=800, damage=10, cost=1, retreat=1)
    killer = poke("斩", hp=70, damage=90, cost=1, retreat=1)
    opp = poke("靶", hp=80, damage=10, cost=1, retreat=1)
    state = main_state()
    params = HeuristicParams()
    assert pokemon_score(in_play(30, wall), params) > pokemon_score(in_play(31, killer), params)
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (in_play(30, wall, energies=0), in_play(31, killer, energies=1)),
        "hand": (),
        "prizes": state.players[0].prizes[:own_prizes],
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, opp, energies=0),
        "prizes": state.players[1].prizes[:opp_prizes],
    })
    return state.model_copy(update={"players": (p0, p1), "phase": "promote"})


def test_promote_when_behind_prefers_paid_ko():
    """落后 → promote 下标 1（已付清且能击杀），不是分更高的墙。"""
    act = decide(engine_at(_promote_state(own_prizes=6, opp_prizes=2)))
    assert act == Action(kind="promote", bench_index=1)


def test_promote_when_tied_stays_on_pokemon_score():
    """未落后 → 仍 promote 墙（下标 0）。"""
    act = decide(engine_at(_promote_state(own_prizes=6, opp_prizes=6)))
    assert act == Action(kind="promote", bench_index=0)


def test_promote_gate_off_stays_on_pokemon_score():
    params = HeuristicParams(prize_pressure_gate=False)
    act = decide(engine_at(_promote_state(own_prizes=6, opp_prizes=2)), params)
    assert act == Action(kind="promote", bench_index=0)
