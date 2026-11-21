"""单卡 DSL 测试（task 152b）：酿光市——从 cards/ 真实文件装载。

酿光市（CSV10C-217 档，J 标 2 印刷，竞技场）：
「双方玩家每次在自己的回合有1次机会，可以选择自己弃牌区中最多2张
「基本【雷】能量」，在给对手看过之后加入手牌。」——
stadium_grant（深钵镇/城镇百货先例，引擎 stadium_used_this_turn 强制每方
每回合 1 次，DSL 不重复声明）+ recover_from_discard own_discard
filters=[basic_energy, energy_雷] choose=2 destination=hand up_to=true
（能量回收-10.6 先例：弃牌区无匹配 → 可行性门不枚举 use_stadium，
chooser.py:608-612；up_to 池含空选 ()，选 0 不卡）+ reveal own_hand
（filters 与移动目标一致，task 132 D-WP3-4 口径：仅落结构化事件流）。
"""

from pathlib import Path

from helpers import energy, engine_at, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef

CARDS = Path(__file__).parent.parent / "cards"
DOC = load_card_doc(CARDS / "酿光市.yml")


def light(name: str = "基本【雷】能量") -> CardDef:
    return energy(name, "雷")


def special_light(name: str = "特殊【雷】能量") -> CardDef:
    """特殊能量 stub：雷属性但非基本能量（is_basic_energy=False）。"""
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy",
                   energy_type="雷", is_basic_energy=False)


def light_engine(
    p0_discard: tuple = (), p1_discard: tuple = (),
) -> object:
    """main 阶段、场上竞技场为酿光市（p0 放置）、双方弃牌区为指定构成。"""
    state = main_state()
    stadium = inst(70, CardDef(
        card_id="stub-酿光市", name="酿光市", supertype="trainer",
        trainer_subtype="竞技场",
    ))
    state = state.model_copy(update={"stadium": stadium, "stadium_owner": 0})
    p0 = state.players[0].model_copy(update={"discard": p0_discard})
    p1 = state.players[1].model_copy(update={"discard": p1_discard})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"酿光市": DOC}
    return e


def choose_actions(e, player: int = 0) -> list:
    return [a for a in e.legal_actions(player) if a.kind == "choose"]


def test_酿光市_挂载() -> None:
    """J 标 2 印刷同文本等价类全收（闸 1 --db 已核归一化 text_raw 一致 + 赛制合法）。"""
    assert DOC.card.card_ids == ("CSV10C-217", "CSV10C-286")


def test_酿光市_两张基本雷回手() -> None:
    """use_stadium → up-to-2 选 2 张基本【雷】能量入手 → reveal 落流；本回合不可再发动。"""
    e = light_engine(p0_discard=(
        inst(60, light()), inst(61, light()), inst(62, energy("基本【草】能量", "草")),
    ))
    e.apply(0, Action(kind="use_stadium"))
    assert e.state.phase == "choice"
    choices = choose_actions(e)
    # up_to：池含空选；非【雷】基本能量（62）不进池
    assert sorted(a.choices for a in choices) == [(), (60,), (60, 61), (61,)]
    e.apply(0, next(a for a in choices if a.choices == (60, 61)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    hand_iids = {c.iid for c in p0.hand}
    assert {60, 61} <= hand_iids
    assert {c.iid for c in p0.discard} == {62}
    reveals = [ev for ev in e.events if ev.kind == "reveal"]
    assert len(reveals) == 1
    assert sorted(reveals[0].detail["iids"]) == [60, 61]
    # 「每次在自己的回合有1次机会」：本回合不可再次发动
    assert not [a for a in e.legal_actions(0) if a.kind == "use_stadium"]


def test_酿光市_一张时up_to取一() -> None:
    """弃牌区仅 1 张匹配：池 = {空选, 该张}，取 1 张入手的全链路。"""
    e = light_engine(p0_discard=(inst(60, light()),))
    e.apply(0, Action(kind="use_stadium"))
    choices = choose_actions(e)
    assert sorted(a.choices for a in choices) == [(), (60,)]
    e.apply(0, next(a for a in choices if a.choices == (60,)))
    assert e.state.phase == "main"
    assert any(c.iid == 60 for c in e.state.players[0].hand)
    assert not e.state.players[0].discard


def test_酿光市_空选不卡() -> None:
    """up_to 空选 ()：不回收、效果链正常收尾回 main，reveal 空池落流不报错。"""
    e = light_engine(p0_discard=(inst(60, light()),))
    e.apply(0, Action(kind="use_stadium"))
    e.apply(0, next(a for a in choose_actions(e) if a.choices == ()))
    assert e.state.phase == "main"
    assert {c.iid for c in e.state.players[0].discard} == {60}
    reveals = [ev for ev in e.events if ev.kind == "reveal"]
    assert len(reveals) == 1 and reveals[0].detail["iids"] == []


def test_酿光市_零张时行动不可枚举() -> None:
    """弃牌区无匹配（0 张 / 仅非【雷】）：可行性门关闭，use_stadium 不枚举（无效果不可使用）。"""
    e = light_engine()
    assert not [a for a in e.legal_actions(0) if a.kind == "use_stadium"]
    e2 = light_engine(p0_discard=(inst(60, energy("基本【草】能量", "草")),))
    assert not [a for a in e2.legal_actions(0) if a.kind == "use_stadium"]


def test_酿光市_候选池仅基本雷能量() -> None:
    """负例：基本【草】能量 / 特殊【雷】能量（is_basic=False）均不进候选池。"""
    e = light_engine(p0_discard=(
        inst(60, light()),
        inst(61, energy("基本【草】能量", "草")),
        inst(62, special_light()),
    ))
    e.apply(0, Action(kind="use_stadium"))
    pooled = {iid for a in choose_actions(e) for iid in a.choices}
    assert pooled == {60}


def test_酿光市_双方各自回合各一次() -> None:
    """stadium_used_this_turn 为每方独立回合标记：p0 用过后 p1 回合仍可用 1 次。"""
    e = light_engine(
        p0_discard=(inst(60, light()),),
        p1_discard=(inst(80, light()),),
    )
    e.apply(0, Action(kind="use_stadium"))
    e.apply(0, next(a for a in choose_actions(e) if a.choices == (60,)))
    assert any(c.iid == 60 for c in e.state.players[0].hand)
    e.apply(0, Action(kind="end_turn"))  # → p1 回合（turn 3）
    assert e.state.current_player == 1
    stadium_acts = [a for a in e.legal_actions(1) if a.kind == "use_stadium"]
    assert len(stadium_acts) == 1
    e.apply(1, Action(kind="use_stadium"))
    choices = choose_actions(e, player=1)
    assert sorted(a.choices for a in choices) == [(), (80,)]
    e.apply(1, next(a for a in choices if a.choices == (80,)))
    assert any(c.iid == 80 for c in e.state.players[1].hand)
    # p1 本回合同样限 1 次
    assert not [a for a in e.legal_actions(1) if a.kind == "use_stadium"]
