"""task 009：chooser 机制 + 检索/回收/选择式弃牌原语验收测试。

规则出处：rules-manual §3（牌库/奖赏非公开；检索时选择方可查看牌库选卡）/
§5（训练家卡用完放弃牌区）；检索牌库后必须洗牌（官方规则·检索）；
检索类效果为 up-to 语义（可以不找）；备战区满时巢穴球无合法落点不可使用。
"""

import hashlib
import json

import pytest
from helpers import basic, deck60, energy, engine_at, inst, main_state

from battlefrontier.dsl import DslError, parse_card_doc
from battlefrontier.engine.actions import Action, IllegalActionError
from battlefrontier.engine.state import CardDef, GameState, InPlayPokemon
from battlefrontier.runner.play import play_game

ULTRA_BALL_DOC = parse_card_doc("""
card:
  name_group: 高级球
effects:
  - trigger: on_play
    cost:
      - {action: discard, selector: own_hand, choose: 2}
    actions:
      - {action: search_deck, selector: own_deck, filters: [pokemon], choose: 1, destination: hand}
      - {action: shuffle_deck}
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

NIGHT_STRETCHER_DOC = parse_card_doc("""
card:
  name_group: 夜间担架
effects:
  - trigger: on_play
    actions:
      - {action: recover_from_discard, selector: own_discard, filters: [pokemon_or_basic_energy], choose: 1, destination: hand}
""")


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品")


def ultra_engine(hand_extras: tuple = (), **kwargs):
    """main 阶段、p0 手牌含高级球的引擎。默认手牌：小火龙(50)+能量(51)+高级球(60)。"""
    state = main_state(p0_extra_hand=(inst(60, item("高级球")),) + hand_extras, **kwargs)
    engine = engine_at(state)
    engine.card_effects = {"高级球": ULTRA_BALL_DOC}
    return engine


def kinds_of(e, player=0):
    return {a.kind for a in e.legal_actions(player)}


# ── 高级球 e2e（选择式成本 + 检索入手 + 洗牌）────────────────────────────

def test_ultra_ball_full_flow() -> None:
    e = ultra_engine()
    # 打出 → 挂起：手牌选弃 2（池 = 小火龙50 + 能量51）
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert [a.choices for a in choices] == [(50, 51)]  # 恰好 2 张，唯一组合
    e.apply(0, choices[0])
    p0 = e.state.players[0]
    assert sorted(c.iid for c in p0.discard) == [50, 51]
    # 再挂起：牌库检索 1 只宝可梦（10 妙蛙种子 iid 100~109 + 可以不找）
    assert e.state.phase == "choice"
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert () in [a.choices for a in choices]  # 检索可以不找（up-to 语义）
    pick = next(a for a in choices if a.choices == (100,))
    deck_before = len(e.state.players[0].deck)
    e.apply(0, pick)
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert [c.iid for c in p0.hand] == [100]  # 检索入手
    assert sorted(c.iid for c in p0.discard) == [50, 51, 60]  # 高级球本体收尾进弃牌区
    assert len(p0.deck) == deck_before - 1  # 取走 1 张且已洗牌
    kinds = [ev.kind for ev in e.events]
    assert kinds.count("effect_start") == 1 and kinds.count("effect_end") == 1


def test_ultra_ball_decline_search_still_shuffles() -> None:
    """检索选择空集（不找）：效果空结算但仍洗牌（检索后必洗）。"""
    e = ultra_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose"))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == ()))
    p0 = e.state.players[0]
    assert len(p0.hand) == 0 and len(p0.deck) == 10  # 没拿牌
    results = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(results) == 1  # 洗牌执行了


def test_ultra_ball_cost_not_payable_not_enumerated() -> None:
    """成本可行性门：除本体外手牌不足 2 张 → 不可打出。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={"hand": (inst(60, item("高级球")), inst(50, basic("小火龙")))})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"高级球": ULTRA_BALL_DOC}
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]


# ── 巢穴球 e2e（检索直放备战区）─────────────────────────────────────────

def nest_engine(**kwargs):
    state = main_state(p0_extra_hand=(inst(60, item("巢穴球")),), **kwargs)
    engine = engine_at(state)
    engine.card_effects = {"巢穴球": NEST_BALL_DOC}
    return engine


def test_nest_ball_to_bench() -> None:
    e = nest_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    # 池 = 牌库中的基础宝可梦（10 妙蛙种子）+ 不找
    assert () in [a.choices for a in choices]
    e.apply(0, next(a for a in choices if a.choices == (100,)))
    p0 = e.state.players[0]
    assert len(p0.bench) == 1 and p0.bench[0].current.iid == 100
    assert 100 in p0.entered_play_this_turn  # 当回合登场 → 不可进化（联动规则）
    assert e.state.phase == "main"


def test_nest_ball_full_bench_not_enumerated() -> None:
    """备战区满（5 只）：巢穴球无合法落点，不可使用。"""
    full_bench = tuple(InPlayPokemon(stack=(inst(700 + i, basic("小火龙")),)) for i in range(5))
    state = main_state(p0_extra_hand=(inst(60, item("巢穴球")),))
    p0 = state.players[0].model_copy(update={"bench": full_bench})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"巢穴球": NEST_BALL_DOC}
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]


# ── 夜间担架 e2e（弃牌区回收 + 过滤器）───────────────────────────────────

def test_night_stretcher_filter_and_recover() -> None:
    state = main_state(p0_extra_hand=(inst(60, item("夜间担架")),))
    discard = (
        inst(80, basic("拉鲁拉丝")),      # 宝可梦 ✅
        inst(81, energy()),                # 基本能量 ✅
        inst(82, item("高级球")),          # 训练家 ❌
    )
    p0 = state.players[0].model_copy(update={"discard": discard})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"夜间担架": NIGHT_STRETCHER_DOC}
    e.apply(0, Action(kind="play_trainer", iid=60))
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert sorted(a.choices for a in choices) == [(80,), (81,)]  # 训练家被过滤
    e.apply(0, next(a for a in choices if a.choices == (81,)))
    p0 = e.state.players[0]
    assert 81 in [c.iid for c in p0.hand]
    assert sorted(c.iid for c in p0.discard) == [60, 80, 82]  # 本体进弃牌区
    assert e.state.phase == "main"


def test_recover_no_target_noop() -> None:
    """弃牌区无合法目标：不挂起，效果 no-op（有事件），本体照常进弃牌区。"""
    e = ultra_engine()  # 复用 main 局面，弃牌区为空
    state = e.state
    p0 = state.players[0].model_copy(update={
        "hand": state.players[0].hand + (inst(61, item("夜间担架")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"夜间担架": NIGHT_STRETCHER_DOC}
    e.apply(0, Action(kind="play_trainer", iid=61))
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert 61 in [c.iid for c in e.state.players[0].discard]


# ── 选择合法性 / 隐藏信息 / 序列化 / 确定性 ──────────────────────────────

def test_illegal_choose_rejected() -> None:
    e = ultra_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    with pytest.raises(IllegalActionError):
        e.apply(0, Action(kind="choose", choices=(999,)))  # iid 不在池
    with pytest.raises(IllegalActionError):
        e.apply(0, Action(kind="choose", choices=(50,)))   # 数量不符 min=max=2


def test_search_pool_visible_only_to_chooser() -> None:
    """牌库检索挂起时：选择方可见检索池内容；对手视图不可见（rules-manual §3）。"""
    e = ultra_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose"))
    assert e.state.pending_choice is not None
    view_self = e.state.visible_state(0)
    assert view_self.pending_pool is not None
    assert {c.iid for c in view_self.pending_pool} == set(range(100, 110))
    view_opp = e.state.visible_state(1)
    assert view_opp.pending_pool is None


def test_pending_choice_serializable() -> None:
    e = ultra_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    restored = GameState.model_validate(e.state.model_dump(mode="json"))
    assert restored == e.state


def test_choice_deterministic_same_seed() -> None:
    """选择不消耗随机源：同种子 + 同选择序列 → 事件流逐条一致。"""
    def run():
        e = ultra_engine()
        e.apply(0, Action(kind="play_trainer", iid=60))
        e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose"))
        e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (100,)))
        return hashlib.sha256(json.dumps(
            [ev.model_dump(mode="json") for ev in e.events],
            ensure_ascii=False, sort_keys=True,
        ).encode()).hexdigest()
    assert run() == run()


def test_play_game_with_chooser_deterministic() -> None:
    """含高级球的整局对局：同种子事件流 hash 一致（play_game 级确定性回归）。"""
    deck = deck60()[:-4] + [item("高级球")] * 4
    effects = {"高级球": ULTRA_BALL_DOC}
    r1 = play_game(deck, deck, seed=7, card_effects=effects)
    r2 = play_game(deck, deck, seed=7, card_effects=effects)
    assert r1.events_hash == r2.events_hash


# ── 失败路径（不猜）─────────────────────────────────────────────────────

def test_unknown_filter_dsl_error() -> None:
    doc = parse_card_doc("""
card:
  name_group: 坏过滤器
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [not_a_filter], choose: 1, destination: hand}
""")
    state = main_state(p0_extra_hand=(inst(60, item("坏过滤器")),))
    e = engine_at(state)
    e.card_effects = {"坏过滤器": doc}
    with pytest.raises(DslError, match="未知"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_choose_on_unsupported_primitive_dsl_error() -> None:
    doc = parse_card_doc("""
card:
  name_group: 坏原语
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1, choose: 1}
""")
    state = main_state(p0_extra_hand=(inst(60, item("坏原语")),))
    e = engine_at(state)
    e.card_effects = {"坏原语": doc}
    with pytest.raises(DslError, match="choose"):
        e.apply(0, Action(kind="play_trainer", iid=60))
