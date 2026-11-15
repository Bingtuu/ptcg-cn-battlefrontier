"""单卡 DSL 测试（task 139 批次 2/6）：桃歹郎ex——从 cards/ 真实文件装载。

桃歹郎ex（CSV8C-136 档，H 标 7 印刷等价类，基础恶 ex 190）：
「特性: 支配锁链——在自己的回合可以使用1次。选择自己备战区中的1只【恶】
宝可梦（除『桃歹郎【ex】』外），将其与战斗宝可梦互换。然后，令新的战斗
宝可梦陷入【中毒】状态。在这个回合，如果已经使用了其他的『支配锁链』的
话，则无法使用这个特性。」（switch filters=[pokemon_恶, not_name:桃歹郎ex]
D-139-3 + apply_status own_active D-139-4 + once_per_turn_shared 同名共享锁）
「【恶】【恶】 焦躁爆破 60×——造成对手已经获得的奖赏卡张数×60伤害。」
（damage count=opponent_taken_prizes per=60，月月熊 老练招式同计数词）
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    InPlayPokemon,
    SpecialCondition,
)

CARDS_DIR = Path(__file__).parent.parent / "cards"

PECH_DOC = load_card_doc(CARDS_DIR / "桃歹郎ex.yml")


def pecharunt(iid: int) -> InPlayPokemon:
    card = CardDef(card_id="stub-桃歹郎ex", name="桃歹郎ex", supertype="pokemon",
                   hp=190, stage=0, energy_type="恶", rule_box="ex",
                   attacks=(AttackDef(name="焦躁爆破", cost=("恶", "恶"), damage=60),),
                   retreat_cost=2, has_ability=True,
                   ability_names=("支配锁链",))
    return in_play(iid, card)


def dark_mon(iid: int, name: str = "恶兽") -> InPlayPokemon:
    card = CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=100, stage=0, energy_type="恶")
    return in_play(iid, card)


def type_mon(iid: int, name: str, energy_type: str) -> InPlayPokemon:
    card = CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=100, stage=0, energy_type=energy_type)
    return in_play(iid, card)


def chain_game(*, bench: tuple[InPlayPokemon, ...],
               active: InPlayPokemon | None = None) -> object:
    """p0 战斗场桃歹郎ex（默认）+ 指定备战区。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": active or pecharunt(1),
        "bench": bench,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"桃歹郎ex": PECH_DOC}
    return e


def test_桃歹郎ex_挂载等价类() -> None:
    """H 标同文本 7 印刷（db 归一化 text_raw 实测一致，2026-11-15）。"""
    assert PECH_DOC.card.card_ids == (
        "CSV8C-136", "CSV8C-227", "CSV8C-250", "CSV8C-257",
        "CSV9.5C-116", "CSV9.5C-241", "CSVNC-029")


def test_支配锁链_备战池过滤恶且排除桃歹郎ex() -> None:
    e = chain_game(bench=(dark_mon(80), type_mon(81, "雷兽", "雷"), pecharunt(82)))
    e.apply(0, Action(kind="use_ability", iid=1))
    pc = e.state.pending_choice
    assert pc.pool == "own_bench"
    assert set(pc.pool_iids) == {80}


def test_支配锁链_换位后新战斗场中毒() -> None:
    e = chain_game(bench=(dark_mon(80),))
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(80,)))
    p0 = e.state.players[0]
    assert p0.active.current.iid == 80
    assert SpecialCondition.POISONED in p0.active.conditions


def test_支配锁链_每回合1次_同名共享() -> None:
    """「使用了其他的『支配锁链』」：同名共享锁（once_per_turn_shared，
    大比鸟ex 音速搜索先例——按卡名键控，本卡为唯一持有者等价）。"""
    e = chain_game(bench=(dark_mon(80), pecharunt(81)))
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(80,)))
    # 同回合：备战区另一张桃歹郎ex 的支配锁链也不可使用
    assert not [a for a in e.legal_actions(0)
                if a.kind == "use_ability" and a.iid == 81]


def test_支配锁链_无合法目标_特性不枚举() -> None:
    e = chain_game(bench=(type_mon(80, "雷兽", "雷"),))
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


def blast_game(p1_prizes: int) -> object:
    """p0 桃歹郎ex 战斗场（2 恶能量）；p1 剩余奖赏 n 张（已拿 6−n）。"""
    state = main_state(p0_active_energies=0)
    p0 = state.players[0].model_copy(update={
        "active": pecharunt(1).model_copy(update={
            "attached_energy": (inst(910, _dark_energy()), inst(911, _dark_energy())),
        }),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("厚皮兽", hp=300)),
        "prizes": tuple(inst(400 + i, basic("小火龙")) for i in range(p1_prizes)),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"桃歹郎ex": PECH_DOC}
    return e


def _dark_energy() -> CardDef:
    return CardDef(card_id="stub-恶能量", name="基本恶能量", supertype="energy",
                   energy_type="恶", is_basic_energy=True)


def test_焦躁爆破_对手已拿2奖赏_120伤害() -> None:
    e = blast_game(4)  # 已拿 2 张 → 2×60
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 120


def test_焦躁爆破_对手未拿奖赏_0伤害() -> None:
    e = blast_game(6)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0


def test_焦躁爆破_对手已拿5奖赏_300伤害昏厥() -> None:
    e = blast_game(1)
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    assert p1.active is None or p1.active.current.iid != 2
    assert 2 in [c.iid for c in p1.discard]
