"""单卡 DSL 测试（task 139 批次 1/6）：钥圈儿——从 cards/ 真实文件装载。

钥圈儿（CSV1C-060 档，G 标 3 印刷等价类，基础超 70）：
「特性: 恶作剧之锁——只要这只宝可梦在战斗场上，双方场上【基础】宝可梦的
特性（除『恶作剧之锁』外），全部消除。」（D-139-1：suppress_ability
stages=[0] + exclude_abilities + condition holder_is_active）
「【无】 狙落 10——在造成伤害前，将放于对手战斗宝可梦身上的『宝可梦道具』
放于弃牌区。」（D-139-2：discard selector=opponent_active_tool）
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    InPlayPokemon,
)

CARDS_DIR = Path(__file__).parent.parent / "cards"

KLEFKI_DOC = load_card_doc(CARDS_DIR / "钥圈儿.yml")


def klefki(iid: int) -> InPlayPokemon:
    card = CardDef(card_id="stub-钥圈儿", name="钥圈儿", supertype="pokemon",
                   hp=70, stage=0, energy_type="超",
                   attacks=(AttackDef(name="狙落", cost=("无",), damage=10),),
                   retreat_cost=1, ability_names=("恶作剧之锁",))
    return in_play(iid, card, energies=1)


def draw_mon(iid: int, *, stage: int = 0, player: int = 0) -> InPlayPokemon:
    name = f"抽牌兽{player}"
    card = CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=70, stage=stage, has_ability=True)
    return in_play(iid, card)


def _draw_doc(name: str):
    from battlefrontier.dsl import parse_card_doc
    return parse_card_doc(f"""
card:
  name_group: {name}
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {{action: draw, selector: own_deck, count: 1}}
""")


def lock_game(*, klefki_active: bool, target_stage: int = 0,
              target_player: int = 0) -> object:
    """锁兽在 p1 场上（战斗场/备战区）；目标方场上抽牌兽。"""
    state = main_state()
    k = klefki(2)
    victim = draw_mon(1, stage=target_stage, player=target_player)
    p0 = state.players[0]
    p1 = state.players[1]
    if klefki_active:
        p1 = p1.model_copy(update={"active": k, "bench": ()})
    else:
        p1 = p1.model_copy(update={"active": in_play(7, basic("占位")), "bench": (k,)})
    if target_player == 0:
        p0 = p0.model_copy(update={"active": victim})
    else:
        p1 = p1.model_copy(update={"bench": p1.bench + (victim,)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"钥圈儿": KLEFKI_DOC,
                      "抽牌兽0": _draw_doc("抽牌兽0"), "抽牌兽1": _draw_doc("抽牌兽1")}
    return e


def test_钥圈儿_挂载等价类() -> None:
    """G 标同文本 3 印刷（db 归一化 text_raw 实测一致，2026-11-15）。"""
    assert KLEFKI_DOC.card.card_ids == ("CSV1C-060", "CSVL1C-028", "CSVL1C-069")


def test_恶作剧之锁_对手基础特性消除() -> None:
    e = lock_game(klefki_active=True)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


def test_恶作剧之锁_锁兽退备战区_特性恢复() -> None:
    e = lock_game(klefki_active=False)
    assert {a.iid for a in e.legal_actions(0) if a.kind == "use_ability"} == {1}


def test_恶作剧之锁_锁兽方自己的基础特性也被消除() -> None:
    """「双方场上」：锁兽方（p1）另一只基础的特性同样被消除。"""
    e = lock_game(klefki_active=True, target_player=1)
    e.state = e.state.model_copy(update={"current_player": 1})
    assert not [a for a in e.legal_actions(1) if a.kind == "use_ability"]


def test_恶作剧之锁_进化宝可梦特性不消除() -> None:
    e = lock_game(klefki_active=True, target_stage=1)
    assert {a.iid for a in e.legal_actions(0) if a.kind == "use_ability"} == {1}


def test_恶作剧之锁_自身特性豁免() -> None:
    """「除『恶作剧之锁』外」：锁兽（基础）自己不被消除（无自我封存）。"""
    e = lock_game(klefki_active=True)
    assert not e._ability_suppressed(e.state.players[1].active)


def test_狙落_道具先于伤害进弃牌区() -> None:
    """对手战斗场挂道具：狙落 → 道具进对手弃牌区 + discard_tool 事件 + 伤害 10。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": klefki(1)})
    tool = CardDef(card_id="stub-道具", name="勇气护符", supertype="trainer",
                   trainer_subtype="宝可梦道具")
    target = in_play(2, basic("厚皮兽", hp=300)).model_copy(
        update={"attached_tool": inst(500, tool)})
    p1 = state.players[1].model_copy(update={"active": target})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"钥圈儿": KLEFKI_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    assert p1.active.attached_tool is None
    assert 500 in [c.iid for c in p1.discard]
    assert p1.active.damage == 10
    evs = [ev for ev in e.events if ev.kind == "discard_tool"]
    assert [ev.detail["iid"] for ev in evs] == [500]


def test_狙落_无道具_伤害照算() -> None:
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": klefki(1)})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"钥圈儿": KLEFKI_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 10
