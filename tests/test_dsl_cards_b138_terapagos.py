"""单卡 DSL 测试（task 138）：太乐巴戈斯ex——从 cards/ 真实文件装载。

太乐巴戈斯ex（CSV9C-175 档，基础无 ex 230，H 标 7 印刷等价类）：
「【无】【无】 同盟打击 30×——这个招式，在后攻玩家的最初回合无法使用。
造成自己备战宝可梦数量×30伤害。」（usage_gate=second_player_first_turn
D-138-1 枚举点使用门 + bench_count_own D-138-2 计数词）
「【草】【水】【雷】 皇冠蛋白石 180——在下一个对手的回合，这只宝可梦不会
受到【基础】宝可梦（除【无】宝可梦外）的招式的伤害。」（prevent_attack_damage
D-138-3 时效减伤：opponent_next_turn + attacker_stage=basic +
except_attacker_type=无；仅招式伤害）
"""

from pathlib import Path

import pytest
from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action, IllegalActionError
from battlefrontier.engine.state import AttackDef, CardDef, InPlayPokemon

CARDS_DIR = Path(__file__).parent.parent / "cards"

TERA_DOC = load_card_doc(CARDS_DIR / "太乐巴戈斯ex.yml")


def tera_card() -> CardDef:
    return CardDef(
        card_id="CSV9C-175", name="太乐巴戈斯ex", supertype="pokemon",
        hp=230, stage=0, energy_type="无", rule_box="ex",
        attacks=(
            AttackDef(name="同盟打击", cost=("无", "无"), damage=30,
                      damage_modifier="×"),
            AttackDef(name="皇冠蛋白石", cost=("草", "水", "雷"), damage=180),
        ),
        retreat_cost=2,
    )


def tera_mon(iid: int, energies: tuple[str, ...] = ()) -> InPlayPokemon:
    """太乐巴戈斯ex 实例；energies = 附着能量属性列表（按序构造实例）。"""
    attached = tuple(
        inst(9000 + iid * 10 + j,
             CardDef(card_id=f"stub-能{j}", name=f"能{j}", supertype="energy",
                     energy_type=t, is_basic_energy=True))
        for j, t in enumerate(energies)
    )
    return InPlayPokemon(stack=(inst(iid, tera_card()),), attached_energy=attached)


def typed_mon(iid: int, name: str, energy_type: str, *,
              hp: int = 300, damage: int = 100, cost: int = 1) -> InPlayPokemon:
    card = CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=hp, stage=0, energy_type=energy_type,
                   attacks=(AttackDef(name="打击", cost=("无",) * cost, damage=damage),),
                   retreat_cost=1)
    return in_play(iid, card, cost)


def game(*, p0_active: InPlayPokemon, p1_active: InPlayPokemon | None = None,
         p0_bench: tuple[InPlayPokemon, ...] = (),
         turn: int = 2, current: int = 0):
    state = main_state(p1_active_energies=1)
    p0 = state.players[0].model_copy(update={
        "active": p0_active, "bench": p0_bench,
    })
    p1 = state.players[1].model_copy(update={
        "active": p1_active or state.players[1].active,
    })
    state = state.model_copy(update={
        "players": (p0, p1), "turn": turn, "current_player": current,
    })
    e = engine_at(state)
    e.card_effects = {"太乐巴戈斯ex": TERA_DOC}
    return e


def test_太乐巴戈斯ex_挂载等价类() -> None:
    """H 标同文本 7 印刷（db 归一化 text_raw 实测一致，2026-11-15）。"""
    assert TERA_DOC.card.card_ids == (
        "CSV9C-175", "CSV9C-232", "CSV9C-251", "CSV9C-262",
        "CSV9.5C-156", "CSV9.5C-248", "CSV9.5C-259")


def test_同盟打击_后攻最初回合不枚举_皇冠蛋白石不受门影响() -> None:
    # p1 = 后攻（first_player=0），其最初回合 = turn==1 且行动方=1
    p1 = tera_mon(2, ("无", "草", "水", "雷"))
    e = game(p0_active=in_play(1, basic("前台"), 1), p1_active=p1,
             turn=1, current=1)
    acts = e.legal_actions(1)
    attack_names = {
        e.state.players[1].active.current.card.attacks[a.attack_index].name
        for a in acts if a.kind == "attack"
    }
    assert "同盟打击" not in attack_names
    assert "皇冠蛋白石" in attack_names


def test_同盟打击_后攻第二回合起枚举() -> None:
    p1 = tera_mon(2, ("无", "草", "水", "雷"))
    e = game(p0_active=in_play(1, basic("前台"), 1), p1_active=p1,
             turn=3, current=1)
    attack_names = {
        e.state.players[1].active.current.card.attacks[a.attack_index].name
        for a in e.legal_actions(1) if a.kind == "attack"
    }
    assert "同盟打击" in attack_names


def test_同盟打击_后攻最初回合直接驱动报非法() -> None:
    p1 = tera_mon(2, ("无", "无"))
    e = game(p0_active=in_play(1, basic("前台"), 1), p1_active=p1,
             turn=1, current=1)
    with pytest.raises(IllegalActionError):
        e.apply(1, Action(kind="attack", attack_index=0))


def test_同盟打击_伤害等于己方备战数量乘30() -> None:
    bench = (typed_mon(60, "备1", "雷"), typed_mon(61, "备2", "雷"))
    p0 = tera_mon(1, ("无", "无"))
    e = game(p0_active=p0, p1_active=typed_mon(2, "靶兽", "雷"),
             p0_bench=bench)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 60  # 2 × 30


def test_皇冠蛋白石_180伤害且施加时效减伤() -> None:
    p0 = tera_mon(1, ("草", "水", "雷"))
    e = game(p0_active=p0, p1_active=typed_mon(2, "靶兽", "雷", damage=100))
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 180
    shield = e.state.players[0].active.attack_shield
    assert shield is not None and shield[3] == 0 and shield[4] == ("无",)


def test_皇冠蛋白石_对手下个回合基础非无招式免疫() -> None:
    p0 = tera_mon(1, ("草", "水", "雷"))
    e = game(p0_active=p0, p1_active=typed_mon(2, "雷兽", "雷", damage=100))
    e.apply(0, Action(kind="attack", attack_index=1))
    e.apply(1, Action(kind="attack", attack_index=0))  # 基础雷 → 0
    assert e.state.players[0].active.damage == 0
    # 对手回合结束 → 盾清除
    assert e.state.players[0].active.attack_shield is None


def test_皇冠蛋白石_无属性与过期后照常伤害() -> None:
    p0 = tera_mon(1, ("草", "水", "雷"))
    e = game(p0_active=p0, p1_active=typed_mon(2, "无兽", "无", damage=100))
    e.apply(0, Action(kind="attack", attack_index=1))
    e.apply(1, Action(kind="attack", attack_index=0))  # 无属性不被排除
    assert e.state.players[0].active.damage == 100
