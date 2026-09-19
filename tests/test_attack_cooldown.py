"""攻击冷却机制测试（task 026 WP4 裁决 2，2026-09-14）：lock_attack 原语。

拉帝亚斯ex 无限之刃「在下一个自己的回合，这只宝可梦无法使用招式」：
- DSL：on_attack 效果块内 `{action: lock_attack, selector: self}` 把本效果块绑定的
  招式名锁到来源宝可梦（InPlayPokemon.attack_locks + attack_lock_turn = 当前 turn）。
- 解禁时点：_begin_turn 时清该玩家场上 attack_lock_turn 距当前 turn ≥ 2 的锁
  （turn 仅在先攻方回合开始递增：攻击于 turn N → 下个自己回合 N+1 仍锁 → N+2 解禁）。
- 撤退/离场/昏厥天然清除（撤退随特殊状态一并清）；进化继承锁（model_copy 字段
  保留——决议口径，待核）。
"""

import pytest
from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

LOCK_DOC = parse_card_doc("""
card:
  name_group: 锁定兽
effects:
  - trigger: on_attack
    attack: 无限之刃
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 200}}
      - {action: lock_attack, selector: self}
""")


def lock_mon() -> CardDef:
    return CardDef(
        card_id="stub-锁定兽", name="锁定兽", supertype="pokemon", hp=160, stage=0,
        attacks=(
            AttackDef(name="无限之刃", cost=("无",), damage=200),
            AttackDef(name="普通击", cost=("无",), damage=10),
        ),
        retreat_cost=1,
    )


def lock_engine(*, p1_hp: int = 500) -> object:
    """main 阶段（turn=2，先攻 p0）：p0 战斗场锁定兽（1 无能量）+ 备战 1 只；
    对手战斗场高 HP 占位（200 伤害不昏厥）。"""
    state = main_state(p1_bench=(in_play(72, basic("对手占位")),))
    active = in_play(1, lock_mon()).model_copy(update={
        "attached_energy": (inst(9001, energy()),),
    })
    p0 = state.players[0].model_copy(update={
        "active": active, "bench": (in_play(70, basic("备战兽")),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("硬兽", hp=p1_hp), 1),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"锁定兽": LOCK_DOC}
    return e


def attack_indices(e) -> list[int]:
    return sorted(a.attack_index for a in e.legal_actions(0) if a.kind == "attack")


def test_lock_attack_next_own_turn_locked_then_recovers():
    """无限之刃后：下个自己回合该招式不枚举（其他招式不受影响）；再下个自己回合恢复。"""
    e = lock_engine()
    assert attack_indices(e) == [0, 1]
    e.apply(0, Action(kind="attack", attack_index=0))  # 无限之刃 @turn 2
    assert e.state.players[1].active.damage == 200
    locked = e.state.players[0].active
    assert locked.attack_locks == ("无限之刃",) and locked.attack_lock_turn == 2
    assert e.state.current_player == 1
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 3
    assert e.state.turn == 3 and e.state.current_player == 0
    assert attack_indices(e) == [1]  # 无限之刃锁定，普通击不受影响
    e.apply(0, Action(kind="end_turn"))  # → p1 turn 3
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 4
    assert e.state.turn == 4 and e.state.current_player == 0
    assert e.state.players[0].active.attack_locks == ()  # 解禁（字段清除）
    assert attack_indices(e) == [0, 1]  # 恢复可宣言


def test_lock_attack_retreat_clears():
    """撤退后锁清除（随特殊状态一并清；备战区的该宝可梦攻击锁字段为空）。"""
    e = lock_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 3
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats  # 1 能量付卡面 1 费
    e.apply(0, retreats[0])
    retreated = e.state.players[0].bench[0]
    assert retreated.current.card.name == "锁定兽"
    assert retreated.attack_locks == () and retreated.attack_lock_turn is None


def test_lock_attack_evolve_inherits():
    """进化继承锁（决议口径，待核）：锁定中进化 → 锁保留，同名招式仍不可宣言。"""
    evolved = CardDef(
        card_id="stub-锁定兽进化", name="锁定兽进化", supertype="pokemon",
        hp=200, stage=1, evolves_from="锁定兽",
        attacks=(AttackDef(name="无限之刃", cost=("无",), damage=200),),
        retreat_cost=1,
    )
    state = main_state(p0_extra_hand=(inst(60, evolved),),
                       p1_bench=(in_play(72, basic("对手占位")),))
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, lock_mon()).model_copy(update={
            "attached_energy": (inst(9001, energy()),),
        }),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("硬兽", hp=500), 1),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"锁定兽": LOCK_DOC, "锁定兽进化": LOCK_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))  # @turn 2 锁定
    e.apply(1, Action(kind="end_turn"))  # → p0 turn 3
    e.apply(0, Action(kind="evolve", iid=60, target_iid=1))
    active = e.state.players[0].active
    assert active.current.card.name == "锁定兽进化"
    assert active.attack_locks == ("无限之刃",)  # 进化继承锁
    assert attack_indices(e) == []  # 同名招式仍不可宣言（能量只有 1 张也够成本 1 无）


def test_lock_attack_bad_forms_dsl_error():
    """selector≠self / 效果块无 attack 绑定（on_play）→ DslError（不猜）。"""
    bad_selector = parse_card_doc("""
card:
  name_group: 锁定兽
effects:
  - trigger: on_attack
    attack: 无限之刃
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 200}}
      - {action: lock_attack, selector: opponent_active}
""")
    e = lock_engine()
    e.card_effects = {"锁定兽": bad_selector}
    with pytest.raises(DslError, match="lock_attack"):
        e.apply(0, Action(kind="attack", attack_index=0))
    no_binding = parse_card_doc("""
card:
  name_group: 测试物品
effects:
  - trigger: on_play
    actions:
      - {action: lock_attack, selector: self}
""")
    state = main_state(
        p0_extra_hand=(inst(60, CardDef(card_id="stub-测试物品", name="测试物品",
                                        supertype="trainer", trainer_subtype="物品")),),
    )
    e2 = engine_at(state)
    e2.card_effects = {"测试物品": no_binding}
    with pytest.raises(DslError, match="lock_attack"):
        e2.apply(0, Action(kind="play_trainer", iid=60))
