"""单卡 DSL 测试（task 132 批次 1/3）：斗子——从 cards/ 真实文件装载，stub 引擎驱动全链路。

斗子（CSV10.6C-085，支援者）：选择自己牌库中的进化宝可梦和能量各1张，在给对手
看过之后加入手牌。并重洗牌库。
- 两段式 search_deck（各 up-to 1）：进化宝可梦 → 能量，两段独立 chooser 交互
  （choose_groups 为组间互斥「或」语义，跨组各取 1 不可达，不适用）。
- 「能量」不限基本：chooser energy = 能量卡超类型，特殊能量可检。
- reveal 按组各落一条事件（给对手看过，仅结构化事件流 D-WP3-4）；检索后必洗牌。
"""

from pathlib import Path

from helpers import basic, energy, inst, main_state, stage1

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

DOUZI_DOC = load_card_doc(CARDS_DIR / "斗子.yml")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def special_energy(name: str = "特殊能量", energy_type: str = "无") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy",
                   energy_type=energy_type, is_basic_energy=False)


def play_engine(deck) -> GameEngine:
    """main 阶段：p0 手牌含斗子（iid 60），牌库可定制。"""
    state = main_state(p0_extra_hand=(inst(60, supporter_card("斗子")),))
    p0 = state.players[0].model_copy(update={"deck": deck})
    e = GameEngine(RandomSource(0))
    e.state = state.model_copy(update={"players": (p0, state.players[1])})
    e.card_effects = {"斗子": DOUZI_DOC}
    return e


def douzi_deck() -> tuple:
    return (
        inst(100, basic("基甲")),
        inst(101, stage1("进甲", "基甲")),
        inst(102, stage1("进乙", "基乙")),
        inst(103, energy("基本能量", "草")),
        inst(104, special_energy("薄雾能量")),
        inst(105, supporter_card("干扰支援者")),
    )


def prim_results(e, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


def test_斗子_两段检索枚举():
    """段1 枚举 = 进化 up-to 1（基础/训练家/能量不进池）；段2 枚举 = 能量 up-to 1。"""
    e = play_engine(douzi_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.pool_iids == (101, 102)
    assert {a.choices for a in e.legal_actions(0)} == {(), (101,), (102,)}
    e.apply(0, Action(kind="choose", choices=(102,)))
    assert e.state.players[0].hand[-1].iid == 102  # 段1 已入手
    pc = e.state.pending_choice
    assert pc.pool_iids == (103, 104)
    assert {a.choices for a in e.legal_actions(0)} == {(), (103,), (104,)}


def test_斗子_双组各取1全流():
    """进化 ×1 + 能量 ×1 → 入手 + 两条 reveal（按组）+ 重洗，回主阶段。"""
    e = play_engine(douzi_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(102,)))
    e.apply(0, Action(kind="choose", choices=(104,)))
    p0 = e.state.players[0]
    assert {102, 104} <= {c.iid for c in p0.hand}
    assert sorted(c.iid for c in p0.deck) == [100, 101, 103, 105]
    reveals = [ev for ev in e.events if ev.kind == "reveal"]
    assert len(reveals) == 2
    assert reveals[0].detail["iids"] == [102]           # 进化宝可梦组
    assert set(reveals[1].detail["iids"]) == {51, 104}  # 能量组（手牌原有 51 + 所检 104）
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


def test_斗子_特殊能量可检():
    """「能量」不限基本：薄雾能量（is_basic_energy=False）入段2候选池。"""
    e = play_engine(douzi_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=()))
    e.apply(0, Action(kind="choose", choices=(104,)))
    p0 = e.state.players[0]
    assert 104 in [c.iid for c in p0.hand]
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 105]
    assert e.state.phase == "main" and e.state.current_player == 0


def test_斗子_缺能量组只取进化():
    """牌库无能量：段2 池空不挂起（尽力而为 no-op），重洗仍执行。"""
    deck = (inst(100, basic("基甲")), inst(101, stage1("进甲", "基甲")),
            inst(105, supporter_card("干扰支援者")))
    e = play_engine(deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(101,)))
    assert e.state.pending_choice is None  # 段2 能量池空，不挂起
    p0 = e.state.players[0]
    assert 101 in [c.iid for c in p0.hand]
    assert sorted(c.iid for c in p0.deck) == [100, 105]
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


def test_斗子_全空选仍重洗():
    """两段均选 0（检索 up-to 口径可放弃）→ no-op，「并重洗牌库」义务不免除。"""
    e = play_engine(douzi_deck())
    hand_before = tuple(c.iid for c in e.state.players[0].hand)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=()))
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert tuple(c.iid for c in p0.hand) == tuple(i for i in hand_before if i != 60)
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 104, 105]
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0
