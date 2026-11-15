"""单卡 DSL 测试（task 136 扩批第三轮）：城镇百货——从 cards/ 真实文件装载。

城镇百货（CSV5C-128 档，G 标 3 印刷，竞技场）：
「双方玩家，每次在自己的回合有1次机会，可选择自己牌库中的1张
「宝可梦道具」，在给对手看过之后，加入手牌。并重洗牌库。」——
stadium_grant（深钵镇先例）+ search_deck trainer_tool（「宝可梦道具」=
训练家宝可梦道具子类，非道具物品/能量/宝可梦均不进池）+ reveal own_hand
（task 132 斗子 D-WP3-4 口径）+ shuffle_deck。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef

CARDS = Path(__file__).parent.parent / "cards"
DOC = load_card_doc(CARDS / "城镇百货.yml")


def tool(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def plain_item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def stadium_engine(deck: tuple) -> object:
    """main 阶段、场上竞技场为城镇百货（p0 放置）、p0 牌库为指定构成。"""
    state = main_state()
    stadium = inst(70, CardDef(
        card_id="stub-城镇百货", name="城镇百货", supertype="trainer",
        trainer_subtype="竞技场",
    ))
    state = state.model_copy(update={"stadium": stadium, "stadium_owner": 0})
    p0 = state.players[0].model_copy(update={"deck": deck})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"城镇百货": DOC}
    return e


def bazaar_deck() -> tuple:
    return (
        inst(100, tool("勇气护符")),
        inst(101, plain_item("伤药")),          # 物品（非宝可梦道具）
        inst(102, basic("小拉达")),             # 宝可梦
        inst(103, energy()),                    # 能量
        inst(104, tool("气球")),
    )


def test_城镇百货_挂载() -> None:
    """G 标 3 印刷同文本等价类全收（闸 1 --db 已核归一化 text_raw 一致）。"""
    assert DOC.card.card_ids == ("CSV5C-128", "CSVM1aC-031", "CSVM1cC-027")


def test_城镇百货_全链路() -> None:
    """use_stadium → 检索「宝可梦道具」1 张入手 → 展示 + 洗牌；每回合限 1 次。"""
    e = stadium_engine(bazaar_deck())
    e.apply(0, Action(kind="use_stadium"))
    assert e.state.phase == "choice"
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    # up-to 口径（尖钉镇道馆先例）：可以不找
    assert sorted(a.choices for a in choices) == [(), (100,), (104,)]
    e.apply(0, next(a for a in choices if a.choices == (100,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert any(c.iid == 100 for c in p0.hand)
    assert len(p0.deck) == 4  # 取走 1 张且已洗牌
    shuffles = [ev for ev in e.events
                if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
    assert any(ev.kind == "reveal" for ev in e.events)
    # 「每次在自己的回合有1次机会」：本回合不可再次发动
    assert not [a for a in e.legal_actions(0) if a.kind == "use_stadium"]


def test_城镇百货_检索池仅宝可梦道具() -> None:
    """负例：物品（非道具）/宝可梦/能量不进检索池。"""
    e = stadium_engine(bazaar_deck())
    e.apply(0, Action(kind="use_stadium"))
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {100, 104}
