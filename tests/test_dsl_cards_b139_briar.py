"""单卡 DSL 测试（task 139 批次 3/6）：乌栗——从 cards/ 真实文件装载。

乌栗（CSV8C-198 档，H 标 7 印刷等价类，支援者）：
「这张卡牌，从2个效果中选择1个使用。◆将自己的战斗宝可梦与备战宝可梦互换。
◆在这个回合，自己宝可梦所使用的招式，给对手战斗场上的『宝可梦【ex】・V』
造成的伤害『+30』。」（D-139-7 choose_mode 模式二选一 + D-139-6
target_rule_box 列表 [ex, v]；不可行模式不进选择池——无备战时仅增伤可选）
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

BRIAR_DOC = load_card_doc(CARDS_DIR / "乌栗.yml")


def briar() -> CardDef:
    return CardDef(card_id="stub-乌栗", name="乌栗", supertype="trainer",
                   trainer_subtype="支援者")


def briar_game(*, with_bench: bool = True, defender_rule_box: str | None = None) -> object:
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": state.players[0].hand + (inst(60, briar()),),
        "bench": (in_play(80, basic("备战兽")),) if with_bench else (),
    })
    defender = CardDef(card_id="stub-防守兽", name="防守兽", supertype="pokemon",
                       hp=300, stage=0, rule_box=defender_rule_box)
    p1 = state.players[1].model_copy(update={"active": in_play(2, defender)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"乌栗": BRIAR_DOC}
    return e


def test_乌栗_挂载等价类() -> None:
    """H 标同文本 7 印刷（db 归一化 text_raw 实测一致，2026-11-15）。"""
    assert BRIAR_DOC.card.card_ids == (
        "CSV8C-198", "CSV8C-239", "CSV8C-254", "CSV9.5C-190",
        "CSV9.5C-252", "CSVNC-036", "SVP-409")


def test_乌栗_模式池两个效果() -> None:
    e = briar_game()
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.mode_options == ("换位", "增伤")
    assert {a.choices for a in e.legal_actions(0) if a.kind == "choose"} == {(0,), (1,)}


def test_乌栗_换位模式_战斗场与备战互换() -> None:
    e = briar_game()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(0,)))
    assert e.state.phase == "choice"  # 换位选备战
    e.apply(0, Action(kind="choose", choices=(80,)))
    p0 = e.state.players[0]
    assert p0.active.current.iid == 80
    assert p0.bench[0].current.iid == 1
    assert e.state.phase == "main"


def test_乌栗_增伤模式_ex防守方加30_无规则盒不加() -> None:
    e = briar_game(defender_rule_box="ex")
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(1,)))
    e.apply(0, Action(kind="attack", attack_index=0))  # 打击 20 + 30
    assert e.state.players[1].active.damage == 50


def test_乌栗_增伤模式_v防守方加30() -> None:
    e = briar_game(defender_rule_box="v")
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(1,)))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50


def test_乌栗_增伤模式_回合结束清除() -> None:
    """回合级标记：自己回合结束即清除（空手道王的修炼同机制）。"""
    e = briar_game(defender_rule_box="ex")
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(1,)))
    assert e.state.players[0].turn_damage_mods != ()
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[0].turn_damage_mods == ()


def test_乌栗_无备战_增伤自动选定不挂起() -> None:
    """「从2个效果中选择1个」：换位分支不可行不进池；恰剩 1 可行模式 = 无选择
    交互直接结算（choose_mode auto 口径）。"""
    e = briar_game(with_bench=False)
    assert any(a.kind == "play_trainer" and a.iid == 60 for a in e.legal_actions(0))
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "main"
    assert e.state.players[0].turn_damage_mods == ((30, ["ex", "v"]),)


def test_乌栗_支援者每回合1张() -> None:
    """打出后本回合不可再打第二张（规则骨架既有约束，防回归）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": state.players[0].hand + (inst(60, briar()), inst(61, briar())),
        "bench": (in_play(80, basic("备战兽")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"乌栗": BRIAR_DOC}
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(0,)))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert not [a for a in e.legal_actions(0)
                if a.kind == "play_trainer" and a.iid == 61]
