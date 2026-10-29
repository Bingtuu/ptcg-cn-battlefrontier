"""task 079：手牌能量优先贴到再贴一张就付清的高伤目标。"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"
GHOLDENGO_DOC = load_card_doc(CARDS_DIR / "赛富豪ex.yml")
GHOLDENGO_FX = {"赛富豪ex": GHOLDENGO_DOC}


def _split_state():
    active_card = CardDef(
        card_id="stub-双招", name="双招", supertype="pokemon", hp=130, stage=0,
        retreat_cost=2,
        attacks=(
            AttackDef(name="小", cost=("无",), damage=20),
            AttackDef(name="大", cost=("无",) * 4, damage=170),
        ),
    )
    bench_card = CardDef(
        card_id="stub-差一张", name="差一张", supertype="pokemon", hp=100, stage=0,
        retreat_cost=1,
        attacks=(AttackDef(name="中", cost=("无", "无"), damage=120),),
    )
    opp = CardDef(
        card_id="stub-靶", name="靶", supertype="pokemon", hp=100, stage=0,
        attacks=(AttackDef(name="撞", cost=("无",), damage=10),), retreat_cost=1,
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active_card, energies=1),
        "bench": (in_play(3, bench_card, energies=1),),
        "hand": (inst(51, energy()),),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp, energies=0)})
    return state.model_copy(update={"players": (p0, p1)})


def _observe(state, params=None):
    engine = engine_at(state)
    agent = HeuristicAgent(params)
    return agent.observe(engine.state.visible_state(0), engine.legal_actions(0))


def test_attach_to_bench_that_becomes_ready_not_active_second_attack():
    """战斗场 1 能招已付清、4 能招还差得远；备战 2 能招已有 1 张 → 贴备战。"""
    act = _observe(_split_state())
    assert act == Action(kind="attach_energy", iid=51, target_iid=3)


def test_gate_off_feeds_active_unpaid_second_attack():
    """energy_target_gate=False → 战斗场还有没付清的招，能量仍给战斗场。"""
    params = HeuristicParams(energy_target_gate=False)
    act = _observe(_split_state(), params)
    assert act == Action(kind="attach_energy", iid=51, target_iid=1)


def gholdengo() -> CardDef:
    """与 tests/test_agent_dsl_estimate.py 同卡面（手牌弹药型淘金潮）。"""
    return CardDef(
        card_id="stub-赛富豪ex", name="赛富豪ex", supertype="pokemon", hp=260, stage=1,
        energy_type="钢", rule_box="ex", has_ability=True,
        attacks=(AttackDef(name="淘金潮", cost=("无",), damage=50),), retreat_cost=1,
    )


def state_with(
    p0_active: CardDef, *, energies: int = 1, p0_hand: tuple = (), opp_hp: int = 70,
    opp_damage: int = 0, p0_deck: int = 10, p1_prizes: int = 6,
):
    """与 tests/test_agent_dsl_estimate.py 的 state_with 同语义。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, p0_active, energies),
        "hand": p0_hand,
        "deck": tuple(inst(100 + i, basic("垫牌")) for i in range(p0_deck)),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("对手", hp=opp_hp), 1).model_copy(
            update={"damage": opp_damage}),
        "prizes": state.players[1].prizes[:p1_prizes],
    })
    return state.model_copy(update={"players": (p0, p1)})


def test_hand_ammo_still_skips_when_active_can_attack():
    """手牌弹药型主动已能开打（费用已满足）→ _pick_energy_attach 返回 None（囤弹药）。

    夹具抄 tests/test_agent_dsl_estimate.py。开关默认开（HeuristicParams()）仍跳过。
    """
    state = state_with(gholdengo(), energies=1, p0_hand=(inst(51, energy()),))
    engine = engine_at(state)
    view = engine.state.visible_state(0)
    acts = [a for a in engine.legal_actions(0) if a.kind == "attach_energy"]
    assert acts
    agent = HeuristicAgent(HeuristicParams(), card_effects=GHOLDENGO_FX)
    assert agent._pick_energy_attach(view, acts) is None
