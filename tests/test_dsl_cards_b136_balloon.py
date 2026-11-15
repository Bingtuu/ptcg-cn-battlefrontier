"""单卡 DSL 测试（task 136 扩批）：气球——从 cards/ 真实文件装载。

气球（CSV10.5C-082 / SVP-485，I 标，宝可梦道具）：
「身上放有这张卡牌的宝可梦【撤退】所需能量减少2个。」——passive_static
modify_retreat_cost value=2（持有者道具口径，无 scope；紧急滑板先例，
引擎 _effective_retreat_cost 读声明，撤退枚举与执行两触点接入）。

气球-2阶进化（CSV3C-119，G 标，同名异文本拆分档）：
「身上放有这张卡牌的【2阶进化】宝可梦【撤退】所需能量，全部消除。」——
condition holder_stage:2（task 027 新冲天能量先例）+ value=all
（驱劲能量 未来先例；归零旗标与数值减免无顺序依赖）。

D 标 4 印刷（CS1DC-189 等）为异标点文本且不在当前 standard 快照
（2026-09-16）合法集内，按挂载纪律不挂（闸 1 --db 已核）。
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.state import CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

BALLOON_DOC = load_card_doc(CARDS_DIR / "气球.yml")
BALLOON_STAGE2_DOC = load_card_doc(CARDS_DIR / "气球-2阶进化.yml")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def retreater(cost: int) -> CardDef:
    return basic("撤退兽", hp=70, retreat=cost)


def stage2_mon(cost: int) -> CardDef:
    return CardDef(card_id="stub-二阶兽", name="二阶兽", supertype="pokemon",
                   hp=130, stage=2, evolves_from="stub-一阶兽", retreat_cost=cost)


def stage1_mon(cost: int) -> CardDef:
    return CardDef(card_id="stub-一阶兽", name="一阶兽", supertype="pokemon",
                   hp=90, stage=1, evolves_from="stub-撤退兽", retreat_cost=cost)


def balloon_engine(holder: CardDef, *, energies: int,
                   doc, with_tool: bool = True) -> object:
    """main 阶段：p0 战斗场持有者（可调费/stage ± 气球道具）+ 备战 1 只。"""
    state = main_state(p0_active_energies=0)
    active = in_play(1, holder, energies)
    if with_tool:
        active = active.model_copy(update={
            "attached_tool": inst(90, tool_card("气球")),
        })
    p0 = state.players[0].model_copy(update={
        "active": active, "bench": (in_play(70, basic("占位兽")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"气球": doc}
    return e


# ── 挂载 ──────────────────────────────────────────────────────────────────────


def test_气球_挂载() -> None:
    """主档 = I 标「减少2个。」等价类（池内印刷 CSV10.5C-082 + 同文本 SVP-485）。"""
    assert BALLOON_DOC.card.card_ids == ("CSV10.5C-082", "SVP-485")


def test_气球2阶进化_挂载() -> None:
    """拆分档 = G 标异文本（【2阶进化】限定、全部消除），card_ids 不相交。"""
    assert BALLOON_STAGE2_DOC.card.card_ids == ("CSV3C-119",)


# ── 气球（减少2个）───────────────────────────────────────────────────────────


def test_气球_撤退费减2_两触点生效() -> None:
    """卡面撤退费 3 −2 = 1：1 能量可撤，实付 1（枚举层与执行层同读声明）。"""
    e = balloon_engine(retreater(3), energies=1, doc=BALLOON_DOC)
    assert e._effective_retreat_cost(e.state.players[0].active, 0) == 1
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats
    e.apply(0, retreats[0])
    assert len(e.state.players[0].discard) == 1
    assert any(ev.kind == "retreat" and ev.detail["paid"] == 1 for ev in e.events)


def test_气球_减免下限归零_0能可撤() -> None:
    """卡面撤退费 2 −2 = 0（clamp 下限 0）：0 能量可撤，实付 0。"""
    e = balloon_engine(retreater(2), energies=0, doc=BALLOON_DOC)
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats
    e.apply(0, retreats[0])
    assert e.state.players[0].discard == ()
    assert any(ev.kind == "retreat" and ev.detail["paid"] == 0 for ev in e.events)


def test_气球_无道具按卡面费() -> None:
    """对照组：无道具时卡面 3 费，1 能量不可撤退。"""
    e = balloon_engine(retreater(3), energies=1, doc=BALLOON_DOC, with_tool=False)
    assert not [a for a in e.legal_actions(0) if a.kind == "retreat"]


# ── 气球-2阶进化（持有者 2 阶全免）────────────────────────────────────────────


def test_气球2阶进化_持有者2阶全免() -> None:
    """【2阶进化】持有者：撤退费全部消除，0 能量可撤，实付 0。"""
    e = balloon_engine(stage2_mon(3), energies=0, doc=BALLOON_STAGE2_DOC)
    assert e._effective_retreat_cost(e.state.players[0].active, 0) == 0
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats
    e.apply(0, retreats[0])
    assert e.state.players[0].discard == ()
    assert any(ev.kind == "retreat" and ev.detail["paid"] == 0 for ev in e.events)


def test_气球2阶进化_非2阶持有者不免() -> None:
    """非 2 阶（1 阶）持有者：条件不成立，按卡面费（2 费，1 能量不可撤）。"""
    e = balloon_engine(stage1_mon(2), energies=1, doc=BALLOON_STAGE2_DOC)
    assert e._effective_retreat_cost(e.state.players[0].active, 0) == 2
    assert not [a for a in e.legal_actions(0) if a.kind == "retreat"]
