"""task 016：evolve 原语（神奇糖果跳阶 + 招式学习器「进化」）+ 授予招式执行。

规则出处：rules-manual §4（进化：特殊状态恢复、伤害保留；当回合登场/已进化不可再
进化）；神奇糖果 text_raw「（在自己最初的回合，以及对这个回合刚出场的宝可梦无法
使用。）」；学习器「进化」text_raw「选择自己最多2只备战宝可梦，从自己牌库中选择
从该宝可梦进化而来的卡牌各1张，各放于其身上进行进化。并重洗牌库。」。
链拓扑数据驱动：CardDef.evolution_chain（db evolution_chain_id），引擎零硬编码。
"""

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import load_card_dir, parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef, SpecialCondition

CHAIN_R = "ch-ralts"
CHAIN_C = "ch-char"


def ralts() -> CardDef:
    return CardDef(card_id="stub-拉鲁拉丝", name="拉鲁拉丝", supertype="pokemon",
                   hp=70, stage=0, evolution_chain=CHAIN_R,
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),), retreat_cost=1)


def kirlia() -> CardDef:
    return CardDef(card_id="stub-奇鲁莉安", name="奇鲁莉安", supertype="pokemon",
                   hp=90, stage=1, evolves_from="拉鲁拉丝", evolution_chain=CHAIN_R,
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),), retreat_cost=1)


def gardevoir_s2() -> CardDef:
    return CardDef(card_id="stub-沙奈朵", name="沙奈朵", supertype="pokemon",
                   hp=310, stage=2, evolves_from="奇鲁莉安", evolution_chain=CHAIN_R,
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),), retreat_cost=1)


def charmander() -> CardDef:
    return CardDef(card_id="stub-小火龙c", name="小火龙c", supertype="pokemon",
                   hp=70, stage=0, evolution_chain=CHAIN_C,
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),), retreat_cost=1)


def charmeleon() -> CardDef:
    return CardDef(card_id="stub-火恐龙", name="火恐龙", supertype="pokemon",
                   hp=90, stage=1, evolves_from="小火龙c", evolution_chain=CHAIN_C,
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),), retreat_cost=1)


def candy() -> CardDef:
    return CardDef(card_id="stub-神奇糖果", name="神奇糖果", supertype="trainer",
                   trainer_subtype="物品")


def learner() -> CardDef:
    return CardDef(card_id="stub-招式学习器 进化", name="招式学习器 进化",
                   supertype="trainer", trainer_subtype="宝可梦道具",
                   attacks=(AttackDef(name="进化", cost=("无",), damage=None),))


CANDY_DOC = parse_card_doc("""
card:
  name_group: 神奇糖果
effects:
  - trigger: on_play
    actions:
      - {action: evolve, selector: own_hand, choose: 1, filters: [stage2_pokemon], args: {mode: skip_stage}}
""")

LEARNER_FULL_DOC = parse_card_doc("""
card:
  name_group: 招式学习器 进化
effects:
  - trigger: passive_static
    actions:
      - {action: grant_attack, args: {attack: 进化, discard_at_turn_end: true}}
  - trigger: on_attack
    attack: 进化
    actions:
      - {action: evolve, selector: own_bench, choose: 2, args: {mode: from_deck}}
      - {action: shuffle_deck}
""")


def candy_engine(*, hand_extra=(), active=None, bench=(), turn=None,
                 entered: frozenset = frozenset()):
    """main 局面：p0 手牌含神奇糖果（iid 60）+ hand_extra；active/bench 可自带。"""
    state = main_state(p0_extra_hand=(inst(60, candy()), *hand_extra))
    updates = {}
    if active is not None:
        updates["active"] = active
    if bench:
        updates["bench"] = bench
    if entered:
        updates["entered_play_this_turn"] = entered
    p0 = state.players[0].model_copy(update=updates)
    state = state.model_copy(update={"players": (p0, state.players[1])})
    if turn is not None:
        state = state.model_copy(update={"turn": turn})
    e = engine_at(state)
    e.card_effects = {"神奇糖果": CANDY_DOC}
    return e


def play_candy_actions(e):
    return [a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]


def learner_engine(*, holder_energy=1, bench=(), deck=(), holder_card=None):
    """main 局面：p0 战斗场 = 带学习器（iid 90）的 holder；deck 全量替换。"""
    holder = in_play(1, holder_card or basic("妙蛙种子"), holder_energy)
    holder = holder.model_copy(update={"attached_tool": inst(90, learner())})
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": holder, "bench": bench,
        "deck": deck or state.players[0].deck,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"招式学习器 进化": LEARNER_FULL_DOC}
    return e


def choose_actions(e, player=0):
    return [a for a in e.legal_actions(player) if a.kind == "choose"]


# ── 神奇糖果：两段式跳阶进化 ─────────────────────────────────────────────

def test_candy_two_stage_flow() -> None:
    """手牌 stage2 跳阶放到同链基础身上：状态清除、伤害保留、本体进弃牌区。"""
    target = in_play(1, ralts())
    target = target.model_copy(update={"damage": 20, "conditions": {SpecialCondition.CONFUSED}})
    e = candy_engine(hand_extra=(inst(61, gardevoir_s2()),), active=target)
    acts = play_candy_actions(e)
    assert len(acts) == 1
    e.apply(0, acts[0])
    # 第一段：选手牌 stage2
    picks = choose_actions(e)
    assert (61,) in [a.choices for a in picks]
    e.apply(0, next(a for a in picks if a.choices == (61,)))
    # 第二段：选同链基础目标
    picks = choose_actions(e)
    assert [a.choices for a in picks] == [(1,)]
    e.apply(0, picks[0])
    p0 = e.state.players[0]
    assert p0.active.current.card.name == "沙奈朵"
    assert len(p0.active.stack) == 2
    assert p0.active.damage == 20  # 伤害保留
    assert p0.active.conditions == frozenset()  # 特殊状态恢复（rules-manual §4）
    assert 61 in p0.evolved_this_turn
    assert 60 in [c.iid for c in p0.discard]  # 糖果本体进弃牌区
    assert any(ev.kind == "evolve" for ev in e.events)


def test_candy_gate_no_stage2_in_hand() -> None:
    e = candy_engine(active=in_play(1, ralts()))
    assert play_candy_actions(e) == []


def test_candy_gate_no_matching_basic() -> None:
    """手牌有 stage2 但场上无同链基础 → 不枚举。"""
    e = candy_engine(hand_extra=(inst(61, gardevoir_s2()),),
                     active=in_play(1, charmander()))
    assert play_candy_actions(e) == []


def test_candy_gate_entered_this_turn() -> None:
    """「对这个回合刚出场的宝可梦无法使用」：唯一同链基础当回合登场 → 不枚举。"""
    e = candy_engine(hand_extra=(inst(61, gardevoir_s2()),),
                     active=in_play(1, ralts()), entered=frozenset({1}))
    assert play_candy_actions(e) == []


def test_candy_gate_first_turn() -> None:
    """「在自己最初的回合无法使用」：turn==1（双方各自首回合都在 game turn 1 内）。"""
    e = candy_engine(hand_extra=(inst(61, gardevoir_s2()),),
                     active=in_play(1, ralts()), turn=1)
    assert play_candy_actions(e) == []


def test_candy_wrong_chain_target_not_in_pool() -> None:
    """异链基础不进第二段选择池。"""
    e = candy_engine(hand_extra=(inst(61, gardevoir_s2()),),
                     active=in_play(1, charmander()),
                     bench=(in_play(70, ralts()),))
    e.apply(0, play_candy_actions(e)[0])
    e.apply(0, next(a for a in choose_actions(e) if a.choices == (61,)))
    assert [a.choices for a in choose_actions(e)] == [(70,)]


# ── 招式学习器：授予招式枚举与「进化」攻击流程 ───────────────────────────

def test_granted_attack_enumerated_with_energy() -> None:
    """授予招式 attack_index 接自身招式后；能量不足不枚举。"""
    e = learner_engine(holder_energy=1)
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert [a.attack_index for a in attacks] == [0, 1]  # 0=打击（自身） 1=进化（授予）
    e = learner_engine(holder_energy=0)
    assert [a for a in e.legal_actions(0) if a.kind == "attack"] == []


def test_learner_evolve_attack_flow() -> None:
    """选 2 只备战 → 逐只牌库检索进化 → 洗牌 → 道具回合末弃置 → 对手回合。"""
    deck = (inst(100, kirlia()), inst(101, charmeleon()),
            *(inst(110 + i, basic("妙蛙种子")) for i in range(5)))
    bench = (in_play(70, ralts()), in_play(71, charmander()))
    e = learner_engine(bench=bench, deck=deck)
    e.apply(0, Action(kind="attack", attack_index=1))
    # 第一段：选 ≤2 备战（两只牌库都有进化形态）
    picks = [a.choices for a in choose_actions(e)]
    assert (70, 71) in picks
    e.apply(0, next(a for a in choose_actions(e) if a.choices == (70, 71)))
    # 第二段：第一只（70 拉鲁拉丝）牌库选进化形态
    picks = [a.choices for a in choose_actions(e)]
    assert (100,) in picks and (101,) not in picks  # 只给「从拉鲁拉丝进化而来」的
    e.apply(0, next(a for a in choose_actions(e) if a.choices == (100,)))
    # 第三段：第二只（71 小火龙c）
    picks = [a.choices for a in choose_actions(e)]
    assert (101,) in picks and (100,) not in picks
    e.apply(0, next(a for a in choose_actions(e) if a.choices == (101,)))
    p0 = e.state.players[0]
    assert p0.bench[0].current.card.name == "奇鲁莉安"
    assert p0.bench[1].current.card.name == "火恐龙"
    assert {100, 101} <= p0.evolved_this_turn
    assert any(ev.kind == "shuffle" or ev.kind == "effect_primitive" for ev in e.events)
    assert 90 in [c.iid for c in p0.discard]  # 学习器回合末弃置（task 015 机制）
    assert e.state.current_player == 1  # 攻击后回合结束


def test_learner_bench_without_evolution_excluded() -> None:
    """牌库无进化形态的备战宝可梦不进第一段池。"""
    deck = (inst(100, kirlia()),)  # 只有拉鲁拉丝的进化形态
    bench = (in_play(70, ralts()), in_play(71, charmander()))
    e = learner_engine(bench=bench, deck=deck)
    e.apply(0, Action(kind="attack", attack_index=1))
    picks = [a.choices for a in choose_actions(e)]
    assert (70,) in picks and (71,) not in picks and (70, 71) not in picks


def test_learner_choose_zero_still_shuffles() -> None:
    """「最多2只」= 可不选；空选后仍洗牌、回合正常结束。"""
    bench = (in_play(70, ralts()),)
    e = learner_engine(bench=bench, deck=(inst(100, kirlia()),))
    e.apply(0, Action(kind="attack", attack_index=1))
    e.apply(0, next(a for a in choose_actions(e) if a.choices == ()))
    p0 = e.state.players[0]
    assert p0.bench[0].current.card.name == "拉鲁拉丝"  # 未进化
    assert e.state.current_player == 1
    assert 90 in [c.iid for c in p0.discard]


# ── 定义库与对局级确定性 ────────────────────────────────────────────────

def test_card_library_twenty() -> None:
    docs = load_card_dir("cards")
    # 定义库总数断言由最新入库任务的测试持有（当前 test_m2_closeout::test_card_library_m2_closeout）
    assert "神奇糖果" in docs
    candy_eff = docs["神奇糖果"].effects[0]
    assert candy_eff.actions[0].action == "evolve"
    assert candy_eff.actions[0].args["mode"] == "skip_stage"
    learner_doc = docs["招式学习器 进化"]
    bound = [e for e in learner_doc.effects if e.trigger == "on_attack"]
    assert len(bound) == 1 and bound[0].attack == "进化"


def test_play_game_with_evolve_deterministic() -> None:
    """含神奇糖果/学习器的整局对局：同种子事件流 hash 一致。"""
    from battlefrontier.runner.play import play_game

    deck = ([ralts()] * 16 + [kirlia()] * 4 + [gardevoir_s2()] * 4
            + [candy()] * 4 + [learner()] * 2
            + [energy("基本超能量", "超")] * 15 + [energy()] * 15)
    effects = load_card_dir("cards")
    r1 = play_game(deck, deck, seed=23, card_effects=effects)
    r2 = play_game(deck, deck, seed=23, card_effects=effects)
    assert r1.events_hash == r2.events_hash
