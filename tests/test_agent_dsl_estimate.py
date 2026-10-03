"""task 032 WP2（A2 变量伤害入斩杀表 + A3 囤能例外 + A4 牌库资源管理）。

D-032-2：HeuristicAgent(params, card_effects=None)，None 全回退现状。
D-032-3：on_attack 效果的变量伤害公式（count 计数词）映射可见状态量估算，
入 _attack_damage_table；未知结构回退静态基值。
D-032-4：伤害关联 any_count discard——能斩杀选达到斩杀的最小张数，否则全选倾泻。
D-032-5：手牌弹药型主动在场 → 能量留手牌不附着。
D-032-6：牌库余量 ≤ 阈值 → 抑制含 draw 的训练家 / 降权含 draw 的招式。

fixture DSL 文档优先用真实卡（赛富豪ex 淘金潮 50× / 猛雷鼓ex 极雷轰 70× /
赫普的古月鸟 opponent_prizes_in:[4,3]），stub 卡定义驱动，不碰卡名分支。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.agent.dsl_estimate import (
    DamageEstimate,
    attack_has_draw,
    card_has_draw,
    estimate_attack_damage,
    has_hand_ammo_pattern,
)
from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams
from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.state import AttackDef, CardDef, PendingChoice

CARDS_DIR = Path(__file__).parent.parent / "cards"

GHOLDENGO_DOC = load_card_doc(CARDS_DIR / "赛富豪ex.yml")
RAGING_BOLT_DOC = load_card_doc(CARDS_DIR / "猛雷鼓ex.yml")
CRAMORANT_DOC = load_card_doc(CARDS_DIR / "赫普的古月鸟.yml")

GHOLDENGO_FX = {"赛富豪ex": GHOLDENGO_DOC}
RAGING_BOLT_FX = {"猛雷鼓ex": RAGING_BOLT_DOC}

SUPPORTER_DOC = parse_card_doc("""
card:
  name_group: 测试支援者
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 2}
""")

DRAW_ITEM_DOC = parse_card_doc("""
card:
  name_group: 测试物品
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")

NON_DRAW_ITEM_DOC = parse_card_doc("""
card:
  name_group: 测试物品2
effects:
  - trigger: on_play
    actions:
      - {action: discard, selector: own_hand, count: all}
""")

DRAW_ATTACK_DOC = parse_card_doc("""
card:
  name_group: 过牌手
effects:
  - trigger: on_attack
    attack: 过牌击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 100}}
      - {action: draw, count: 2}
""")

FLIP_DOC = parse_card_doc("""
card:
  name_group: 掷币手
effects:
  - trigger: on_attack
    attack: 掷币击
    actions:
      - {action: coin_flip, count: 2}
      - {action: damage, selector: opponent_active, count: flip_heads_count, args: {op: "×", per: 30}}
""")

UNKNOWN_COND_DOC = parse_card_doc("""
card:
  name_group: 首回手
effects:
  - trigger: on_attack
    attack: 首回击
    condition: first_own_turn
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 120}}
""")


def trainer(name: str, subtype: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype=subtype)


def gholdengo() -> CardDef:
    return CardDef(
        card_id="stub-赛富豪ex", name="赛富豪ex", supertype="pokemon", hp=260, stage=1,
        energy_type="钢", rule_box="ex", has_ability=True,
        attacks=(AttackDef(name="淘金潮", cost=("无",), damage=50),), retreat_cost=1,
    )


def raging_bolt() -> CardDef:
    return CardDef(
        card_id="stub-猛雷鼓ex", name="猛雷鼓ex", supertype="pokemon", hp=240, stage=0,
        energy_type="雷", rule_box="ex",
        attacks=(
            AttackDef(name="飞溅咆哮", cost=("无",), damage=None),
            AttackDef(name="极雷轰", cost=("无", "无"), damage=70),
        ),
        retreat_cost=2,
    )


def cramorant() -> CardDef:
    return CardDef(
        card_id="stub-赫普的古月鸟", name="赫普的古月鸟", supertype="pokemon", hp=110, stage=0,
        attacks=(AttackDef(name="随性喷吐", cost=("无",), damage=120),),
    )


def draw_attacker() -> CardDef:
    return CardDef(
        card_id="stub-过牌手", name="过牌手", supertype="pokemon", hp=120, stage=0,
        attacks=(
            AttackDef(name="过牌击", cost=("无",), damage=100),
            AttackDef(name="普通击", cost=("无",), damage=30),
        ),
    )


def flip_attacker() -> CardDef:
    return CardDef(
        card_id="stub-掷币手", name="掷币手", supertype="pokemon", hp=100, stage=0,
        attacks=(AttackDef(name="掷币击", cost=("无",), damage=30),),
    )


def first_turn_attacker() -> CardDef:
    return CardDef(
        card_id="stub-首回手", name="首回手", supertype="pokemon", hp=100, stage=0,
        attacks=(AttackDef(name="首回击", cost=("无",), damage=120),),
    )


def state_with(
    p0_active: CardDef, *, energies: int = 1, p0_hand: tuple = (), opp_hp: int = 70,
    opp_damage: int = 0, p0_deck: int = 10, p1_prizes: int = 6,
):
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


def decide(engine: GameEngine, agent: HeuristicAgent) -> Action:
    return agent.observe(engine.state.visible_state(0), engine.legal_actions(0))


# ── 6. card_effects=None / 无文档回退现状 ─────────────────────────────────

def test_none_card_effects_matches_default_agent() -> None:
    engine = engine_at(main_state())
    view, acts = engine.state.visible_state(0), engine.legal_actions(0)
    assert HeuristicAgent(card_effects=None).observe(view, acts) == HeuristicAgent().observe(view, acts)


def test_none_card_effects_choose_fallback_matches() -> None:
    engine = engine_at(_pending_discard_state(opp_hp=150))
    view, acts = engine.state.visible_state(0), engine.legal_actions(0)
    assert HeuristicAgent(card_effects=None).observe(view, acts) == HeuristicAgent().observe(view, acts)


def test_doc_missing_falls_back_to_static_damage_table() -> None:
    """card_effects 给了但栈顶卡无文档 → 伤害表 = 静态基值（现状路径）。"""
    view = engine_at(main_state()).state.visible_state(0)
    agent = HeuristicAgent(card_effects={"不相干": SUPPORTER_DOC})
    assert agent._attack_damage_table(view) == HeuristicAgent()._attack_damage_table(view)


# ── 7. 变量伤害估算（真实卡 DSL 文档驱动）─────────────────────────────────

def test_gold_rush_estimate_50x_hand_basic_energy() -> None:
    """淘金潮 50×：手牌 4 张基本能量 → 估算 200（小火龙不计）。"""
    hand = tuple(inst(50 + i, energy()) for i in range(4)) + (inst(60, basic("小火龙")),)
    state = state_with(gholdengo(), p0_hand=hand)
    view = state.visible_state(0)
    est = estimate_attack_damage(view, "淘金潮", 50, gholdengo(), GHOLDENGO_FX)
    assert est == DamageEstimate(amount=200, lethal_ok=True)
    agent = HeuristicAgent(card_effects=GHOLDENGO_FX)
    assert agent._attack_damage_table(view) == [200]


def test_thunder_estimate_70x_own_attached_energy() -> None:
    """极雷轰 70×：自身附着 3 能量 → 估算 210。"""
    state = state_with(raging_bolt(), energies=3)
    view = state.visible_state(0)
    est = estimate_attack_damage(view, "极雷轰", 70, raging_bolt(), RAGING_BOLT_FX)
    assert est == DamageEstimate(amount=210, lethal_ok=True)
    agent = HeuristicAgent(card_effects=RAGING_BOLT_FX)
    assert agent._attack_damage_table(view) == [0, 210]


def test_no_damage_node_returns_none() -> None:
    """飞溅咆哮（弃手牌+抽6，无 damage 节点）→ None 回退基值。"""
    view = state_with(raging_bolt(), energies=2).visible_state(0)
    assert estimate_attack_damage(view, "飞溅咆哮", None, raging_bolt(), RAGING_BOLT_FX) is None


def test_unknown_counter_returns_none() -> None:
    """flip_heads_count（掷币结果，可见状态不可得）→ None 回退基值。"""
    view = state_with(flip_attacker()).visible_state(0)
    assert estimate_attack_damage(view, "掷币击", 30, flip_attacker(), {"掷币手": FLIP_DOC}) is None
    agent = HeuristicAgent(card_effects={"掷币手": FLIP_DOC})
    assert agent._attack_damage_table(view) == [30]


# ── 8. 斩杀检测使用估算值 ─────────────────────────────────────────────────

def test_lethal_uses_estimate_attack_beats_supporter() -> None:
    """手牌 4 能量 + 淘金潮（对手战斗场剩 180）：50×4=200 斩杀 → 攻击优先于支援者。"""
    hand = tuple(inst(50 + i, energy()) for i in range(4)) + (
        inst(61, trainer("测试支援者", "支援者")),)
    state = state_with(gholdengo(), p0_hand=hand, opp_hp=180)
    fx = {**GHOLDENGO_FX, "测试支援者": SUPPORTER_DOC}
    engine = engine_at(state)
    engine.card_effects = fx
    agent = HeuristicAgent(card_effects=fx)
    first = decide(engine, agent)  # 嘉奖硬币（ability_manual）排序最前，先发动
    assert first == Action(kind="use_ability", iid=1)
    engine.apply(0, first)
    assert decide(engine, agent) == Action(kind="attack", attack_index=0)
    # 对照：无 card_effects → 静态 50 < 180 不斩杀 → 打支援者（现状）
    assert decide(engine, HeuristicAgent()) == Action(kind="play_trainer", iid=61)


# ── 9. D-032-4 斩杀最小弃置 / 不可斩杀倾泻 ────────────────────────────────

def _pending_discard_state(opp_hp: int):
    """淘金潮 any_count discard 挂起：池 = 手牌 4 张基本能量（iid 50-53）。"""
    hand = tuple(inst(50 + i, energy()) for i in range(4))
    state = state_with(gholdengo(), p0_hand=hand, opp_hp=opp_hp)
    pc = PendingChoice(
        player=0, source=inst(1, gholdengo()), effect_index=1, cursor=0,
        pool="own_hand", filters=("basic_energy",), min_choose=0, max_choose=4,
        pool_iids=(50, 51, 52, 53), step_phase="actions",
    )
    return state.model_copy(update={"phase": "choice", "pending_choice": pc})


def test_lethal_discard_picks_minimal_count() -> None:
    """剩 150：50×3=150 达标 → 选最小 3 张（tie-break choices 升序），不倾泻第 4 张。"""
    engine = engine_at(_pending_discard_state(opp_hp=150))
    assert decide(engine, HeuristicAgent(card_effects=GHOLDENGO_FX)) == Action(
        kind="choose", choices=(50, 51, 52))


def test_nonlethal_discard_dumps_all() -> None:
    """剩 400：全弃也斩不掉 → 倾泻全选 4 张。"""
    engine = engine_at(_pending_discard_state(opp_hp=400))
    assert decide(engine, HeuristicAgent(card_effects=GHOLDENGO_FX)) == Action(
        kind="choose", choices=(50, 51, 52, 53))


def test_discard_choice_without_effects_keeps_highest_score() -> None:
    """无 card_effects → 回退 actions 段最高分（能量各 1 分 → 全选）。"""
    engine = engine_at(_pending_discard_state(opp_hp=150))
    assert decide(engine, HeuristicAgent()) == Action(kind="choose", choices=(50, 51, 52, 53))


# ── 10. A3 囤能例外 ──────────────────────────────────────────────────────

def test_hand_ammo_pattern_detection() -> None:
    assert has_hand_ammo_pattern(gholdengo(), GHOLDENGO_FX)
    # 极雷轰弃的是附着能量（own_attached_energy），不是手牌弹药
    assert not has_hand_ammo_pattern(raging_bolt(), RAGING_BOLT_FX)
    assert not has_hand_ammo_pattern(gholdengo(), None)
    assert not has_hand_ammo_pattern(basic("白板"), GHOLDENGO_FX)


def test_hand_ammo_active_skips_energy_attach() -> None:
    """手牌弹药型主动在场 → _pick_energy_attach 返回 None（能量留手牌）。"""
    state = state_with(gholdengo(), energies=0, p0_hand=(inst(51, energy()),))
    engine = engine_at(state)
    view = engine.state.visible_state(0)
    acts = [a for a in engine.legal_actions(0) if a.kind == "attach_energy"]
    assert acts
    agent = HeuristicAgent(card_effects=GHOLDENGO_FX)
    assert agent._pick_energy_attach(view, acts) is None
    assert decide(engine, agent) == Action(kind="end_turn")


def test_no_doc_keeps_energy_attach_behavior() -> None:
    """无 DSL 文档 → 现状附着（补给未就绪战斗场）。"""
    state = state_with(gholdengo(), energies=0, p0_hand=(inst(51, energy()),))
    engine = engine_at(state)
    view = engine.state.visible_state(0)
    acts = [a for a in engine.legal_actions(0) if a.kind == "attach_energy"]
    picked = HeuristicAgent()._pick_energy_attach(view, acts)
    assert picked == Action(kind="attach_energy", iid=51, target_iid=1)


# ── 11. A4 牌库资源管理 ──────────────────────────────────────────────────

TRAINER_FX = {"测试物品": DRAW_ITEM_DOC, "测试物品2": NON_DRAW_ITEM_DOC}


def _deck_state(p0_deck: int, p0_hand: tuple, active: CardDef | None = None, opp_hp: int = 70):
    state = state_with(active or basic("打手"), p0_hand=p0_hand, p0_deck=p0_deck, opp_hp=opp_hp)
    engine = engine_at(state)
    engine.card_effects = {**TRAINER_FX, "过牌手": DRAW_ATTACK_DOC}
    return engine


def test_deck_low_suppresses_draw_trainer() -> None:
    """牌库 6 ≤ 阈值 6：含 draw 物品（iid 60）被抑制，改打不含 draw 的（iid 61）。"""
    hand = (inst(60, trainer("测试物品", "物品")), inst(61, trainer("测试物品2", "物品")))
    engine = _deck_state(6, hand)
    assert decide(engine, HeuristicAgent(card_effects=engine.card_effects)) == Action(
        kind="play_trainer", iid=61)


def test_deck_high_plays_draw_trainer() -> None:
    """牌库 10 > 阈值：正常打含 draw 物品（iid 小者）。"""
    hand = (inst(60, trainer("测试物品", "物品")), inst(61, trainer("测试物品2", "物品")))
    engine = _deck_state(10, hand)
    assert decide(engine, HeuristicAgent(card_effects=engine.card_effects)) == Action(
        kind="play_trainer", iid=60)


def test_deck_low_all_draw_trainers_suppressed_attacks() -> None:
    """牌库低 + 手牌只有含 draw 训练家 → 跳过训练家继续排序到攻击。"""
    engine = _deck_state(6, (inst(60, trainer("测试物品", "物品")),))
    act = decide(engine, HeuristicAgent(card_effects=engine.card_effects))
    assert act == Action(kind="attack", attack_index=0)


def test_deck_protect_disabled_keeps_draw_trainer() -> None:
    """deck_protect=False（旧 YAML 无参兼容的反面）：牌库低也照打 draw 物品。"""
    hand = (inst(60, trainer("测试物品", "物品")), inst(61, trainer("测试物品2", "物品")))
    engine = _deck_state(6, hand)
    agent = HeuristicAgent(HeuristicParams(deck_protect=False), card_effects=engine.card_effects)
    assert decide(engine, agent) == Action(kind="play_trainer", iid=60)


def test_deck_low_excludes_draw_attack() -> None:
    """攻击侧：牌库低时含 draw 的招式（过牌击 100）被排除，选普通击（30）。"""
    engine = _deck_state(6, (), active=draw_attacker(), opp_hp=300)
    assert decide(engine, HeuristicAgent(card_effects=engine.card_effects)) == Action(
        kind="attack", attack_index=1)


def test_deck_high_keeps_draw_attack() -> None:
    """牌库高时按伤害取过牌击（100 > 30）。"""
    engine = _deck_state(10, (), active=draw_attacker(), opp_hp=300)
    assert decide(engine, HeuristicAgent(card_effects=engine.card_effects)) == Action(
        kind="attack", attack_index=0)


def test_draw_detection_helpers() -> None:
    assert card_has_draw(trainer("测试物品", "物品"), TRAINER_FX)
    assert not card_has_draw(trainer("测试物品2", "物品"), TRAINER_FX)
    assert not card_has_draw(trainer("测试物品", "物品"), None)
    assert attack_has_draw(draw_attacker(), "过牌击", {"过牌手": DRAW_ATTACK_DOC})
    assert not attack_has_draw(draw_attacker(), "普通击", {"过牌手": DRAW_ATTACK_DOC})
    assert not attack_has_draw(draw_attacker(), "过牌击", None)


# ── 12. 效果 condition 奖赏词求值（古月鸟型）──────────────────────────────

def _cramorant_engine(p1_prizes: int) -> GameEngine:
    hand = (inst(61, trainer("测试支援者", "支援者")),)
    state = state_with(cramorant(), p0_hand=hand, opp_hp=100, p1_prizes=p1_prizes)
    engine = engine_at(state)
    engine.card_effects = {"赫普的古月鸟": CRAMORANT_DOC, "测试支援者": SUPPORTER_DOC}
    return engine


def test_cramorant_condition_unsatisfied_not_lethal() -> None:
    """对手剩 6 奖赏 ∉ [4,3]：120 不参与斩杀 → 打支援者；估算标记不可斩杀。"""
    engine = _cramorant_engine(6)
    fx = engine.card_effects
    view = engine.state.visible_state(0)
    assert estimate_attack_damage(view, "随性喷吐", 120, cramorant(), fx) == DamageEstimate(
        amount=0, lethal_ok=False)
    assert decide(engine, HeuristicAgent(card_effects=fx)) == Action(kind="play_trainer", iid=61)


def test_cramorant_condition_satisfied_lethal() -> None:
    """对手剩 4 奖赏 ∈ [4,3]：120 ≥ 100 斩杀 → 攻击优先于支援者。"""
    engine = _cramorant_engine(4)
    fx = engine.card_effects
    view = engine.state.visible_state(0)
    assert estimate_attack_damage(view, "随性喷吐", 120, cramorant(), fx) == DamageEstimate(
        amount=120, lethal_ok=True)
    assert decide(engine, HeuristicAgent(card_effects=fx)) == Action(kind="attack", attack_index=0)


def test_unknown_condition_in_table_but_not_lethal() -> None:
    """未知 condition（first_own_turn）：基值仍入伤害表，但不参与斩杀判定。"""
    hand = (inst(61, trainer("测试支援者", "支援者")),)
    state = state_with(first_turn_attacker(), p0_hand=hand, opp_hp=100)
    engine = engine_at(state)
    engine.card_effects = {"首回手": UNKNOWN_COND_DOC, "测试支援者": SUPPORTER_DOC}
    fx = engine.card_effects
    view = engine.state.visible_state(0)
    assert estimate_attack_damage(view, "首回击", 120, first_turn_attacker(), fx) == DamageEstimate(
        amount=120, lethal_ok=False)
    agent = HeuristicAgent(card_effects=fx)
    assert agent._attack_damage_table(view) == [120]
    assert decide(engine, agent) == Action(kind="play_trainer", iid=61)
