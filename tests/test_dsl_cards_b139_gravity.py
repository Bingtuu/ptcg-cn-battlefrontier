"""单卡 DSL 测试（task 139 批次 4/6）：重力山——从 cards/ 真实文件装载。

重力山（CSV7C-201 档，H 标 2 印刷等价类，竞技场）：
「双方场上的所有【2阶进化】宝可梦的最大HP，各『-30』。」
（D-139-5：modify_hp 竞技场来源 + args.target_filters=[stage2_pokemon]；
减伤为有效 HP 动态求值——场被顶/被弃即恢复；伤害 ≥ 新有效 HP 昏厥走
既有 _do_play_stadium 触点，rules-manual §8 剩余 HP ≤ 0 口径）
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

MOUNTAIN_DOC = load_card_doc(CARDS_DIR / "重力山.yml")


def mountain() -> CardDef:
    return CardDef(card_id="stub-重力山", name="重力山", supertype="trainer",
                   trainer_subtype="竞技场")


def stage2_mon(iid: int, hp: int = 150, damage: int = 0) -> object:
    card = CardDef(card_id="stub-二阶兽", name="二阶兽", supertype="pokemon",
                   hp=hp, stage=2)
    m = in_play(iid, card)
    return m.model_copy(update={"damage": damage}) if damage else m


def mountain_game(*, p0_active=None, p1_active=None) -> object:
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": state.players[0].hand + (inst(60, mountain()),),
        "active": p0_active or stage2_mon(1),
    })
    p1 = state.players[1].model_copy(update={"active": p1_active or stage2_mon(2)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"重力山": MOUNTAIN_DOC}
    return e


def test_重力山_挂载等价类() -> None:
    """H 标同文本 2 印刷（db 归一化 text_raw 实测一致，2026-11-15）。"""
    assert MOUNTAIN_DOC.card.card_ids == ("CSV7C-201", "CSV8C-261")


def test_重力山_双方2阶最大HP减30() -> None:
    e = mountain_game()
    e.apply(0, Action(kind="play_stadium", iid=60))
    assert e._effective_hp(e.state.players[0].active, 0) == 120
    assert e._effective_hp(e.state.players[1].active, 1) == 120


def test_重力山_基础与1阶不受影响() -> None:
    e = mountain_game(p0_active=in_play(1, basic("妙蛙种子")),
                      p1_active=None)
    e.apply(0, Action(kind="play_stadium", iid=60))
    assert e._effective_hp(e.state.players[0].active, 0) == 70
    assert e._effective_hp(e.state.players[1].active, 1) == 120


def test_重力山_伤害达新HP_打出即昏厥() -> None:
    """150 HP 叠 125 伤害：打出后有效 HP 120 → 剩余 HP ≤ 0 昏厥（§8）。"""
    e = mountain_game(p0_active=stage2_mon(1, damage=125))
    e.apply(0, Action(kind="play_stadium", iid=60))
    p0 = e.state.players[0]
    assert 1 in [c.iid for c in p0.discard]
    assert e.state.phase in ("promote", "game_over")


def test_重力山_场被顶_修正即时消失() -> None:
    e = mountain_game()
    e.apply(0, Action(kind="play_stadium", iid=60))
    plain = CardDef(card_id="stub-空场", name="空场", supertype="trainer",
                    trainer_subtype="竞技场")
    e.state = e.state.model_copy(update={"stadium": inst(61, plain)})
    assert e._effective_hp(e.state.players[0].active, 0) == 150
