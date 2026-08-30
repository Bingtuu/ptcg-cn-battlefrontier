"""task 007：解释器骨架 + play_trainer 引擎接入验收测试（PRD §5.4 / §6.6）。"""

import pytest

from battlefrontier.dsl import DslError, parse_card_doc
from battlefrontier.engine.actions import Action
from tests.helpers import basic, energy, engine_at, inst, main_state, stage1

RESEARCH_DOC = parse_card_doc("""
card:
  name_group: 博士的研究
effects:
  - trigger: on_play
    cost:
      - {action: discard, selector: own_hand, count: all}
    actions:
      - {action: draw, count: 7}
""")

DRAW1_DOC = parse_card_doc("""
card:
  name_group: 测试抽牌
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
    observe: [test_anchor]
""")

SEARCH_DOC = parse_card_doc("""
card:
  name_group: 测试检索
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, count: 1, destination: hand}
""")

COPY_DOC = parse_card_doc("""
card:
  name_group: 测试复制
effects:
  - trigger: on_play
    actions:
      - {action: reveal, selector: own_hand}
""")

COUNTER_DOC = parse_card_doc("""
card:
  name_group: 测试计数
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: own_remaining_prizes}
""")


def trainer(name: str, subtype: str):
    from battlefrontier.engine.state import CardDef

    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype=subtype)


def item(name: str):
    return trainer(name, "物品")


def supporter(name: str):
    return trainer(name, "支援者")


def research_engine(**kwargs):
    """main 阶段、手牌含博士的研究的引擎（博士的研究 DSL 已注册）。"""
    state = main_state(p0_extra_hand=(inst(60, item("博士的研究")),), **kwargs)
    engine = engine_at(state)
    engine.card_effects = {"博士的研究": RESEARCH_DOC}
    return engine


# ── 端到端：博士的研究 ─────────────────────────────────


def test_play_professors_research_end_to_end():
    engine = research_engine()
    # 初始手牌：小火龙(50) + 能量(51) + 博士的研究(60)
    engine.apply(0, Action(kind="play_trainer", iid=60))
    p0 = engine.state.players[0]
    assert [c.iid for c in p0.hand] == [100, 101, 102, 103, 104, 105, 106]
    # 弃牌区：先效果弃的 2 张手牌，最后是本体
    assert [c.iid for c in p0.discard] == [50, 51, 60]


def test_effect_event_stream_fields():
    engine = research_engine()
    engine.apply(0, Action(kind="play_trainer", iid=60))
    kinds = [ev.kind for ev in engine.events]
    assert kinds.index("effect_start") < kinds.index("effect_primitive") < kinds.index("effect_end")
    primitives = [ev for ev in engine.events if ev.kind == "effect_primitive"]
    assert len(primitives) == 2  # cost discard + action draw
    for ev in primitives:
        assert {"effect_id", "card", "action", "params", "result"} <= set(ev.detail)
        assert ev.detail["card"] == "博士的研究"
    assert primitives[0].detail["action"] == "discard"
    assert primitives[0].detail["result"]["discarded"] == 2
    assert primitives[1].detail["action"] == "draw"
    assert primitives[1].detail["result"]["drawn"] == 7


def test_observe_anchor_emitted():
    state = main_state(p0_extra_hand=(inst(60, item("测试抽牌")),))
    engine = engine_at(state)
    engine.card_effects = {"测试抽牌": DRAW1_DOC}
    engine.apply(0, Action(kind="play_trainer", iid=60))
    observe = [ev for ev in engine.events if ev.kind == "effect_observe"]
    assert len(observe) == 1
    assert observe[0].detail["anchor"] == "test_anchor"


# ── play_trainer 枚举与支援者规则（PRD §6.6）────────────


def test_play_trainer_enumerated_in_main_phase():
    engine = research_engine()
    assert Action(kind="play_trainer", iid=60) in engine.legal_actions(0)


def test_play_trainer_not_enumerated_during_setup():
    state = main_state(p0_extra_hand=(inst(60, item("博士的研究")),))
    state = state.model_copy(update={"phase": "setup_active"})
    engine = engine_at(state)
    engine.card_effects = {"博士的研究": RESEARCH_DOC}
    assert not [a for a in engine.legal_actions(0) if a.kind == "play_trainer"]


def test_trainer_without_dsl_doc_not_playable():
    state = main_state(p0_extra_hand=(inst(60, item("神秘卡")),))
    engine = engine_at(state)  # 无 DSL 文档
    assert not [a for a in engine.legal_actions(0) if a.kind == "play_trainer"]


def test_items_unlimited_per_turn():
    state = main_state(p0_extra_hand=(inst(60, item("测试抽牌")), inst(61, item("测试抽牌"))))
    engine = engine_at(state)
    engine.card_effects = {"测试抽牌": DRAW1_DOC}
    engine.apply(0, Action(kind="play_trainer", iid=60))
    assert Action(kind="play_trainer", iid=61) in engine.legal_actions(0)
    engine.apply(0, Action(kind="play_trainer", iid=61))


def test_second_supporter_not_legal_same_turn():
    state = main_state(p0_extra_hand=(inst(60, supporter("测试抽牌")), inst(61, supporter("测试抽牌"))))
    engine = engine_at(state)
    engine.card_effects = {"测试抽牌": DRAW1_DOC}
    engine.apply(0, Action(kind="play_trainer", iid=60))
    assert Action(kind="play_trainer", iid=61) not in engine.legal_actions(0)


def test_supporter_banned_for_first_player_on_turn_one():
    state = main_state(p0_extra_hand=(inst(60, supporter("测试抽牌")), inst(61, item("测试抽牌"))))
    state = state.model_copy(update={"turn": 1})  # first_player=0 的先攻首回合
    engine = engine_at(state)
    engine.card_effects = {"测试抽牌": DRAW1_DOC}
    assert Action(kind="play_trainer", iid=60) not in engine.legal_actions(0)
    assert Action(kind="play_trainer", iid=61) in engine.legal_actions(0)


def test_supporter_marker_resets_next_turn():
    state = main_state(p0_extra_hand=(inst(60, supporter("测试抽牌")), inst(61, supporter("测试抽牌"))))
    engine = engine_at(state)
    engine.card_effects = {"测试抽牌": DRAW1_DOC}
    engine.apply(0, Action(kind="play_trainer", iid=60))
    engine.apply(0, Action(kind="end_turn"))
    engine.apply(1, Action(kind="end_turn"))
    assert Action(kind="play_trainer", iid=61) in engine.legal_actions(0)


# ── 错误路径与边界 ─────────────────────────────────────


def test_unimplemented_primitive_raises_dsl_error():
    """词表有而未实现的原语（reveal）= DslError「未实现」（copy_attack 已于 task 017 实现，
    本测试改用 reveal 锁定「词表有而未实现」路径）。"""
    state = main_state(p0_extra_hand=(inst(60, item("测试复制")),))
    engine = engine_at(state)
    engine.card_effects = {"测试复制": COPY_DOC}
    with pytest.raises(DslError, match="未实现"):
        engine.apply(0, Action(kind="play_trainer", iid=60))


def test_search_deck_requires_choose():
    """task 009：search_deck 已实现但必须经 chooser（choose=N）；count=int 形式报错。"""
    state = main_state(p0_extra_hand=(inst(60, item("测试检索")),))
    engine = engine_at(state)
    engine.card_effects = {"测试检索": SEARCH_DOC}
    with pytest.raises(DslError, match="choose"):
        engine.apply(0, Action(kind="play_trainer", iid=60))


def test_draw_counter_expression_supported():
    """task 017：draw 支持计数表达式（own_remaining_prizes = 剩余奖赏 6 张 → 抽 6）。"""
    state = main_state(p0_extra_hand=(inst(60, item("测试计数")),))
    engine = engine_at(state)
    engine.card_effects = {"测试计数": COUNTER_DOC}
    hand_before = len(state.players[0].hand) - 1  # 本体打出后
    deck_before = len(state.players[0].deck)
    engine.apply(0, Action(kind="play_trainer", iid=60))
    assert len(engine.state.players[0].hand) == hand_before + 6
    assert len(engine.state.players[0].deck) == deck_before - 6


def test_draw_caps_at_deck_size():
    state = main_state(p0_extra_hand=(inst(60, item("博士的研究")),))
    p0 = state.players[0].model_copy(update={"deck": state.players[0].deck[:3]})
    state = state.model_copy(update={"players": (p0, state.players[1])})
    engine = engine_at(state)
    engine.card_effects = {"博士的研究": RESEARCH_DOC}
    engine.apply(0, Action(kind="play_trainer", iid=60))
    p0_after = engine.state.players[0]
    assert len(p0_after.hand) == 3  # 牌库只有 3 张，抽完即止，不判负
    assert engine.state.phase == "main"


# ── 对局级确定性 ───────────────────────────────────────


def test_determinism_with_trainer_in_deck():
    from battlefrontier.runner.play import play_game

    deck = [basic("妙蛙种子")] * 20 + [item("测试抽牌")] * 20 + [energy()] * 20
    effects = {"测试抽牌": DRAW1_DOC}
    r1 = play_game(deck, deck, seed=7, card_effects=effects)
    r2 = play_game(deck, deck, seed=7, card_effects=effects)
    assert r1.events_hash == r2.events_hash
    # 确实走到了解释器路径（防御：牌组里训练家卡真的被打出过）
    assert any(ev.kind == "effect_start" for ev in r1.events)


# ── task 025：coin_flip 原语 + 节点级门控（if_flip_heads / if_flip_tails）──
# 掷币走引擎单一随机源（RandomSource.flip_coin，混乱判定同款）；条件词读最近一次
# coin_flip 结果，不满足的节点跳过并落 skipped 标注事件；无前置掷币 = DslError（不猜）。

from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource

FLIP_SEARCH_DOC = parse_card_doc("""
card:
  name_group: 测试掷币检索
effects:
  - trigger: on_play
    actions:
      - {action: coin_flip}
      - {action: search_deck, selector: own_deck, filters: [evolved_pokemon], choose: 1, destination: hand, condition: if_flip_heads}
      - {action: search_deck, selector: own_deck, filters: [basic_pokemon], choose: 1, destination: hand, condition: if_flip_tails}
      - {action: shuffle_deck}
""")

NO_FLIP_GATE_DOC = parse_card_doc("""
card:
  name_group: 测试无掷币门控
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1, condition: if_flip_heads}
""")

BAD_NODE_CONDITION_DOC = parse_card_doc("""
card:
  name_group: 测试未知门控
effects:
  - trigger: on_play
    actions:
      - {action: coin_flip}
      - {action: draw, count: 1, condition: if_flip_maybe}
""")

FLIP_TWICE_DOC = parse_card_doc("""
card:
  name_group: 测试连掷
effects:
  - trigger: on_play
    actions:
      - {action: coin_flip, args: {times: 2}}
""")


def flip_engine(seed: int, doc, name: str, deck: tuple | None = None) -> GameEngine:
    """main 阶段、p0 手牌含测试物品（iid 60）的引擎；随机源种子可注入。"""
    state = main_state(p0_extra_hand=(inst(60, item(name)),))
    if deck is not None:
        p0 = state.players[0].model_copy(update={"deck": deck})
        state = state.model_copy(update={"players": (p0, state.players[1])})
    engine = GameEngine(RandomSource(seed))
    engine.state = state
    engine.card_effects = {name: doc}
    return engine


def mixed_evolution_deck() -> tuple:
    """基础 ×2（100/101）+ 1 阶进化 ×2（102/103）。"""
    return (
        inst(100, basic("妙蛙种子")), inst(101, basic("小火龙")),
        inst(102, stage1("妙蛙草", "妙蛙种子")), inst(103, stage1("火恐龙", "小火龙")),
    )


def skipped_events(engine) -> list:
    return [
        ev for ev in engine.events
        if ev.kind == "effect_primitive" and ev.detail["result"].get("skipped")
    ]


def test_coin_flip_heads_gates_to_heads_branch():
    """seed 0 首掷 = 正面：进化宝可梦检索挂起，反面分支落 skipped 事件且不挂起。"""
    e = flip_engine(0, FLIP_SEARCH_DOC, "测试掷币检索", deck=mixed_evolution_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {102, 103}  # 仅进化宝可梦（过滤器 evolved_pokemon）
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (102,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert [c.iid for c in p0.hand] == [50, 51, 102]
    skips = skipped_events(e)
    assert [ev.detail["action"] for ev in skips] == ["search_deck"]
    assert skips[0].detail["result"]["condition"] == "if_flip_tails"
    assert any(
        ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"
        for ev in e.events
    )


def test_coin_flip_tails_branch_and_skip_before_suspend():
    """seed 1 首掷 = 反面：正面分支先跳过（skipped 事件先于挂起），反面分支检索基础。"""
    e = flip_engine(1, FLIP_SEARCH_DOC, "测试掷币检索", deck=mixed_evolution_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    skips = skipped_events(e)
    assert len(skips) == 1 and skips[0].detail["result"]["condition"] == "if_flip_heads"
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {100, 101}
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (101,)))
    assert [c.iid for c in e.state.players[0].hand] == [50, 51, 101]
    assert len(skipped_events(e)) == 1  # 反面分支真实执行，无第二个 skipped


def test_coin_flip_event_records_faces():
    """coin_flip 落 effect_primitive 事件，detail 含正/反面明细。"""
    e = flip_engine(0, FLIP_SEARCH_DOC, "测试掷币检索", deck=mixed_evolution_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    flip = next(
        ev for ev in e.events
        if ev.kind == "effect_primitive" and ev.detail["action"] == "coin_flip"
    )
    assert flip.detail["result"]["flips"] == ["heads"]
    assert flip.detail["result"]["heads"] == 1


def test_node_condition_without_preceding_flip_raises():
    """无前置 coin_flip 遇 if_flip_heads = DslError（不猜）。"""
    e = flip_engine(0, NO_FLIP_GATE_DOC, "测试无掷币门控")
    with pytest.raises(DslError, match="coin_flip"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_unknown_node_condition_raises():
    """未知节点 condition 词 = DslError（词注册在解释器）。"""
    e = flip_engine(0, BAD_NODE_CONDITION_DOC, "测试未知门控")
    with pytest.raises(DslError, match="condition"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_coin_flip_times_arg():
    """args.times=2：连掷 2 次，事件记录全部正反面；门控读最后一次（seed 0：正反→反面）。"""
    e = flip_engine(0, FLIP_TWICE_DOC, "测试连掷")
    e.apply(0, Action(kind="play_trainer", iid=60))
    flip = next(
        ev for ev in e.events
        if ev.kind == "effect_primitive" and ev.detail["action"] == "coin_flip"
    )
    assert flip.detail["result"]["flips"] == ["heads", "tails"]
    assert flip.detail["result"]["heads"] == 1


# ── task 025：heal（恢复 HP = 去伤害指示物）+ switch own_bench（own 侧互换）──
# 规则出处：rules-manual §7.1「恢复途径：回到备战区（撤退或效果）；进化；恢复类效果」；
# §5 撤退条目「伤害指示物保留、特殊状态消除」——效果互换与撤退同规则（不清伤害、清状态、
# 不占每回合撤退次数）。恢复不超过已有伤害（floor 0）。

from battlefrontier.engine.state import SpecialCondition
from tests.helpers import in_play

HEAL_ACTIVE_DOC = parse_card_doc("""
card:
  name_group: 测试恢复战斗场
effects:
  - trigger: on_play
    actions:
      - {action: heal, selector: own_active, args: {amount: 30}}
""")

HEAL_CHOOSE_DOC = parse_card_doc("""
card:
  name_group: 测试恢复选择
effects:
  - trigger: on_play
    actions:
      - {action: heal, selector: own_pokemon_in_play, choose: 1, filters: [has_damage_counters], args: {amount: 30}}
""")

SWITCH_OWN_DOC = parse_card_doc("""
card:
  name_group: 测试自家互换
effects:
  - trigger: on_play
    actions:
      - {action: switch, selector: own_bench, choose: 1}
""")


def heal_engine(doc, name: str, *, active_damage: int = 0, paralyzed: bool = False,
                bench: tuple = ()) -> GameEngine:
    """main 阶段、p0 战斗场带指定伤害/状态 + 备战区，手牌含测试物品（iid 60）。"""
    state = main_state(p0_extra_hand=(inst(60, item(name)),))
    p0 = state.players[0]
    active = p0.active.model_copy(update={
        "damage": active_damage,
        "conditions": frozenset({SpecialCondition.PARALYZED}) if paralyzed else frozenset(),
    })
    p0 = p0.model_copy(update={"active": active, "bench": bench})
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {name: doc}
    return engine


def test_heal_own_active_removes_counters():
    """战斗场 50 伤害，恢复 30 → 剩 20（= 去 3 个「10」指示物）。"""
    e = heal_engine(HEAL_ACTIVE_DOC, "测试恢复战斗场", active_damage=50)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.players[0].active.damage == 20
    ev = next(
        ev for ev in e.events
        if ev.kind == "effect_primitive" and ev.detail["action"] == "heal"
    )
    assert ev.detail["result"]["healed"] == 30


def test_heal_floors_at_existing_damage():
    """已有伤害 20 < 恢复量 30：只去 20，HP 不过量恢复（floor 0）。"""
    e = heal_engine(HEAL_ACTIVE_DOC, "测试恢复战斗场", active_damage=20)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.players[0].active.damage == 0
    ev = next(
        ev for ev in e.events
        if ev.kind == "effect_primitive" and ev.detail["action"] == "heal"
    )
    assert ev.detail["result"]["healed"] == 20


def test_heal_choose_target_with_filter():
    """choose 路径：池 = 场上有伤害指示物的宝可梦（has_damage_counters），挂起后恢复所选。"""
    bench = (
        in_play(70, basic("小拉达")).model_copy(update={"damage": 40}),
        in_play(71, basic("喵喵")),  # 无伤害 → 被过滤器排除
    )
    e = heal_engine(HEAL_CHOOSE_DOC, "测试恢复选择", active_damage=10, bench=bench)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {1, 70}  # 战斗场(iid 1)与备战 70，喵喵(71)无伤害不进池
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (70,)))
    p0 = e.state.players[0]
    assert p0.bench[0].damage == 10
    assert p0.active.damage == 10  # 未选的不动


def test_heal_choose_no_damaged_target_noop():
    """全场无伤害指示物：池空不挂起（尽力而为空结算），不进入 choice 阶段。"""
    e = heal_engine(HEAL_CHOOSE_DOC, "测试恢复选择", bench=(in_play(70, basic("小拉达")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "main"


def test_switch_own_bench_swaps_and_clears_status():
    """own 侧互换：战斗场（麻痹 + 30 伤害）↔ 备战 70；回备战清特殊状态、伤害保留。"""
    e = heal_engine(
        SWITCH_OWN_DOC, "测试自家互换",
        active_damage=30, paralyzed=True, bench=(in_play(70, basic("小拉达")),),
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (70,)))
    p0 = e.state.players[0]
    assert p0.active.current.iid == 70
    assert p0.bench[0].current.iid == 1
    assert p0.bench[0].conditions == frozenset()  # 回备战区特殊状态恢复（§7.1）
    assert p0.bench[0].damage == 30  # 伤害指示物保留（§5 撤退条目同理）
    assert not p0.retreated_this_turn  # 效果互换不占每回合撤退次数


def test_switch_own_bench_unavailable_without_bench():
    """无备战宝可梦：可行性门拦截，不枚举该物品。"""
    e = heal_engine(SWITCH_OWN_DOC, "测试自家互换")
    assert Action(kind="play_trainer", iid=60) not in e.legal_actions(0)


# ── task 025：bounce（放回手牌，弗图博士的剧本机制件）────────────────────
# 规则出处：卡面 rule_reference 句「（除宝可梦以外的卡牌，全部放于弃牌区。）」+
# rules-reference 附录 A 决议（整叠回手 / 战斗场空置须换上 / 无宝可梦判负）。

from battlefrontier.engine.state import CardDef, InPlayPokemon

BOUNCE_DOC = parse_card_doc("""
card:
  name_group: 测试放回手牌
effects:
  - trigger: on_play
    actions:
      - {action: bounce, selector: own_pokemon_in_play, choose: 1}
""")


def tool_card(name: str = "测试道具") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def bounce_engine(*, bench: tuple = (), active_mon: InPlayPokemon | None = None) -> GameEngine:
    state = main_state(p0_extra_hand=(inst(60, item("测试放回手牌")),))
    p0 = state.players[0]
    p0 = p0.model_copy(update={
        "active": active_mon if active_mon is not None else p0.active,
        "bench": bench,
    })
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"测试放回手牌": BOUNCE_DOC}
    return engine


def stacked_mon() -> InPlayPokemon:
    """备战区进化链（底 70 基础 + 顶 71 一阶）+ 能量 72 + 道具 73。"""
    return InPlayPokemon(
        stack=(inst(70, basic("妙蛙种子")), inst(71, stage1("妙蛙草", "妙蛙种子"))),
        attached_energy=(inst(72, energy()),),
        attached_tool=inst(73, tool_card()),
        damage=40,
        conditions=frozenset({SpecialCondition.POISONED}),
    )


def test_bounce_bench_returns_stack_and_discards_attachments():
    """备战目标：整叠宝可梦卡（进化链 2 张）回手牌；能量 + 道具进弃牌区。"""
    e = bounce_engine(bench=(stacked_mon(),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (71,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert p0.bench == ()
    assert [c.iid for c in p0.hand[-2:]] == [70, 71]  # 整叠回手（底→顶）
    assert [c.iid for c in p0.discard] == [72, 73, 60]  # 能量、道具、本体


def test_bounce_active_with_bench_promotes_then_continues_main():
    """战斗场目标：换上流程后继续当前主阶段（不推进回合、不抽牌）。"""
    e = bounce_engine(bench=(in_play(70, basic("小拉达")),))
    turn_before = e.state.turn
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (1,)))
    assert e.state.phase == "promote" and e.state.current_player == 0
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert e.state.turn == turn_before  # 未推进回合
    p0 = e.state.players[0]
    assert p0.active.current.iid == 70
    assert 1 in [c.iid for c in p0.hand]  # 被放回的战斗宝可梦在手牌
    assert not [ev for ev in e.events if ev.kind == "draw"]  # 主阶段内换上不抽牌
    # 换回后仍可正常行动（主阶段继续）
    assert e.legal_actions(0)


def test_bounce_active_without_bench_loses():
    """放回后场上无宝可梦：判负（附录 A 决议，🔲 待核；与 §8 胜利条件②同语义）。"""
    e = bounce_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (1,)))
    assert e.state.phase == "game_over"
    assert e.state.winner == 1
    over = next(ev for ev in e.events if ev.kind == "game_over")
    assert over.detail["reason"] == "no_pokemon"


# ── task 025：modify_damage 声明式伤害修正结算接入（不服输头带机制件）────
# 仿 task 015 _effective_hp 模式：道具 passive_static 的 modify_damage 声明由引擎
# 求值（condition 判定持有者），接入 _attack_damage 顺序 2（rules-manual §6：
# 基准 → 攻方修饰 → 弱点 ×2 → 抗性 -30）；白板与 DSL damage 两路径共用；
# 仅作用于「给对手的战斗宝可梦造成的伤害」（卡面口径），备战落点不加。

from battlefrontier.engine.state import AttackDef

BAND_DOC = parse_card_doc("""
card:
  name_group: 测试头带
effects:
  - trigger: passive_static
    condition: own_prizes_more_than_opponent
    actions:
      - {action: modify_damage, args: {amount: 30}}
""")

DSL_DMG_DOC = parse_card_doc("""
card:
  name_group: 测试招式伤害
effects:
  - trigger: on_attack
    attack: 打击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 20}}
""")

DSL_DMG_ANY_DOC = parse_card_doc("""
card:
  name_group: 测试选落点伤害
effects:
  - trigger: on_attack
    attack: 打击
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 20}}
""")


def band_engine(*, p0_prizes: int = 6, p1_prizes: int = 5,
                tool_on_bench: bool = False, attacker_doc=None,
                attacker_card: CardDef | None = None,
                defender_card: CardDef | None = None,
                p1_bench: tuple = ()) -> GameEngine:
    """p0 战斗场（或备战）挂测试头带（iid 80）的攻击局面。"""
    atk_card = attacker_card or basic("妙蛙种子")
    dfd_card = defender_card or basic("小火龙")
    tool = inst(80, tool_card("测试头带"))
    p0_active = in_play(1, atk_card, 1)
    p0_bench = ()
    if tool_on_bench:
        p0_bench = (in_play(70, basic("小拉达")).model_copy(update={"attached_tool": tool}),)
    else:
        p0_active = p0_active.model_copy(update={"attached_tool": tool})
    state = main_state(p1_bench=p1_bench)
    p0 = state.players[0].model_copy(update={
        "active": p0_active, "bench": p0_bench,
        "prizes": state.players[0].prizes[:p0_prizes],
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, dfd_card, 1),
        "prizes": state.players[1].prizes[:p1_prizes],
    })
    engine = engine_at(state.model_copy(update={"players": (p0, p1)}))
    engine.card_effects = {"测试头带": BAND_DOC}
    if attacker_doc is not None:
        engine.card_effects[atk_card.name] = attacker_doc
    return engine


def test_modify_damage_whiteboard_applies_when_condition_met():
    """白板攻击：自己奖赏多于对手 → +30（20→50）。"""
    e = band_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50


def test_modify_damage_whiteboard_off_when_condition_fails():
    """条件不满足（奖赏不比对手多）→ 原伤害 20。"""
    e = band_engine(p1_prizes=6)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20


def test_modify_damage_before_weakness():
    """修饰在弱点前结算（rules-manual §6 顺序 2→3）：(20+30)×2 = 100。"""
    atk = CardDef(card_id="stub-超打手", name="超打手", supertype="pokemon", hp=70,
                  stage=0, energy_type="超",
                  attacks=(AttackDef(name="打击", cost=("无",), damage=20),))
    dfd = CardDef(card_id="stub-弱超", name="弱超", supertype="pokemon", hp=200,
                  stage=0, weakness="超",
                  attacks=(AttackDef(name="打击", cost=("无",), damage=10),))
    e = band_engine(attacker_card=atk, defender_card=dfd)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 100


def test_modify_damage_dsl_damage_path():
    """DSL damage（on_attack 绑定招式）同样接入：20+30=50。"""
    atk = CardDef(card_id="stub-dsl打手", name="测试招式伤害", supertype="pokemon", hp=70,
                  stage=0, attacks=(AttackDef(name="打击", cost=("无",), damage=None),))
    e = band_engine(attacker_card=atk, attacker_doc=DSL_DMG_DOC)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50


def test_modify_damage_not_applied_to_bench_target():
    """落点为对手备战宝可梦时不加（卡面口径：给对手的战斗宝可梦造成的伤害）。"""
    atk = CardDef(card_id="stub-选落点", name="测试选落点伤害", supertype="pokemon", hp=70,
                  stage=0, attacks=(AttackDef(name="打击", cost=("无",), damage=None),))
    e = band_engine(attacker_card=atk, attacker_doc=DSL_DMG_ANY_DOC,
                    p1_bench=(in_play(90, basic("超梦")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (90,)))
    assert e.state.players[1].bench[0].damage == 20  # 无 +30
    assert e.state.players[1].active.damage == 0


def test_modify_damage_only_holder_tool_counts():
    """道具挂在备战宝可梦身上：战斗场攻击者无修正（按持有者求值，task 015 同口径）。"""
    e = band_engine(tool_on_bench=True)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
