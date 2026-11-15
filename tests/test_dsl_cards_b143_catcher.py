"""单卡 DSL 测试（task 143 补挂批）：反击捕捉器-1只对手——从 cards/ 真实文件装载。

反击捕捉器 CSM1DC-236（M1D 档）：**词序变体异文本拆分档**——本印刷
「选择1只对手的备战宝可梦」与主类 12 印刷「选择对手的1只备战宝可梦」
归一化 text_raw 不一致（2026-11-16 db 实测），按同名多文本拆分纪律独立
成档；效果语义与主类逐字相同（仅词序差异），condition 门 + gust 互换。
task 141 事故实证该印刷会被卡名解析首命中落入（vanilla 静默退化），
本档即封堵该路径。
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_dir, load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef, SpecialCondition

CARDS_DIR = Path(__file__).parent.parent / "cards"

CATCHER_M1D_DOC = load_card_doc(CARDS_DIR / "反击捕捉器-1只对手.yml")


def trainer(name: str, subtype: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype=subtype)


def catcher_engine() -> object:
    """main 局面、p0 手牌含反击捕捉器（iid 60）、对手奖赏少 1 且备战 2 只。"""
    state = main_state(p0_extra_hand=(inst(60, trainer("反击捕捉器", "物品")),))
    p1 = state.players[1].model_copy(update={
        "prizes": state.players[1].prizes[:5],
        "active": state.players[1].active.model_copy(update={
            "conditions": frozenset({SpecialCondition.CONFUSED}),
        }),
        "bench": (in_play(300, basic("小火龙")), in_play(301, basic("妙蛙种子"))),
    })
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.card_effects = {"反击捕捉器": CATCHER_M1D_DOC}
    return e


def test_反击捕捉器_M1D词序变体档挂载() -> None:
    """M1D 印刷独立成档；与主类同组并存、card_ids 不相交。"""
    assert CATCHER_M1D_DOC.card.card_ids == ("CSM1DC-236",)
    docs = load_card_dir(CARDS_DIR)
    group = docs.by_name("反击捕捉器")
    assert len(group) == 2  # 主类 12 印刷 + 词序变体档
    ids = [i for d in group for i in d.card.card_ids]
    assert len(ids) == len(set(ids)), "同组 card_ids 必须不相交"


def test_反击捕捉器_M1D词序变体_条件门不枚举() -> None:
    """「只有剩余奖赏比对手多时才可使用」：6v6 不枚举（与主类同语义）。"""
    state = main_state(p0_extra_hand=(inst(60, trainer("反击捕捉器", "物品")),))
    e = engine_at(state)
    e.card_effects = {"反击捕捉器": CATCHER_M1D_DOC}
    assert not [a for a in e.legal_actions(0)
                if a.kind == "play_trainer" and a.iid == 60]


def test_反击捕捉器_M1D词序变体_互换流程() -> None:
    """选对手备战 1 只与战斗场互换；被换下宝可梦特殊状态清除。"""
    e = catcher_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    choices = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert choices == [(300,), (301,)]
    e.apply(0, next(a for a in e.legal_actions(0)
                    if a.kind == "choose" and a.choices == (300,)))
    p1 = e.state.players[1]
    assert e.state.phase == "main"
    assert p1.active.current.iid == 300
    assert not p1.active.conditions  # 混乱随换位清除（rules-manual §4）
    assert p1.bench[0].current.iid != 300
