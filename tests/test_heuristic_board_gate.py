"""task 078：前场质量门控。不改 pokemon_score 公式。"""

from pathlib import Path

import yaml
from helpers import basic, energy, engine_at, in_play, inst, main_state, stage1

from battlefrontier.agent.heuristic import (
    HeuristicAgent,
    HeuristicParams,
    pokemon_score,
)
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import AttackDef, CardDef, GameState, PlayerState


def setup_state(hand, phase="setup_active", bench=()):
    """与 tests/test_heuristic_agent.py 同语义（该模块导入会拉 ptcgdb）。"""
    p0 = PlayerState(
        hand=tuple(hand),
        deck=tuple(inst(100 + i, basic("垫牌")) for i in range(10)),
        active=in_play(1, basic("已就位")) if phase == "setup_bench" else None,
        bench=bench,
    )
    p1 = PlayerState(deck=tuple(inst(300 + i, basic("对手垫牌")) for i in range(10)))
    return GameState(players=(p0, p1), current_player=0, phase=phase)


def engine_with(state: GameState, card_effects: dict | None = None) -> GameEngine:
    e = GameEngine(RandomSource(0), card_effects=card_effects)
    e.state = state
    return e


def decide(engine, params=None):
    agent = HeuristicAgent(params)
    view = engine.state.visible_state(0)
    return agent.observe(view, engine.legal_actions(0))


def two_attack(name: str, *, hp: int, damage: int, cost: int, retreat: int) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, retreat_cost=retreat,
        attacks=(AttackDef(name="打击", cost=("无",) * cost, damage=damage),),
    )


def test_retreat_to_bench_ko_when_active_chip_cannot_ko():
    """战斗场 60 付得起但不斩杀；备战 190 付得起且斩杀 → 撤退。"""
    active = two_attack("低伤", hp=110, damage=60, cost=1, retreat=0)
    bench = two_attack("杀招", hp=200, damage=190, cost=1, retreat=1)
    opp = two_attack("靶", hp=150, damage=10, cost=1, retreat=1)
    state = main_state(p0_active_energies=1, p1_active_energies=0)
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(3, bench, energies=1),),
        "hand": (),  # 手里有能量时 _decide_main 会先附着，测不到撤退
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp, energies=0)})
    state = state.model_copy(update={"players": (p0, p1)})
    act = decide(engine_at(state))
    assert act == Action(kind="retreat", bench_index=0)


def test_no_retreat_when_active_already_kos():
    """战斗场自己 190 已能斩杀 → 不撤，打出攻击。"""
    active = two_attack("已能杀", hp=200, damage=190, cost=1, retreat=0)
    bench = two_attack("备选", hp=200, damage=200, cost=1, retreat=1)
    opp = two_attack("靶", hp=150, damage=10, cost=1, retreat=1)
    state = main_state(p0_active_energies=1)
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(3, bench, energies=1),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp, energies=0)})
    state = state.model_copy(update={"players": (p0, p1)})
    act = decide(engine_at(state))
    assert act.kind == "attack"


def test_gate_off_keeps_chip_active():
    """board_quality_gate=False：付得起就不撤。"""
    active = two_attack("低伤", hp=110, damage=60, cost=1, retreat=0)
    bench = two_attack("杀招", hp=200, damage=190, cost=1, retreat=1)
    opp = two_attack("靶", hp=150, damage=10, cost=1, retreat=1)
    state = main_state(p0_active_energies=1)
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active, energies=1),
        "bench": (in_play(3, bench, energies=1),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp, energies=0)})
    state = state.model_copy(update={"players": (p0, p1)})
    params = HeuristicParams(board_quality_gate=False)
    act = decide(engine_at(state), params)
    assert act.kind != "retreat"


def test_setup_prefers_basic_that_heads_a_line_in_hand():
    """高伤基础 vs 低伤基础+手里的一阶 → 放低伤基础。"""
    fat = basic("高伤", hp=110, damage=60)
    baby = basic("幼基", hp=60, damage=10)
    evo = stage1("一阶", "幼基", hp=90, damage=30)
    hand = [inst(10, fat), inst(11, baby), inst(12, evo), inst(13, energy())]
    act = decide(engine_with(setup_state(hand)))
    assert act == Action(kind="place_active", iid=11)


def test_setup_without_line_still_uses_pokemon_score():
    """手里没有进化关系 → 仍放 pokemon_score 更高的基础。"""
    fat = basic("高伤", hp=110, damage=60)
    weak = basic("弱", hp=40, damage=10)
    hand = [inst(10, weak), inst(11, fat)]
    act = decide(engine_with(setup_state(hand)))
    assert act == Action(kind="place_active", iid=11)
    assert pokemon_score(inst(11, fat), HeuristicParams()) > pokemon_score(
        inst(10, weak), HeuristicParams())


def test_promote_still_follows_pokemon_score():
    """promote 不改：分高的备战换上。"""
    low = in_play(3, basic("弱", hp=40, damage=10))
    high = in_play(4, basic("强", hp=100, damage=50))
    p0 = PlayerState(
        deck=tuple(inst(100 + i, basic("垫")) for i in range(10)),
        bench=(low, high),
    )
    p1 = PlayerState(deck=tuple(inst(300 + i, basic("对手")) for i in range(10)))
    state = GameState(players=(p0, p1), current_player=0, phase="promote")
    act = decide(engine_with(state))
    assert act == Action(kind="promote", bench_index=1)


def test_t078_local_experiment_pins_the_diagnosed_cell():
    """本机验收实验：与 t077 同格、种子从 208000 起的 100 局。

    只核 YAML 字段（云端无 ptcg-cn.db，不经 load_experiment）。utf-8 读取。
    """
    raw = yaml.safe_load(
        (Path(__file__).parent.parent / "experiments" / "t078-gard-zoro.example.yml")
        .read_text(encoding="utf-8"))
    assert raw["name"] == "t078-gard-zoro"
    assert raw["games"] == 100
    assert raw["seed_start"] == 208000
    assert raw["decks"]["a"]["deck_id"] == "mik_moe:678647"
    assert raw["decks"]["b"]["deck_id"] == "mik_moe:690359"
    assert raw["agents"]["a"]["type"] == "heuristic"
    assert raw["agents"]["b"]["type"] == "heuristic"
    assert "params" not in raw["agents"]["a"]
    assert "params" not in raw["agents"]["b"]
