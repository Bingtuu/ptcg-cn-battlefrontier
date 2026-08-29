"""task 003-C/D：主阶段规则（进化/能量/撤退）与战斗结算（伤害/昏厥/奖赏/胜负）。

规则出处：官方规则书「回合的进行」——每只宝可梦每回合限进化 1 次、
登场当回合不可进化；能量每回合限附着 1 张；撤退需丢弃撤退费用数量的能量，
撤退后特殊状态恢复；招式需足够能量；昏厥后对手拿 1 张奖赏卡，无备战区可换
上则判负；拿完 6 张奖赏卡获胜。
"""


from helpers import (
    basic,
    engine_at,
    finish_setup,
    in_play,
    inst,
    main_state,
    new_game,
    stage1,
)

from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import GameState, PlayerState, SpecialCondition


def kinds_of(e, player=0):
    return {a.kind for a in e.legal_actions(player)}


# ── C：主阶段铺备战区（规则书·行动阶段：放置基础宝可梦不限次，≤5）─────────

def test_place_basic_to_bench_in_main_phase() -> None:
    e = engine_at(main_state())  # p0 手牌含小火龙(50，基础)
    places = [a for a in e.legal_actions(0) if a.kind == "place_bench"]
    assert len(places) == 1 and places[0].iid == 50
    e.apply(0, places[0])
    p0 = e.state.players[0]
    assert len(p0.bench) == 1
    assert [c.iid for c in p0.hand] == [51]
    assert 50 in p0.entered_play_this_turn  # 当回合登场 → 不可进化（联动规则）


def test_place_bench_main_stage1_not_placeable() -> None:
    hand_evo = inst(60, stage1("妙蛙草", "妙蛙种子"))
    e = engine_at(main_state(p0_extra_hand=(hand_evo,)))
    places = [a for a in e.legal_actions(0) if a.kind == "place_bench"]
    assert {a.iid for a in places} == {50}  # 只有基础宝可梦可放


def test_place_bench_main_blocked_when_full() -> None:
    state = main_state()
    full_bench = tuple(in_play(10 + i, basic("超音蝠")) for i in range(5))
    p0 = state.players[0].model_copy(update={"bench": full_bench})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    assert "place_bench" not in kinds_of(e)


# ── C：能量附着 ──────────────────────────────────────────

def test_attach_energy_once_per_turn() -> None:
    e = engine_at(main_state())
    acts = [a for a in e.legal_actions(0) if a.kind == "attach_energy"]
    assert acts  # 手牌有能量可附着
    e.apply(0, acts[0])
    assert "attach_energy" not in kinds_of(e)  # 第二次不再出现


def test_attach_requires_energy_in_hand() -> None:
    state = main_state()
    p0 = state.players[0].model_copy(update={"hand": ()})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    assert "attach_energy" not in kinds_of(e)


# ── C：进化 ─────────────────────────────────────────────

def test_evolve_matching_only() -> None:
    hand_evo = inst(60, stage1("妙蛙草", "妙蛙种子"))
    e = engine_at(main_state(p0_extra_hand=(hand_evo,)))
    evos = [a for a in e.legal_actions(0) if a.kind == "evolve"]
    assert len(evos) == 1 and evos[0].iid == 60 and evos[0].target_iid == 1
    e.apply(0, evos[0])
    active = e.state.players[0].active
    assert active.current.card.name == "妙蛙草"
    assert len(active.stack) == 2


def test_cannot_evolve_same_turn_entered_play() -> None:
    hand_evo = inst(60, stage1("妙蛙草", "妙蛙种子"))
    state = main_state(p0_extra_hand=(hand_evo,))
    p0 = state.players[0].model_copy(update={"entered_play_this_turn": frozenset({1})})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    assert "evolve" not in kinds_of(e)


def test_cannot_evolve_twice_same_turn() -> None:
    hand = (
        inst(60, stage1("妙蛙草", "妙蛙种子")),
        inst(61, stage1("妙蛙草", "妙蛙种子")),
    )
    e = engine_at(main_state(p0_extra_hand=hand))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "evolve"))
    assert "evolve" not in kinds_of(e)  # 栈顶 iid 变了，但同回合已进化锁定


def test_cannot_evolve_on_first_turn_after_setup() -> None:
    """【rules-manual §1.1】setup 放置的宝可梦视为刚登场：双方各自第一回合不可进化，
    到自己的第二回合才解锁。"""
    e = new_game(seed=0)  # first_player=1，其起手含妙蛙草、战斗场为妙蛙种子
    finish_setup(e)
    fp = e.state.first_player
    assert e.state.turn == 1
    assert "evolve" not in {a.kind for a in e.legal_actions(fp)}
    # 双方各自结束第一回合（先攻首回合不可攻击）→ 进入先攻方第二回合
    e.apply(fp, Action(kind="end_turn"))
    e.apply(1 - fp, Action(kind="end_turn"))
    assert e.state.turn == 2 and e.state.current_player == fp
    assert "evolve" in {a.kind for a in e.legal_actions(fp)}
# ── C：撤退 ─────────────────────────────────────────────

def test_retreat_pays_cost_and_clears_conditions() -> None:
    bench = (in_play(3, basic("小火龙")),)
    state = main_state(p0_active_energies=1, p1_bench=())
    p0 = state.players[0].model_copy(update={"bench": bench})
    p0 = p0.model_copy(update={
        "active": p0.active.model_copy(update={
            "conditions": frozenset({SpecialCondition.POISONED}),
        }),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert len(retreats) == 1 and retreats[0].bench_index == 0
    e.apply(0, retreats[0])
    p0_after = e.state.players[0]
    assert p0_after.active.current.card.name == "小火龙"
    old = p0_after.bench[0]
    assert old.conditions == frozenset()  # 撤退恢复特殊状态（规则书·撤退）
    assert len(old.attached_energy) == 0  # 撤退费用 1 已弃
    assert len(p0_after.discard) == 1


def test_retreat_blocked_without_energy() -> None:
    state = main_state(p0_active_energies=0)
    p0 = state.players[0].model_copy(update={"bench": (in_play(3, basic("小火龙")),)})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    assert "retreat" not in kinds_of(e)


def test_retreat_once_per_turn() -> None:
    """【官方规则·撤退】撤退在自己的回合只有 1 次机会（pokemon.cn basic_rules05）。"""
    bench = (in_play(3, basic("小火龙")), in_play(4, basic("超音蝠")))
    state = main_state(p0_active_energies=1)
    p0 = state.players[0].model_copy(update={"bench": bench})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats
    e.apply(0, retreats[0])
    # 撤退后战斗场是小火龙（无能量），但即使有能量本回合也不能再撤退
    p0_after = e.state.players[0]
    assert p0_after.retreated_this_turn is True
    assert "retreat" not in kinds_of(e)
    # 次回合重置
    e.apply(0, Action(kind="end_turn"))
    e.apply(1, Action(kind="end_turn"))
    assert e.state.players[0].retreated_this_turn is False


# ── D：攻击与伤害 ────────────────────────────────────────

def test_attack_requires_enough_energy() -> None:
    e = engine_at(main_state(p0_active_energies=0))
    assert "attack" not in kinds_of(e)
    e2 = engine_at(main_state(p0_active_energies=1))
    assert "attack" in kinds_of(e2)


def test_attack_deals_damage_and_ends_turn() -> None:
    e = engine_at(main_state())
    e.apply(0, Action(kind="attack"))
    assert e.state.players[1].active.damage == 20
    assert e.state.current_player == 1  # 回合结束自动移交并抽牌
    assert e.state.phase == "main"


# ── D：昏厥 / 奖赏 / 胜负 ────────────────────────────────

def test_knockout_prize_and_promote() -> None:
    state = main_state()
    hurt = state.players[1].active.model_copy(update={"damage": 60})  # 70HP，再打 20 昏厥
    p1 = state.players[1].model_copy(update={
        "active": hurt, "bench": (in_play(3, basic("小火龙")),),
    })
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.apply(0, Action(kind="attack"))
    p0, p1 = e.state.players
    assert p1.active is None  # 昏厥待换上
    assert any(c.iid == 2 for c in p1.discard)  # 昏厥宝可梦进弃牌堆
    assert len(p1.discard) == 2  # 附着的 1 能量一并弃置
    assert len(p0.prizes) == 5 and len(p0.hand) == 3  # 拿 1 奖赏
    # take_prize 事件记录拿到的是哪张（回放保真）
    prize_events = [ev for ev in e.events if ev.kind == "take_prize"]
    assert len(prize_events) == 1
    assert {"iid", "name"} <= set(prize_events[0].detail)
    # 换上阶段：只有 promote 可选
    promotes = e.legal_actions(1)
    assert {a.kind for a in promotes} == {"promote"}
    e.apply(1, promotes[0])
    assert e.state.players[1].active.current.card.name == "小火龙"
    assert e.state.current_player == 1 and e.state.phase == "main"  # 攻击方回合结束后移交


def test_win_by_taking_last_prize() -> None:
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "prizes": state.players[0].prizes[:1],
    })
    hurt = state.players[1].active.model_copy(update={"damage": 60})
    p1 = state.players[1].model_copy(update={
        "active": hurt, "bench": (in_play(3, basic("小火龙")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.apply(0, Action(kind="attack"))
    assert e.state.phase == "game_over" and e.state.winner == 0


def test_win_by_opponent_no_pokemon() -> None:
    state = main_state()
    hurt = state.players[1].active.model_copy(update={"damage": 60})
    p1 = state.players[1].model_copy(update={"active": hurt})  # 无备战区
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.apply(0, Action(kind="attack"))
    assert e.state.phase == "game_over" and e.state.winner == 0
    assert e.legal_actions(1) == []


def test_draw_result_expressible() -> None:
    # 平局口径可表达：winner=None + is_draw=True，统计计 0.5（对齐 db matchup 口径）
    s = GameState(players=(PlayerState(), PlayerState()), phase="game_over",
                  winner=None, is_draw=True)
    assert s.winner is None and s.is_draw
