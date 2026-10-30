"""task 085：非斩杀路径上的一层复制输出。

不改复制击杀短路。不引入 prize_pressure_gate。
"""

from helpers import basic, energy, engine_at, in_play, inst, main_state

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
FX = {"复制手": COPY_DOC, "双招复制": COPY_DOC, "测试支援者": SUPPORTER_DOC}


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


def _copier(*, cost: tuple[str, ...] = ("无",)) -> CardDef:
    return CardDef(
        card_id="stub-复制手", name="复制手", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="复制", cost=cost, damage=None),),
    )


def _printed(name: str, *, hp: int, damage: int, cost: tuple[str, ...] = ("无",)) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="打击", cost=cost, damage=damage),),
    )


def test_copy_ko_still_attacks_before_supporter_with_conversion_gate():
    """084 Q2=C：转换开关默认开，也不推迟复制斩杀。"""
    supporter = CardDef(
        card_id="stub-测试支援者", name="测试支援者", supertype="trainer",
        trainer_subtype="支援者",
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (inst(61, supporter),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=100, damage=10), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    act = _observe(state, HeuristicParams())
    assert act == Action(kind="attack", attack_index=0)


def test_retreat_onto_higher_copy_when_neither_kos():
    """都不能斩杀。备战复制 200 > 战斗场印面 60 → 撤。关开关则不撤。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _printed("芯片", hp=110, damage=60), energies=1),
        "bench": (
            in_play(3, _copier(), energies=1),
            in_play(70, _donor(), energies=0),
        ),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="retreat", bench_index=0)
    off = HeuristicParams(copy_conversion_gate=False)
    act_off = _observe(state, off)
    assert act_off.kind == "attack"
    assert act_off != Action(kind="retreat", bench_index=0)


def test_active_copy_ko_still_refuses_retreat():
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=100), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="attack", attack_index=0)


def _unpaid_donor() -> CardDef:
    """印面 200，但两费未付。pokemon_score 高；自己的前瞻伤害是 0。复制仍可读这 200。"""
    return CardDef(
        card_id="stub-未付供体", name="未付供体", supertype="pokemon",
        hp=180, stage=0, retreat_cost=0, owner="N",
        attacks=(AttackDef(name="打击", cost=("无", "无"), damage=200),),
    )


def test_promote_non_ko_prefers_copy_over_higher_score():
    """供体分更高，但自己没付清。复制前瞻 200，对手 400 血，两边都不斩杀 → 换上复制。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (
            in_play(3, _copier(), energies=1),
            in_play(70, _unpaid_donor(), energies=0),
        ),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1), "phase": "promote"})
    assert _observe(state) == Action(kind="promote", bench_index=0)
    off = HeuristicParams(copy_conversion_gate=False)
    assert _observe(state, off) == Action(kind="promote", bench_index=1)


def test_promote_without_copy_candidate_keeps_score_order():
    """没有复制候选：高分墙仍优先于低分芯片。"""
    wall = _printed("墙", hp=250, damage=10)
    chip = _printed("芯片", hp=80, damage=20)
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (in_play(3, chip, energies=1), in_play(4, wall, energies=1)),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1), "phase": "promote"})
    assert _observe(state) == Action(kind="promote", bench_index=1)


def test_energy_enables_copy_over_smaller_printed_attack():
    """复制差一张，启用后前瞻 200；印面差一张只有 40。贴复制身体。"""
    printed = _printed("小招", hp=100, damage=40, cost=("无", "无"))
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _printed("已付清", hp=90, damage=30), energies=1),
        "bench": (
            in_play(3, printed, energies=1),
            in_play(4, _copier(cost=("无", "无")), energies=1),
            in_play(70, _donor(), energies=0),
        ),
        "hand": (inst(51, energy()),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="attach_energy", iid=51, target_iid=4)
    off = HeuristicParams(copy_conversion_gate=False)
    assert _observe(state, off) == Action(kind="attach_energy", iid=51, target_iid=3)


def test_pick_attack_uses_copy_damage_when_not_lethal():
    """两招都付清、都斩杀不了：复制 200 高于印面 50。关开关选印面。"""
    body = CardDef(
        card_id="stub-双招复制", name="双招复制", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0,
        attacks=(
            AttackDef(name="芯片", cost=("无",), damage=50),
            AttackDef(name="复制", cost=("无",), damage=None),
        ),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, body, energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="attack", attack_index=1)
    off = HeuristicParams(copy_conversion_gate=False)
    assert _observe(state, off) == Action(kind="attack", attack_index=0)


def test_single_copy_attack_is_unchanged_when_it_does_not_ko():
    """只有一条复制招式、且斩杀不了：两个开关都打出 attack_index=0。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="attack", attack_index=0)
    off = HeuristicParams(copy_conversion_gate=False)
    assert _observe(state, off) == Action(kind="attack", attack_index=0)


def test_lookahead_gate_off_hides_copy_from_conversion():
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _printed("芯片", hp=110, damage=60), energies=1),
        "bench": (
            in_play(3, _copier(), energies=1),
            in_play(70, _donor(), energies=0),
        ),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    params = HeuristicParams(ko_prize_lookahead_gate=False, copy_conversion_gate=True)
    act = _observe(state, params)
    assert act.kind == "attack"
    assert act != Action(kind="retreat", bench_index=0)
