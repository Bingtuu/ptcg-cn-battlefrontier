"""单卡 DSL 测试分片：task 025 批 1 wave 2（w2）。

从 cards/ 真实文件装载（load_card_doc），stub 引擎驱动全链路。

═══ 本 wave 卡单 ═══
能量输送：检索牌库 1 张基本能量入手 + 洗牌。
规则出处：检索为 up-to 语义（牌库非公开区域，可以不找）；检索后必须洗牌（官方规则·检索）。

其余 5 卡（小刚的发掘 / 尖钉镇道馆 / 暗码迷的解读 / 赫普的包包 / 宝可装置3.0）
因缺词/缺机制标 blocked，未写 DSL，详见批 1 wave 2 交付报告。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

ENERGY_SEARCH_DOC = load_card_doc(CARDS_DIR / "能量输送.yml")


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品")


def special_energy(name: str = "特殊能量") -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="energy",
        energy_type="无", is_basic_energy=False,
    )


def energy_search_engine(deck: tuple):
    """main 阶段、p0 手牌含能量输送（iid 60）、牌库为指定构成的引擎。"""
    state = main_state(p0_extra_hand=(inst(60, item("能量输送")),))
    p0 = state.players[0].model_copy(update={"deck": deck})
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"能量输送": ENERGY_SEARCH_DOC}
    return engine


def mixed_deck() -> tuple:
    """4 张牌：基本能量 ×2（合法）+ 特殊能量 + 宝可梦（均应被过滤）。"""
    return (
        inst(100, energy("基本火能量", energy_type="火")),
        inst(101, energy("基本超能量", energy_type="超")),
        inst(102, special_energy()),
        inst(103, basic("妙蛙种子")),
    )


def test_能量输送_full_flow() -> None:
    """全链路：挂起检索 → 选 1 张基本能量 → 入手 → 洗牌 → 本体进弃牌区。"""
    e = energy_search_engine(mixed_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    # 池 = {100, 101}，最多 1 张（up-to 语义含空集）
    assert sorted(a.choices for a in choices) == [(), (100,), (101,)]
    e.apply(0, next(a for a in choices if a.choices == (101,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert 101 in [c.iid for c in p0.hand]  # 入手
    assert [c.iid for c in p0.discard] == [60]  # 本体收尾进弃牌区
    assert len(p0.deck) == 3  # 取走 1 张且已洗牌
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1


def test_能量输送_filtering() -> None:
    """负例：特殊能量与宝可梦均不进检索池。"""
    e = energy_search_engine(mixed_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {100, 101}  # 特殊能量(is_basic_energy=False)/宝可梦被过滤


def test_能量输送_decline_search_still_shuffles() -> None:
    """选空集（不找）：效果空结算，但洗牌仍执行（检索后必洗）。"""
    e = energy_search_engine(mixed_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == ()))
    p0 = e.state.players[0]
    assert len(p0.hand) == 2  # 打出本体后剩 2 张手牌，未新增
    assert len(p0.deck) == 4
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1


def test_能量输送_no_basic_energy_noop() -> None:
    """牌库无基本能量：池空不挂起（尽力而为），效果空结算但仍洗牌。"""
    deck = (inst(100, special_energy()), inst(101, basic("妙蛙种子")))
    e = energy_search_engine(deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert len(e.state.players[0].hand) == 2
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
