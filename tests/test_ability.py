"""task 011：特性框架（use_ability 枚举 / 限次 / 可行性门）+ 精神拥抱 / 再起动 e2e。

规则出处：rules-manual 特性节——特性在自己回合按文本次数发动；
「精神拥抱」（沙奈朵ex）：弃牌区基本【超】能量附着于自己【超】宝可梦 + 2 个
伤害指示物，会被昏厥的宝可梦不可选（落在目标过滤器 would_survive_20）；
「再起动」（梦幻ex）：每回合 1 次，抽牌至手牌 3 张（超出空结算）。
"""

import pytest
from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import load_card_dir, parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action, IllegalActionError
from battlefrontier.engine.state import CardDef, InPlayPokemon

GARDEVOIR_DOC = parse_card_doc("""
card:
  name_group: 沙奈朵ex
effects:
  - trigger: ability_manual
    limit: unlimited
    actions:
      - {action: attach_energy, selector: own_discard, filters: [basic_energy, energy_超], choose: 1, destination: attach, args: {target_filters: [pokemon_超, would_survive_20], damage_counters: 2}}
""")

MEW_DOC = parse_card_doc("""
card:
  name_group: 梦幻ex
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: draw, args: {until_hand: 3}}
""")

SHARED_DOC = parse_card_doc("""
card:
  name_group: 测试共享特性
effects:
  - trigger: ability_manual
    limit: once_per_turn_shared
    actions:
      - {action: draw, count: 1}
""")

BAD_GATE_DOC = parse_card_doc("""
card:
  name_group: 坏特性
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: place_damage_counters, selector: self, count: 2}
""")


def gardevoir(hp: int = 310) -> CardDef:
    return CardDef(card_id="stub-沙奈朵ex", name="沙奈朵ex", supertype="pokemon",
                   hp=hp, stage=2, evolves_from="奇鲁莉安", energy_type="超", rule_box="ex")


def mew() -> CardDef:
    return CardDef(card_id="stub-梦幻ex", name="梦幻ex", supertype="pokemon",
                   hp=190, stage=0, energy_type="超", rule_box="ex")


def psy_energy() -> CardDef:
    return CardDef(card_id="stub-基本超能量", name="基本超能量", supertype="energy",
                   energy_type="超", is_basic_energy=True)


def state_p0(**updates):
    """main 局面，按参数覆盖 p0 的区域。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={k: v for k, v in updates.items() if v is not None})
    return state.model_copy(update={"players": (p0, state.players[1])})


def mew_engine(**updates):
    e = engine_at(state_p0(active=in_play(10, mew()), **updates))
    e.card_effects = {"梦幻ex": MEW_DOC}
    return e


def gardevoir_engine(discard, active_damage: int = 0, bench=(), hp: int = 310):
    active = InPlayPokemon(stack=(inst(10, gardevoir(hp)),), damage=active_damage)
    e = engine_at(state_p0(active=active, bench=bench, discard=discard))
    e.card_effects = {"沙奈朵ex": GARDEVOIR_DOC}
    return e


def use_abilities(e, player=0):
    return [a for a in e.legal_actions(player) if a.kind == "use_ability"]


# ── 枚举与非法行动 ───────────────────────────────────────────────────────

def test_use_ability_enumerated_only_with_doc() -> None:
    e = mew_engine()
    assert use_abilities(e) == [Action(kind="use_ability", iid=10)]
    assert use_abilities(e, player=1) == []  # p1 无文档不枚举
    with pytest.raises(IllegalActionError):
        e.apply(1, Action(kind="use_ability", iid=2))


def test_use_ability_without_doc_illegal() -> None:
    e = engine_at(main_state())
    with pytest.raises(IllegalActionError):
        e.apply(0, Action(kind="use_ability", iid=1))


# ── 限次强制 ─────────────────────────────────────────────────────────────

def test_once_per_turn_and_recover_next_turn() -> None:
    e = mew_engine()
    e.apply(0, Action(kind="use_ability", iid=10))
    assert use_abilities(e) == []  # 本回合已用
    e.apply(0, Action(kind="end_turn"))
    e.apply(1, Action(kind="end_turn"))  # p1 空过
    assert e.state.turn == 3 and e.state.current_player == 0
    assert use_abilities(e) == [Action(kind="use_ability", iid=10)]  # 下回合恢复


def test_once_per_turn_shared_by_name() -> None:
    """同名共享限次：一只用后，同名另一只本回合也不可用（化危为吉式）。"""
    mon = CardDef(card_id="stub-测试共享特性", name="测试共享特性", supertype="pokemon", hp=100)
    state = state_p0(active=in_play(10, mon), bench=(in_play(11, mon),))
    e = engine_at(state)
    e.card_effects = {"测试共享特性": SHARED_DOC}
    assert sorted(a.iid for a in use_abilities(e)) == [10, 11]
    e.apply(0, Action(kind="use_ability", iid=10))
    assert use_abilities(e) == []  # 同名共享：11 也不可用


def test_unlimited_not_blocked_by_use() -> None:
    """unlimited：用后不锁（精神拥抱任意次）；枚举只受可行性门限制。"""
    discard = (inst(80, psy_energy()), inst(82, psy_energy()))
    e = gardevoir_engine(discard)
    e.apply(0, Action(kind="use_ability", iid=10))
    for a in [x for x in e.legal_actions(0) if x.kind == "choose"]:
        e.apply(0, a) if a.choices == (80,) else None
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (10,)))
    assert use_abilities(e) == [Action(kind="use_ability", iid=10)]  # 弃牌区还有一张 → 仍可用


def test_visible_state_marks_abilities_used() -> None:
    e = mew_engine()
    e.apply(0, Action(kind="use_ability", iid=10))
    vis = e.state.visible_state(0)
    assert vis.own.abilities_used_this_turn == frozenset({10})


# ── 梦幻ex「再起动」e2e ──────────────────────────────────────────────────

def test_restart_draws_until_hand_three() -> None:
    e = mew_engine()  # 默认手牌 2 张（50/51）
    e.apply(0, Action(kind="use_ability", iid=10))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51, 100]  # 补 1 张至 3
    prims = [ev for ev in e.events if ev.kind == "effect_primitive"]
    assert prims[0].detail["action"] == "draw" and prims[0].detail["result"]["drawn"] == 1
    start = next(ev for ev in e.events if ev.kind == "effect_start")
    assert start.detail["trigger"] == "ability_manual" and start.detail["limit"] == "once_per_turn"
    assert any(ev.kind == "use_ability" for ev in e.events)


def test_restart_full_hand_noop_but_legal() -> None:
    """手牌已 ≥3：发动合法、空结算（规则不禁止无收益发动），仍占用限次。"""
    e = mew_engine(hand=(inst(50, basic("小火龙")), inst(51, energy()), inst(52, energy())))
    e.apply(0, Action(kind="use_ability", iid=10))
    assert [c.iid for c in e.state.players[0].hand] == [50, 51, 52]
    assert use_abilities(e) == []


# ── 沙奈朵ex「精神拥抱」e2e（两段式选择）────────────────────────────────

def test_psy_embrace_full_flow() -> None:
    discard = (inst(80, psy_energy()), inst(81, basic("小火龙")))  # 宝可梦被过滤
    e = gardevoir_engine(discard)
    e.apply(0, Action(kind="use_ability", iid=10))
    # 第一段：弃牌区选基本超能量（恰好 1 张）
    assert e.state.phase == "choice"
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert [a.choices for a in choices] == [(80,)]
    e.apply(0, choices[0])
    # 第二段：选自己场上超宝可梦（战斗场沙奈朵ex）
    assert e.state.phase == "choice"
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (10,)))
    # 结算：能量附着 + 2 个伤害指示物（20 伤害）；弃牌区剩 81
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert [c.iid for c in p0.active.attached_energy] == [80]
    assert p0.active.damage == 20
    assert [c.iid for c in p0.discard] == [81]


def test_psy_embrace_target_guard_excludes_lethal() -> None:
    """会被昏厥的目标（damage+20 ≥ hp）不入目标池；可放备战区合法目标。"""
    bench = (in_play(11, gardevoir(hp=70)),)  # 0 伤 70 血：合法
    e = gardevoir_engine((inst(80, psy_energy()),), active_damage=300, bench=bench)  # 300+20≥310
    e.apply(0, Action(kind="use_ability", iid=10))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose"))  # 选能量 80
    choices = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert choices == [(11,)]  # 战斗场被会昏厥守卫排除


def test_psy_embrace_gate() -> None:
    """可行性门：弃牌区无基本超能量 / 无合法目标 → 不枚举（不猜）。"""
    e = gardevoir_engine((inst(81, basic("小火龙")),))  # 无能量
    assert use_abilities(e) == []
    e = gardevoir_engine((inst(80, psy_energy()),), active_damage=300)  # 唯一目标会昏厥
    assert use_abilities(e) == []


def test_ability_gate_unknown_primitive_dsl_error() -> None:
    """可行性门未覆盖的原语形式：DslError（不猜），编写期即暴露。"""
    mon = CardDef(card_id="stub-坏特性", name="坏特性", supertype="pokemon", hp=100)
    e = engine_at(state_p0(active=in_play(10, mon)))
    e.card_effects = {"坏特性": BAD_GATE_DOC}
    with pytest.raises(DslError, match="可行性门"):
        e.legal_actions(0)


# ── 定义库与对局级确定性 ────────────────────────────────────────────────

def test_card_library_covers_ability_cards() -> None:
    docs = load_card_dir("cards")
    assert {"博士的研究", "高级球", "巢穴球", "夜间担架", "沙奈朵ex", "梦幻ex"} <= set(docs)
    g = docs["沙奈朵ex"].effects[0]
    assert g.trigger == "ability_manual" and g.limit == "unlimited"
    assert g.actions[0].action == "attach_energy" and g.actions[0].args["damage_counters"] == 2
    m = docs["梦幻ex"].effects[0]
    assert m.limit == "once_per_turn" and m.actions[0].args["until_hand"] == 3


def test_play_game_with_abilities_deterministic() -> None:
    """含特性卡的整局对局：同种子事件流 hash 一致（选择不消耗随机源）。"""
    from battlefrontier.runner.play import play_game

    deck = [mew()] * 4 + [basic("小火龙")] * 20 + [psy_energy()] * 20 + [energy()] * 16
    effects = load_card_dir("cards")
    r1 = play_game(deck, deck, seed=5, card_effects=effects)
    r2 = play_game(deck, deck, seed=5, card_effects=effects)
    assert r1.events_hash == r2.events_hash
