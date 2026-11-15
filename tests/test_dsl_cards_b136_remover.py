"""单卡 DSL 测试（task 136 批次 4/5）：道具拆除器——从 cards/ 真实文件装载。

道具拆除器（CSV10.6C-080 等价类 2 印刷，I 标，物品）：
「选择放于双方场上的宝可梦身上最多2张『宝可梦道具』，放于弃牌区」——
discard selector=tools_attached_both（task 136 引擎扩展 D-136-3）：
choose=2 + up_to（min_choose=0），所选道具摘下进其持有者弃牌区；
双方场上均无道具不可打出（可行性门）。
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef, InPlayPokemon

CARDS_DIR = Path(__file__).parent.parent / "cards"

REMOVER_DOC = load_card_doc(CARDS_DIR / "道具拆除器.yml")


def remover() -> CardDef:
    return CardDef(card_id="stub-道具拆除器", name="道具拆除器", supertype="trainer",
                   trainer_subtype="物品")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def tool_mon(iid: int, tool_iid: int) -> InPlayPokemon:
    m = in_play(iid, basic(f"载体{iid}"))
    return m.model_copy(update={"attached_tool": inst(tool_iid, tool_card(f"道具{tool_iid}"))})


def remover_engine(*, with_tools: bool) -> object:
    """p0 手牌含道具拆除器（iid 60）；双方场上各挂道具。"""
    state = main_state(p0_extra_hand=(inst(60, remover()),))
    p0 = state.players[0].model_copy(update={
        "active": tool_mon(1, 500) if with_tools else in_play(1, basic("载体甲")),
    })
    p1 = state.players[1].model_copy(update={
        "active": tool_mon(2, 501) if with_tools else in_play(2, basic("载体乙")),
        "bench": (tool_mon(80, 502),) if with_tools else (),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"道具拆除器": REMOVER_DOC}
    return e


def test_道具拆除器_挂载同文本等价类() -> None:
    """I 标 2 印刷（CSV10.6C-080 / SVP-483）同文本等价类全收。"""
    assert REMOVER_DOC.card.card_ids == ("CSV10.6C-080", "SVP-483")


def test_道具拆除器_池含双方场上道具_最多2张() -> None:
    """打出 → choice 阶段：池 = 双方场上 3 张道具，min 0 / max 2。"""
    e = remover_engine(with_tools=True)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert set(pc.pool_iids) == {500, 501, 502}
    assert pc.min_choose == 0 and pc.max_choose == 2


def test_道具拆除器_所选道具进各持有者弃牌区() -> None:
    """选己方 500 + 对手 501：各进其持有者弃牌区；未选的不动。"""
    e = remover_engine(with_tools=True)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(500, 501)))
    p0, p1 = e.state.players
    assert 500 in [c.iid for c in p0.discard]
    assert 501 in [c.iid for c in p1.discard]
    assert p0.active.attached_tool is None
    assert p1.active.attached_tool is None
    assert p1.bench[0].attached_tool is not None  # 未选的不动
    assert e.state.phase == "main" and e.state.current_player == 0  # 物品不结束回合
    evs = [ev for ev in e.events if ev.kind == "discard_tool"]
    assert {ev.detail["iid"] for ev in evs} == {500, 501}


def test_道具拆除器_只选1张合法() -> None:
    """「最多2张」= up-to：选 1 张即可结算。"""
    e = remover_engine(with_tools=True)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(502,)))
    p1 = e.state.players[1]
    assert 502 in [c.iid for c in p1.discard]
    assert p1.bench[0].attached_tool is None


def test_道具拆除器_全场上无道具不可打出() -> None:
    """可行性门：双方场上均无道具 → 不枚举（无效果不可使用）。"""
    e = remover_engine(with_tools=False)
    assert not [a for a in e.legal_actions(0)
                if a.kind == "play_trainer" and a.iid == 60]
