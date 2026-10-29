"""task 083 F1：共享击杀/拿奖前瞻看见一层 copy_attack。

不改 `_attack_table`，不改 080 的 chooser，不引入 `prize_pressure_gate`。
"""

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
