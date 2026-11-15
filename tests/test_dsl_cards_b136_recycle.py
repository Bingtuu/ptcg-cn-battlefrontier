"""单卡 DSL 测试（task 136 批次 3/5）：能量回收-10.6——从 cards/ 真实文件装载。

能量回收 CSV10.6C-079（I 标 10.6 弹）：**异文本等价类拆分档**——本印刷
text_raw「在给对手看过之后加入手牌」无逗号，与主类 能量回收.yml 14 印刷
（「在给对手看过之后，加入手牌」）归一化文本不一致（2026-11-15 db 实测），
按同名多文本拆分纪律独立成档；效果语义同主类（弃牌区 ≤2 张基本能量入手
up-to + reveal）。
"""

from pathlib import Path

from helpers import basic, engine_at, inst, main_state

from battlefrontier.dsl.loader import load_card_dir, load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

RECYCLE_106_DOC = load_card_doc(CARDS_DIR / "能量回收-10.6.yml")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def energy(name: str, energy_type: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy",
                   energy_type=energy_type, is_basic_energy=True)


def recycle_engine(discard: tuple) -> object:
    """main 阶段、p0 手牌含能量回收（iid 60），弃牌区由参数给定。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("能量回收")),))
    p0 = state.players[0].model_copy(update={"discard": discard})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"能量回收": RECYCLE_106_DOC}
    return e


def recycle_discard() -> tuple:
    """3 张基本能量（属性各异）+ 1 只宝可梦（应被 basic_energy 过滤）。"""
    return (
        inst(400, energy("基本【火】能量", "火")),
        inst(401, energy("基本【草】能量", "草")),
        inst(402, basic("拉鲁拉丝")),
        inst(403, energy("基本【水】能量", "水")),
    )


def prim_results(e, action: str) -> list:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


def test_能量回收_I标异文本档挂载() -> None:
    """I 标印刷 CSV10.6C-079 独立成档；与主类同组并存、card_ids 不相交。"""
    assert RECYCLE_106_DOC.card.card_ids == ("CSV10.6C-079",)
    docs = load_card_dir(CARDS_DIR)
    both = docs.by_name("能量回收")
    assert len(both) == 2  # 主类 14 印刷 / 10.6 异文本档（拆分纪律）
    ids = [i for d in both for i in d.card.card_ids]
    assert len(ids) == len(set(ids))  # 等价类互斥


def test_能量回收_最多2张基本能量入手() -> None:
    """语义同主类：选 2 张基本能量入手；宝可梦不进选择池；reveal 落事件流。"""
    e = recycle_engine(recycle_discard())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    choices = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert (400, 401) in choices and (403,) in choices and () in choices  # up-to 0~2
    assert not any(402 in c for c in choices)  # 宝可梦被 basic_energy 过滤
    e.apply(0, next(a for a in e.legal_actions(0)
                    if a.kind == "choose" and a.choices == (400, 401)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert [c.iid for c in p0.hand] == [50, 51, 400, 401]
    assert sorted(c.iid for c in p0.discard) == [60, 402, 403]  # 本体收尾进弃牌区
    res = prim_results(e, "recover_from_discard")
    assert res[0]["found"] == 2 and res[0]["destination"] == "hand"
    assert any(ev.kind == "reveal" for ev in e.events)  # 「给对手看过之后」


def test_能量回收_up_to可只拿1张或不拿() -> None:
    """「最多2张」= up-to（min_choose=0）：选 1 张 / 空选均合法。"""
    e = recycle_engine(recycle_discard())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0)
                    if a.kind == "choose" and a.choices == (403,)))
    assert [c.iid for c in e.state.players[0].hand] == [50, 51, 403]

    e2 = recycle_engine(recycle_discard())
    e2.apply(0, Action(kind="play_trainer", iid=60))
    e2.apply(0, next(a for a in e2.legal_actions(0)
                     if a.kind == "choose" and a.choices == ()))
    assert [c.iid for c in e2.state.players[0].hand] == [50, 51]
    assert prim_results(e2, "recover_from_discard")[0]["found"] == 0


def test_能量回收_弃牌区无基本能量不可打出() -> None:
    """可行性门：弃牌区无匹配基本能量 → 不枚举（无效果不可使用）。"""
    e = recycle_engine((inst(402, basic("拉鲁拉丝")),))
    assert not [a for a in e.legal_actions(0)
                if a.kind == "play_trainer" and a.iid == 60]
