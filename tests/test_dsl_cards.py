"""单卡 DSL 测试：从 cards/ 真实文件装载（load_card_doc），stub 引擎驱动全链路。

按批次分节注释（task 024 起）。

═══ 批次：task 024 harness 自验卡 ═══
友好宝芬：检索牌库 ≤2 张 HP≤70【基础】宝可梦直放备战区 + 洗牌。
规则出处：检索为 up-to 语义（可以不找）；检索后必须洗牌（官方规则·检索）。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, inst, main_state, stage1

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

POFFIN_DOC = load_card_doc(CARDS_DIR / "友好宝芬.yml")


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品")


def poffin_engine(deck: tuple, **kwargs):
    """main 阶段、p0 手牌含友好宝芬（iid 60）、牌库为指定构成的引擎。"""
    state = main_state(p0_extra_hand=(inst(60, item("友好宝芬")),), **kwargs)
    p0 = state.players[0].model_copy(update={"deck": deck})
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"友好宝芬": POFFIN_DOC}
    return engine


def mixed_deck() -> tuple:
    """5 张牌：HP≤70 基础 ×2（合法）+ HP>70 基础 + 1 阶 + 能量（均应被过滤）。"""
    return (
        inst(100, basic("妙蛙种子", hp=70)),
        inst(101, basic("小拉达", hp=30)),
        inst(102, basic("卡比兽", hp=150)),
        inst(103, stage1("妙蛙草", "妙蛙种子", hp=90)),
        inst(104, energy()),
    )


def test_友好宝芬_full_flow() -> None:
    """全链路：挂起检索 → 选 2 只 HP≤70 基础 → 直放备战区 → 洗牌 → 本体进弃牌区。"""
    e = poffin_engine(mixed_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    # 池 = {100, 101}，最多 2 张（up-to 语义含空集）
    assert sorted(a.choices for a in choices) == [(), (100,), (100, 101), (101,)]
    e.apply(0, next(a for a in choices if a.choices == (100, 101)))
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert [m.current.iid for m in p0.bench] == [100, 101]
    assert {100, 101} <= p0.entered_play_this_turn  # 当回合登场 → 不可进化联动
    assert [c.iid for c in p0.discard] == [60]  # 本体收尾进弃牌区
    assert len(p0.deck) == 3  # 取走 2 张且已洗牌
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1


def test_友好宝芬_hp_and_stage_filtering() -> None:
    """负例：HP>70 的基础、1 阶进化、能量均不进检索池。"""
    e = poffin_engine(mixed_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {100, 101}  # 卡比兽(HP150)/妙蛙草(stage1)/能量被过滤


def test_友好宝芬_decline_search_still_shuffles() -> None:
    """选空集（不找）：效果空结算，但洗牌仍执行（检索后必洗）。"""
    e = poffin_engine(mixed_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == ()))
    p0 = e.state.players[0]
    assert len(p0.bench) == 0 and len(p0.deck) == 5
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1


def test_友好宝芬_no_eligible_target_noop() -> None:
    """牌库无 HP≤70 基础：池空不挂起（尽力而为），效果空结算但仍洗牌。"""
    deck = (inst(100, basic("卡比兽", hp=150)), inst(101, energy()))
    e = poffin_engine(deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert len(e.state.players[0].bench) == 0
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
