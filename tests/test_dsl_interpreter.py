"""task 007：解释器骨架 + play_trainer 引擎接入验收测试（PRD §5.4 / §6.6）。"""

import pytest

from battlefrontier.dsl import DslError, parse_card_doc
from battlefrontier.engine.actions import Action
from tests.helpers import basic, energy, engine_at, inst, main_state

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
