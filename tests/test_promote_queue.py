"""task 026 WP2：promote 队列 + resume 机制（引擎核心改造）。

设计决议（task 026.md WP2 节，2026-09-07 定稿）：
- D-WP2-1 效果内昏厥（含自我昏厥）的换上推迟到效果全部结算完毕后按队列统一进行，
  换上完成后回效果方主阶段（ability/trainer/stadium 类完成）；🔲 待核
  （rules-manual §8 换上义务 + 附录待核清单「同时昏厥结算顺序」）。
- D-WP2-2 多换上队列按昏厥结算顺序（玩家 0→1、备战区→战斗场扫描序）FIFO 逐条换上。
- D-WP2-4 promote_to_main 归并进 resume_after_promotes（bounce 行为回归）。
"""

from helpers import basic, energy, engine_at, in_play, inst, main_state
from test_attack import battle, energies, mon
from test_confusion import confused_battle, confused_engine

from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef, InPlayPokemon


def attacker(name: str = "打手", damage: int = 100) -> CardDef:
    return mon(name, attacks=(AttackDef(name="撞击", cost=("无",), damage=damage),))


def ability_mon(name: str, hp: int = 90) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon", hp=hp, stage=0)


# ── 1/2/3：三条既有行为走新机制的回归不变式 ────────────────────────────────

def test_attack_ko_promote_queue_then_defender_turn():
    """白板攻击昏厥对手战斗场（回归）：入队 → 换上 → 防守方回合开始（行为不变）。"""
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, attacker()),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, basic("小火龙")),)),
        p1_bench=(InPlayPokemon(stack=(inst(3, basic("小火龙")),)),),
    ))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "promote" and e.state.current_player == 1
    assert e.state.promote_queue == (1,)  # 队列机制不变式
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.promote_queue == ()
    assert e.state.phase == "main" and e.state.current_player == 1
    assert e.state.turn == 2  # begin_turn(防守方) 不递增（turn 仅先攻方回合开始 +1）


def test_confusion_self_ko_uses_queue_and_turn_after_promote():
    """混乱反面自我昏厥（回归）：攻击方入队换上，turn_after_promote 回合权给对手。"""
    bench = (InPlayPokemon(stack=(inst(5, basic("小火龙")),)),)
    e = confused_engine(confused_battle(atk_hp=30, p0_bench=bench), heads=False)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "promote" and e.state.current_player == 0
    assert e.state.promote_queue == (0,)
    assert e.state.turn_after_promote == 1  # 攻击已消耗，回合权给对手（D1 决议）
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.turn_after_promote is None
    assert e.state.current_player == 1 and e.state.phase == "main"


BOUNCE_DOC = parse_card_doc("""
card:
  name_group: 测试放回手牌
effects:
  - trigger: on_play
    actions:
      - {action: bounce, selector: own_pokemon_in_play, choose: 1}
""")


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def test_bounce_active_goes_resume_after_promotes():
    """bounce 战斗场（回归，D-WP2-4）：resume_after_promotes=(效果方, main)，换上后回主阶段。"""
    state = main_state(p0_extra_hand=(inst(60, item("测试放回手牌")),))
    p0 = state.players[0].model_copy(update={"bench": (in_play(70, basic("小拉达")),)})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"测试放回手牌": BOUNCE_DOC}
    turn_before = e.state.turn
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(1,)))  # 战斗场（iid 1）
    assert e.state.phase == "promote" and e.state.current_player == 0
    assert e.state.resume_after_promotes == (0, "main")  # promote_to_main 归并
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.resume_after_promotes is None
    assert e.state.phase == "main" and e.state.current_player == 0
    assert e.state.turn == turn_before  # 未推进回合、未抽牌


# ── 4/5：效果内昏厥的推迟换上 ──────────────────────────────────────────────

SELF_DESTRUCT_DOC = parse_card_doc("""
card:
  name_group: 自爆兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: ko_self, selector: self}
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 10}}
""")


def test_double_promote_queue_fifo_then_back_to_main():
    """一次效果两个待换上（自爆 + 指示物昏厥对手战斗场）：队列 (0, 1) 按入队序
    逐条换上，全部完成后回效果方（我方）主阶段（D-WP2-1/2；咒怨炸弹语序保真：
    先自我昏厥对手拿奖赏、后放指示物我方拿奖赏）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, ability_mon("自爆兽")),
        "bench": (in_play(70, basic("小拉达")),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, mon("厚皮兽", hp=100)),
        "bench": (in_play(80, basic("喵喵")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"自爆兽": SELF_DESTRUCT_DOC}
    e.apply(0, Action(kind="use_ability", iid=1))
    # ko_self 立即结算：整叠弃置 + 对手拿奖赏；换上推迟（不翻阶段），继续挂起选指示物目标
    assert e.state.phase == "choice"
    assert e.state.promote_queue == (0,)
    assert e.state.players[0].active is None
    assert len(e.state.players[1].hand) == 1  # 对手已拿 1 张奖赏
    e.apply(0, Action(kind="choose", choices=(2,)))  # 10 个指示物昏厥对手战斗场
    assert e.state.promote_queue == (0, 1)  # 入队序 = 结算序
    assert e.state.phase == "promote" and e.state.current_player == 0
    assert e.state.resume_after_promotes == (0, "main")
    prize_events = [ev for ev in e.events if ev.kind == "take_prize"]
    assert [ev.player for ev in prize_events] == [1, 0]  # 先自爆（对手拿）后昏厥（我方拿）
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.phase == "promote" and e.state.current_player == 1
    assert e.state.promote_queue == (1,)
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.promote_queue == ()
    assert e.state.phase == "main" and e.state.current_player == 0  # 回效果方主阶段
    assert e.state.turn == 2  # 未推进回合
    assert "自爆兽" in [c.card.name for c in e.state.players[0].discard]
    assert "厚皮兽" in [c.card.name for c in e.state.players[1].discard]


BRAINWAVE_DOC = parse_card_doc("""
card:
  name_group: 愿增猿
effects:
  - trigger: ability_manual
    limit: once_per_turn
    condition: holder_has_energy:恶
    actions:
      - {action: move_damage_counters, selector: own_pokemon_in_play, choose: 1, args: {max_counters: 3, target_pool: opponent_pokemon_any}}
""")


def test_brainwave_ko_returns_to_own_main():
    """亢奋脑力昏厥对手战斗场 → 对手换上后回【我方】主阶段。

    行为修正（task 026 WP2 测试 5）：旧实现 check_knockouts 立即翻 promote 阶段
    且 _do_promote 默认 begin_turn(换上方)，效果致昏厥错进对手回合；正确口径 =
    效果内昏厥的换上推迟到效果完成后，换上后回效果方主阶段（D-WP2-1）——
    回合未被消耗（特性非攻击），对手不抽牌。
    """
    state = main_state()
    m = in_play(1, ability_mon("愿增猿", hp=110)).model_copy(update={
        "attached_energy": (inst(9500, energy("基本恶能量", "恶")),),
    })
    wounded = in_play(70, basic("小火龙")).model_copy(update={"damage": 30})
    p0 = state.players[0].model_copy(update={"active": m, "bench": (wounded,)})
    hurt_active = in_play(2, mon("厚皮兽", hp=100)).model_copy(update={"damage": 70})
    p1 = state.players[1].model_copy(update={
        "active": hurt_active,
        "bench": (in_play(80, basic("喵喵")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"愿增猿": BRAINWAVE_DOC}
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(70,)))  # 来源：备战 30 伤害
    e.apply(0, Action(kind="choose", choices=(2,)))   # 落点：对手战斗场（70+30=100 昏厥）
    assert e.state.phase == "promote" and e.state.current_player == 1
    assert e.state.promote_queue == (1,)
    assert e.state.resume_after_promotes == (0, "main")
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 0  # 回我方主阶段
    assert e.state.turn == 2
    assert not [ev for ev in e.events if ev.kind == "draw"]  # 未进对手回合（不抽牌）


# ── 6：双方同时无宝可梦的平局口径 ──────────────────────────────────────────

def test_double_ko_no_pokemon_is_draw():
    """双方战斗场同时昏厥且备战均空 → 平局（rules-manual §8 同时胜利口径，🔲 待核）。"""
    state = battle(
        InPlayPokemon(stack=(inst(1, basic("妙蛙种子")),), damage=999),
        InPlayPokemon(stack=(inst(2, basic("小火龙")),), damage=999),
    )
    e = engine_at(state)
    e.check_knockouts()
    assert e.state.phase == "game_over"
    assert e.state.is_draw and e.state.winner is None
    over = next(ev for ev in e.events if ev.kind == "game_over")
    assert over.detail["reason"] == "no_pokemon"


def test_single_side_no_pokemon_loses():
    """仅一方战斗场昏厥且备战空：对手胜（rules-manual §8 胜利条件②，回归）。"""
    state = battle(
        InPlayPokemon(stack=(inst(1, basic("妙蛙种子")),), damage=999),
        InPlayPokemon(stack=(inst(2, basic("小火龙")),)),
    )
    e = engine_at(state)
    e.check_knockouts()
    assert e.state.phase == "game_over"
    assert e.state.winner == 1 and not e.state.is_draw


# ── 7：解释器终局守卫 ─────────────────────────────────────────────────────

LAST_PRIZE_DOC = parse_card_doc("""
card:
  name_group: 自爆兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: ko_self, selector: self}
      - {action: draw, count: 2}
""")


def test_run_effect_breaks_on_game_over():
    """ko_self 使对手拿完最后奖赏 → game_over；run_effect 节点循环中断，后续 draw 不执行。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, ability_mon("自爆兽")),
        "bench": (in_play(70, basic("小拉达")),),
    })
    p1 = state.players[1].model_copy(update={"prizes": state.players[1].prizes[:1]})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"自爆兽": LAST_PRIZE_DOC}
    hand_before = len(e.state.players[0].hand)
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "game_over" and e.state.winner == 1
    over = next(ev for ev in e.events if ev.kind == "game_over")
    assert over.detail["reason"] == "prizes"
    assert len(e.state.players[0].hand) == hand_before  # draw 节点未执行
    prims = [ev.detail["action"] for ev in e.events if ev.kind == "effect_primitive"]
    assert prims == ["ko_self"]
