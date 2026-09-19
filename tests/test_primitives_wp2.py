"""task 026 WP2：ko_self（自我昏厥）+ place_damage_counters（放置伤害指示物）原语。

规则出处：rules-manual §8（自己的宝可梦昏厥：整叠弃置、对手按规则盒拿奖赏、
战斗场昏厥须换上——换上推迟到效果完成后按 promote_queue 统一进行，D-WP2-1）；
§6（伤害指示物不是招式伤害：不结算弱点/抗性）。
D-WP2-3：「可使用」的放弃选项不建模——满足即自动发动，池不足 min_choose 收缩至
池大小，池空 no-op 不挂起。
"""

import pytest
from helpers import basic, engine_at, in_play, inst, main_state
from test_attack import mon

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.state import CardDef


def ability_mon(name: str, hp: int = 90) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon", hp=hp, stage=0)


def tool_card(name: str = "测试道具") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def ability_engine(doc, name: str, *, p0_bench: tuple = (), p1_bench: tuple = (),
                   p1_active=None, p1_prizes: int = 6) -> GameEngine:
    """main 阶段：p0 战斗场 = 特性卡（iid 1）；p1 战斗场 iid 2（hp70 默认）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, ability_mon(name)), "bench": p0_bench,
    })
    p1 = state.players[1].model_copy(update={
        "active": p1_active if p1_active is not None else state.players[1].active,
        "bench": p1_bench,
        "prizes": state.players[1].prizes[:p1_prizes],
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {name: doc}
    return e


# ── ko_self ────────────────────────────────────────────────────────────────

KO_SELF_DOC = parse_card_doc("""
card:
  name_group: 自爆兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: ko_self, selector: self}
""")


def test_ko_self_bench_discards_whole_stack_and_takes_prize():
    """备战位自我昏厥：整叠（含能量/道具）进弃牌区、对手拿 1 张奖赏、无换上、回合继续
    （rules-manual §8：备战昏厥同样结算奖赏，无需换上）。"""
    stacked = in_play(70, ability_mon("自爆兽"), 1).model_copy(update={
        "attached_tool": inst(73, tool_card()),
    })
    state = main_state()
    p0 = state.players[0].model_copy(update={"bench": (stacked,)})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"自爆兽": KO_SELF_DOC}
    e.apply(0, Action(kind="use_ability", iid=70))
    p0a, p1a = e.state.players
    assert p0a.bench == ()
    assert [c.iid for c in p0a.discard] == [70, 9700, 73]  # 栈 + 能量 + 道具整叠弃置
    assert len(p1a.prizes) == 5 and len(p1a.hand) == 1  # 对手按规则盒拿 1 张
    assert any(ev.kind == "knockout" and ev.detail["name"] == "自爆兽" for ev in e.events)
    assert e.state.promote_queue == ()  # 备战昏厥无换上
    assert e.state.phase == "main" and e.state.current_player == 0  # 回合继续


def test_ko_self_active_promotes_after_effect_back_to_main():
    """战斗场自我昏厥 + 有备战：换上推迟到效果完成后（D-WP2-1），换上后回我方主阶段。"""
    e = ability_engine(KO_SELF_DOC, "自爆兽",
                       p0_bench=(in_play(70, basic("小拉达")),))
    turn_before = e.state.turn
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "promote" and e.state.current_player == 0
    assert e.state.promote_queue == (0,)
    assert e.state.resume_after_promotes == (0, "main")
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert e.state.turn == turn_before  # 未推进回合、未抽牌
    assert e.state.players[0].active.current.iid == 70
    assert not [ev for ev in e.events if ev.kind == "draw"]


def test_ko_self_active_without_bench_loses():
    """战斗场自我昏厥 + 无备战（对手场上有宝可梦）：立即 game_over(no_pokemon) 判负
    （rules-manual §8 胜利条件②，与 check_knockouts 同口径）。"""
    e = ability_engine(KO_SELF_DOC, "自爆兽")
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "game_over" and e.state.winner == 1
    assert not e.state.is_draw
    over = next(ev for ev in e.events if ev.kind == "game_over")
    assert over.detail["reason"] == "no_pokemon"


def test_ko_self_last_prize_wins_no_promote():
    """自我昏厥使对手拿完最后奖赏 → 立即 game_over(prizes)；有备战也不再换上。"""
    e = ability_engine(KO_SELF_DOC, "自爆兽",
                       p0_bench=(in_play(70, basic("小拉达")),), p1_prizes=1)
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "game_over" and e.state.winner == 1
    over = next(ev for ev in e.events if ev.kind == "game_over")
    assert over.detail["reason"] == "prizes"
    assert e.state.promote_queue == ()  # 终局不入队


def test_ko_self_bad_forms_dsl_error():
    """selector≠self / 带 choose → DslError（不猜）。"""
    for node in (
        "{action: ko_self, selector: own_active}",
        "{action: ko_self, selector: self, choose: 1}",
    ):
        doc = parse_card_doc(f"""
card:
  name_group: 妙蛙种子
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {node}
""")
        e = engine_at(main_state())
        e.card_effects = {"妙蛙种子": doc}
        with pytest.raises(DslError, match="ko_self"):
            e.apply(0, Action(kind="use_ability", iid=1))


def test_ko_self_source_not_in_play_dsl_error():
    """来源不在场上（训练家卡语境的 selector=self）→ DslError（不猜）。"""
    doc = parse_card_doc("""
card:
  name_group: 测试自爆
effects:
  - trigger: on_play
    actions:
      - {action: ko_self, selector: self}
""")
    state = main_state(p0_extra_hand=(inst(60, item_card("测试自爆")),))
    e = engine_at(state)
    e.card_effects = {"测试自爆": doc}
    with pytest.raises(DslError, match="不在场上"):
        e.apply(0, Action(kind="play_trainer", iid=60))


# ── place_damage_counters ──────────────────────────────────────────────────

COUNTERS_ANY_DOC = parse_card_doc("""
card:
  name_group: 指示兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 5}}
""")

COUNTERS_BENCH2_DOC = parse_card_doc("""
card:
  name_group: 铺伤兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: place_damage_counters, selector: opponent_bench, choose: 2, args: {counters: 1}}
""")


def test_place_counters_any_choose1_adds_50_no_weakness():
    """opponent_pokemon_any choose=1 + counters=5 → 目标 +50（每指示物 10）；
    指示物不是招式伤害：目标有弱点也不 ×2（rules-manual §6）。"""
    weak = in_play(80, mon("弱超兽", hp=200, weakness="超"))
    e = ability_engine(COUNTERS_ANY_DOC, "指示兽", p1_bench=(weak,))
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "choice"
    picks = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert picks == [(2,), (80,)]  # 对手战斗场 + 备战
    e.apply(0, Action(kind="choose", choices=(80,)))
    p1 = e.state.players[1]
    assert p1.bench[0].damage == 50  # 不结算弱点（若按招式伤害 ×2 会是 100）
    assert p1.active.damage == 0
    assert e.state.phase == "main" and e.state.current_player == 0


def test_place_counters_ko_active_promotes_then_own_main():
    """指示物致对手战斗场昏厥 → 入队换上 → ability 完成后回我方主阶段（D-WP2-1）。"""
    hurt = in_play(2, mon("厚皮兽", hp=100)).model_copy(update={"damage": 60})
    e = ability_engine(COUNTERS_ANY_DOC, "指示兽",
                       p1_active=hurt, p1_bench=(in_play(80, basic("喵喵")),))
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(2,)))  # 60+50=110 ≥ 100 昏厥
    assert e.state.phase == "promote" and e.state.current_player == 1
    assert e.state.promote_queue == (1,)
    assert e.state.resume_after_promotes == (0, "main")
    assert len(e.state.players[0].prizes) == 5  # 我方拿 1 张奖赏
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert e.state.turn == 2  # 未推进回合


def test_place_counters_ko_bench_no_promote():
    """指示物致对手备战昏厥：拿奖赏、无换上（§8），回合继续我方主阶段。"""
    hurt_bench = in_play(80, mon("脆皮兽", hp=60)).model_copy(update={"damage": 10})
    e = ability_engine(COUNTERS_ANY_DOC, "指示兽", p1_bench=(hurt_bench,))
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(80,)))  # 10+50=60 昏厥
    p1 = e.state.players[1]
    assert p1.bench == () and "脆皮兽" in [c.card.name for c in p1.discard]
    assert len(e.state.players[0].prizes) == 5
    assert e.state.promote_queue == ()
    assert e.state.phase == "main" and e.state.current_player == 0


def test_place_counters_bench_choose2_each_plus_10():
    """opponent_bench choose=2 + counters=1：两只备战各 +10。"""
    e = ability_engine(COUNTERS_BENCH2_DOC, "铺伤兽",
                       p1_bench=(in_play(80, basic("喵喵")), in_play(81, basic("小拉达"))))
    e.apply(0, Action(kind="use_ability", iid=1))
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert picks == [(80, 81)]  # min=max=2，唯一组合
    e.apply(0, Action(kind="choose", choices=(80, 81)))
    assert [b.damage for b in e.state.players[1].bench] == [10, 10]
    assert e.state.phase == "main"


def test_place_counters_bench_pool_shrinks_min_choose():
    """池不足（备战仅 1 只 < choose=2）：min_choose 收缩至池大小（D-WP2-3），只能选那 1 只。"""
    e = ability_engine(COUNTERS_BENCH2_DOC, "铺伤兽",
                       p1_bench=(in_play(80, basic("喵喵")),))
    e.apply(0, Action(kind="use_ability", iid=1))
    pc = e.state.pending_choice
    assert pc is not None and pc.min_choose == 1 and pc.max_choose == 2
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert picks == [(80,)]
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 10


def test_place_counters_bench_empty_pool_noop_no_suspend():
    """对手备战空：池空不挂起、no-op（D-WP2-3），效果照常完成回主阶段。"""
    e = ability_engine(COUNTERS_BENCH2_DOC, "铺伤兽")
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert e.state.players[1].active.damage == 0
    prim = next(ev for ev in e.events
                if ev.kind == "effect_primitive" and ev.detail["action"] == "place_damage_counters")
    assert prim.detail["result"] == {"placed": 0, "reason": "no_targets"}


def test_place_counters_bad_forms_dsl_error():
    """未知 selector / 缺 counters / counters 非正或非 int / 缺 choose → DslError（不猜）。"""
    bad_nodes = (
        "{action: place_damage_counters, selector: own_pokemon_in_play, choose: 1, args: {counters: 1}}",
        "{action: place_damage_counters, selector: opponent_pokemon_any, choose: 1}",
        "{action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 0}}",
        "{action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: -1}}",
        "{action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: '5'}}",
        "{action: place_damage_counters, selector: opponent_pokemon_any, args: {counters: 1}}",
        "{action: place_damage_counters, selector: opponent_pokemon_any, choose: 2, args: {counters: 1}}",
    )
    for node in bad_nodes:
        doc = parse_card_doc(f"""
card:
  name_group: 测试铺伤
effects:
  - trigger: on_play
    actions:
      - {node}
""")
        state = main_state(p0_extra_hand=(inst(60, item_card("测试铺伤")),))
        e = engine_at(state)
        e.card_effects = {"测试铺伤": doc}
        with pytest.raises(DslError, match="place_damage_counters"):
            e.apply(0, Action(kind="play_trainer", iid=60))


# ── 可行性门 ───────────────────────────────────────────────────────────────

def _no_opponent_pokemon_state():
    """对手场上无宝可梦（合成态，仅可行性门求值用）。"""
    state = main_state()
    p1 = state.players[1].model_copy(update={"active": None, "bench": ()})
    return state.model_copy(update={"players": (state.players[0], p1)})


def test_ability_feasible_ko_self_always_feasible():
    """ko_self 恒可行（对手场上无宝可梦也可发动）。"""
    state = _no_opponent_pokemon_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, ability_mon("自爆兽"))})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"自爆兽": KO_SELF_DOC}
    assert Action(kind="use_ability", iid=1) in e.legal_actions(0)


def test_ability_feasible_place_counters_requires_opponent_pokemon():
    """place_damage_counters：对手场上无宝可梦 → 特性不枚举；有则枚举。"""
    state = _no_opponent_pokemon_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, ability_mon("指示兽"))})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"指示兽": COUNTERS_ANY_DOC}
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    e2 = ability_engine(COUNTERS_ANY_DOC, "指示兽")
    assert Action(kind="use_ability", iid=1) in e2.legal_actions(0)


def test_ability_feasible_unknown_primitive_dsl_error():
    """特性可行性门未知原语仍 DslError（不猜）。"""
    doc = parse_card_doc("""
card:
  name_group: 妙蛙种子
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: bounce, selector: own_pokemon_in_play, choose: 1}
""")
    e = engine_at(main_state())
    e.card_effects = {"妙蛙种子": doc}
    with pytest.raises(DslError, match="可行性门"):
        e.legal_actions(0)


def test_playable_feasible_counters_trainer_not_blocked():
    """训练家卡语境 place_damage_counters 不被可行性门误拦（actions 宽松通过）。"""
    doc = parse_card_doc("""
card:
  name_group: 测试铺伤
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 3}}
""")
    state = main_state(p0_extra_hand=(inst(60, item_card("测试铺伤")),))
    e = engine_at(state)
    e.card_effects = {"测试铺伤": doc}
    assert Action(kind="play_trainer", iid=60) in e.legal_actions(0)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"  # 正常挂起选目标
