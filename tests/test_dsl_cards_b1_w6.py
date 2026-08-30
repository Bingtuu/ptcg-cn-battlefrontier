"""task 025 批 1 wave 6：单卡 DSL 测试分片（从 cards/ 真实文件装载，stub 引擎驱动全链路）。

彷徨夜灵（CS2.5C-018）：奇异之光 = 无伤害施加混乱；精神拳 60 无效果文走引擎白板伤害。
玛俐的捣蛋小妖（CSV10C-146）：骗取 = 无伤害抽 1 张；推打 10 走引擎白板伤害。
"""

from pathlib import Path

from helpers import engine_at, inst
from test_attack import battle, energies, mon

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, InPlayPokemon, SpecialCondition

CARDS_DIR = Path(__file__).parent.parent / "cards"

DUSCLOPS_DOC = load_card_doc(CARDS_DIR / "彷徨夜灵.yml")
IMPIDOC_DOC = load_card_doc(CARDS_DIR / "玛俐的捣蛋小妖.yml")

DUSCLOPS_ATTACKS = (
    AttackDef(name="奇异之光", cost=("无",), damage=None),
    AttackDef(name="精神拳", cost=("超", "无", "无"), damage=60),
)
IMPIDOC_ATTACKS = (
    AttackDef(name="骗取", cost=("无",), damage=None),
    AttackDef(name="推打", cost=("恶",), damage=10),
)


def _engine(card, energies_attached, doc):
    """p0 战斗场为目标卡（指定附着能量），p1 战斗场厚皮兽 hp200，main 阶段。"""
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, card),), attached_energy=energies_attached),
        InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=200)),)),
    ))
    e.card_effects = {card.name: doc}
    return e


# ── 彷徨夜灵 ─────────────────────────────────────────────────────────────

def test_彷徨夜灵_奇异之光_applies_confusion_no_damage() -> None:
    """奇异之光：无伤害，对手战斗宝可梦陷入混乱（effect 全由 DSL 块结算）。"""
    card = mon("彷徨夜灵", attacks=DUSCLOPS_ATTACKS, hp=90, energy_type="超")
    e = _engine(card, energies("超"), DUSCLOPS_DOC)
    e.apply(0, Action(kind="attack", attack_index=0))
    d = e.state.players[1].active
    assert d.damage == 0
    assert d.conditions == frozenset({SpecialCondition.CONFUSED})
    prims = [ev.detail["action"] for ev in e.events if ev.kind == "effect_primitive"]
    assert prims == ["apply_status"]
    assert e.state.current_player == 1  # 招式结算完回合权给对手


def test_彷徨夜灵_精神拳_vanilla_damage() -> None:
    """精神拳 60 无效果文：DSL 不绑定，引擎白板伤害结算。"""
    card = mon("彷徨夜灵", attacks=DUSCLOPS_ATTACKS, hp=90, energy_type="超")
    e = _engine(card, energies("超", "超", "超"), DUSCLOPS_DOC)
    e.apply(0, Action(kind="attack", attack_index=1))
    d = e.state.players[1].active
    assert d.damage == 60
    assert d.conditions == frozenset()
    assert not [ev for ev in e.events if ev.kind == "effect_primitive"]


# ── 玛俐的捣蛋小妖 ───────────────────────────────────────────────────────

def test_玛俐的捣蛋小妖_骗取_draws_one() -> None:
    """骗取：无伤害，从自己牌库上方抽 1 张。"""
    card = mon("玛俐的捣蛋小妖", attacks=IMPIDOC_ATTACKS, hp=70, energy_type="恶")
    e = _engine(card, energies("恶"), IMPIDOC_DOC)
    e.apply(0, Action(kind="attack", attack_index=0))
    p0 = e.state.players[0]
    assert len(p0.hand) == 1 and p0.hand[0].iid == 100  # 牌库顶
    assert len(p0.deck) == 9
    assert e.state.players[1].active.damage == 0
    prims = [ev.detail["action"] for ev in e.events if ev.kind == "effect_primitive"]
    assert prims == ["draw"]


def test_玛俐的捣蛋小妖_推打_vanilla_damage() -> None:
    """推打 10 无效果文：DSL 不绑定，引擎白板伤害结算。"""
    card = mon("玛俐的捣蛋小妖", attacks=IMPIDOC_ATTACKS, hp=70, energy_type="恶")
    e = _engine(card, energies("恶"), IMPIDOC_DOC)
    e.apply(0, Action(kind="attack", attack_index=1))
    d = e.state.players[1].active
    assert d.damage == 10
    assert not [ev for ev in e.events if ev.kind == "effect_primitive"]
