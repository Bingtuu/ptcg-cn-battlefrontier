"""task 026 WP2：trigger_on_event 引擎分发（own_play_from_hand_to_bench，摔角鹰人机制）。

分发点 = _do_place_bench 主阶段入口：仅「自己的回合从手牌使出放于备战区」触发
（setup 阶段不触发；DSL search_deck destination=bench 不经 place_bench 行动，天然不触发）。
同卡多个同事件效果 = DslError（不猜，需要时再扩展顺序分发）。
「可使用」的放弃选项不建模（D-WP2-3）：满足即自动发动。
"""

import pytest
from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef

HAWLUCHA_DOC = parse_card_doc("""
card:
  name_group: 摔角鹰人
effects:
  - trigger: trigger_on_event
    event: own_play_from_hand_to_bench
    actions:
      - {action: place_damage_counters, selector: opponent_bench, choose: 2, args: {counters: 1}}
""")

DOUBLE_TRIGGER_DOC = parse_card_doc("""
card:
  name_group: 摔角鹰人
effects:
  - trigger: trigger_on_event
    event: own_play_from_hand_to_bench
    actions:
      - {action: place_damage_counters, selector: opponent_bench, choose: 1, args: {counters: 1}}
  - trigger: trigger_on_event
    event: own_play_from_hand_to_bench
    actions:
      - {action: draw, count: 1}
""")

COND_TRIGGER_DOC = parse_card_doc("""
card:
  name_group: 摔角鹰人
effects:
  - trigger: trigger_on_event
    event: own_play_from_hand_to_bench
    condition: first_own_turn
    actions:
      - {action: draw, count: 1}
""")

NEST_BALL_DOC = parse_card_doc("""
card:
  name_group: 巢穴球
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_pokemon], choose: 1, destination: bench}
      - {action: shuffle_deck}
""")


def hawlucha(name: str = "摔角鹰人", hp: int = 70) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon", hp=hp, stage=0)


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def trigger_engine(*, doc=HAWLUCHA_DOC, p1_bench=(), turn: int | None = None):
    """main 阶段：p0 手牌含摔角鹰人（iid 60），文档已挂载。"""
    state = main_state(p0_extra_hand=(inst(60, hawlucha()),), p1_bench=p1_bench)
    if turn is not None:
        state = state.model_copy(update={"turn": turn})
    e = engine_at(state)
    e.card_effects = {"摔角鹰人": doc}
    return e


def test_place_bench_main_phase_triggers():
    """主阶段从手牌放备战区 → 触发：挂起选对手备战 2 只各 +10；完成后回主阶段，
    特性卡本体留在场上（不弃置，completion="ability"）。"""
    e = trigger_engine(p1_bench=(in_play(80, basic("喵喵")), in_play(81, basic("小拉达"))))
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "choice"
    trig = next(ev for ev in e.events if ev.kind == "trigger_on_event")
    assert trig.detail["event"] == "own_play_from_hand_to_bench"
    assert trig.detail["iid"] == 60 and trig.detail["name"] == "摔角鹰人"
    place = next(ev for ev in e.events if ev.kind == "place_bench")
    assert e.events.index(place) < e.events.index(trig)  # 放置在前，触发在后
    e.apply(0, Action(kind="choose", choices=(80, 81)))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert [b.damage for b in e.state.players[1].bench] == [10, 10]
    assert e.state.players[0].bench[-1].current.iid == 60  # 本体在备战区
    assert 60 not in [c.iid for c in e.state.players[0].discard]


def test_trigger_bench_pool_of_one_shrinks():
    """对手备战仅 1 只（< choose=2）：min_choose 收缩至池大小（D-WP2-3），选那 1 只。"""
    e = trigger_engine(p1_bench=(in_play(80, basic("喵喵")),))
    e.apply(0, Action(kind="place_bench", iid=60))
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert picks == [(80,)]
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 10
    assert e.state.phase == "main"


def test_trigger_opponent_bench_empty_noop():
    """对手备战空：池空 no-op 不挂起（D-WP2-3），特性仍发动（事件落），流程回主阶段。"""
    e = trigger_engine()
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert any(ev.kind == "trigger_on_event" for ev in e.events)
    assert e.state.players[1].active.damage == 0


def test_setup_place_bench_does_not_trigger():
    """setup 阶段放备战区不触发（分发门 = 进入时 phase=="main"）。"""
    state = main_state(p0_extra_hand=(inst(60, hawlucha()),),
                       p1_bench=(in_play(80, basic("喵喵")),))
    state = state.model_copy(update={"phase": "setup_bench"})
    e = engine_at(state)
    e.card_effects = {"摔角鹰人": HAWLUCHA_DOC}
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "setup_bench"  # 不挂起、不翻阶段
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
    assert e.state.players[1].bench[0].damage == 0


def test_search_deck_to_bench_does_not_trigger():
    """巢穴球（search_deck destination=bench）直放备战区：非「从手牌使出」，不触发。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("巢穴球")),),
                       p1_bench=(in_play(80, basic("喵喵")),))
    deck = (inst(100, hawlucha()),) + tuple(
        inst(101 + i, basic("妙蛙种子")) for i in range(9)
    )
    p0 = state.players[0].model_copy(update={"deck": deck})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"摔角鹰人": HAWLUCHA_DOC, "巢穴球": NEST_BALL_DOC}
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    e.apply(0, Action(kind="choose", choices=(100,)))  # 检索摔角鹰人直放备战区
    assert e.state.phase == "main"  # 不二次挂起（未触发）
    assert e.state.players[0].bench[-1].current.iid == 100  # 已放上备战区
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
    assert e.state.players[1].bench[0].damage == 0


def test_multiple_same_event_triggers_dsl_error():
    """一张卡多个同事件 trigger_on_event 效果 → DslError（不猜；需要时再扩展顺序分发）。"""
    e = trigger_engine(doc=DOUBLE_TRIGGER_DOC,
                       p1_bench=(in_play(80, basic("喵喵")),))
    with pytest.raises(DslError, match="trigger_on_event"):
        e.apply(0, Action(kind="place_bench", iid=60))


def test_trigger_condition_not_met_no_fire():
    """触发效果的 condition 不满足（first_own_turn，main_state turn=2）→ 不发动。"""
    e = trigger_engine(doc=COND_TRIGGER_DOC)
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "main"
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
    assert [c.iid for c in e.state.players[0].hand] == [50, 51]  # 放下 60，draw 未执行


def test_trigger_condition_met_fires():
    """condition 满足（turn=1 自己最初的回合）→ 发动（draw 1 入手）。"""
    e = trigger_engine(doc=COND_TRIGGER_DOC, turn=1)
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "main"
    assert any(ev.kind == "trigger_on_event" for ev in e.events)
    # 手牌：3（50/51/60）- 放下的 60 + 抽 1 = 3
    assert [c.iid for c in e.state.players[0].hand] == [50, 51, 100]
