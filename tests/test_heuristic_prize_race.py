"""task 086：路径可见后的奖杯节奏。禁止 prize_pressure_gate。"""

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams
from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

COPY_DOC = parse_card_doc("""
card:
  name_group: 复制手
effects:
  - trigger: on_attack
    attack: 复制
    actions:
      - {action: copy_attack, selector: own_bench_attack, choose: 1, filters: ["owner_pokemon:N"]}
""")
SUPPORTER_DOC = parse_card_doc("""
card:
  name_group: 测试支援者
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 2}
""")
FX = {"复制手": COPY_DOC, "测试支援者": SUPPORTER_DOC}


def _observe(state, params=None, card_effects=FX):
    engine = engine_at(state)
    engine.card_effects = card_effects
    agent = HeuristicAgent(params, card_effects=card_effects)
    return agent.observe(engine.state.visible_state(0), engine.legal_actions(0))


def _donor() -> CardDef:
    return CardDef(
        card_id="stub-供体", name="供体", supertype="pokemon",
        hp=100, stage=0, retreat_cost=0, owner="N",
        attacks=(AttackDef(name="打击", cost=(), damage=200),),
    )


def _copier() -> CardDef:
    return CardDef(
        card_id="stub-复制手", name="复制手", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="复制", cost=("无",), damage=None),),
    )


def _printed(name: str, *, hp: int, damage: int) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="打击", cost=("无",), damage=damage),),
    )


def _supporter() -> CardDef:
    return CardDef(
        card_id="stub-测试支援者", name="测试支援者", supertype="trainer",
        trainer_subtype="支援者",
    )


def _unpaid_donor() -> CardDef:
    """印面 200，两费未付。pokemon_score 高；自己前瞻伤害 0。复制仍可读 200。"""
    return CardDef(
        card_id="stub-未付供体", name="未付供体", supertype="pokemon",
        hp=180, stage=0, retreat_cost=0, owner="N",
        attacks=(AttackDef(name="打击", cost=("无", "无"), damage=200),),
    )


def _copy_bench_vs_printed_active(*, behind: bool, opp_hp: int = 400):
    """战斗场印面 60；备战复制 200 + 供体。两边都不斩杀（opp_hp 大）。"""
    state = main_state()
    own_prizes = state.players[0].prizes
    opp_prizes = state.players[1].prizes[:2] if behind else state.players[1].prizes
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _printed("芯片", hp=110, damage=60), energies=1),
        "bench": (
            in_play(3, _copier(), energies=1),
            in_play(70, _donor(), energies=0),
        ),
        "hand": (),
        "prizes": own_prizes,
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=opp_hp), energies=0),
        "prizes": opp_prizes,
    })
    state = state.model_copy(update={"players": (p0, p1)})
    if behind:
        assert len(state.players[0].prizes) > len(state.players[1].prizes)
    else:
        assert len(state.players[0].prizes) == len(state.players[1].prizes)
    return state


def test_lookahead_gate_off_prize_race_has_no_effect():
    """总闸关：即使落后 + prize_race 开，也不因奖差撤到复制。"""
    state = _copy_bench_vs_printed_active(behind=True)
    params = HeuristicParams(
        ko_prize_lookahead_gate=False,
        copy_conversion_gate=False,
        prize_race_gate=True,
    )
    act = _observe(state, params)
    assert act.kind == "attack"
    assert act != Action(kind="retreat", bench_index=0)


def test_behind_retreats_to_higher_copy_when_prize_race_on():
    """落后 + 复制路径可见 + 备战复制伤严格更高 → 撤。隔离 085：关 conversion。"""
    state = _copy_bench_vs_printed_active(behind=True)
    params = HeuristicParams(copy_conversion_gate=False, prize_race_gate=True)
    assert _observe(state, params) == Action(kind="retreat", bench_index=0)
    off = HeuristicParams(copy_conversion_gate=False, prize_race_gate=False)
    act_off = _observe(state, off)
    assert act_off.kind == "attack"
    assert act_off != Action(kind="retreat", bench_index=0)


def test_not_behind_does_not_retreat_just_for_prize_race():
    """不落后 + 同上布局：不因奖杯节奏撤（085 层另议，本测关 conversion）。"""
    state = _copy_bench_vs_printed_active(behind=False)
    params = HeuristicParams(copy_conversion_gate=False, prize_race_gate=True)
    act = _observe(state, params)
    assert act.kind == "attack"
    assert act != Action(kind="retreat", bench_index=0)


def test_behind_higher_printed_non_copy_does_not_retreat():
    """落后 + 仅印面更高的非复制备战 → 不撤（081 反例回归）。"""
    chip = _printed("低伤", hp=110, damage=60)
    bigger = _printed("中伤", hp=100, damage=120)
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, chip, energies=1),
        "bench": (in_play(3, bigger, energies=1),),
        "hand": (),
        "prizes": state.players[0].prizes,
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=300), energies=0),
        "prizes": state.players[1].prizes[:2],
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert len(state.players[0].prizes) > len(state.players[1].prizes)
    act = _observe(state, HeuristicParams(prize_race_gate=True))
    assert act.kind == "attack"
    assert act != Action(kind="retreat", bench_index=0)


def test_can_ko_still_attacks_before_supporter():
    """can_ko 时仍攻击，先于支援者（不因奖差推迟斩杀）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (inst(61, _supporter()),),
        "prizes": state.players[0].prizes,
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=100, damage=10), energies=0),
        "prizes": state.players[1].prizes[:2],
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert len(state.players[0].prizes) > len(state.players[1].prizes)
    act = _observe(state, HeuristicParams(prize_race_gate=True))
    assert act == Action(kind="attack", attack_index=0)


def test_behind_promote_prefers_copy_over_higher_score():
    """落后 + 路径可见：换上复制优先于更高分无复制供体。隔离 085。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (
            in_play(3, _copier(), energies=1),
            in_play(70, _unpaid_donor(), energies=0),
        ),
        "hand": (),
        "prizes": state.players[0].prizes,
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
        "prizes": state.players[1].prizes[:2],
    })
    state = state.model_copy(update={"players": (p0, p1), "phase": "promote"})
    assert len(state.players[0].prizes) > len(state.players[1].prizes)
    params = HeuristicParams(copy_conversion_gate=False, prize_race_gate=True)
    assert _observe(state, params) == Action(kind="promote", bench_index=0)
    off = HeuristicParams(copy_conversion_gate=False, prize_race_gate=False)
    assert _observe(state, off) == Action(kind="promote", bench_index=1)


def test_not_behind_promote_does_not_prefer_copy_just_for_prize_race():
    """不落后：关 conversion 时不因奖杯节奏把复制抬过更高分供体。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (
            in_play(3, _copier(), energies=1),
            in_play(70, _unpaid_donor(), energies=0),
        ),
        "hand": (),
        "prizes": state.players[0].prizes,
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
        "prizes": state.players[1].prizes,
    })
    state = state.model_copy(update={"players": (p0, p1), "phase": "promote"})
    assert len(state.players[0].prizes) == len(state.players[1].prizes)
    params = HeuristicParams(copy_conversion_gate=False, prize_race_gate=True)
    assert _observe(state, params) == Action(kind="promote", bench_index=1)


def test_no_prize_pressure_gate_attribute_and_tune_stays_10():
    params = HeuristicParams()
    assert hasattr(params, "prize_race_gate")
    assert params.prize_race_gate is True
    assert not hasattr(params, "prize_pressure_gate")
    from battlefrontier.tune.space import search_space
    assert len(search_space()) == 10