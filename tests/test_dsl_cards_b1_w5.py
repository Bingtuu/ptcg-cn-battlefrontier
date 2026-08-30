"""task 025 批 1 wave 5：单卡 DSL 测试分片（从 cards/ 真实文件装载，stub 引擎驱动全链路）。

朋友手册：弃牌区 ≤2 张支援者回牌库 + 洗牌（recover_from_discard destination=deck up-to 语义）。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

PALPAD_DOC = load_card_doc(CARDS_DIR / "朋友手册.yml")


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品")


def supporter(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="支援者")


def palpad_engine(discard: tuple):
    """main 阶段、p0 手牌含朋友手册（iid 60）、弃牌区为指定构成的引擎。"""
    state = main_state(p0_extra_hand=(inst(60, item("朋友手册")),))
    p0 = state.players[0].model_copy(update={"discard": discard})
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"朋友手册": PALPAD_DOC}
    return engine


def mixed_discard() -> tuple:
    """支援者 ×2（合法）+ 物品 + 能量（均应被过滤）。"""
    return (
        inst(100, supporter("博士的研究")),
        inst(101, supporter("奇树")),
        inst(102, item("高级球")),
        inst(103, energy()),
    )


def test_朋友手册_full_flow() -> None:
    """全链路：挂起回收 → 选 2 张支援者 → 回牌库并洗牌 → 本体收尾进弃牌区。"""
    deck_before = 10
    e = palpad_engine(mixed_discard())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    # 池 = {100, 101}（物品/能量被过滤），最多 2 张（up-to 语义含空集）
    assert sorted(a.choices for a in choices) == [(), (100,), (100, 101), (101,)]
    e.apply(0, next(a for a in choices if a.choices == (100, 101)))
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert len(p0.deck) == deck_before + 2  # 2 张支援者已回牌库（洗牌后位置不定）
    assert {c.iid for c in p0.deck} >= {100, 101}
    assert [c.iid for c in p0.discard] == [102, 103, 60]  # 本体收尾进弃牌区
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
    assert any(ev.kind == "effect_observe" and ev.detail["anchor"] == "key_search" for ev in e.events)


def test_朋友手册_up_to_semantics_choose_one() -> None:
    """「最多2张」：只选 1 张合法（回牌库 up-to 语义，min_choose=0）。"""
    e = palpad_engine(mixed_discard())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (101,)))
    p0 = e.state.players[0]
    assert len(p0.deck) == 11
    assert 101 in {c.iid for c in p0.deck}
    assert [c.iid for c in p0.discard] == [100, 102, 103, 60]


def test_朋友手册_choose_none_still_shuffles() -> None:
    """选空集（不回收）：效果空结算，但洗牌仍执行。"""
    e = palpad_engine(mixed_discard())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == ()))
    p0 = e.state.players[0]
    assert len(p0.deck) == 10
    assert [c.iid for c in p0.discard] == [100, 101, 102, 103, 60]
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1


def test_朋友手册_no_supporter_noop() -> None:
    """弃牌区无支援者：池空不挂起（尽力而为），效果空结算但仍洗牌。"""
    e = palpad_engine((inst(100, item("高级球")), inst(101, basic("妙蛙种子"))))
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "main" and e.state.pending_choice is None
    p0 = e.state.players[0]
    assert len(p0.deck) == 10
    assert [c.iid for c in p0.discard] == [100, 101, 60]
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
