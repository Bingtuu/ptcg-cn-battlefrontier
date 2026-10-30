"""task 087：非斩杀 setup 优先于芯片；斩杀不 defer。"""

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams
from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef
from battlefrontier.tune.space import search_space

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
ENABLE_DOC = parse_card_doc("""
card:
  name_group: 启用剂
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_discard, filters: [basic_energy], choose: 1, destination: attach, args: {target_pool: own_pokemon_in_play}}
""")
ZERO_ITEM_DOC = parse_card_doc("""
card:
  name_group: 零价物品
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")
HEAL_DOC = parse_card_doc("""
card:
  name_group: 治疗剂
effects:
  - trigger: on_play
    actions:
      - {action: heal, selector: own_active, args: {amount: 50}}
""")
FX = {
    "复制手": COPY_DOC,
    "双招复制": COPY_DOC,
    "测试支援者": SUPPORTER_DOC,
    "启用剂": ENABLE_DOC,
    "零价物品": ZERO_ITEM_DOC,
    "治疗剂": HEAL_DOC,
}


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


def _dual_body() -> CardDef:
    """复制已付清；终击再贴 1 能即可斩杀。"""
    return CardDef(
        card_id="stub-双招复制", name="双招复制", supertype="pokemon",
        hp=160, stage=0, retreat_cost=0,
        attacks=(
            AttackDef(name="复制", cost=("无",), damage=None),
            AttackDef(name="终击", cost=("无", "无"), damage=400),
        ),
    )


def _supporter() -> CardDef:
    return CardDef(
        card_id="stub-测试支援者", name="测试支援者", supertype="trainer",
        trainer_subtype="支援者",
    )


def _enable_item() -> CardDef:
    return CardDef(
        card_id="stub-启用剂", name="启用剂", supertype="trainer",
        trainer_subtype="物品",
    )


def _zero_item() -> CardDef:
    return CardDef(
        card_id="stub-零价物品", name="零价物品", supertype="trainer",
        trainer_subtype="物品",
    )


def _heal_item() -> CardDef:
    return CardDef(
        card_id="stub-治疗剂", name="治疗剂", supertype="trainer",
        trainer_subtype="物品",
    )


def _nonlethal_copy_state(*, hand, discard=()):
    """复制付清可见、对手血厚 → can_ko 假。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _dual_body(), energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": hand,
        "discard": discard,
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    return state.model_copy(update={"players": (p0, p1)})


def test_copy_ko_still_attacks_before_supporter():
    """Q2=C：can_ko 时永不 defer，即使门默认开。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, _copier(), energies=1),
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (inst(61, _supporter()),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=100, damage=10), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state, HeuristicParams()) == Action(kind="attack", attack_index=0)


def test_high_setup_enable_energy_plays_trainer_before_chip():
    """非斩杀 + E 启用下击杀 > 芯片 → 先物品。"""
    state = _nonlethal_copy_state(
        hand=(inst(80, _enable_item()),),
        discard=(inst(90, energy()),),
    )
    assert _observe(state) == Action(kind="play_trainer", iid=80)


def test_gate_off_zero_item_keeps_today_order():
    """门关：零价值物品仍按今天先打出。"""
    state = _nonlethal_copy_state(hand=(inst(80, _zero_item()),))
    off = HeuristicParams(setup_before_chip_gate=False)
    assert _observe(state, off) == Action(kind="play_trainer", iid=80)


def test_zero_value_item_skipped_then_chip():
    """Q3=B：非斩杀路径可见时跳过零价值物品，落到芯片攻击。"""
    state = _nonlethal_copy_state(hand=(inst(80, _zero_item()),))
    assert _observe(state) == Action(kind="attack", attack_index=0)


def test_path_not_visible_gate_has_no_effect():
    """无复制路径：门开也不改今天先物品。"""
    printed = CardDef(
        card_id="stub-芯片", name="芯片", supertype="pokemon",
        hp=110, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="打击", cost=("无",), damage=60),),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, printed, energies=1),
        "bench": (),
        "hand": (inst(80, _zero_item()),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("靶", hp=400), energies=0),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="play_trainer", iid=80)


def test_heal_setup_beats_chip_when_it_saves_from_opp_ko():
    """H：治疗使己方从被斩杀变为扛住 → 先物品。"""
    state = main_state()
    own = in_play(1, _copier(), energies=1).model_copy(update={"damage": 120})
    threat = CardDef(
        card_id="stub-厚血对方", name="厚血对方", supertype="pokemon",
        hp=400, stage=0, retreat_cost=0,
        attacks=(AttackDef(name="打击", cost=("无",), damage=50),),
    )
    p0 = state.players[0].model_copy(update={
        "active": own,
        "bench": (in_play(70, _donor(), energies=0),),
        "hand": (inst(80, _heal_item()),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, threat, energies=1),
    })
    state = state.model_copy(update={"players": (p0, p1)})
    assert _observe(state) == Action(kind="play_trainer", iid=80)


def test_default_gate_true_not_in_tune_no_prize_pressure():
    assert HeuristicParams().setup_before_chip_gate is True
    assert len(search_space()) == 10
    names = {d.name for d in search_space()}
    assert "setup_before_chip_gate" not in names
    assert not hasattr(HeuristicParams(), "prize_pressure_gate")
