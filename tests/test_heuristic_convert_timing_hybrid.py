"""task 093：落后且零伤一层复制时，先 place_bench 供体基础。

Q3 已过（49/236）。禁止 prize_pressure_gate。不改斩杀短路、选择、换上、
撤退、特性与支援者序。关闸 = 今天的攻击。
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
      - {action: draw, count: 1}
""")
ITEM_DOC = parse_card_doc("""
card:
  name_group: 测试物品
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")
FX = {"复制手": COPY_DOC, "测试支援者": SUPPORTER_DOC, "测试物品": ITEM_DOC}


def _copy_doc(*, selector: str = "own_bench_attack", filters: str = '["owner_pokemon:N"]'):
    return parse_card_doc(f"""
card:
  name_group: 复制手
effects:
  - trigger: on_attack
    attack: 复制
    actions:
      - {{action: copy_attack, selector: {selector}, choose: 1, filters: {filters}}}
""")


def _observe(state, params=None, card_effects=None):
    fx = FX if card_effects is None else card_effects
    engine = engine_at(state)
    engine.card_effects = fx
    agent = HeuristicAgent(params, card_effects=fx)
    return agent.observe(engine.state.visible_state(0), engine.legal_actions(0))


def _copier(attacks: tuple[AttackDef, ...] | None = None) -> CardDef:
    if attacks is None:
        attacks = (AttackDef(name="复制", cost=("无",), damage=None),)
    return CardDef(
        card_id="stub-复制手", name="复制手", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0, attacks=attacks,
    )


def _mon(
    name: str, *, damage: int | None = 100, owner: str | None = "N",
    stage: int = 0, evolves_from: str | None = None,
    attacks: tuple[AttackDef, ...] | None = None,
    cost: tuple[str, ...] = ("无", "无"),
) -> CardDef:
    if attacks is None:
        attacks = (AttackDef(name="打击", cost=cost, damage=damage),)
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=120, stage=stage, evolves_from=evolves_from, retreat_cost=0,
        owner=owner, attacks=attacks,
    )


def _printed(name: str, *, hp: int, damage: int, cost: tuple[str, ...] = ("无",)) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="打击", cost=cost, damage=damage),),
    )


def _trainer(name: str, subtype: str) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="trainer",
        trainer_subtype=subtype,
    )


def _board(
    *, hand: tuple, bench: tuple = (), active=None, mode: str = "behind",
    opp_hp: int = 400, active_card: CardDef | None = None,
):
    state = main_state()
    own_all = state.players[0].prizes
    opp_all = state.players[1].prizes
    if mode == "behind":
        own_p, opp_p = own_all, opp_all[:2]
    elif mode == "ahead":
        own_p, opp_p = own_all[:2], opp_all
    elif mode == "tied":
        own_p, opp_p = own_all, opp_all
    else:
        raise AssertionError(mode)
    if active is None:
        active = in_play(1, active_card or _copier(), energies=1)
    p0 = state.players[0].model_copy(update={
        "active": active,
        "bench": bench,
        "hand": hand,
        "prizes": own_p,
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=opp_hp), energies=0),
        "bench": (),
        "prizes": opp_p,
    })
    state = state.model_copy(update={"players": (p0, p1)})
    own_n = len(state.players[0].prizes)
    opp_n = len(state.players[1].prizes)
    if mode == "behind":
        assert own_n > opp_n
    elif mode == "ahead":
        assert own_n < opp_n
    else:
        assert own_n == opp_n
    return state


def _zero_hand():
    return (inst(40, _mon("供体", damage=120)),)


def test_gate_defaults_on_and_is_not_pressure():
    """默认开。不新增 prize_pressure_gate。不进 tune 由 test_tune_space 钉住。"""
    assert getattr(HeuristicParams(), "convert_timing_hybrid_gate", False) is True
    assert not hasattr(HeuristicParams(), "prize_pressure_gate")


def test_behind_zero_copy_places_matching_basic():
    """落后 + 即将打出的一层复制有效伤害 0 + 手里合格基础 → place_bench。"""
    state = _board(hand=_zero_hand())
    assert _observe(state) == Action(kind="place_bench", iid=40)


def test_gate_off_keeps_the_zero_copy_attack():
    """关闸：同一局面打出今天的 0 伤复制。"""
    state = _board(hand=_zero_hand())
    params = HeuristicParams(convert_timing_hybrid_gate=False)
    act = _observe(state, params)
    assert act == Action(kind="attack", attack_index=0)


def test_tied_prizes_do_not_place():
    """打平不放。"""
    state = _board(hand=_zero_hand(), mode="tied")
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_ahead_does_not_place():
    """领先（剩余奖赏更少）不放。"""
    state = _board(hand=_zero_hand(), mode="ahead")
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_positive_copy_chip_does_not_place():
    """备战供体已让这一挥 >0：不放手里更高的基础。"""
    state = _board(
        hand=(inst(40, _mon("手里", damage=200)),),
        bench=(in_play(70, _mon("场上", damage=80), energies=0),),
    )
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_copy_damage_zero_still_places_hand_donor():
    """via=copy 且 best 伤害是 0：仍放手里伤害 >0 的基础。"""
    state = _board(
        hand=(inst(40, _mon("手里", damage=110)),),
        bench=(in_play(70, _mon("零伤", damage=0), energies=0),),
    )
    assert _observe(state) == Action(kind="place_bench", iid=40)


def test_conversion_off_still_uses_copied_damage():
    """copy_conversion 关时，一层复制伤害仍按 _one_layer_copy，不按印面 0 去放。"""
    state = _board(
        hand=(inst(40, _mon("手里", damage=200)),),
        bench=(in_play(70, _mon("场上", damage=80), energies=0),),
    )
    params = HeuristicParams(copy_conversion_gate=False)
    act = _observe(state, params)
    assert act == Action(kind="attack", attack_index=0)


def test_conversion_off_print_zero_still_places():
    """没有供体时复制返回 None，印面是 0：关 conversion 也放。"""
    state = _board(hand=_zero_hand())
    params = HeuristicParams(copy_conversion_gate=False)
    assert _observe(state, params) == Action(kind="place_bench", iid=40)


def test_lookahead_gate_off_print_zero_still_places():
    """前瞻闸关时复制返回 None，印面 0 的一层 copy 仍放合格基础。"""
    state = _board(hand=_zero_hand())
    params = HeuristicParams(ko_prize_lookahead_gate=False)
    assert _observe(state, params) == Action(kind="place_bench", iid=40)


def test_filter_miss_attacks():
    """主人过滤不过：维持攻击。"""
    state = _board(hand=(inst(40, _mon("外人", damage=200, owner=None)),))
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_strike_zero_attacks():
    """过滤过但最高复制伤害是 0：不放。"""
    state = _board(hand=(inst(40, _mon("空击", damage=0)),))
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_higher_strike_beats_smaller_iid():
    """多张合格：伤害高者优先，即使 iid 更大。"""
    state = _board(hand=(
        inst(8, _mon("低", damage=50)),
        inst(40, _mon("高", damage=180)),
    ))
    assert _observe(state) == Action(kind="place_bench", iid=40)


def test_tie_strike_picks_min_iid():
    """伤害相同：iid 小。"""
    state = _board(hand=(
        inst(30, _mon("甲", damage=100)),
        inst(12, _mon("乙", damage=100)),
    ))
    assert _observe(state) == Action(kind="place_bench", iid=12)


def test_strike_uses_max_attack_on_the_card():
    """同一张基础取招式最高伤害，不取第一招。"""
    card = _mon("多招", attacks=(
        AttackDef(name="空", cost=(), damage=0),
        AttackDef(name="重", cost=(), damage=90),
    ))
    state = _board(hand=(inst(40, card),))
    assert _observe(state) == Action(kind="place_bench", iid=40)


def test_matching_basic_beats_higher_unfiltered_damage():
    """过滤不过的更高伤害不抢过合格基础。"""
    state = _board(hand=(
        inst(5, _mon("外人", damage=300, owner=None)),
        inst(9, _mon("合格", damage=40)),
    ))
    assert _observe(state) == Action(kind="place_bench", iid=9)


def test_unknown_filter_does_not_place():
    """过滤读不懂：不放，也不抛。"""
    fx = dict(FX)
    fx["复制手"] = _copy_doc(filters='["not_a_real_filter"]')
    state = _board(hand=_zero_hand())
    act = _observe(state, card_effects=fx)
    assert act == Action(kind="attack", attack_index=0)


def test_other_copy_selector_does_not_place():
    """不是 own_bench_attack 的复制：不放。"""
    fx = dict(FX)
    fx["复制手"] = _copy_doc(selector="opponent_active_attack")
    state = _board(hand=_zero_hand())
    act = _observe(state, card_effects=fx)
    assert act == Action(kind="attack", attack_index=0)


def test_printed_zero_attack_is_not_a_copy():
    """印面 0 但不是一层 copy：不放。"""
    active = in_play(1, _printed("白板", hp=100, damage=0, cost=("无",)), energies=1)
    state = _board(
        hand=(inst(40, _mon("供体", damage=200)),),
        active=active,
    )
    act = _observe(state)
    assert act.kind == "attack"
    assert act != Action(kind="place_bench", iid=40)


def test_positive_printed_attack_beats_zero_copy():
    """_pick_attack 会选正伤害印面招时，不因旁边有 0 伤复制而放基础。"""
    active = in_play(1, _copier(attacks=(
        AttackDef(name="打击", cost=("无",), damage=30),
        AttackDef(name="复制", cost=("无",), damage=None),
    )), energies=1)
    state = _board(hand=_zero_hand(), active=active)
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_can_ko_still_attacks():
    """084：复制能斩杀时仍攻击，不改放手里的基础，也不先打支援者。"""
    state = _board(
        hand=(
            inst(16, _trainer("测试支援者", "支援者")),
            inst(40, _mon("手里", damage=100)),
        ),
        bench=(in_play(70, _mon("场上", damage=200), energies=0),),
        opp_hp=80,
    )
    assert _observe(state) == Action(kind="attack", attack_index=0)


def test_retreat_ko_still_happens_before_place():
    """撤退能斩杀时先撤，R 看不到这一步。"""
    state = _board(
        hand=(inst(40, _mon("手里", damage=120)),),
        bench=(in_play(3, _printed("打手", hp=100, damage=200), energies=1),),
        opp_hp=80,
    )
    assert _observe(state) == Action(kind="retreat", bench_index=0)


def test_item_still_before_place():
    """物品仍先于攻击档，R 不插到物品前。"""
    state = _board(hand=(
        inst(15, _trainer("测试物品", "物品")),
        inst(40, _mon("供体", damage=120)),
    ))
    assert _observe(state) == Action(kind="play_trainer", iid=15)


def test_supporter_still_before_place():
    """支援者序不变：已经要打支援者时不放基础。"""
    state = _board(hand=(
        inst(16, _trainer("测试支援者", "支援者")),
        inst(40, _mon("供体", damage=120)),
    ))
    assert _observe(state) == Action(kind="play_trainer", iid=16)


def test_full_bench_has_no_place_so_attacks():
    """备战已满，没有合法 place_bench：维持攻击。"""
    bench = tuple(
        in_play(10 + i, _printed(f"占位{i}", hp=60, damage=0), energies=0)
        for i in range(5)
    )
    state = _board(hand=_zero_hand(), bench=bench)
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)


def test_stage1_in_hand_is_not_placed():
    """非基础不在 place_bench 里：不造非法放置。"""
    card = _mon("一阶", damage=200, stage=1, evolves_from="没有这只")
    state = _board(hand=(inst(40, card),))
    act = _observe(state)
    assert act == Action(kind="attack", attack_index=0)
