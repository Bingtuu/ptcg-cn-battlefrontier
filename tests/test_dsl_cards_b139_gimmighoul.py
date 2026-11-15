"""单卡 DSL 测试（task 139 侧 quest 1/2）：索财灵-小使者——异文本拆分新档。

索财灵（CSV9C-096 档，H 标 2 印刷等价类，基础超）——task 139 印刷补挂侧
quest 处置：CSV9C-096 与现有 索财灵-连掷硬币.yml（G 标连掷硬币类）归一化
text_raw 不一致（db 实测 2026-11-15）→ 按同名多文本拆分纪律新建本档。
「【无】 小使者——选择自己牌库中最多2张基本能量，在给对手看过之后，
加入手牌。并重洗牌库。」（search_deck up-to 2 + reveal + shuffle_deck；
「【无】【无】【无】 撞击 50」为白板固定伤害，无需 DSL）
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

MESSENGER_DOC = load_card_doc(CARDS_DIR / "索财灵-小使者.yml")


def gimmighoul(iid: int) -> object:
    card = CardDef(card_id="stub-索财灵", name="索财灵", supertype="pokemon",
                   hp=60, stage=0, energy_type="超",
                   attacks=(AttackDef(name="小使者", cost=("无",), damage=0),
                            AttackDef(name="撞击", cost=("无",) * 3, damage=50)),
                   retreat_cost=1)
    return in_play(iid, card, energies=1)


def energy_card(iid: int) -> CardDef:
    return CardDef(card_id=f"stub-能量{iid}", name="基本草能量", supertype="energy",
                   energy_type="草", is_basic_energy=True)


def messenger_game() -> object:
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": gimmighoul(1),
        "deck": tuple(inst(300 + i, energy_card(i)) for i in range(4))
                + tuple(inst(310 + i, basic("妙蛙种子")) for i in range(6)),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"索财灵": MESSENGER_DOC}
    return e


def test_索财灵小使者_挂载等价类() -> None:
    """H 标同文本 2 印刷（db 归一化 text_raw 实测一致，2026-11-15）。"""
    assert MESSENGER_DOC.card.card_ids == ("CSV9C-096", "CSVM2cC-004")


def test_小使者_检索最多2张基本能量_给对手看过_重洗() -> None:
    e = messenger_game()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.pool == "own_deck"
    assert set(pc.pool_iids) == {300, 301, 302, 303}
    assert pc.min_choose == 0 and pc.max_choose == 2
    e.apply(0, Action(kind="choose", choices=(300, 302)))
    p0 = e.state.players[0]
    hand_ids = {c.iid for c in p0.hand}
    assert {300, 302} <= hand_ids
    # 重洗：剩余 8 张回库（事件流含 shuffle）
    assert len(p0.deck) == 8
    assert any(ev.kind == "effect_primitive" and ev.detail.get("action") == "shuffle_deck"
               for ev in e.events)
    assert any(ev.kind == "effect_primitive" and ev.detail.get("action") == "reveal"
               for ev in e.events)


def test_小使者_牌库无基本能量_空结算仍重洗() -> None:
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": gimmighoul(1),
        "deck": tuple(inst(300 + i, basic("妙蛙种子")) for i in range(10)),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"索财灵": MESSENGER_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "main"
    assert any(ev.kind == "effect_primitive" and ev.detail.get("action") == "shuffle_deck"
               for ev in e.events)
