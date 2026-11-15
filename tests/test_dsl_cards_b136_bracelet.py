"""单卡 DSL 测试（task 136 批次 5/5）：英勇手镯——从 cards/ 真实文件装载。

英勇手镯（CSV10.6C-082，I 标，宝可梦道具）：
「身上放有这张卡牌的宝可梦（除『拥有规则的宝可梦』外）所使用的招式给对手
战斗场上的『宝可梦【ex】』造成的伤害『+30』」——passive_static modify_damage
+30 + args.target_rule_box=ex（极限腰带/空手道王的修炼先例）；「除拥有规则的
宝可梦外」= 道具附着限制（全局规则），引擎附着枚举暂未按规则盒过滤（task 136
遗留），非本卡效果语义。
"""

from pathlib import Path

from helpers import engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef, InPlayPokemon

CARDS_DIR = Path(__file__).parent.parent / "cards"

BRACELET_DOC = load_card_doc(CARDS_DIR / "英勇手镯.yml")


def bracelet() -> CardDef:
    return CardDef(card_id="stub-英勇手镯", name="英勇手镯", supertype="trainer",
                   trainer_subtype="宝可梦道具")


def attacker() -> CardDef:
    return CardDef(card_id="stub-攻击者", name="攻击者", supertype="pokemon",
                   hp=100, stage=0, energy_type="斗",
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
                   retreat_cost=1)


def defender(*, ex: bool) -> CardDef:
    return CardDef(card_id=f"stub-防守{'ex' if ex else ''}",
                   name=f"防守{'ex' if ex else ''}", supertype="pokemon",
                   hp=300, stage=0, energy_type="草",
                   rule_box="ex" if ex else None)


def bracelet_engine(*, defender_ex: bool) -> object:
    """p0 战斗场攻击者（附着 1 能 + 英勇手镯），p1 战斗场 ex/非 ex 防守。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": InPlayPokemon(
            stack=(inst(1, attacker()),),
            attached_energy=(inst(9001, CardDef(
                card_id="stub-能", name="基本无能量", supertype="energy",
                energy_type="无", is_basic_energy=True)),),
            attached_tool=inst(950, bracelet()),
        ),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, defender(ex=defender_ex)),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"英勇手镯": BRACELET_DOC}
    return e


def test_英勇手镯_挂载() -> None:
    """全库 1 印刷（CSV10.6C-082）。"""
    assert BRACELET_DOC.card.card_ids == ("CSV10.6C-082",)


def test_英勇手镯_对ex防守方加30() -> None:
    """持有者招式对对手战斗场 ex：20+30=50。"""
    e = bracelet_engine(defender_ex=True)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50


def test_英勇手镯_对非ex防守方不加() -> None:
    """防守方非 ex：target_rule_box 过滤，不加成。"""
    e = bracelet_engine(defender_ex=False)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
