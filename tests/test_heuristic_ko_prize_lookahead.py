"""task 083：共享击杀/拿奖前瞻。

F1 看见一层 copy_attack。F3 让撤退、攻击击杀与 promote 只读该出口。
不改 `_attack_table`，不改 080 的 chooser，不引入 `prize_pressure_gate`。
"""

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.agent.heuristic import (
    HeuristicAgent,
    HeuristicParams,
    pokemon_score,
)
from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

COPY_DOC = parse_card_doc("""
card:
  name_group: 复制手
effects:
  - trigger: on_attack
    attack: 暗夜
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


def _mon(name: str, *, owner: str | None, hp: int, damage: int, cost: tuple[str, ...]) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, retreat_cost=0, owner=owner,
        attacks=(AttackDef(name="打击", cost=cost, damage=damage),),
    )


def _copier() -> CardDef:
    return CardDef(
        card_id="stub-复制手", name="复制手", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="暗夜", cost=("无",), damage=None),),
    )


def _supporter() -> CardDef:
    return CardDef(
        card_id="stub-测试支援者", name="测试支援者", supertype="trainer",
        trainer_subtype="支援者",
    )


def _engine(state):
    engine = engine_at(state)
    engine.card_effects = FX
    return engine


def _observe(state, params=None, card_effects=FX):
    engine = _engine(state)
    agent = HeuristicAgent(params, card_effects=card_effects)
    return agent.observe(engine.state.visible_state(0), engine.legal_actions(0))


def _agent_view(state, params=None, card_effects=FX):
    engine = _engine(state)
    agent = HeuristicAgent(params, card_effects=card_effects)
    return agent, engine.state.visible_state(0)


def _base(*, donor, decoy=None, opp_hp: int, hand=()):
    state = main_state()
    bench = [in_play(70, donor, energies=0)]
    if decoy is not None:
        bench.append(in_play(71, decoy, energies=0))
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": tuple(bench),
        "hand": hand,
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=opp_hp, damage=10), energies=0),
    })
    return state.model_copy(update={"players": (p0, p1)})


def _ko_state():
    """供体 owner=N、印面 200、0 能量（两费未付清）。复制手已付 1 无色。对手 HP 100。"""
    donor = _mon("供体", owner="N", hp=100, damage=200, cost=("无", "无"))
    state = _base(donor=donor, opp_hp=100, hand=(inst(61, _supporter()),))
    return state


def test_copy_ko_attacks_before_supporter():
    """印面 damage=None 的复制手，供体足够击杀 → 击杀优先于支援者。"""
    act = _observe(_ko_state())
    assert act == Action(kind="attack", attack_index=0)


def test_gate_off_does_not_see_copy_ko():
    """开关关：复制击杀不可见，仍先打支援者。"""
    assert getattr(HeuristicParams(), "ko_prize_lookahead_gate", None) is True
    params = HeuristicParams(ko_prize_lookahead_gate=False)
    act = _observe(_ko_state(), params)
    assert act == Action(kind="play_trainer", iid=61)


def test_unpaid_donor_still_visible_when_copier_paid():
    """供体费用未满足、复制手自己已付清 → 仍看见击杀。供体不必付费。"""
    state = _ko_state()
    donor = state.players[0].bench[0]
    assert donor.attached_energy == ()
    assert len(donor.current.card.attacks[0].cost) == 2
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_lookahead_reports_stable_copy_ko():
    """同一 view 上 can_ko / best_damage / via 稳定；不写进攻击表。"""
    state = _ko_state()
    agent, view = _agent_view(state)
    assert hasattr(agent, "_ko_prize_lookahead")
    first = agent._ko_prize_lookahead(view)
    second = agent._ko_prize_lookahead(view)
    assert first.can_ko is True
    assert first.best_damage == 200
    assert first.via == "copy"
    assert (second.can_ko, second.best_damage, second.via) == (
        first.can_ko, first.best_damage, first.via,
    )
    table = agent._attack_table(view)
    assert table[0] == (0, True)


def test_gate_off_lookahead_stays_on_print():
    """开关关：共享接口回到印面口径（复制手印面 0，看不见供体 200）。"""
    assert getattr(HeuristicParams(), "ko_prize_lookahead_gate", None) is True
    params = HeuristicParams(ko_prize_lookahead_gate=False)
    agent, view = _agent_view(_ko_state(), params)
    assert hasattr(agent, "_ko_prize_lookahead")
    look = agent._ko_prize_lookahead(view)
    assert look.can_ko is False
    assert look.via == "print"
    assert look.best_damage == 0


def test_owner_filter_ignores_non_matching_ko():
    """N 供体只有 10 伤。非 N 的 400 伤不进复制池。

    路人费用未付清，078 不会因为它的印面击杀而撤退；若复制池漏进它，
    会走 attack。正确口径仍先打支援者。
    """
    donor = _mon("供体", owner="N", hp=100, damage=10, cost=())
    decoy = _mon("路人", owner="别人", hp=100, damage=400, cost=("无", "无"))
    state = _base(donor=donor, decoy=decoy, opp_hp=100, hand=(inst(61, _supporter()),))
    act = _observe(state)
    assert act == Action(kind="play_trainer", iid=61)


def test_no_doc_on_agent_does_not_guess():
    """引擎有文档（攻击合法），Agent 没文档 → 不猜，仍先支援者。"""
    state = _ko_state()
    act = _observe(state, card_effects=None)
    assert act == Action(kind="play_trainer", iid=61)


def test_unknown_filter_does_not_guess():
    """未知 filter 的 DslError 不猜，维持印面，仍先支援者。"""
    bad = parse_card_doc("""
card:
  name_group: 复制手
effects:
  - trigger: on_attack
    attack: 暗夜
    actions:
      - {action: copy_attack, selector: own_bench_attack, choose: 1, filters: ["not_a_real_filter"]}
""")
    fx = {"复制手": bad, "测试支援者": SUPPORTER_DOC}
    act = _observe(_ko_state(), card_effects=fx)
    assert act == Action(kind="play_trainer", iid=61)


def test_nested_copy_does_not_recurse():
    """复制手只读供体印面 10，不把供体自己的 copy_attack 再展开成 400。

    深层不属于复制手的 owner 过滤。若从复制手再套一层，击杀分支会直接 attack。
    供体自己换上后的一层复制仍然看得到这 400，所以撤退换上供体，而不是打支援者。
    """
    donor_doc = parse_card_doc("""
card:
  name_group: 供体
effects:
  - trigger: on_attack
    attack: 打击
    actions:
      - {action: copy_attack, selector: own_bench_attack, choose: 1}
""")
    donor = _mon("供体", owner="N", hp=100, damage=10, cost=())
    deep = _mon("深层", owner="别人", hp=100, damage=400, cost=("无", "无"))
    state = _base(donor=donor, decoy=deep, opp_hp=100, hand=(inst(61, _supporter()),))
    fx = {"复制手": COPY_DOC, "供体": donor_doc, "测试支援者": SUPPORTER_DOC}
    agent, view = _agent_view(state, card_effects=fx)
    look = agent._ko_prize_lookahead(view)
    assert look.can_ko is False
    assert look.best_damage == 10
    assert look.via == "copy"
    act = agent.observe(view, _engine(state).legal_actions(0))
    assert act == Action(kind="retreat", bench_index=0)


def test_copy_ko_does_not_retreat_onto_bench_that_also_kos():
    """战斗场复制能击杀，备战印面也能击杀 → 不撤，打出复制。"""
    donor = _mon("供体", owner="N", hp=100, damage=200, cost=())
    state = _base(donor=donor, opp_hp=100, hand=())
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)
    agent, view = _agent_view(state)
    retreats = [a for a in _engine(state).legal_actions(0) if a.kind == "retreat"]
    assert retreats
    assert agent._pick_retreat(view, retreats) is None


def test_neither_ko_does_not_retreat_just_because_behind():
    """两边都不能击杀：落后也不撤到更高的非击杀。不做 081。"""
    chip = CardDef(
        card_id="stub-低伤", name="低伤", supertype="pokemon",
        hp=110, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="打击", cost=("无",), damage=60),),
    )
    bigger = CardDef(
        card_id="stub-中伤", name="中伤", supertype="pokemon",
        hp=100, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="打击", cost=("无",), damage=120),),
    )
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
    act = _observe(state)
    assert act.kind == "attack"
    assert act != Action(kind="retreat", bench_index=0)


def _wall_and_striker() -> tuple[CardDef, CardDef]:
    wall = CardDef(
        card_id="stub-墙", name="墙", supertype="pokemon",
        hp=250, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="撞击", cost=("无",), damage=10),),
    )
    striker = CardDef(
        card_id="stub-打手", name="打手", supertype="pokemon",
        hp=30, stage=0, retreat_cost=2,
        attacks=(AttackDef(name="打击", cost=("无",), damage=50),),
    )
    return wall, striker


def _promote_state():
    """打手在备战 0，墙在备战 1。打手能击杀，墙分更高。我方奖赏更少（领先）。"""
    wall, striker = _wall_and_striker()
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (in_play(3, striker, energies=1), in_play(4, wall, energies=1)),
        "hand": (),
        "prizes": state.players[0].prizes[:1],
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=50), energies=0),
    })
    return state.model_copy(update={"players": (p0, p1), "phase": "promote"})


def test_promote_prefers_ko_over_higher_score_even_when_ahead():
    """Q15：换上后能击杀就优先于纯 pokemon_score，不看是否落后。"""
    wall, striker = _wall_and_striker()
    params = HeuristicParams()
    assert pokemon_score(in_play(4, wall), params) > pokemon_score(in_play(3, striker), params)
    state = _promote_state()
    assert len(state.players[0].prizes) < len(state.players[1].prizes)
    act = _observe(state)
    assert act == Action(kind="promote", bench_index=0)


def test_promote_gate_off_keeps_higher_score():
    wall, _striker = _wall_and_striker()
    state = _promote_state()
    params = HeuristicParams(ko_prize_lookahead_gate=False)
    act = _observe(state, params)
    assert pokemon_score(in_play(4, wall), params) > pokemon_score(
        state.players[0].bench[0], params,
    )
    assert act == Action(kind="promote", bench_index=1)


def test_lookahead_matches_view_as_active():
    """同一只宝可梦，直接当战斗场和经 `_view_as_active` 口径一致。"""
    state = _ko_state()
    agent, view = _agent_view(state)
    direct = agent._ko_prize_lookahead(view)
    via_mon = agent._ko_prize_lookahead(view, mon=view.own.active)
    assert (via_mon.can_ko, via_mon.best_damage, via_mon.via) == (
        direct.can_ko, direct.best_damage, direct.via,
    )
    bench = view.own.bench[0]
    swapped = agent._ko_prize_lookahead(agent._view_as_active(view, bench))
    passed = agent._ko_prize_lookahead(view, mon=bench)
    assert (passed.can_ko, passed.best_damage, passed.via) == (
        swapped.can_ko, swapped.best_damage, swapped.via,
    )


# ── 有效 HP（勇气护符 modify_hp）────────────────────────────────────────

CHARM_DOC = parse_card_doc("""
card:
  name_group: 勇气护符
effects:
  - trigger: passive_static
    condition: holder_is_basic
    actions:
      - {action: modify_hp, args: {amount: 50}}
""")
TOWER_DOC = parse_card_doc("""
card:
  name_group: 阻碍之塔
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_tool}
""")
CHARM_FX = {**FX, "勇气护符": CHARM_DOC}


def _charm_card() -> CardDef:
    return CardDef(
        card_id="stub-勇气护符", name="勇气护符", supertype="trainer",
        trainer_subtype="宝可梦道具",
    )


def _dark_copier() -> CardDef:
    return CardDef(
        card_id="stub-复制手", name="复制手", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0, energy_type="恶",
        attacks=(AttackDef(name="暗夜", cost=("无",), damage=None),),
    )


def _dark_striker() -> CardDef:
    return CardDef(
        card_id="stub-恶攻", name="恶攻", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0, energy_type="恶",
        attacks=(AttackDef(name="打击", cost=("无",), damage=50),),
    )


def _setup_mon() -> CardDef:
    return CardDef(
        card_id="stub-铺场", name="铺场", supertype="pokemon",
        hp=220, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="打击", cost=("无",), damage=30),),
    )


def _willing(*, tool: bool, stage: int = 0):
    """卡面 HP 110、已伤 20。印面剩余 90；基础宝可梦挂护符后有效剩余 140。"""
    card = CardDef(
        card_id="stub-靶", name="靶", supertype="pokemon",
        hp=110, stage=stage, retreat_cost=1, weakness="恶",
        attacks=(AttackDef(name="撞击", cost=("无",), damage=10),),
    )
    mon = in_play(2, card, energies=0)
    updates: dict = {"damage": 20}
    if tool:
        updates["attached_tool"] = inst(80, _charm_card())
    return mon.model_copy(update=updates)


def _charm_print_state(*, tool: bool, stage: int = 0, stadium=None):
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _dark_striker(), energies=1),
        "bench": (),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={"active": _willing(tool=tool, stage=stage)})
    return state.model_copy(update={
        "players": (p0, p1),
        "stadium": stadium,
    })


def _charm_copy_state(*, tool: bool):
    donor = _mon("供体", owner="N", hp=70, damage=50, cost=())
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _dark_copier(), energies=1),
        "bench": (in_play(70, donor, energies=0),),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={"active": _willing(tool=tool)})
    return state.model_copy(update={"players": (p0, p1)})


def _charm_promote_state(*, tool: bool):
    donor = _mon("供体", owner="N", hp=70, damage=50, cost=())
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (
            in_play(3, _dark_copier(), energies=1),
            in_play(70, donor, energies=0),
            in_play(4, _setup_mon(), energies=1),
        ),
        "hand": (),
    })
    p1 = state.players[1].model_copy(update={"active": _willing(tool=tool)})
    return state.model_copy(update={"players": (p0, p1), "phase": "promote"})


def test_charm_blocks_print_ko_between_printed_and_effective_hp():
    """印面招式 100 介于印面剩余 90 与有效剩余 140 之间 → 不能击杀。"""
    agent, view = _agent_view(
        _charm_print_state(tool=True), card_effects={"勇气护符": CHARM_DOC},
    )
    look = agent._ko_prize_lookahead(view)
    assert look.best_damage == 100
    assert look.via == "print"
    assert look.can_ko is False


def test_no_tool_print_ko_unchanged():
    """无道具：同一 100 伤仍按印面剩余 90 击杀。"""
    agent, view = _agent_view(
        _charm_print_state(tool=False), card_effects={"勇气护符": CHARM_DOC},
    )
    look = agent._ko_prize_lookahead(view)
    assert look.best_damage == 100
    assert look.can_ko is True


def test_charm_on_evolved_does_not_raise_hp():
    """holder_is_basic 不成立：护符不加 HP，100 ≥ 印面剩余 90，仍能击杀。"""
    agent, view = _agent_view(
        _charm_print_state(tool=True, stage=1), card_effects={"勇气护符": CHARM_DOC},
    )
    look = agent._ko_prize_lookahead(view)
    assert look.best_damage == 100
    assert look.can_ko is True


def test_suppress_tool_ignores_charm_hp():
    """阻碍之塔消除道具后，护符不加 HP，击杀回到印面剩余。"""
    stadium = inst(90, CardDef(
        card_id="stub-阻碍之塔", name="阻碍之塔", supertype="trainer",
        trainer_subtype="竞技场",
    ))
    agent, view = _agent_view(
        _charm_print_state(tool=True, stadium=stadium),
        card_effects={"勇气护符": CHARM_DOC, "阻碍之塔": TOWER_DOC},
    )
    look = agent._ko_prize_lookahead(view)
    assert look.best_damage == 100
    assert look.can_ko is True


def test_charm_blocks_copy_ko_between_printed_and_effective_hp():
    """复制 50 × 恶弱点 = 100，护符后有效剩余 140 → can_ko 为假，伤害仍是 100。"""
    agent, view = _agent_view(_charm_copy_state(tool=True), card_effects=CHARM_FX)
    look = agent._ko_prize_lookahead(view)
    assert look.via == "copy"
    assert look.best_damage == 100
    assert look.can_ko is False


def test_no_tool_copy_ko_unchanged():
    """无道具：复制 100 ≥ 印面剩余 90，仍然击杀。"""
    agent, view = _agent_view(_charm_copy_state(tool=False), card_effects=CHARM_FX)
    look = agent._ko_prize_lookahead(view)
    assert look.via == "copy"
    assert look.best_damage == 100
    assert look.can_ko is True


def test_promote_does_not_prefer_false_copy_ko_under_charm():
    """护符把复制击杀打成假阳性时，promote 回到 pokemon_score，不抬复制手。"""
    state = _charm_promote_state(tool=True)
    params = HeuristicParams()
    copier = state.players[0].bench[0]
    setup = state.players[0].bench[2]
    assert pokemon_score(setup, params) > pokemon_score(copier, params)
    act = _observe(state, card_effects=CHARM_FX)
    assert act == Action(kind="promote", bench_index=2)


def test_promote_still_prefers_real_copy_ko_without_tool():
    """无道具时复制确实击杀，promote 仍优先复制手，不看分数。"""
    state = _charm_promote_state(tool=False)
    act = _observe(state, card_effects=CHARM_FX)
    assert act == Action(kind="promote", bench_index=0)
