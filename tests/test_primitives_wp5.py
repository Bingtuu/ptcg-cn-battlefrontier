"""task 026 WP5 机制测试：任意数量弃置×N 伤害族 / attached_energy_on_target /
modify_attack_cost 声明式 / 白蕾雅奖赏加成 / coin_flip until_tails /
bounce attachments=hand / transform 替换原语。

设计决议（tasks/task 026.md WP5 节，2026-09-14 定稿）：
- D-WP5-1 任意数量弃置 = up-to all（min_choose=0）；选 0 张 → 伤害 0，招式仍可宣言。
  前序弃置张数经 ExecutionContext.discarded_this_effect 传递（挂起/恢复经
  PendingChoice.discarded_count 穿透，同 flip/cost_discarded 口径）。
- D-WP5-2 白蕾雅奖赏加成：仅「招式伤害致对手战斗场昏厥」路径触发；回合级标记
  （PlayerState.extra_prize_tera_ko，回合结束 _on_turn_end 清除）；多拿 1 张在
  _knockout_one（take_prize 触点）结算，奖赏不足按剩余拿取（拿完即胜）。
- D-WP5-3 变身启动：替换不触发昏厥/奖赏/换上；伤害/状态不继承；entered_play_this_turn
  登记；检索 up-to（可以不找 → no-op，重洗仍执行）。
- D-WP5-4 月月熊 费用减免：modify_attack_cost 声明式（passive_static，引擎
  _effective_attack_cost 求值点读声明）；减免 = opponent_taken_prizes 个【无】，
  下限 0、只减无色部分；离场即失效（求值点实时读声明）。
- until_tails：单次行动内连续掷到反面为止，逐次走引擎单一随机源；
  正面次数经 flip_heads_count 计数词供 damage 引用。
"""

import pytest
from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import ExecutionContext, parse_card_doc, run_effect
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import AttackDef, CardDef, SpecialCondition


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def engine_at_seed(state, seed: int) -> GameEngine:
    e = GameEngine(RandomSource(seed))
    e.state = state
    return e


def attack_engine(doc, attacker: CardDef, *, p0_hand=(), p0_bench=(), p0_discard=(),
                  p0_deck=None, p1_active=None, p1_bench=(), p1_prizes: int = 6,
                  p0_energies=(), seed: int = 0, turn: int = 2):
    """main 阶段：p0 战斗场攻击者（iid 1）+ 可调手牌/备战/牌库，p1 战斗场可调。"""
    state = main_state()
    active = in_play(1, attacker)
    if p0_energies:
        active = active.model_copy(update={"attached_energy": p0_energies})
    p0 = state.players[0].model_copy(update={
        "active": active, "bench": p0_bench, "discard": p0_discard,
        "hand": p0_hand,
    })
    if p0_deck is not None:
        p0 = p0.model_copy(update={"deck": p0_deck})
    p1 = state.players[1].model_copy(update={
        "bench": p1_bench,
        # 默认对手战斗场换高 HP（防 KO 干扰伤害断言）；p1_active 传入时以传入为准
        "active": in_play(2, basic("硬兽", hp=500), 1),
    })
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    p1 = p1.model_copy(update={
        "prizes": p1.prizes[:p1_prizes],
    })
    e = engine_at_seed(state.model_copy(update={
        "players": (p0, p1), "turn": turn,
    }), seed)
    e.card_effects = {attacker.name: doc}
    return e


def play_engine(doc, name: str = "测试卡", *, p0_bench: tuple = (), discard: tuple = (),
                deck=None, extra_hand: tuple = (), kind="item", p1_prizes: int = 6,
                p1_bench: tuple = (), p1_active=None, p0_active=None):
    """main 阶段：p0 手牌含测试训练家卡（iid 60）。"""
    card_fn = item_card if kind == "item" else supporter_card
    state = main_state(p0_extra_hand=(inst(60, card_fn(name)),) + extra_hand)
    p0 = state.players[0].model_copy(update={"bench": p0_bench, "discard": discard})
    if deck is not None:
        p0 = p0.model_copy(update={"deck": deck})
    if p0_active is not None:
        p0 = p0.model_copy(update={"active": p0_active})
    p1 = state.players[1].model_copy(update={
        "prizes": state.players[1].prizes[:p1_prizes], "bench": p1_bench,
    })
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {name: doc}
    return e


def ability_engine(doc, name: str, mon: CardDef | None = None, *, p0_bench: tuple = (),
                   deck=None, turn: int = 1, energies: int = 0, damage: int = 0,
                   conditions=frozenset()):
    """main 阶段：p0 战斗场特性持有兽（iid 1）。"""
    state = main_state()
    active = in_play(1, mon if mon is not None else basic(name), energies).model_copy(
        update={"damage": damage, "conditions": conditions},
    )
    p0 = state.players[0].model_copy(update={"active": active, "bench": p0_bench})
    if deck is not None:
        p0 = p0.model_copy(update={"deck": deck})
    e = engine_at(state.model_copy(update={
        "players": (p0, state.players[1]), "turn": turn,
    }))
    e.card_effects = {active.current.card.name: doc}
    return e


def run_doc(e, doc, source, player: int = 0):
    """直接跑效果（绕过可行性门）：DslError 等原语层语义用。"""
    ctx = ExecutionContext(engine=e, player=player, source=source,
                           effect_id="test", trigger=doc.effects[0].trigger)
    return run_effect(ctx, doc.effects[0])


# ── discard any_count + discarded_this_effect（清单 1-3）──────────────────────

GOLD_RUSH_DOC = parse_card_doc("""
card:
  name_group: 测试淘金
effects:
  - trigger: on_attack
    attack: 淘金潮
    actions:
      - {action: discard, selector: own_hand, filters: [basic_energy], args: {any_count: true}}
      - {action: damage, selector: opponent_active, count: discarded_this_effect, args: {op: "×", per: 50}}
""")

THUNDER_DOC = parse_card_doc("""
card:
  name_group: 测试极雷
effects:
  - trigger: on_attack
    attack: 极雷轰
    actions:
      - {action: discard, selector: own_attached_energy, filters: [basic_energy], args: {any_count: true}}
      - {action: damage, selector: opponent_active, count: discarded_this_effect, args: {op: "×", per: 70}}
""")


def gold_rusher() -> CardDef:
    return CardDef(
        card_id="stub-淘金兽", name="淘金兽", supertype="pokemon",
        hp=200, stage=0, energy_type="钢",
        attacks=(AttackDef(name="淘金潮", cost=("无",), damage=None),),
    )


def test_discard_any_count_hand_choose2_damage100():
    """清单1：手牌任意数量基本能量弃置（up-to all，非能量被过滤）→ 张数×50。"""
    hand = (
        inst(50, energy("草能量", "草")), inst(51, energy("火能量", "火")),
        inst(52, energy("水能量", "水")), inst(53, basic("非能量")),
    )
    e = attack_engine(GOLD_RUSH_DOC, gold_rusher(), p0_hand=hand,
                      p0_energies=(inst(9001, energy()),))
    e.apply(0, Action(kind="attack", attack_index=0))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool == "own_hand"
    assert pc.pool_iids == (50, 51, 52)  # 非能量被 basic_energy 过滤
    assert pc.min_choose == 0 and pc.max_choose == 3  # up-to all
    e.apply(0, Action(kind="choose", choices=(50, 52)))
    p0 = e.state.players[0]
    assert sorted(c.iid for c in p0.discard) == [50, 52]
    assert [c.iid for c in p0.hand] == [51, 53]
    assert e.state.players[1].active.damage == 100  # 2×50（弱点：小火龙 stub 无弱点）
    assert e.state.phase == "main" and e.state.current_player == 1  # 回合推进


def test_discard_any_count_choose0_damage0_declarable():
    """清单1/D-WP5-1：选 0 张 → 伤害 0，招式仍可宣言、回合照常推进。"""
    hand = (inst(50, energy("草能量", "草")),)
    e = attack_engine(GOLD_RUSH_DOC, gold_rusher(), p0_hand=hand,
                      p0_energies=(inst(9001, energy()),))
    assert Action(kind="attack", attack_index=0) in e.legal_actions(0)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=()))
    assert e.state.players[1].active.damage == 0
    assert [c.iid for c in e.state.players[0].hand] == [50]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_discard_any_count_attached_energy_cross_pokemon():
    """清单2：own_attached_energy = 场上全体附着能量池；跨宝可梦摘下弃置，张数×70。"""
    attacker = CardDef(
        card_id="stub-极雷兽", name="极雷兽", supertype="pokemon",
        hp=200, stage=0, energy_type="雷",
        attacks=(AttackDef(name="极雷轰", cost=("雷", "斗"), damage=None),),
    )
    energies = (inst(9001, energy("雷能量", "雷")), inst(9002, energy("斗能量", "斗")))
    bench = in_play(70, basic("备战兽")).model_copy(update={
        "attached_energy": (inst(9070, energy("雷能量", "雷")),),
    })
    e = attack_engine(THUNDER_DOC, attacker, p0_energies=energies, p0_bench=(bench,))
    e.apply(0, Action(kind="attack", attack_index=0))
    pc = e.state.pending_choice
    assert pc.pool == "own_attached_energy"
    assert pc.pool_iids == (9001, 9002, 9070)
    assert pc.min_choose == 0 and pc.max_choose == 3
    e.apply(0, Action(kind="choose", choices=(9002, 9070)))  # 跨两只摘
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [9001]
    assert p0.bench[0].attached_energy == ()
    assert sorted(c.iid for c in p0.discard) == [9002, 9070]
    assert e.state.players[1].active.damage == 140  # 2×70


def test_discard_any_count_attached_choose0_damage0():
    """清单2：场上能量选 0 张 → 伤害 0 可宣言（附着能量保留）。"""
    attacker = CardDef(
        card_id="stub-极雷兽", name="极雷兽", supertype="pokemon",
        hp=200, stage=0, energy_type="雷",
        attacks=(AttackDef(name="极雷轰", cost=("雷", "斗"), damage=None),),
    )
    energies = (inst(9001, energy("雷能量", "雷")), inst(9002, energy("斗能量", "斗")))
    e = attack_engine(THUNDER_DOC, attacker, p0_energies=energies)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=()))
    assert e.state.players[1].active.damage == 0
    assert [c.iid for c in e.state.players[0].active.attached_energy] == [9001, 9002]


def test_discarded_this_effect_no_preceding_discard_is_zero():
    """清单3：计数词仅读前序——本效果内无 discard 前置 → 0。"""
    doc = parse_card_doc("""
card:
  name_group: 测试无前置
effects:
  - trigger: on_attack
    attack: 空击
    actions:
      - {action: damage, selector: opponent_active, count: discarded_this_effect, args: {op: "×", per: 50}}
""")
    attacker = CardDef(
        card_id="stub-空击兽", name="空击兽", supertype="pokemon",
        hp=100, stage=0,
        attacks=(AttackDef(name="空击", cost=("无",), damage=None),),
    )
    e = attack_engine(doc, attacker, p0_energies=(inst(9001, energy()),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0
    assert e.state.phase == "main" and e.state.current_player == 1


def test_discard_any_count_bad_forms_dsl_error():
    """清单3：any_count 非 bool / 与 choose 并存 → DslError；未知计数词 → DslError（装载闸）。"""
    bad_bool = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - {action: discard, selector: own_hand, args: {any_count: "yes"}}
""")
    e = play_engine(bad_bool, "测试坏卡")
    with pytest.raises(DslError, match="any_count"):
        e.apply(0, Action(kind="play_trainer", iid=60))

    bad_combo = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - {action: discard, selector: own_hand, choose: 1, args: {any_count: true}}
""")
    e2 = play_engine(bad_combo, "测试坏卡")
    with pytest.raises(DslError, match="any_count"):
        e2.apply(0, Action(kind="play_trainer", iid=60))

    with pytest.raises(DslError, match="counters"):
        parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - {action: damage, selector: opponent_active, count: no_such_counter, args: {op: "×", per: 10}}
""")


# ── attached_energy_on_target（清单 4-5）─────────────────────────────────────

STORM_DOC = parse_card_doc("""
card:
  name_group: 测试落雷
effects:
  - trigger: on_attack
    attack: 落雷风暴
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, count: attached_energy_on_target, args: {op: "×", per: 30}}
""")


def stormer() -> CardDef:
    return CardDef(
        card_id="stub-落雷兽", name="落雷兽", supertype="pokemon",
        hp=180, stage=0, energy_type="雷",
        attacks=(AttackDef(name="落雷风暴", cost=("雷", "斗"), damage=None),),
    )


def storm_energies() -> tuple:
    return (inst(9001, energy("雷能量", "雷")), inst(9002, energy("斗能量", "斗")))


def test_attached_energy_on_target_active_x30():
    """清单4：目标附着能量数×30（战斗场目标 2 能 = 60）。"""
    p1_active = in_play(2, basic("小火龙", hp=200), 2)
    e = attack_engine(STORM_DOC, stormer(), p0_energies=storm_energies(),
                      p1_active=p1_active)
    e.apply(0, Action(kind="attack", attack_index=0))
    pc = e.state.pending_choice
    assert pc.pool == "opponent_pokemon_any"
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[1].active.damage == 60


def test_attached_energy_on_target_bench_no_weakness_resistance():
    """清单4：备战目标不计算弱点抗性（贯穿规则回归）——备战 3 能、弱点命中仍 90 不翻倍。"""
    weak_bench = CardDef(
        card_id="stub-弱雷兽", name="弱雷兽", supertype="pokemon",
        hp=200, stage=0, weakness="雷",
        attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
    )
    p1_bench = (in_play(70, weak_bench, 3),)
    p1_active = in_play(2, basic("小火龙", hp=200), 1)
    e = attack_engine(STORM_DOC, stormer(), p0_energies=storm_energies(),
                      p1_active=p1_active, p1_bench=p1_bench)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(70,)))
    assert e.state.players[1].bench[0].damage == 90  # 3×30，不 ×2


def test_attached_energy_on_target_zero_energy():
    """清单4：目标无能量 → 伤害 0。"""
    p1_active = in_play(2, basic("小火龙", hp=200), 0)
    e = attack_engine(STORM_DOC, stormer(), p0_energies=storm_energies(),
                      p1_active=p1_active)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[1].active.damage == 0


# ── modify_attack_cost 声明式 + opponent_taken_prizes（清单 6-8）──────────────

VETERAN_DOC = parse_card_doc("""
card:
  name_group: 测试熊
effects:
  - trigger: passive_static
    actions:
      - {action: modify_attack_cost, args: {attack: 血月, value: opponent_taken_prizes}}
""")


def veteran_bear() -> CardDef:
    return CardDef(
        card_id="stub-熊", name="熊", supertype="pokemon",
        hp=200, stage=0, energy_type="斗",
        attacks=(
            AttackDef(name="血月", cost=("无",) * 5, damage=240),
            AttackDef(name="斗技", cost=("斗", "斗"), damage=50),
        ),
    )


def bear_engine(*, energies: tuple, p1_prizes: int, doc=VETERAN_DOC,
                attacker: CardDef | None = None):
    """main 阶段：p0 战斗场熊（iid 1）+ 指定附着能量；p1 剩余奖赏可调。"""
    mon = attacker if attacker is not None else veteran_bear()
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, mon).model_copy(update={"attached_energy": energies}),
    })
    p1 = state.players[1].model_copy(update={"prizes": state.players[1].prizes[:p1_prizes]})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {} if doc is None else {mon.name: doc}
    return e


def colorless(n: int, start: int = 9001) -> tuple:
    return tuple(inst(start + i, energy()) for i in range(n))


def test_modify_attack_cost_reduction_tiers():
    """清单6/8：对手已拿 0/2/5 奖赏（剩余 6/4/1）→ 血月费用 5/3/0 个【无】。"""
    # 拿 0：费用不变——4 能量不可宣言，5 能量可
    e = bear_engine(energies=colorless(4), p1_prizes=6)
    assert not [a for a in e.legal_actions(0) if a.kind == "attack" and a.attack_index == 0]
    e = bear_engine(energies=colorless(5), p1_prizes=6)
    assert Action(kind="attack", attack_index=0) in e.legal_actions(0)
    # 拿 2：减 2【无】→ 3 能量可宣言
    e = bear_engine(energies=colorless(3), p1_prizes=4)
    assert Action(kind="attack", attack_index=0) in e.legal_actions(0)
    e = bear_engine(energies=colorless(2), p1_prizes=4)
    assert not [a for a in e.legal_actions(0) if a.kind == "attack" and a.attack_index == 0]
    # 拿 5：减 5【无】→ clamp 下限 0，0 能量可宣言
    e = bear_engine(energies=(), p1_prizes=1)
    assert Action(kind="attack", attack_index=0) in e.legal_actions(0)


def test_modify_attack_cost_colorless_only():
    """清单7：只减【无】不减少有色部分——含有色费用合成用例锁定。"""
    mixed = CardDef(
        card_id="stub-混费兽", name="混费兽", supertype="pokemon",
        hp=200, stage=0,
        attacks=(AttackDef(name="血月", cost=("斗", "斗", "无", "无", "无"), damage=100),),
    )
    doc = parse_card_doc("""
card:
  name_group: 混费兽
effects:
  - trigger: passive_static
    actions:
      - {action: modify_attack_cost, args: {attack: 血月, value: opponent_taken_prizes}}
""")
    fight = lambda n, start: tuple(inst(start + i, energy("斗能量", "斗")) for i in range(n))
    # 拿 5（减免 5 > 3 个【无】，clamp 只减 3）→ 有效费用 （斗，斗）：2 斗能量即可
    e = bear_engine(energies=fight(2, 9001), p1_prizes=1, doc=doc, attacker=mixed)
    assert Action(kind="attack", attack_index=0) in e.legal_actions(0)
    # 拿 5、仅 1 斗 + 4 无 → 有色部分（斗斗）不满足，不可宣言
    e = bear_engine(energies=fight(1, 9001) + colorless(4, 9011), p1_prizes=1,
                    doc=doc, attacker=mixed)
    assert not [a for a in e.legal_actions(0) if a.kind == "attack"]
    # 拿 0：5 能量（2 斗 + 3 无）可宣言（全额费用）
    e = bear_engine(energies=fight(2, 9001) + colorless(3, 9011), p1_prizes=6,
                    doc=doc, attacker=mixed)
    assert Action(kind="attack", attack_index=0) in e.legal_actions(0)


def test_modify_attack_cost_source_gone_full_cost():
    """清单7：来源离场失效（求值点实时读声明）——战斗场非声明卡 → 全额费用。"""
    other = CardDef(
        card_id="stub-无特性兽", name="无特性兽", supertype="pokemon",
        hp=200, stage=0,
        attacks=(AttackDef(name="血月", cost=("无",) * 5, damage=240),),
    )
    e = bear_engine(energies=colorless(3), p1_prizes=4, doc=None, attacker=other)
    assert not [a for a in e.legal_actions(0) if a.kind == "attack"]


def test_modify_attack_cost_bad_value_dsl_error():
    """清单8：非法 value（负 int / 未知计数词）→ DslError（求值点不猜）。"""
    bad_negative = parse_card_doc("""
card:
  name_group: 熊
effects:
  - trigger: passive_static
    actions:
      - {action: modify_attack_cost, args: {attack: 血月, value: -1}}
""")
    e = bear_engine(energies=colorless(5), p1_prizes=6, doc=bad_negative)
    with pytest.raises(DslError, match="modify_attack_cost"):
        e.legal_actions(0)

    bad_word = parse_card_doc("""
card:
  name_group: 熊
effects:
  - trigger: passive_static
    actions:
      - {action: modify_attack_cost, args: {attack: 血月, value: no_such_counter}}
""")
    e2 = bear_engine(energies=colorless(5), p1_prizes=6, doc=bad_word)
    with pytest.raises(DslError):
        e2.legal_actions(0)


# ── 白蕾雅奖赏加成（清单 9-11）────────────────────────────────────────────────

BRIAR_DOC = parse_card_doc("""
card:
  name_group: 测试白蕾雅
effects:
  - trigger: on_play
    condition: opponent_prizes_eq:2
    actions:
      - {action: prize_bonus, args: {amount: 1, scope: tera_attack_ko}}
""")


def tera_attacker(name: str = "太晶兽", damage: int = 20) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=130, stage=0, is_tera=True,
        attacks=(AttackDef(name="打击", cost=("无",), damage=damage),),
    )


def briar_engine(*, p1_prizes: int, attacker: CardDef, p1_active_hp: int = 30,
                 p1_bench: tuple = (), extra_docs: dict | None = None):
    """main 阶段：p0 手牌白蕾雅（iid 60，支援者）+ 战斗场攻击者（附 1 能量）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": (inst(60, supporter_card("测试白蕾雅")),),
        "active": in_play(1, attacker, 1),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("小火龙", hp=p1_active_hp), 1),
        "prizes": state.players[1].prizes[:p1_prizes],
        "bench": p1_bench,
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"测试白蕾雅": BRIAR_DOC, attacker.name: (extra_docs or {}).get(attacker.name)}
    return e


def test_prize_bonus_condition_gate():
    """清单9：对手剩余奖赏 ≠2 → 不可使用（playable condition 门）；=2 → 可使用。"""
    e = briar_engine(p1_prizes=3, attacker=tera_attacker())
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer"]
    e2 = briar_engine(p1_prizes=2, attacker=tera_attacker())
    assert Action(kind="play_trainer", iid=60) in e2.legal_actions(0)


def test_prize_bonus_tera_attack_ko_takes_extra():
    """清单9/11：本回合太晶宝可梦招式伤害昏厥对手战斗场 → 拿 2 张（1+1，拿取方自己奖赏堆）。"""
    e = briar_engine(p1_prizes=2, attacker=tera_attacker(), p1_active_hp=20,
                     p1_bench=(in_play(70, basic("对手备战")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="attack", attack_index=0))
    p0 = e.state.players[0]
    assert len(p0.prizes) == 4  # 拿 2 张（规则 1 + 加成 1）：6 − 2
    prizes = [ev for ev in e.events if ev.kind == "take_prize"]
    assert len(prizes) == 2
    assert any(ev.kind == "prize_bonus" for ev in e.events)


def test_prize_bonus_non_tera_no_bonus():
    """清单10：非太晶宝可梦招式昏厥 → 不加成（拿 1 张）。"""
    plain = CardDef(
        card_id="stub-凡兽", name="凡兽", supertype="pokemon",
        hp=130, stage=0, attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
    )
    e = briar_engine(p1_prizes=2, attacker=plain, p1_active_hp=20,
                     p1_bench=(in_play(70, basic("对手备战")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert len(e.state.players[0].prizes) == 5  # 只拿 1
    assert len([ev for ev in e.events if ev.kind == "take_prize"]) == 1


def test_prize_bonus_counters_ko_no_bonus():
    """清单10：指示物致昏厥（非招式伤害路径）→ 不加成。"""
    counters_doc = parse_card_doc("""
card:
  name_group: 测试指示物
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 3}}
""")
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": (inst(60, supporter_card("测试白蕾雅")), inst(61, item_card("测试指示物"))),
        "active": in_play(1, tera_attacker(), 1),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("小火龙", hp=30), 1),
        "prizes": state.players[1].prizes[:2],
        "bench": (in_play(70, basic("对手备战")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"测试白蕾雅": BRIAR_DOC, "测试指示物": counters_doc}
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="play_trainer", iid=61))
    e.apply(0, Action(kind="choose", choices=(2,)))  # 3 指示物 KO 战斗场
    assert len(e.state.players[0].prizes) == 5  # 不加成（拿 1 张）
    assert e.state.phase == "promote"  # 换上流程（非终局）


def test_prize_bonus_bench_ko_no_bonus():
    """清单10：招式伤害昏厥备战宝可梦（非战斗场）→ 不加成。"""
    snipe_doc = parse_card_doc("""
card:
  name_group: 太晶狙击兽
effects:
  - trigger: on_attack
    attack: 狙击
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 50}}
""")
    sniper = CardDef(
        card_id="stub-太晶狙击兽", name="太晶狙击兽", supertype="pokemon",
        hp=130, stage=0, is_tera=True,
        attacks=(AttackDef(name="狙击", cost=("无",), damage=None),),
    )
    e = briar_engine(p1_prizes=2, attacker=sniper, p1_active_hp=200,
                     p1_bench=(in_play(70, basic("对手备战", hp=30)),),
                     extra_docs={"太晶狙击兽": snipe_doc})
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(70,)))  # 狙击备战
    assert len(e.state.players[0].prizes) == 5  # 不加成（拿 1 张）


def test_prize_bonus_cleared_next_turn():
    """清单10：回合级标记次回合清除——次回合太晶招式昏厥只拿 1 张。"""
    e = briar_engine(p1_prizes=2, attacker=tera_attacker(), p1_active_hp=20,
                     p1_bench=(in_play(70, basic("对手备战")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="end_turn"))  # → p1（标记随 p0 回合结束清除）
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 3
    e.apply(0, Action(kind="attack", attack_index=0))
    assert len(e.state.players[0].prizes) == 5  # 不加成（拿 1 张）


def test_prize_bonus_bad_args_dsl_error():
    """清单9-11 参数校验：amount 非正 int / 未知 scope → DslError。"""
    bad_amount = parse_card_doc("""
card:
  name_group: 测试白蕾雅
effects:
  - trigger: on_play
    actions:
      - {action: prize_bonus, args: {amount: 0, scope: tera_attack_ko}}
""")
    e = play_engine(bad_amount, "测试白蕾雅", kind="supporter")
    with pytest.raises(DslError, match="prize_bonus"):
        e.apply(0, Action(kind="play_trainer", iid=60))

    bad_scope = parse_card_doc("""
card:
  name_group: 测试白蕾雅
effects:
  - trigger: on_play
    actions:
      - {action: prize_bonus, args: {amount: 1, scope: no_such_scope}}
""")
    e2 = play_engine(bad_scope, "测试白蕾雅", kind="supporter")
    with pytest.raises(DslError, match="prize_bonus"):
        e2.apply(0, Action(kind="play_trainer", iid=60))


# ── coin_flip until_tails + flip_heads_count（清单 12-13）─────────────────────

COIN_FLURRY_DOC = parse_card_doc("""
card:
  name_group: 测试连掷
effects:
  - trigger: on_attack
    attack: 连掷硬币
    actions:
      - {action: coin_flip, args: {until_tails: true}}
      - {action: damage, selector: opponent_active, count: flip_heads_count, args: {op: "×", per: 20}}
""")


def coin_flipper() -> CardDef:
    return CardDef(
        card_id="stub-连掷兽", name="连掷兽", supertype="pokemon",
        hp=60, stage=0,
        attacks=(AttackDef(name="连掷硬币", cost=("无",), damage=None),),
    )


def test_until_tails_seed_locked_sequence_and_damage():
    """清单12/13：seed 2 → 正正正正反（RandomSource 实测），伤害 4×20=80；
    同种子复跑掷币序列与伤害一致。"""
    for _ in range(2):
        e = attack_engine(COIN_FLURRY_DOC, coin_flipper(),
                          p0_energies=(inst(9001, energy()),), seed=2)
        e.apply(0, Action(kind="attack", attack_index=0))
        assert e.state.players[1].active.damage == 80
        flip_events = [ev for ev in e.events
                       if ev.kind == "effect_primitive" and ev.detail.get("action") == "coin_flip"]
        assert flip_events[0].detail["result"]["flips"] == [
            "heads", "heads", "heads", "heads", "tails",
        ]
        assert flip_events[0].detail["result"]["heads"] == 4


def test_until_tails_first_tails_zero_damage():
    """清单12：首掷即反面（seed 1）→ 正面 0 次 → 伤害 0，回合照常推进。"""
    e = attack_engine(COIN_FLURRY_DOC, coin_flipper(),
                      p0_energies=(inst(9001, energy()),), seed=1)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0
    assert e.state.phase == "main" and e.state.current_player == 1


def test_until_tails_last_flip_gates_if_flip_nodes():
    """清单13：until_tails 的末掷（恒为反面）驱动 if_flip_* 门控——
    if_flip_tails 节点执行、if_flip_heads 节点跳过（既有门控语义回归）。"""
    doc = parse_card_doc("""
card:
  name_group: 测试连掷门控
effects:
  - trigger: on_attack
    attack: 连掷硬币
    actions:
      - {action: coin_flip, args: {until_tails: true}}
      - {action: draw, count: 1, condition: if_flip_tails}
      - {action: draw, count: 1, condition: if_flip_heads}
""")
    e = attack_engine(doc, coin_flipper(), p0_energies=(inst(9001, energy()),), seed=2)
    hand_before = len(e.state.players[0].hand)
    e.apply(0, Action(kind="attack", attack_index=0))
    p0 = e.state.players[0]
    assert len(p0.hand) == hand_before + 1  # 仅 if_flip_tails 的 draw 执行
    skipped = [ev for ev in e.events
               if ev.kind == "effect_primitive" and ev.detail.get("result", {}).get("skipped")]
    assert len(skipped) == 1 and skipped[0].detail["params"]["condition"] == "if_flip_heads"


def test_until_tails_bad_args_dsl_error():
    """清单12：until_tails 与 times 并存 / 非 bool → DslError。"""
    bad_combo = parse_card_doc("""
card:
  name_group: 测试坏掷
effects:
  - trigger: on_play
    actions:
      - {action: coin_flip, args: {until_tails: true, times: 3}}
""")
    e = play_engine(bad_combo, "测试坏掷")
    with pytest.raises(DslError, match="until_tails"):
        e.apply(0, Action(kind="play_trainer", iid=60))

    bad_bool = parse_card_doc("""
card:
  name_group: 测试坏掷
effects:
  - trigger: on_play
    actions:
      - {action: coin_flip, args: {until_tails: "yes"}}
""")
    e2 = play_engine(bad_bool, "测试坏掷")
    with pytest.raises(DslError, match="until_tails"):
        e2.apply(0, Action(kind="play_trainer", iid=60))


def test_flip_heads_count_without_flip_dsl_error():
    """清单12：flip_heads_count 无前置掷币 → DslError（不猜，同 last_flip 口径）。"""
    doc = parse_card_doc("""
card:
  name_group: 测试坏计数
effects:
  - trigger: on_attack
    attack: 空击
    actions:
      - {action: damage, selector: opponent_active, count: flip_heads_count, args: {op: "×", per: 20}}
""")
    attacker = CardDef(
        card_id="stub-空击兽", name="空击兽", supertype="pokemon",
        hp=100, stage=0, attacks=(AttackDef(name="空击", cost=("无",), damage=None),),
    )
    e = attack_engine(doc, attacker, p0_energies=(inst(9001, energy()),))
    with pytest.raises(DslError, match="flip_heads_count"):
        e.apply(0, Action(kind="attack", attack_index=0))


# ── bounce args.attachments=hand（清单 14-15）─────────────────────────────────

BOUNCE_HAND_DOC = parse_card_doc("""
card:
  name_group: 测试牡丹
effects:
  - trigger: on_play
    actions:
      - {action: bounce, selector: own_pokemon_in_play, choose: 1, filters: [basic_pokemon], args: {attachments: hand}}
""")

BOUNCE_DEFAULT_DOC = parse_card_doc("""
card:
  name_group: 测试剧本
effects:
  - trigger: on_play
    actions:
      - {action: bounce, selector: own_pokemon_in_play, choose: 1}
""")


def test_bounce_attachments_hand_all_to_hand():
    """清单14：attachments=hand——整叠 + 附着能量/道具全部回手牌，弃牌区不变。"""
    bench_mon = in_play(70, basic("回手兽")).model_copy(update={
        "attached_energy": (inst(9070, energy("草能量", "草")),),
        "attached_tool": inst(80, tool_card("测试道具")),
    })
    e = play_engine(BOUNCE_HAND_DOC, "测试牡丹", kind="supporter",
                    p0_bench=(bench_mon,), discard=(inst(90, basic("旧弃牌")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.pool_iids == (1, 70)  # 战斗场 stub（妙蛙种子 stage0）+ 备战基础
    e.apply(0, Action(kind="choose", choices=(70,)))
    p0 = e.state.players[0]
    assert sorted(c.iid for c in p0.hand) == [50, 51, 70, 80, 9070]  # 整叠+能量+道具回手
    assert [c.iid for c in p0.discard] == [90, 60]  # 仅旧弃牌 + 支援者本体
    assert p0.bench == ()


def test_bounce_attachments_hand_active_promote_regression():
    """清单15：战斗场目标 bounce 后换上流程不变式（resume_after_promotes → 回主阶段）。"""
    e = play_engine(BOUNCE_HAND_DOC, "测试牡丹", kind="supporter",
                    p0_bench=(in_play(70, basic("备战兽")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(1,)))  # 回手战斗场
    assert e.state.phase == "promote" and e.state.current_player == 0
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert 1 in [c.iid for c in e.state.players[0].hand]  # 战斗场整叠回手


def test_bounce_attachments_default_discard_regression():
    """清单14：默认（无 attachments 参数）行为回归——附着物进弃牌区。"""
    bench_mon = in_play(70, basic("回手兽")).model_copy(update={
        "attached_energy": (inst(9070, energy()),),
    })
    e = play_engine(BOUNCE_DEFAULT_DOC, "测试剧本", p0_bench=(bench_mon,))
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(70,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51, 70]  # 整叠回手
    assert sorted(c.iid for c in p0.discard) == [60, 9070]  # 能量 + 本体进弃牌区


def test_bounce_attachments_bad_value_dsl_error():
    """清单15：attachments 非法值 → DslError。"""
    doc = parse_card_doc("""
card:
  name_group: 测试坏牡丹
effects:
  - trigger: on_play
    actions:
      - {action: bounce, selector: own_pokemon_in_play, choose: 1, args: {attachments: deck}}
""")
    e = play_engine(doc, "测试坏牡丹", kind="supporter",
                    p0_bench=(in_play(70, basic("备战兽")),))
    with pytest.raises(DslError, match="attachments"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_bounce_evolved_not_selectable():
    """清单14（牡丹负例）：进化体（栈顶 stage≥1）被 basic_pokemon 场上过滤器排除。"""
    from helpers import stage1

    evolved = in_play(70, basic("底兽")).model_copy(update={
        "stack": (inst(70, basic("底兽")), inst(71, stage1("顶兽", "底兽"))),
    })
    e = play_engine(BOUNCE_HAND_DOC, "测试牡丹", kind="supporter",
                    p0_bench=(evolved,))
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.pool_iids == (1,)  # 进化体（栈顶 iid 71）不可选


# ── transform 替换原语（清单 16-18）───────────────────────────────────────────

TRANSFORM_DOC = parse_card_doc("""
card:
  name_group: 测试百变怪
effects:
  - trigger: ability_manual
    limit: once_per_turn
    condition: self_is_active_and_first_own_turn
    actions:
      - {action: transform, selector: self, choose: 1, filters: [basic_pokemon, not_name:百变怪]}
      - {action: shuffle_deck}
""")


def ditto() -> CardDef:
    return CardDef(
        card_id="stub-百变怪", name="百变怪", supertype="pokemon",
        hp=70, stage=0, attacks=(AttackDef(name="粘粑粑", cost=("无",), damage=10),),
    )


def ditto_deck() -> tuple:
    """牌库：替换兽(100, 基础) + 百变怪(101, 排除) + 顶兽(102, stage1 排除) + 填充。"""
    from helpers import stage1

    return (
        inst(100, basic("替换兽")), inst(101, ditto()),
        inst(102, stage1("顶兽", "替换兽")),
        inst(103, basic("填充兽")),
    )


def test_transform_full_flow():
    """清单16：战斗场百变怪 → 选牌库 1 基础（除百变怪/进化）→ 整叠+附着物进弃牌区、
    被选宝可梦入战斗场（entered_play 登记）→ 重洗；不触发昏厥/奖赏/换上。"""
    active = in_play(1, ditto(), 1).model_copy(update={
        "damage": 30, "conditions": frozenset({SpecialCondition.POISONED}),
    })
    e = ability_engine(TRANSFORM_DOC, "百变怪", ditto(), deck=ditto_deck(), turn=1)
    p0 = e.state.players[0]
    e._set_player(0, p0.model_copy(update={"active": active}))
    acts = [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    assert acts and acts[0].iid == 1
    e.apply(0, acts[0])
    pc = e.state.pending_choice
    assert pc.pool == "own_deck" and pc.pool_iids == (100, 103)  # 百变怪/stage1 排除
    assert pc.min_choose == 0 and pc.max_choose == 1
    e.apply(0, Action(kind="choose", choices=(100,)))
    p0 = e.state.players[0]
    new_active = p0.active
    assert new_active.current.iid == 100 and new_active.current.card.name == "替换兽"
    assert 100 in p0.entered_play_this_turn  # 登场登记
    assert sorted(c.iid for c in p0.discard) == [1, 9010]  # 百变怪整叠 + 附着能量
    assert sorted(c.iid for c in p0.deck) == [101, 102, 103]
    assert [c.iid for c in p0.deck] != [101, 102, 103]  # 重洗
    assert e.state.phase == "main" and e.state.current_player == 0
    assert not [ev for ev in e.events if ev.kind in ("knockout", "take_prize", "promote")]


def test_transform_no_inherit_damage_and_status():
    """清单18/D-WP5-3：伤害/特殊状态不继承（新宝可梦为全新 InPlayPokemon）。"""
    active = in_play(1, ditto(), 1).model_copy(update={
        "damage": 30, "conditions": frozenset({SpecialCondition.POISONED}),
    })
    e = ability_engine(TRANSFORM_DOC, "百变怪", ditto(), deck=ditto_deck(), turn=1)
    e._set_player(0, e.state.players[0].model_copy(update={"active": active}))
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(100,)))
    new_active = e.state.players[0].active
    assert new_active.damage == 0 and new_active.conditions == frozenset()
    assert new_active.attached_energy == ()


def test_transform_up_to_empty_choice_noop_reshuffle():
    """清单16/D-WP5-3：可以不找 → no-op（百变怪留场、不弃置），重洗仍执行。"""
    e = ability_engine(TRANSFORM_DOC, "百变怪", ditto(), deck=ditto_deck(), turn=1)
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert p0.active.current.card.name == "百变怪"
    assert p0.discard == ()
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103]
    assert [c.iid for c in p0.deck] != [100, 101, 102, 103]  # 重洗仍执行


def test_transform_no_legal_target_noop_reshuffle():
    """清单17：牌库无合法目标（全是百变怪/进化/训练家）→ no-op 仍重洗。"""
    from helpers import stage1

    deck = (inst(100, ditto()), inst(101, stage1("顶兽", "替换兽")),
            inst(102, item_card("物品甲")), inst(103, ditto()))
    e = ability_engine(TRANSFORM_DOC, "百变怪", ditto(), deck=deck, turn=1)
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "main" and e.state.pending_choice is None  # 不挂起
    p0 = e.state.players[0]
    assert p0.active.current.card.name == "百变怪"
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103]
    assert [c.iid for c in p0.deck] != [100, 101, 102, 103]  # 重洗仍执行


def test_transform_gates():
    """清单17：备战位不可发动（self_is_active）；非首回合不可发动（first_own_turn）。"""
    # 备战位百变怪 → 特性不枚举
    e = ability_engine(TRANSFORM_DOC, "百变怪", ditto(), deck=ditto_deck(), turn=1,
                       p0_bench=())
    p0 = e.state.players[0]
    e._set_player(0, p0.model_copy(update={
        "bench": (p0.active,), "active": in_play(2, basic("占位兽")),
    }))
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    # turn 2（非最初回合）→ 不枚举
    e2 = ability_engine(TRANSFORM_DOC, "百变怪", ditto(), deck=ditto_deck(), turn=2)
    assert not [a for a in e2.legal_actions(0) if a.kind == "use_ability"]


def test_transform_bad_forms_dsl_error():
    """清单18：selector≠self / choose≠1 → DslError。"""
    bad_selector = parse_card_doc("""
card:
  name_group: 测试百变怪
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: transform, selector: own_bench, choose: 1, filters: [basic_pokemon]}
""")
    e = ability_engine(bad_selector, "百变怪", ditto(), deck=ditto_deck(), turn=1)
    with pytest.raises(DslError, match="transform"):
        e.apply(0, Action(kind="use_ability", iid=1))

    bad_choose = parse_card_doc("""
card:
  name_group: 测试百变怪
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: transform, selector: self, choose: 2, filters: [basic_pokemon]}
""")
    e2 = ability_engine(bad_choose, "百变怪", ditto(), deck=ditto_deck(), turn=1)
    with pytest.raises(DslError, match="transform"):
        e2.apply(0, Action(kind="use_ability", iid=1))
