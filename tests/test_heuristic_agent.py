"""task 018：通用启发式 Agent（PRD §7.2 / D10 不做单卡组定制）。

验收口径见 `tasks/task 018.md`：协议合规 / 可见性纪律 / 布阵优先级 /
行动排序（特性→进化→能量→物品→支援者→攻击）/ 斩杀检测 / 推备 /
chooser 选择策略 / 确定性 tie-break / 参数对象可配置。
"""

from helpers import basic, energy, engine_at, in_play, inst, main_state, stage1

from battlefrontier.agent.base import Agent
from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams, evaluate
from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    GameState,
    PendingChoice,
    PlayerState,
)
from battlefrontier.runner.play import play_game

ABILITY_DOC = parse_card_doc("""
card:
  name_group: 特性手
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: draw, count: 1}
""")

ITEM_DOC = parse_card_doc("""
card:
  name_group: 测试物品
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")

SUPPORTER_DOC = parse_card_doc("""
card:
  name_group: 测试支援者
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 2}
""")


def trainer(name: str, subtype: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype=subtype)


def attacker(name: str, damages: tuple[int, ...], energy_type: str | None = None) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon", hp=70, stage=0,
        energy_type=energy_type,
        attacks=tuple(
            AttackDef(name=f"招式{i}", cost=("无",), damage=d) for i, d in enumerate(damages)
        ),
        retreat_cost=1,
    )


def setup_state(hand, phase="setup_active", bench=()):
    p0 = PlayerState(
        hand=tuple(hand),
        deck=tuple(inst(100 + i, basic("垫牌")) for i in range(10)),
        active=in_play(1, basic("已就位")) if phase == "setup_bench" else None,
        bench=bench,
    )
    p1 = PlayerState(deck=tuple(inst(300 + i, basic("对手垫牌")) for i in range(10)))
    return GameState(players=(p0, p1), current_player=0, phase=phase)


def engine_with(state: GameState, card_effects: dict | None = None) -> GameEngine:
    e = GameEngine(RandomSource(0), card_effects=card_effects)
    e.state = state
    return e


def decide(engine: GameEngine, agent: HeuristicAgent | None = None) -> Action:
    agent = agent or HeuristicAgent()
    view = engine.state.visible_state(0)
    return agent.observe(view, engine.legal_actions(0))


# ── 协议与可见性 ──────────────────────────────────────────

def test_implements_protocol_and_returns_legal_action():
    agent = HeuristicAgent()
    assert isinstance(agent, Agent)
    engine = engine_at(main_state())
    act = decide(engine, agent)
    assert act in engine.legal_actions(0)


def test_hidden_info_invariance():
    """对手手牌/牌库内容不同（数量相同）→ 决策必须一致（不碰隐藏信息）。"""
    state_a = main_state()
    p1 = state_a.players[1].model_copy(update={
        "deck": tuple(inst(300 + i, basic("杰尼龟")) for i in range(10)),
        "hand": (inst(90, basic("皮卡丘")),),
    })
    state_b = state_a.model_copy(update={"players": (state_a.players[0], p1)})
    agent = HeuristicAgent()
    assert decide(engine_at(state_a), agent) == decide(engine_at(state_b), agent)


# ── 开局布阵 ─────────────────────────────────────────────

def test_setup_active_picks_highest_score():
    hand = [inst(10, basic("弱小", hp=40, damage=10)), inst(11, basic("强壮", hp=100, damage=50)),
            inst(12, energy())]
    act = decide(engine_with(setup_state(hand)))
    assert act == Action(kind="place_active", iid=11)


def test_setup_active_tie_break_by_iid():
    hand = [inst(20, basic("甲")), inst(11, basic("乙"))]  # 同分 → 取 iid 小者（确定性）
    act = decide(engine_with(setup_state(hand)))
    assert act == Action(kind="place_active", iid=11)


def test_setup_bench_places_best_then_confirms():
    hand = [inst(10, basic("弱小", hp=40, damage=10)), inst(11, basic("强壮", hp=100, damage=50))]
    act = decide(engine_with(setup_state(hand, phase="setup_bench")))
    assert act == Action(kind="place_bench", iid=11)


def test_setup_bench_confirms_when_full_enough():
    bench = tuple(in_play(30 + i, basic(f"备战{i}")) for i in range(3))  # 默认 max_bench_setup=3
    hand = [inst(10, basic("强壮", hp=100, damage=50))]
    act = decide(engine_with(setup_state(hand, phase="setup_bench", bench=bench)))
    assert act == Action(kind="confirm_setup")


# ── 昏厥推备 ─────────────────────────────────────────────

def test_promote_picks_highest_score():
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": None,
        "bench": (in_play(30, basic("弱小", hp=40, damage=10)),
                  in_play(31, basic("强壮", hp=100, damage=50))),
    })
    state = state.model_copy(update={"players": (p0, state.players[1]), "phase": "promote"})
    assert decide(engine_with(state)) == Action(kind="promote", bench_index=1)


# ── 主阶段行动排序 ────────────────────────────────────────

def test_ability_before_everything():
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, basic("特性手", hp=80), 1)})
    state = state.model_copy(update={"players": (p0, state.players[1])})
    engine = engine_with(state, card_effects={"特性手": ABILITY_DOC})
    act = decide(engine)
    assert act.kind == "use_ability"


def test_evolve_before_energy_and_attack():
    state = main_state(p0_extra_hand=(inst(52, stage1("妙蛙草", "妙蛙种子")),))
    act = decide(engine_at(state))
    assert act == Action(kind="evolve", iid=52, target_iid=1)


def test_energy_to_active_when_it_cannot_attack():
    state = main_state(p0_active_energies=0)
    act = decide(engine_at(state))
    assert act == Action(kind="attach_energy", iid=51, target_iid=1)


def test_energy_to_bench_when_active_ready():
    state = main_state(p0_active_energies=1)
    p0 = state.players[0].model_copy(update={"bench": (in_play(3, basic("小火龙"), 0),)})
    state = state.model_copy(update={"players": (p0, state.players[1])})
    act = decide(engine_at(state))
    assert act == Action(kind="attach_energy", iid=51, target_iid=3)


def test_item_before_supporter():
    state = main_state(p0_extra_hand=(inst(60, trainer("测试物品", "物品")),
                                      inst(61, trainer("测试支援者", "支援者"))))
    engine = engine_with(state, card_effects={"测试物品": ITEM_DOC, "测试支援者": SUPPORTER_DOC})
    act = decide(engine)
    assert act == Action(kind="play_trainer", iid=60)


def test_supporter_before_attack_when_no_lethal():
    state = main_state(p0_extra_hand=(inst(61, trainer("测试支援者", "支援者")),))
    engine = engine_with(state, card_effects={"测试支援者": SUPPORTER_DOC})
    act = decide(engine)
    assert act == Action(kind="play_trainer", iid=61)


def test_attack_when_nothing_else():
    act = decide(engine_at(main_state()))
    assert act == Action(kind="attack", attack_index=0)


def test_end_turn_fallback():
    state = main_state(p0_active_energies=0)
    p0 = state.players[0].model_copy(update={"hand": ()})
    state = state.model_copy(update={"players": (p0, state.players[1])})
    assert decide(engine_at(state)) == Action(kind="end_turn")


# ── 斩杀检测 ─────────────────────────────────────────────

def _lethal_state(own_card: CardDef, opp_card: CardDef, opp_damage: int,
                  extra_hand: tuple = (), card_effects: dict | None = None) -> GameEngine:
    state = main_state(p0_extra_hand=extra_hand)
    p0 = state.players[0].model_copy(update={"active": in_play(1, own_card, 1)})
    p1 = state.players[1].model_copy(
        update={"active": in_play(2, opp_card, 1).model_copy(update={"damage": opp_damage})})
    return engine_with(state.model_copy(update={"players": (p0, p1)}), card_effects)


def test_lethal_beats_supporter():
    engine = _lethal_state(
        basic("打手", damage=20), basic("对手"), opp_damage=60,  # 剩余 10 ≤ 20
        extra_hand=(inst(61, trainer("测试支援者", "支援者")),),
        card_effects={"测试支援者": SUPPORTER_DOC})
    assert decide(engine) == Action(kind="attack", attack_index=0)


def test_lethal_prefers_lethal_over_higher_damage_nonlethal():
    # 招式0=20 不斩杀，招式1=30 斩杀（剩余 25）→ 选招式1
    engine = _lethal_state(attacker("双招式", (20, 30)), basic("对手"), opp_damage=45)
    assert decide(engine) == Action(kind="attack", attack_index=1)


def test_lethal_among_multiple_prefers_higher_damage():
    # 剩余 15，两招都斩杀 → 取伤害高者（招式1=30）
    engine = _lethal_state(attacker("双招式", (20, 30)), basic("对手"), opp_damage=55)
    assert decide(engine) == Action(kind="attack", attack_index=1)


def test_weakness_doubles_for_lethal_check():
    weak = CardDef(card_id="stub-弱火", name="弱火", supertype="pokemon", hp=70, stage=0,
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
                   retreat_cost=1, weakness="火")
    # 剩余 30：20×2=40 斩杀 → 攻击优先于支援者
    engine = _lethal_state(
        attacker("火手", (20,), energy_type="火"), weak, opp_damage=40,
        extra_hand=(inst(61, trainer("测试支援者", "支援者")),),
        card_effects={"测试支援者": SUPPORTER_DOC})
    assert decide(engine) == Action(kind="attack", attack_index=0)
    # 无弱点（剩余 30 > 20）→ 退回支援者
    engine2 = _lethal_state(
        attacker("火手", (20,), energy_type="火"), basic("对手"), opp_damage=40,
        extra_hand=(inst(61, trainer("测试支援者", "支援者")),),
        card_effects={"测试支援者": SUPPORTER_DOC})
    assert decide(engine2) == Action(kind="play_trainer", iid=61)


# ── chooser 选择策略 ─────────────────────────────────────

def test_choose_picks_highest_scored_card():
    strong, weak = basic("强壮", hp=100, damage=50), basic("弱小", hp=40, damage=10)
    p0 = PlayerState(
        deck=(inst(10, strong), inst(11, weak))
        + tuple(inst(100 + i, basic("垫牌")) for i in range(8)),
        active=in_play(1, basic("已就位")),
    )
    p1 = PlayerState(deck=tuple(inst(300 + i, basic("对手垫牌")) for i in range(10)))
    pc = PendingChoice(
        player=0, source=inst(60, trainer("测试物品", "物品")), effect_index=0, cursor=0,
        pool="own_deck", min_choose=1, max_choose=1, pool_iids=(10, 11),
    )
    state = GameState(players=(p0, p1), current_player=0, phase="choice", pending_choice=pc)
    act = decide(engine_with(state))
    assert act == Action(kind="choose", choices=(10,))


# ── 确定性与参数 ─────────────────────────────────────────

def test_deterministic_repeated_calls():
    engine = engine_at(main_state())
    view, actions = engine.state.visible_state(0), engine.legal_actions(0)
    agent = HeuristicAgent()
    assert agent.observe(view, actions) == agent.observe(view, actions)
    assert agent.observe(view, actions) == HeuristicAgent().observe(view, actions)


def test_params_change_decision():
    # 高HP低伤 vs 低HP高伤：默认重伤害选后者；w_damage 调低后选前者
    hand = [inst(10, basic("肉盾", hp=120, damage=10)), inst(11, basic("炮手", hp=60, damage=40))]
    engine = engine_with(setup_state(hand))
    assert decide(engine) == Action(kind="place_active", iid=11)
    assert decide(engine, HeuristicAgent(HeuristicParams(w_damage=0.1))) == \
        Action(kind="place_active", iid=10)


def test_evaluate_rewards_opponent_prize_lead():
    engine = engine_at(main_state())
    base = evaluate(engine.state.visible_state(0), HeuristicParams())
    state = engine.state
    p1 = state.players[1].model_copy(update={"prizes": state.players[1].prizes[:5]})
    ahead = evaluate(
        state.model_copy(update={"players": (state.players[0], p1)}).visible_state(0),
        HeuristicParams())
    assert ahead > base


# ── 集成冒烟 ─────────────────────────────────────────────

def test_smoke_heuristic_vs_random_and_mirror():
    from helpers import deck60

    from battlefrontier.agent.random_agent import RandomAgent
    for seed in (7, 8):
        r = play_game(deck60(), deck60(), seed=seed,
                      agents=[HeuristicAgent(), RandomAgent(RandomSource(seed + 5))])
        assert r.phase == "game_over" and r.turns <= 200
    mirror = play_game(deck60(), deck60(), seed=9,
                       agents=[HeuristicAgent(), HeuristicAgent()])
    assert mirror.phase == "game_over"
