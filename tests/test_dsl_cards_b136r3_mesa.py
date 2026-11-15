"""单卡 DSL 测试（task 136 扩批第三轮）：桌台市——从 cards/ 真实文件装载。

桌台市（CSV1C-126 档，G 标 2 印刷，竞技场）：
「双方玩家，每次在自己的回合有1次机会，可抛掷1次硬币。如果为正面，则选择
自己牌库中的1张宝可梦，在给对手看过之后，加入手牌。并重洗牌库。」——
stadium_grant（深钵镇/城镇百货先例）+ coin_flip + 正面分支三节点
（search_deck pokemon / reveal / shuffle_deck）同挂 if_flip_heads 节点门控
（粉碎之锤先例）：反面 = 空结算（不检索、不洗牌），对齐原文分支结构。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef

CARDS = Path(__file__).parent.parent / "cards"
DOC = load_card_doc(CARDS / "桌台市.yml")

HEADS = next(s for s in range(30) if RandomSource(s).flip_coin())
TAILS = next(s for s in range(30) if not RandomSource(s).flip_coin())


def stadium(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="竞技场")


def mesa_engine(deck: tuple, seed: int) -> object:
    """main 阶段、场上竞技场为桌台市（p0 放置）、p0 牌库为指定构成、钉死掷币种子。"""
    state = main_state()
    st = inst(70, stadium("桌台市"))
    state = state.model_copy(update={"stadium": st, "stadium_owner": 0})
    p0 = state.players[0].model_copy(update={"deck": deck})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"桌台市": DOC}
    e.rng = RandomSource(seed)
    return e


def mesa_deck() -> tuple:
    return (
        inst(100, basic("小拉达")),
        inst(101, energy()),                    # 能量（非宝可梦）
        inst(102, basic("波波")),
    )


def test_桌台市_挂载() -> None:
    """G 标 2 印刷同文本等价类全收（闸 1 --db 已核归一化 text_raw 一致）。"""
    assert DOC.card.card_ids == ("CSV1C-126", "CSVE1C-168")


def test_桌台市_正面检索宝可梦入手并洗牌() -> None:
    """正面：use_stadium → 掷币 → 检索 1 只宝可梦入手 → 展示 + 洗牌；限 1 次。"""
    e = mesa_engine(mesa_deck(), HEADS)
    e.apply(0, Action(kind="use_stadium"))
    assert e.state.phase == "choice"
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert sorted(a.choices for a in choices) == [(), (100,), (102,)]
    e.apply(0, next(a for a in choices if a.choices == (100,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert any(c.iid == 100 for c in p0.hand)
    assert len(p0.deck) == 2  # 取走 1 张且已洗牌
    shuffles = [ev for ev in e.events
                if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
    assert any(ev.kind == "reveal" for ev in e.events)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_stadium"]


def test_桌台市_反面空结算() -> None:
    """反面：不检索、不洗牌、无选择交互——直接回到 main 阶段。"""
    e = mesa_engine(mesa_deck(), TAILS)
    deck_before = e.state.players[0].deck
    hand_before = e.state.players[0].hand
    e.apply(0, Action(kind="use_stadium"))
    assert e.state.phase == "main"
    p0 = e.state.players[0]
    assert p0.hand == hand_before
    assert p0.deck == deck_before
    # 反面：检索/洗牌节点各落一条 skipped 事件（condition 门控），无实际执行
    shuffles = [ev for ev in e.events
                if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert all(ev.detail["result"].get("skipped") for ev in shuffles)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_stadium"]
