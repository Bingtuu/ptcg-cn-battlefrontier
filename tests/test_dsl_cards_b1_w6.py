"""task 025 批 1 wave 6：单卡 DSL 测试分片（从 cards/ 真实文件装载，stub 引擎驱动全链路）。

玛俐的捣蛋小妖（CSV10C-146）：骗取 = 无伤害抽 1 张；推打 10 走引擎白板伤害。
（彷徨夜灵 CS2.5C-018：D 标退环境 + 池内零使用，task 026 WP0 出库；
 H 标 CSV8C-082 咒怨炸弹待 task 026 WP2 place_damage_counters 落地时新写）
"""

from pathlib import Path

from helpers import engine_at, inst
from test_attack import battle, energies, mon

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, InPlayPokemon

CARDS_DIR = Path(__file__).parent.parent / "cards"

IMPIDOC_DOC = load_card_doc(CARDS_DIR / "玛俐的捣蛋小妖.yml")

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
