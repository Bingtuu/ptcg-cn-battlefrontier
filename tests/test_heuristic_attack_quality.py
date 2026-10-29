"""task 080：复燃计数进估算；复制两段按有效伤害排序（D-078-7）。

计数词不走 attack_quality_gate。pokemon_score 公式不动。
"""

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.agent.dsl_estimate import estimate_attack_damage
from battlefrontier.agent.heuristic import (
    HeuristicAgent,
    HeuristicParams,
    pokemon_score,
)
from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

RELIGHT_DOC = parse_card_doc("""
card:
  name_group: 变量手
effects:
  - trigger: on_attack
    attack: 复燃
    actions:
      - {action: damage, selector: opponent_active, count: opponent_discard_basic_energy_count, args: {op: "×", per: 30}}
""")

COPY_DOC = parse_card_doc("""
card:
  name_group: 复制手
effects:
  - trigger: on_attack
    attack: 暗夜
    actions:
      - {action: copy_attack, selector: own_bench_attack, choose: 1, filters: ["owner_pokemon:N"]}
""")

RELIGHT_FX = {"变量手": RELIGHT_DOC}
COPY_FX = {"复制手": COPY_DOC}


def mon_card(name: str, **kw) -> CardDef:
    attacks = kw.pop("attacks", (AttackDef(name="打击", cost=("无",), damage=20),))
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=kw.pop("hp", 200), stage=kw.pop("stage", 0), attacks=attacks, **kw,
    )


def relight_card() -> CardDef:
    return CardDef(
        card_id="stub-变量手", name="变量手", supertype="pokemon", hp=120,
        attacks=(
            AttackDef(name="复燃", cost=("无",), damage=30),
            AttackDef(name="焚身", cost=("无",), damage=90),
        ),
    )


def relight_view(basic_count: int):
    """对手弃牌区放 basic_count 张基本能量，另加 1 张特殊能量和 1 张宝可梦。"""
    special = CardDef(
        card_id="stub-特能", name="特能", supertype="energy",
        is_basic_energy=False, energy_type="火",
    )
    discard = tuple(inst(10 + i, energy()) for i in range(basic_count)) + (
        inst(30, special),
        inst(31, basic("废")),
    )
    state = main_state()
    attacker = relight_card()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, attacker, energies=1),
    })
    p1 = state.players[1].model_copy(update={"discard": discard})
    view = state.model_copy(update={"players": (p0, p1)}).visible_state(0)
    return view, attacker


def attack_acts() -> list[Action]:
    return [
        Action(kind="attack", attack_index=0),
        Action(kind="attack", attack_index=1),
    ]


def test_relight_uses_opponent_basic_energy_in_discard():
    """弃牌区 4 张基本能量（特殊能量与宝可梦不计）→ 30× 估算 120。"""
    view, attacker = relight_view(4)
    est = estimate_attack_damage(view, "复燃", 30, attacker, RELIGHT_FX)
    assert est is not None and est.amount == 120 and est.lethal_ok


def test_pick_attack_prefers_relight_120_over_printed_90():
    """两招都付得起：估算 120 的复燃优先于印面 90。"""
    view, _attacker = relight_view(4)
    agent = HeuristicAgent(card_effects=RELIGHT_FX)
    assert agent._pick_attack(view, attack_acts()).attack_index == 0


def test_zero_basic_energy_estimate_is_zero_and_pick_falls_to_90():
    """弃牌区 0 张基本能量 → 估算 0，仍选印面 90。"""
    view, attacker = relight_view(0)
    est = estimate_attack_damage(view, "复燃", 30, attacker, RELIGHT_FX)
    assert est is not None and est.amount == 0
    agent = HeuristicAgent(card_effects=RELIGHT_FX)
    assert agent._pick_attack(view, attack_acts()).attack_index == 1


def test_counter_not_behind_attack_quality_gate():
    """关掉复制排序开关，复燃估算仍是 120，_pick_attack 仍选它。"""
    view, _attacker = relight_view(4)
    agent = HeuristicAgent(
        params=HeuristicParams(attack_quality_gate=False),
        card_effects=RELIGHT_FX,
    )
    assert agent._attack_damage_table(view)[0] == 120
    assert agent._pick_attack(view, attack_acts()).attack_index == 0


def test_attack_quality_gate_defaults_true():
    assert HeuristicParams().attack_quality_gate is True


def _copy_state(donor_b: CardDef):
    """复制手在战斗场；两只 owner=N 的备战。对手战斗场 HP 100。"""
    copier = mon_card(
        "复制手",
        attacks=(AttackDef(name="暗夜", cost=("无",), damage=None),),
    )
    donor_a = mon_card(
        "高分", owner="N", hp=800,
        attacks=(AttackDef(name="轻打", cost=(), damage=10),),
    )
    opp = mon_card("靶", hp=100, attacks=(AttackDef(name="撞", cost=(), damage=10),))
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(11, copier, energies=1),
        "bench": (in_play(70, donor_a), in_play(71, donor_b)),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp)})
    return state.model_copy(update={"players": (p0, p1)}), donor_a


def _enter_copy_choice(state):
    engine = engine_at(state)
    engine.card_effects = COPY_FX
    engine.apply(0, Action(kind="attack", attack_index=0))
    return engine


def test_copy_chooser_prefers_ko_donor_over_higher_pokemon_score():
    """A：HP 800、伤害 10，默认分更高，打不满 HP 100。

    B：HP 80、伤害 100，分更低，能斩杀。默认开关选 B 的 iid。
    印面 200 在 w_damage=5 下会让 B 的分超过 A，所以 B 取刚好斩杀的 100。
    """
    donor_b = mon_card(
        "斩杀", owner="N", hp=80,
        attacks=(AttackDef(name="重击", cost=(), damage=100),),
    )
    state, donor_a = _copy_state(donor_b)
    params = HeuristicParams()
    assert pokemon_score(in_play(70, donor_a), params) > pokemon_score(
        in_play(71, donor_b), params,
    )
    engine = _enter_copy_choice(state)
    assert engine.state.pending_choice.pool == "own_bench"
    act = HeuristicAgent(card_effects=COPY_FX).observe(
        engine.state.visible_state(0), engine.legal_actions(0),
    )
    assert act.kind == "choose" and act.choices == (71,)


def test_copy_chooser_gate_off_keeps_higher_pokemon_score():
    """attack_quality_gate=False → 仍按 pokemon_score 选高分供体 A。"""
    donor_b = mon_card(
        "斩杀", owner="N", hp=80,
        attacks=(AttackDef(name="重击", cost=(), damage=100),),
    )
    state, _donor_a = _copy_state(donor_b)
    engine = _enter_copy_choice(state)
    agent = HeuristicAgent(
        params=HeuristicParams(attack_quality_gate=False),
        card_effects=COPY_FX,
    )
    act = agent.observe(engine.state.visible_state(0), engine.legal_actions(0))
    assert act.kind == "choose" and act.choices == (70,)


def _anchored_engine():
    """B 两招：下标 0 伤害 10，下标 1 伤害 200。手动选中 B 进入第二段。"""
    donor_b = mon_card(
        "斩杀", owner="N", hp=80,
        attacks=(
            AttackDef(name="轻打", cost=(), damage=10),
            AttackDef(name="重击", cost=(), damage=200),
        ),
    )
    state, _donor_a = _copy_state(donor_b)
    engine = _enter_copy_choice(state)
    assert engine.state.pending_choice.pool == "own_bench"
    engine.apply(0, Action(kind="choose", choices=(71,)))
    pending = engine.state.pending_choice
    assert pending.pool == "anchored_pokemon_attack"
    assert pending.payload[0] == 71
    view = engine.state.visible_state(0)
    visible_iids = {c.iid for c in view.own.hand}
    visible_iids.update(c.iid for c in view.own.discard)
    for mon in (view.own.active, *view.own.bench, view.opponent.active):
        if mon is None:
            continue
        visible_iids.add(mon.current.iid)
        visible_iids.update(e.iid for e in mon.attached_energy)
    # 下标不能撞上可见卡 iid，否则旧评分会把下标当成那张卡
    assert 0 not in visible_iids and 1 not in visible_iids
    return engine


def test_anchored_attack_prefers_higher_damage_index():
    """第二段默认选伤害 200 的下标 1，不选下标 0。"""
    engine = _anchored_engine()
    act = HeuristicAgent(card_effects=COPY_FX).observe(
        engine.state.visible_state(0), engine.legal_actions(0),
    )
    assert act.kind == "choose" and act.choices == (1,)


def test_anchored_attack_gate_off_keeps_lowest_index():
    """开关关：两段下标分数都落空，tie-break 取下标 0。"""
    engine = _anchored_engine()
    agent = HeuristicAgent(
        params=HeuristicParams(attack_quality_gate=False),
        card_effects=COPY_FX,
    )
    act = agent.observe(engine.state.visible_state(0), engine.legal_actions(0))
    assert act.kind == "choose" and act.choices == (0,)


def test_pick_attack_prefers_190_over_60_when_both_payable():
    """同一只 60 与 190 都付得起 → 选 190。不改 end_turn 政策。"""
    card = CardDef(
        card_id="stub-双招", name="双招", supertype="pokemon", hp=160,
        attacks=(
            AttackDef(name="小打", cost=("无",), damage=60),
            AttackDef(name="大打", cost=("无",), damage=190),
        ),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, card, energies=1)})
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=300), energies=0),
    })
    view = state.model_copy(update={"players": (p0, p1)}).visible_state(0)
    picked = HeuristicAgent()._pick_attack(view, attack_acts())
    assert picked.attack_index == 1


def test_only_60_still_attacks_instead_of_end_turn():
    """只有 60 付得起（190 差能量）→ 仍然攻击，不改 end_turn。"""
    card = CardDef(
        card_id="stub-双招", name="双招", supertype="pokemon", hp=160,
        attacks=(
            AttackDef(name="小打", cost=("无",), damage=60),
            AttackDef(name="大打", cost=("无", "无", "无"), damage=190),
        ),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, card, energies=1),
        "hand": (),
        "bench": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=300), energies=0),
    })
    engine = engine_at(state.model_copy(update={"players": (p0, p1)}))
    act = HeuristicAgent().observe(engine.state.visible_state(0), engine.legal_actions(0))
    assert act.kind == "attack" and act.attack_index == 0
