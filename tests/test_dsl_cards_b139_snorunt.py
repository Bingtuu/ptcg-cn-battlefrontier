"""单卡 DSL 测试（task 139 侧 quest 2/2）：雪童子-冰砾——异文本拆分新档。

雪童子（CSV6C-032 档，G 标 2 印刷等价类，基础水）——task 139 印刷补挂侧
quest 处置：CSV6C-032 与现有 雪童子.yml（H 标惊吓类）归一化 text_raw
不一致（db 实测 2026-11-15）→ 按同名多文本拆分纪律新建本档。
「【水】 冰砾 10+——如果对手的战斗宝可梦为【斗】宝可梦的话，则追加
造成30伤害。」（D-139-8 节点条件 if_opponent_active_type:斗；
两段式 damage 各吃一次攻方 modify_damage，与胖嘟嘟ex 力量压制同口径）
"""

from pathlib import Path

from helpers import engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef, InPlayPokemon

CARDS_DIR = Path(__file__).parent.parent / "cards"

ICE_DOC = load_card_doc(CARDS_DIR / "雪童子-冰砾.yml")


def water_energy(iid: int) -> CardDef:
    return CardDef(card_id=f"stub-水{iid}", name="基本水能量", supertype="energy",
                   energy_type="水", is_basic_energy=True)


def snorunt(iid: int) -> InPlayPokemon:
    card = CardDef(card_id="stub-雪童子", name="雪童子", supertype="pokemon",
                   hp=60, stage=0, energy_type="水",
                   attacks=(AttackDef(name="冰砾", cost=("水",), damage=10),),
                   retreat_cost=1)
    return InPlayPokemon(
        stack=(inst(iid, card),),
        attached_energy=(inst(900 + iid, water_energy(iid)),),
    )


def ice_game(defender_type: str) -> object:
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": snorunt(1)})
    defender = CardDef(card_id="stub-防守兽", name="防守兽", supertype="pokemon",
                       hp=300, stage=0, energy_type=defender_type)
    p1 = state.players[1].model_copy(update={"active": in_play(2, defender)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"雪童子": ICE_DOC}
    return e


def test_雪童子冰砾_挂载等价类() -> None:
    """G 标同文本 2 印刷（db 归一化 text_raw 实测一致，2026-11-15）。"""
    assert ICE_DOC.card.card_ids == ("CSV6C-032", "CSVL2C-097")


def test_冰砾_对手斗属性_40伤害() -> None:
    e = ice_game("斗")
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 40


def test_冰砾_对手非斗属性_10伤害() -> None:
    e = ice_game("火")
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 10
