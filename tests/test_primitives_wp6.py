"""task 026 WP6 机制测试：hand_disrupt（雪童子 惊吓）/ bench_size 覆写+失效缩减
（零之大空洞）/ search choose_groups（小刚的发掘）/ distinct+split（赤松）/
deck_top 有序去向（暗码迷的解读）/ own_ko_by_attack + lock_retreat（沙铃仙人掌）/
protection + own_attached_energy choose=1（火恐龙）/ devolve（招式学习器 退化）。

设计决议（tasks/task 026.md WP6 节，2026-09-14 定稿）：
- D-WP6-1 hand_disrupt：「不看正面选择」= 均匀随机（rng.randbelow）；「查看正面」=
  reveal 结构化事件；「放回牌库并重洗」= 入对手牌库后 rng.shuffle；空手 no-op 伤害照算。
- D-WP6-2 bench_size：声明式（passive_static + condition 逐玩家求值，引擎 _bench_size
  读声明取 max，无竞技场/条件不成立 → 5）。失效缩减走 bench_shrink 阶段：超容玩家
  逐只自选弃置（整叠进弃牌、非昏厥无奖赏），双方同缩由（旧）竞技场持有者先；
  战斗场太晶被昏厥先换上（promote 消耗 1 备战位）再缩减。
- D-WP6-3 choose_groups：组间互斥（各组独立 up-to，混合不可达），仅 hand 去向。
- D-WP6-4 distinct+split：distinct=energy_type 分桶互异（桶数 < choose 自动收缩）；
  split=hand_attach 三段流（选能量 → 选入手 1 张 → 剩余附着自己场上 1 只）。
- D-WP6-5 deck_top ordered：选择顺序即牌顶 FIFO；余库本节点内重洗（不写 shuffle 节点）。
- D-WP6-6 own_ko_by_attack：仅战斗场+对手招式伤害致昏厥触发；来源从弃牌区解析
  （离场即失效的场上查找跳过）；opponent_attacker 指向攻击方（已离场 no-op）。
  lock_retreat：目标下个自己回合无法撤退（其回合结束/进化解除）。
- D-WP6-7 protection：招式效果落点守卫（指示物跳过/状态不适用），伤害本体不免疫，
  训练家卡效果不受保护；D-WP6-8 devolve：对手全场各退栈顶 1 张回其手牌，
  伤害保留/状态恢复，HP 超限昏厥走既有 check_knockouts。
"""

import pytest
from helpers import basic, energy, in_play, inst, main_state, stage1

from battlefrontier.dsl import ExecutionContext, parse_card_doc, run_effect
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    InPlayPokemon,
    SpecialCondition,
)


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def stadium_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="竞技场")


def stage2(name: str, evolves_from: str, hp: int = 100) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=hp, stage=2, evolves_from=evolves_from,
                   attacks=(AttackDef(name="打击", cost=("无",), damage=40),))


def stacked(*cards, damage: int = 0, conditions=frozenset()) -> InPlayPokemon:
    return InPlayPokemon(stack=tuple(cards), damage=damage, conditions=conditions)


def bench_mons(start: int, n: int) -> tuple:
    return tuple(in_play(start + i, basic(f"备战{start + i}")) for i in range(n))


def engine_at_seed(state, seed: int) -> GameEngine:
    e = GameEngine(RandomSource(seed))
    e.state = state
    return e


def attack_engine(doc, attacker: CardDef, *, p0_hand=(), p0_bench=(), p0_discard=(),
                  p0_deck=None, p0_energies=(), p1_active=None, p1_bench=(),
                  p1_hand=None, p1_deck=None, p1_prizes: int = 6,
                  seed: int = 0, turn: int = 2, extra_effects: dict | None = None):
    """main 阶段：p0 战斗场攻击者（iid 1）+ 可调手牌/备战/牌库，p1 战斗场可调。"""
    state = main_state()
    active = in_play(1, attacker)
    if p0_energies:
        active = active.model_copy(update={"attached_energy": p0_energies})
    p0 = state.players[0].model_copy(update={
        "active": active, "bench": p0_bench, "discard": p0_discard, "hand": p0_hand,
    })
    if p0_deck is not None:
        p0 = p0.model_copy(update={"deck": p0_deck})
    p1 = state.players[1].model_copy(update={
        "bench": p1_bench,
        "active": in_play(2, basic("硬兽", hp=500), 1),
        "prizes": state.players[1].prizes[:p1_prizes],
    })
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
    if p1_deck is not None:
        p1 = p1.model_copy(update={"deck": p1_deck})
    e = engine_at_seed(state.model_copy(update={
        "players": (p0, p1), "turn": turn,
    }), seed)
    e.card_effects = {attacker.name: doc, **(extra_effects or {})}
    return e


def play_engine(doc, name: str = "测试卡", *, p0_bench: tuple = (), discard: tuple = (),
                deck=None, extra_hand: tuple = (), kind="item", p1_prizes: int = 6,
                p1_bench: tuple = (), p1_active=None, p1_hand=None, p0_active=None,
                seed: int = 0):
    """main 阶段：p0 手牌含测试训练家卡（iid 60）。"""
    card_fn = item_card if kind == "item" else supporter_card
    state = main_state(p0_extra_hand=(inst(60, card_fn(name)),) + extra_hand)
    p0 = state.players[0].model_copy(update={"bench": p0_bench, "discard": discard})
    if deck is not None:
        p0 = p0.model_copy(update={"deck": deck})
    if p0_active is not None:
        p0 = p0.model_copy(update={"active": p0_active})
    p1 = state.players[1].model_copy(update={
        "prizes": state.players[1].prizes[:p1_prizes], "bench": p1_bench,
    })
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
    e = engine_at_seed(state.model_copy(update={"players": (p0, p1)}), seed)
    e.card_effects = {name: doc}
    return e


def stadium_engine(doc, *, p0_active=None, p0_bench: tuple = (), p0_hand=None,
                   p0_deck=None, p1_active=None, p1_bench: tuple = (), p1_hand=None,
                   owner: int = 0, current: int = 0, turn: int = 3,
                   with_stadium: bool = True, seed: int = 0,
                   extra_effects: dict | None = None):
    """main 阶段：场上挂测试竞技场（iid 399，默认持有者 p0）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={"bench": p0_bench})
    if p0_active is not None:
        p0 = p0.model_copy(update={"active": p0_active})
    if p0_hand is not None:
        p0 = p0.model_copy(update={"hand": p0_hand})
    if p0_deck is not None:
        p0 = p0.model_copy(update={"deck": p0_deck})
    p1 = state.players[1].model_copy(update={"bench": p1_bench})
    if p1_active is not None:
        p1 = p1.model_copy(update={"active": p1_active})
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
    update: dict[str, object] = {
        "players": (p0, p1), "current_player": current, "turn": turn,
    }
    if with_stadium:
        update["stadium"] = inst(399, stadium_card("大空洞"))
        update["stadium_owner"] = owner
    e = engine_at_seed(state.model_copy(update=update), seed)
    e.card_effects = {"大空洞": doc, **(extra_effects or {})}
    return e


def run_doc(e, doc, source, player: int = 0):
    """直接跑效果（绕过可行性门）：DslError/no-op 等原语层语义用。"""
    ctx = ExecutionContext(engine=e, player=player, source=source,
                           effect_id="test", trigger=doc.effects[0].trigger)
    return run_effect(ctx, doc.effects[0])


def prim_results(e, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


# ── hand_disrupt（雪童子 惊吓）（清单 1-3）────────────────────────────────────

SNOWLUNT_DOC = parse_card_doc("""
card:
  name_group: 雪童子
effects:
  - trigger: on_attack
    attack: 惊吓
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 20}}
      - {action: hand_disrupt, selector: opponent_hand}
""")


def snowlunt() -> CardDef:
    return CardDef(
        card_id="stub-雪童子", name="雪童子", supertype="pokemon",
        hp=60, stage=0, energy_type="水", weakness="钢", retreat_cost=1,
        attacks=(AttackDef(name="惊吓", cost=("水", "无"), damage=None),),
    )


def snow_energies() -> tuple:
    return (inst(9001, energy("水能量", "水")), inst(9002, energy("水能量", "水")))


def test_hand_disrupt_full_flow_reveal_seed_deterministic():
    """清单1：伤害 20 照算 + 随机看 1 张对手手牌（reveal 事件）→ 洗回对手牌库；
    同种子复跑 disrupt 对象与牌库序逐局一致（种子确定性硬规矩）。"""
    hand = (inst(50, basic("对手甲")), inst(51, basic("对手乙")), inst(52, energy()))
    deck = tuple(inst(300 + i, basic(f"对手库{i}")) for i in range(5))
    runs = []
    for _ in range(2):
        e = attack_engine(SNOWLUNT_DOC, snowlunt(), p0_energies=snow_energies(),
                          p1_hand=hand, p1_deck=deck, seed=7)
        e.apply(0, Action(kind="attack", attack_index=0))
        p1 = e.state.players[1]
        assert p1.active.damage == 20  # 伤害照算
        reveal = next(ev for ev in e.events if ev.kind == "reveal")
        disrupted = reveal.detail["iids"][0]
        assert disrupted in (50, 51, 52)  # 随机对象来自对手手牌
        # 回合权移交后对手回合开始抽 1 张（rules-manual·回合流程）：hand −1（扰乱）
        # +1（抽牌）= 3，deck +1（洗回）−1（抽牌）= 5；「洗回牌库」用稳健断言——
        # hand∪deck 全集不变（洗回牌有概率被回合开始抽牌抽中，仅在 deck 不稳健）
        assert len(p1.hand) == 3 and len(p1.deck) == 5
        assert sorted(c.iid for c in (*p1.hand, *p1.deck)) == [
            50, 51, 52, 300, 301, 302, 303, 304,
        ]
        assert e.state.phase == "main" and e.state.current_player == 1
        runs.append((disrupted, tuple(c.iid for c in p1.deck)))
    assert runs[0] == runs[1]  # 同种子复跑一致


def test_hand_disrupt_empty_hand_noop_damage_applies():
    """清单2：对手空手 → 扰乱 no-op（disrupted=0/empty_hand，无 reveal），伤害 20 照算。"""
    e = attack_engine(SNOWLUNT_DOC, snowlunt(), p0_energies=snow_energies(),
                      p1_hand=())
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
    assert not [ev for ev in e.events if ev.kind == "reveal"]
    assert prim_results(e, "hand_disrupt") == [{"disrupted": 0, "reason": "empty_hand"}]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_hand_disrupt_bad_forms_dsl_error():
    """清单3：selector 非 opponent_hand / 带 count / 带 choose → DslError（不猜）。"""
    bad_selector = parse_card_doc("""
card:
  name_group: 雪童子
effects:
  - trigger: on_attack
    attack: 惊吓
    actions:
      - {action: hand_disrupt, selector: own_hand}
""")
    e = attack_engine(bad_selector, snowlunt(), p0_energies=snow_energies())
    with pytest.raises(DslError, match="hand_disrupt"):
        e.apply(0, Action(kind="attack", attack_index=0))

    bad_count = parse_card_doc("""
card:
  name_group: 雪童子
effects:
  - trigger: on_attack
    attack: 惊吓
    actions:
      - {action: hand_disrupt, selector: opponent_hand, count: 1}
""")
    e2 = attack_engine(bad_count, snowlunt(), p0_energies=snow_energies())
    with pytest.raises(DslError, match="hand_disrupt"):
        e2.apply(0, Action(kind="attack", attack_index=0))

    bad_choose = parse_card_doc("""
card:
  name_group: 雪童子
effects:
  - trigger: on_attack
    attack: 惊吓
    actions:
      - {action: hand_disrupt, selector: opponent_hand, choose: 1}
""")
    e3 = attack_engine(bad_choose, snowlunt(), p0_energies=snow_energies())
    with pytest.raises(DslError, match="hand_disrupt"):
        e3.apply(0, Action(kind="attack", attack_index=0))


# ── bench_size 覆写 + 失效缩减（零之大空洞）（清单 4-8）────────────────────────

HOLE_DOC = parse_card_doc("""
card:
  name_group: 零之大空洞
effects:
  - trigger: passive_static
    condition: own_tera_in_play
    actions:
      - {action: bench_size, args: {value: 8}}
""")


def tera_mon(name: str = "太晶兽", hp: int = 130) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=0, is_tera=True,
        attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
    )


def test_bench_size_tera_stadium_allows_eight():
    """清单4：太晶在场 + 零之大空洞 → 备战区手动放置放到 8 只（第 9 只不枚举）。"""
    e = stadium_engine(HOLE_DOC, p0_active=in_play(1, tera_mon()),
                       p0_bench=bench_mons(70, 5),
                       p0_hand=tuple(inst(50 + i, basic(f"手{i}")) for i in range(4)))
    for _ in range(3):
        acts = [a for a in e.legal_actions(0) if a.kind == "place_bench"]
        assert acts
        e.apply(0, acts[0])
    assert len(e.state.players[0].bench) == 8
    assert not [a for a in e.legal_actions(0) if a.kind == "place_bench"]


def test_bench_size_opponent_without_tera_capped_five():
    """清单4：condition 逐玩家求值——对手场上无太晶 → 仍 5 只上限。"""
    e = stadium_engine(HOLE_DOC, p0_active=in_play(1, tera_mon()),
                       p1_bench=bench_mons(80, 5),
                       p1_hand=(inst(90, basic("对手手")),), current=1)
    assert not [a for a in e.legal_actions(1) if a.kind == "place_bench"]


def test_bench_size_search_to_bench_capacity_eight():
    """清单5：检索直放备战区容量 8——bench 6 时 choose=3 截断为 2（超出经 exclude 剔除）。"""
    search3_doc = parse_card_doc("""
card:
  name_group: 测试巢穴
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_pokemon], choose: 3, destination: bench}
      - {action: shuffle_deck}
""")
    deck = (inst(100, basic("甲")), inst(101, basic("乙")),
            inst(102, basic("丙")), inst(103, energy()))
    e = stadium_engine(HOLE_DOC, p0_active=in_play(1, tera_mon()),
                       p0_bench=bench_mons(70, 6),
                       p0_hand=(inst(60, item_card("测试巢穴")),),
                       p0_deck=deck, extra_effects={"测试巢穴": search3_doc})
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.max_choose == 2  # 容量 8−6=2 截断
    assert pc.pool_iids == (100, 101)  # 第 3 张（102）被容量剔除
    e.apply(0, Action(kind="choose", choices=(100, 101)))
    assert len(e.state.players[0].bench) == 8


def test_bench_size_replaced_shrink_flow_resume_main():
    """清单6：竞技场被顶 → 超容方自选弃置至 5（整叠进弃牌、非昏厥无奖赏）→ 回出牌方主阶段。"""
    e = stadium_engine(HOLE_DOC, p0_active=in_play(1, tera_mon()),
                       p0_bench=bench_mons(70, 6),
                       p1_hand=(inst(90, stadium_card("新竞技场")),),
                       current=1, owner=0)
    e.apply(1, Action(kind="play_stadium", iid=90))
    assert e.state.phase == "bench_shrink" and e.state.current_player == 0
    acts = e.legal_actions(0)
    assert {a.kind for a in acts} == {"shrink_bench"}
    assert {a.choices for a in acts} == {(i,) for i in range(70, 76)}
    e.apply(0, Action(kind="shrink_bench", choices=(72,)))
    p0 = e.state.players[0]
    assert [b.current.iid for b in p0.bench] == [70, 71, 73, 74, 75]
    assert 72 in [c.iid for c in p0.discard]
    assert 399 in [c.iid for c in p0.discard]  # 旧竞技场进持有者弃牌区（既有行为）
    assert not [ev for ev in e.events if ev.kind == "take_prize"]  # 缩减非昏厥无奖赏
    assert any(ev.kind == "bench_shrink" for ev in e.events)
    assert e.state.phase == "main" and e.state.current_player == 1  # resume 出牌方主阶段


def test_bench_size_both_overflow_holder_first():
    """清单6：双方同缩 →（旧）竞技场持有者先执行（原文「由这张卡牌的持有者开始执行」）。"""
    e = stadium_engine(HOLE_DOC, p0_active=in_play(1, tera_mon()),
                       p0_bench=bench_mons(70, 6),
                       p1_active=in_play(2, tera_mon("对手太晶")),
                       p1_bench=bench_mons(80, 6),
                       p1_hand=(inst(90, stadium_card("新竞技场")),),
                       current=1, owner=0)
    e.apply(1, Action(kind="play_stadium", iid=90))
    assert e.state.bench_shrink_queue == (0, 1)  # 持有者 p0 先
    assert e.state.phase == "bench_shrink" and e.state.current_player == 0
    e.apply(0, Action(kind="shrink_bench", choices=(70,)))
    assert e.state.phase == "bench_shrink" and e.state.current_player == 1
    e.apply(1, Action(kind="shrink_bench", choices=(80,)))
    assert e.state.phase == "main" and e.state.current_player == 1
    assert len(e.state.players[0].bench) == 5
    assert len(e.state.players[1].bench) == 5


def test_bench_size_tera_ko_promote_then_shrink():
    """清单7：战斗场太晶被招式昏厥 → 先换上（promote 消耗 1 备战位）再缩减 → begin_turn。"""
    e = attack_engine(None, basic("攻击兽", hp=200, damage=100, cost=1),
                      p0_energies=(inst(9001, energy()),),
                      p1_active=in_play(2, tera_mon("太晶兽", hp=30)),
                      p1_bench=bench_mons(80, 7))
    e.state = e.state.model_copy(update={
        "stadium": inst(399, stadium_card("大空洞")), "stadium_owner": 0,
    })
    e.card_effects = {"大空洞": HOLE_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))  # 80 上战斗场，备战剩 6 只
    assert e.state.phase == "bench_shrink" and e.state.current_player == 1
    e.apply(1, Action(kind="shrink_bench", choices=(83,)))
    p1 = e.state.players[1]
    assert [b.current.iid for b in p1.bench] == [81, 82, 84, 85, 86]
    assert 83 in [c.iid for c in p1.discard]
    assert e.state.phase == "main" and e.state.current_player == 1
    kinds = [ev.kind for ev in e.events]
    assert kinds.index("promote") < kinds.index("bench_shrink")  # 换上先于缩减
    assert len([ev for ev in e.events if ev.kind == "take_prize"]) == 1  # 仅昏厥的 1 次


def test_bench_size_no_stadium_regression_five():
    """清单8：无竞技场 → 5（回归）；太晶在场但无竞技场 → 仍 5。"""
    e = stadium_engine(HOLE_DOC, p0_bench=bench_mons(70, 5),
                       p0_hand=(inst(50, basic("手甲")),), with_stadium=False)
    assert not [a for a in e.legal_actions(0) if a.kind == "place_bench"]
    e2 = stadium_engine(HOLE_DOC, p0_active=in_play(1, tera_mon()),
                        p0_bench=bench_mons(70, 5),
                        p0_hand=(inst(50, basic("手甲")),), with_stadium=False)
    assert not [a for a in e2.legal_actions(0) if a.kind == "place_bench"]


def test_bench_size_bad_value_dsl_error():
    """清单8 + 复核 M-1：value 非正 int / 非 int / 小于规则基准 5 / 超绝对上限 8
    → DslError（求值点不猜；静默钳回违反「覆写」语义）。"""
    for raw in ("0", "-1", '"8"', "4", "9"):
        bad = parse_card_doc(f"""
card:
  name_group: 零之大空洞
effects:
  - trigger: passive_static
    condition: own_tera_in_play
    actions:
      - {{action: bench_size, args: {{value: {raw}}}}}
""")
        e = stadium_engine(bad, p0_active=in_play(1, tera_mon()))
        with pytest.raises(DslError, match="bench_size"):
            e.legal_actions(0)


# ── search choose_groups（小刚的发掘 二选一组合约束）（清单 9-11）────────────────

BROCK_DOC = parse_card_doc("""
card:
  name_group: 小刚的发掘
effects:
  - trigger: on_play
    actions:
      - action: search_deck
        selector: own_deck
        destination: hand
        args:
          choose_groups:
            - {filters: [basic_pokemon], choose: 2}
            - {filters: [evolved_pokemon], choose: 1}
      - {action: reveal, selector: own_hand, filters: [pokemon]}
      - {action: shuffle_deck}
""")


def brock_deck() -> tuple:
    return (
        inst(100, basic("基甲")), inst(101, basic("基乙")),
        inst(102, stage1("进甲", "基甲")), inst(103, stage1("进乙", "基乙")),
        inst(104, item_card("物品甲")), inst(105, energy()),
    )


def brock_engine(deck=None):
    return play_engine(BROCK_DOC, "小刚的发掘", kind="supporter",
                       deck=deck if deck is not None else brock_deck())


def test_choose_groups_enumeration_exclusive():
    """清单9：枚举 = 基础子集（0-2 张）∪ 进化单选（0-1 张），混合不可达。"""
    e = brock_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.pool_iids == (100, 101, 102, 103)  # 训练家/能量不进池
    choices = {a.choices for a in e.legal_actions(0)}
    assert choices == {(), (100,), (101,), (100, 101), (102,), (103,)}


def test_choose_groups_pick_two_basics_hand_reveal_shuffle():
    """清单9：选 2 张基础 → 入手 + reveal（给对手看过）+ 重洗（同种子复跑牌序一致）。"""
    orders = []
    for _ in range(2):
        e = brock_engine()
        e.apply(0, Action(kind="play_trainer", iid=60))
        e.apply(0, Action(kind="choose", choices=(100, 101)))
        p0 = e.state.players[0]
        assert {100, 101} <= {c.iid for c in p0.hand}
        assert sorted(c.iid for c in p0.deck) == [102, 103, 104, 105]
        reveal = next(ev for ev in e.events if ev.kind == "reveal")
        assert {100, 101} <= set(reveal.detail["iids"])
        assert prim_results(e, "shuffle_deck")  # 重洗执行
        assert e.state.phase == "main" and e.state.current_player == 0
        orders.append(tuple(c.iid for c in p0.deck))
    assert orders[0] == orders[1]


def test_choose_groups_pick_zero_noop_shuffle():
    """清单10：选 0（可以不找）→ no-op，重洗仍执行。"""
    e = brock_engine()
    hand_before = tuple(c.iid for c in e.state.players[0].hand)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    # 打出的支援者本体离场进弃牌区（WP3 先例口径，test_primitives_wp3.py:585）
    assert tuple(c.iid for c in p0.hand) == tuple(i for i in hand_before if i != 60)
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 104, 105]
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


def test_choose_groups_pool_shrink():
    """清单10：组池不足按池收缩（仅 1 基础、无进化 → 枚举收缩）。"""
    deck = (inst(100, basic("基甲")), inst(104, item_card("物品甲")))
    e = brock_engine(deck=deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    choices = {a.choices for a in e.legal_actions(0)}
    assert choices == {(), (100,)}


def test_choose_groups_bad_forms_dsl_error():
    """清单11：choose_groups 与 choose/filters 并存、destination≠hand、畸形组 → DslError。"""
    with_choose = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - action: search_deck
        selector: own_deck
        choose: 1
        destination: hand
        args:
          choose_groups:
            - {filters: [basic_pokemon], choose: 2}
""")
    e = play_engine(with_choose, "测试坏卡")
    with pytest.raises(DslError, match="choose_groups"):
        e.apply(0, Action(kind="play_trainer", iid=60))

    with_filters = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - action: search_deck
        selector: own_deck
        filters: [pokemon]
        destination: hand
        args:
          choose_groups:
            - {filters: [basic_pokemon], choose: 2}
""")
    e2 = play_engine(with_filters, "测试坏卡")
    with pytest.raises(DslError, match="choose_groups"):
        e2.apply(0, Action(kind="play_trainer", iid=60))

    to_bench = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - action: search_deck
        selector: own_deck
        destination: bench
        args:
          choose_groups:
            - {filters: [basic_pokemon], choose: 2}
""")
    e3 = play_engine(to_bench, "测试坏卡")
    with pytest.raises(DslError, match="choose_groups"):
        e3.apply(0, Action(kind="play_trainer", iid=60))

    malformed = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - action: search_deck
        selector: own_deck
        destination: hand
        args:
          choose_groups:
            - {filters: [basic_pokemon]}
""")
    e4 = play_engine(malformed, "测试坏卡")
    with pytest.raises(DslError, match="choose_groups"):
        e4.apply(0, Action(kind="play_trainer", iid=60))


# ── search distinct+split（赤松 属性互异 + 拆分去向）（清单 12-14）────────────────

AKAMATSU_DOC = parse_card_doc("""
card:
  name_group: 赤松
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_energy], choose: 2, destination: hand, args: {distinct: energy_type, split: hand_attach}}
      - {action: reveal, selector: own_hand, filters: [basic_energy]}
      - {action: shuffle_deck}
""")


def aka_deck() -> tuple:
    return (
        inst(100, energy("火能量", "火")), inst(101, energy("水能量", "水")),
        inst(102, energy("草能量", "草")), inst(103, energy("火能量二", "火")),
        inst(104, basic("宝可梦甲")),
    )


def aka_engine(deck=None):
    return play_engine(AKAMATSU_DOC, "赤松", kind="supporter",
                       deck=deck if deck is not None else aka_deck())


def test_distinct_enumeration_no_same_type_pairs():
    """清单12：枚举仅含属性互异子集——同属性对（100,103 皆火）不可达。"""
    e = aka_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.max_choose == 2  # min(choose=2, 3 属性桶)
    choices = {a.choices for a in e.legal_actions(0)}
    assert choices == {
        (), (100,), (101,), (102,), (103,),
        (100, 101), (100, 102), (101, 102), (101, 103), (102, 103),
    }
    assert (100, 103) not in choices  # 同属性对排除


def test_distinct_split_full_flow_hand_and_attach():
    """清单12：选 2 张互异能量 → 段2 选 1 张入手 → 段3 剩余附着自己场上 1 只。"""
    e = aka_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(100, 101)))  # 火 + 水
    pc2 = e.state.pending_choice
    assert pc2.pool == "own_deck" and pc2.pool_iids == (100, 101)
    assert pc2.min_choose == 1 and pc2.max_choose == 1
    e.apply(0, Action(kind="choose", choices=(101,)))  # 水入手
    p0 = e.state.players[0]
    assert 101 in [c.iid for c in p0.hand]
    assert 101 not in [c.iid for c in p0.deck]
    pc3 = e.state.pending_choice
    assert pc3.pool == "own_pokemon_in_play" and pc3.min_choose == 1
    e.apply(0, Action(kind="choose", choices=(1,)))  # 附着战斗场（iid 1）
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [9010, 100]  # 火能量附着
    assert sorted(c.iid for c in p0.deck) == [102, 103, 104]
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert 101 in reveal.detail["iids"]
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


def test_distinct_single_type_shrinks_to_one():
    """清单13（用户补充场景）：牌库仅单属性能量 → choose 自动收缩为 1，
    选 1 张直接入手，无段2/段3。"""
    deck = (inst(100, energy("火能量", "火")), inst(103, energy("火能量二", "火")),
            inst(104, basic("宝可梦甲")))
    e = aka_engine(deck=deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.max_choose == 1  # 单桶收缩
    choices = {a.choices for a in e.legal_actions(0)}
    assert choices == {(), (100,), (103,)}
    e.apply(0, Action(kind="choose", choices=(103,)))
    p0 = e.state.players[0]
    assert 103 in [c.iid for c in p0.hand]
    assert e.state.pending_choice is None  # 无后续段
    assert e.state.phase == "main" and e.state.current_player == 0


def test_distinct_choose_zero_noop_shuffle():
    """清单13：选 0 → 全 no-op（无段2/段3），重洗仍执行。"""
    e = aka_engine()
    hand_before = tuple(c.iid for c in e.state.players[0].hand)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    # 打出的支援者本体离场进弃牌区（WP3 先例口径，test_primitives_wp3.py:585）
    assert tuple(c.iid for c in p0.hand) == tuple(i for i in hand_before if i != 60)
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 104]
    assert prim_results(e, "shuffle_deck")
    assert e.state.phase == "main" and e.state.current_player == 0


def test_distinct_split_bad_forms_dsl_error():
    """清单14：distinct 非法值 / split 非法值 / split 无 distinct / split 去向非 hand
    → DslError（不猜）。"""
    bad_distinct = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_energy], choose: 2, destination: hand, args: {distinct: hp, split: hand_attach}}
""")
    e = play_engine(bad_distinct, "测试坏卡")
    with pytest.raises(DslError, match="distinct"):
        e.apply(0, Action(kind="play_trainer", iid=60))

    bad_split = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_energy], choose: 2, destination: hand, args: {distinct: energy_type, split: hand}}
""")
    e2 = play_engine(bad_split, "测试坏卡")
    with pytest.raises(DslError, match="split"):
        e2.apply(0, Action(kind="play_trainer", iid=60))

    distinct_only = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_energy], choose: 2, destination: hand, args: {distinct: energy_type}}
""")
    e3 = play_engine(distinct_only, "测试坏卡")
    with pytest.raises(DslError, match="split"):
        e3.apply(0, Action(kind="play_trainer", iid=60))

    split_bench = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_energy], choose: 2, destination: bench, args: {distinct: energy_type, split: hand_attach}}
""")
    e4 = play_engine(split_bench, "测试坏卡")
    with pytest.raises(DslError, match="split"):
        e4.apply(0, Action(kind="play_trainer", iid=60))


# ── deck_top 有序去向（暗码迷的解读）（清单 15-17）───────────────────────────────

CIPHER_DOC = parse_card_doc("""
card:
  name_group: 暗码迷的解读
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, choose: 2, destination: deck_top, args: {ordered: true}}
""")


def cipher_engine(deck=None, seed: int = 0):
    d = deck if deck is not None else tuple(
        inst(100 + i, basic(f"库{i}")) for i in range(10)
    )
    return play_engine(CIPHER_DOC, "暗码迷的解读", kind="supporter", deck=d, seed=seed)


def test_deck_top_ordered_fifo():
    """清单15：选择顺序即牌顶 FIFO——(103,101) → deck[0]=103, deck[1]=101；
    逆序 (101,103) 是另一合法行动；余库集合不变且重洗（同种子复跑一致）。"""
    orders = []
    for _ in range(2):
        e = cipher_engine()
        e.apply(0, Action(kind="play_trainer", iid=60))
        acts = e.legal_actions(0)
        assert Action(kind="choose", choices=(103, 101)) in acts
        assert Action(kind="choose", choices=(101, 103)) in acts  # 有序：两者皆合法
        e.apply(0, Action(kind="choose", choices=(103, 101)))
        deck = e.state.players[0].deck
        assert (deck[0].iid, deck[1].iid) == (103, 101)
        assert len(deck) == 10
        assert sorted(c.iid for c in deck[2:]) == [100, 102, 104, 105, 106, 107, 108, 109]
        orders.append(tuple(c.iid for c in deck))
    assert orders[0] == orders[1]  # 余库重洗走单一随机源，同种子逐局一致


def test_deck_top_choose_zero_reshuffle_only():
    """清单16：选 0 → 仅整库重洗（「剩余的牌库重洗」空选依然成立），牌顶无置入。"""
    orders = []
    for _ in range(2):
        e = cipher_engine()
        e.apply(0, Action(kind="play_trainer", iid=60))
        e.apply(0, Action(kind="choose", choices=()))
        deck = e.state.players[0].deck
        assert len(deck) == 10
        assert sorted(c.iid for c in deck) == list(range(100, 110))
        orders.append(tuple(c.iid for c in deck))
        assert e.state.phase == "main" and e.state.current_player == 0
    assert orders[0] == orders[1]


def test_deck_top_deck_one_card_shrink():
    """清单17：牌库仅 1 张 → max 收缩 1；选 1 张置回牌顶（等价原位）。"""
    e = cipher_engine(deck=(inst(100, basic("独卡")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    choices = {a.choices for a in e.legal_actions(0)}
    assert choices == {(), (100,)}
    e.apply(0, Action(kind="choose", choices=(100,)))
    deck = e.state.players[0].deck
    assert [c.iid for c in deck] == [100]


def test_deck_top_requires_ordered_dsl_error():
    """清单17：deck_top 去向无 args.ordered=true → DslError（不猜无序语义）。"""
    bad = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, choose: 2, destination: deck_top}
""")
    e = play_engine(bad, "测试坏卡")
    with pytest.raises(DslError, match="ordered"):
        e.apply(0, Action(kind="play_trainer", iid=60))


# ── own_ko_by_attack + opponent_attacker（沙铃仙人掌 炸裂针刺）（清单 18-21）──────

CACTUS_DOC = parse_card_doc("""
card:
  name_group: 沙铃仙人掌
effects:
  - trigger: trigger_on_event
    event: own_ko_by_attack
    actions:
      - {action: place_damage_counters, selector: opponent_attacker, args: {counters: 6}}
""")


def cactus(hp: int = 110) -> CardDef:
    return CardDef(
        card_id="stub-沙铃仙人掌", name="沙铃仙人掌", supertype="pokemon",
        hp=hp, stage=0, energy_type="草", weakness="火", retreat_cost=2,
        attacks=(AttackDef(name="穷追不舍", cost=("无",), damage=None),),
    )


def test_own_ko_by_attack_counters_on_attacker():
    """清单18：战斗场受对手招式伤害昏厥 → 触发，攻击方 +6 指示物（60）；换上后回合开始。"""
    e = attack_engine(None, basic("攻击兽", hp=200, damage=100, cost=1),
                      p0_energies=(inst(9001, energy()),),
                      p1_active=in_play(2, cactus(hp=50)),
                      p1_bench=(in_play(80, basic("对手备战")),),
                      extra_effects={"沙铃仙人掌": CACTUS_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert any(ev.kind == "trigger_on_event"
               and ev.detail.get("event") == "own_ko_by_attack" for ev in e.events)
    assert e.state.players[0].active.damage == 60  # 针刺反噬
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 1


def test_own_ko_by_attack_item_counters_no_trigger():
    """清单19：物品效果指示物致昏厥（非招式伤害路径）→ 不触发。"""
    counters_doc = parse_card_doc("""
card:
  name_group: 测试指示物
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 5}}
""")
    e = play_engine(counters_doc, "测试指示物",
                    p1_active=in_play(2, cactus(hp=50)),
                    p1_bench=(in_play(80, basic("对手备战")),))
    e.card_effects["沙铃仙人掌"] = CACTUS_DOC
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(2,)))  # 50 伤害 KO 战斗场
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
    assert e.state.players[0].active.damage == 0
    assert e.state.phase == "promote" and e.state.current_player == 1


def test_own_ko_by_attack_bench_ko_no_trigger():
    """清单19：备战区昏厥（非战斗场）→ 不触发。"""
    counters_doc = parse_card_doc("""
card:
  name_group: 测试指示物
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 5}}
""")
    e = play_engine(counters_doc, "测试指示物",
                    p1_bench=(in_play(80, cactus(hp=50)),))
    e.card_effects["沙铃仙人掌"] = CACTUS_DOC
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(80,)))  # KO 备战
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
    assert e.state.players[0].active.damage == 0
    assert e.state.phase == "main" and e.state.current_player == 0


def test_own_ko_by_attack_attacker_gone_noop():
    """清单20：排水时攻击方已离场（前序 ko_self）→ 针刺 no-op（attacker_gone）；
    双方换上后回合权给被攻击方（攻击已消耗）。"""
    suicide_doc = parse_card_doc("""
card:
  name_group: 自爆兽
effects:
  - trigger: on_attack
    attack: 自爆
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 100}}
      - {action: ko_self, selector: self}
""")
    attacker = CardDef(
        card_id="stub-自爆兽", name="自爆兽", supertype="pokemon",
        hp=200, stage=0, attacks=(AttackDef(name="自爆", cost=("无",), damage=None),),
    )
    e = attack_engine(suicide_doc, attacker, p0_energies=(inst(9001, energy()),),
                      p0_bench=(in_play(70, basic("己方备战")),),
                      p1_active=in_play(2, cactus(hp=50)),
                      p1_bench=(in_play(80, basic("对手备战")),),
                      extra_effects={"沙铃仙人掌": CACTUS_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert any(ev.kind == "trigger_on_event"
               and ev.detail.get("event") == "own_ko_by_attack" for ev in e.events)
    results = prim_results(e, "place_damage_counters")
    assert results and results[0]["placed"] == 0
    assert results[0]["reason"] == "attacker_gone"
    # 双方战斗场均昏厥：被攻击方先换上，攻击方后换上
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase == "promote" and e.state.current_player == 0
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 1  # 攻击已消耗


def test_place_damage_counters_opponent_attacker_bad_forms():
    """清单21：opponent_attacker 带 choose / 无昏厥事件上下文（on_play）→ DslError。"""
    with_choose = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: trigger_on_event
    event: own_ko_by_attack
    actions:
      - {action: place_damage_counters, selector: opponent_attacker, choose: 1, args: {counters: 6}}
""")
    # choose 形式校验先于上下文（挂起纪律），经 run_doc 直跑触发
    e = attack_engine(None, basic("攻击兽", hp=200, damage=100, cost=1),
                      p0_energies=(inst(9001, energy()),),
                      p1_active=in_play(2, cactus(hp=50)),
                      extra_effects={"沙铃仙人掌": with_choose})
    with pytest.raises(DslError, match="place_damage_counters"):
        run_doc(e, with_choose, inst(2, cactus()), player=1)

    on_play_doc = parse_card_doc("""
card:
  name_group: 测试坏卡
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: opponent_attacker, args: {counters: 6}}
""")
    e2 = play_engine(on_play_doc, "测试坏卡")
    with pytest.raises(DslError, match="opponent_attacker"):
        e2.apply(0, Action(kind="play_trainer", iid=60))


# ── lock_retreat（沙铃仙人掌 穷追不舍）（清单 22-24）──────────────────────────────

PURSUIT_DOC = parse_card_doc("""
card:
  name_group: 追猎兽
effects:
  - trigger: on_attack
    attack: 穷追不舍
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 20}}
      - {action: lock_retreat, selector: opponent_active}
""")


def pursuer() -> CardDef:
    return CardDef(
        card_id="stub-追猎兽", name="追猎兽", supertype="pokemon",
        hp=110, stage=0, attacks=(AttackDef(name="穷追不舍", cost=("无",), damage=None),),
    )


def test_lock_retreat_blocks_next_turn_then_expires():
    """清单22：被锁目标下个自己回合撤退不枚举；其回合结束解除，再下回合解禁。"""
    p1_active = in_play(2, basic("逃跑兽", retreat=1), 1)  # 附 1 能，撤退费 1
    e = attack_engine(PURSUIT_DOC, pursuer(), p0_energies=(inst(9001, energy()),),
                      p1_active=p1_active, p1_bench=(in_play(80, basic("对手备战")),))
    e.apply(0, Action(kind="attack", attack_index=0))  # turn 2，p0 攻击
    assert e.state.players[1].active.retreat_lock is True
    assert e.state.players[1].active.damage == 20  # 伤害照算
    assert e.state.phase == "main" and e.state.current_player == 1
    assert not [a for a in e.legal_actions(1) if a.kind == "retreat"]  # 锁定
    e.apply(1, Action(kind="end_turn"))  # p1 回合结束 → 解除
    assert e.state.players[1].active.retreat_lock is False
    e.apply(0, Action(kind="end_turn"))  # → p1 turn 3
    assert [a for a in e.legal_actions(1) if a.kind == "retreat"]  # 解禁


def test_lock_retreat_evolution_clears():
    """清单23：进化清除撤退锁（D-WP6-6）——进化后立即可撤退。"""
    p1_active = in_play(2, basic("底兽", retreat=1), 1)
    p1_hand = (inst(90, stage1("顶兽", "底兽")),)
    e = attack_engine(PURSUIT_DOC, pursuer(), p0_energies=(inst(9001, energy()),),
                      p1_active=p1_active, p1_hand=p1_hand,
                      p1_bench=(in_play(80, basic("对手备战")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.retreat_lock is True
    assert not [a for a in e.legal_actions(1) if a.kind == "retreat"]
    e.apply(1, Action(kind="evolve", iid=90, target_iid=2))
    assert e.state.players[1].active.current.card.name == "顶兽"
    assert e.state.players[1].active.retreat_lock is False
    assert [a for a in e.legal_actions(1) if a.kind == "retreat"]


def test_lock_retreat_bad_forms_dsl_error():
    """清单24：selector 非 opponent_active / 带 choose → DslError（不猜）。"""
    bad_selector = parse_card_doc("""
card:
  name_group: 追猎兽
effects:
  - trigger: on_attack
    attack: 穷追不舍
    actions:
      - {action: lock_retreat, selector: self}
""")
    e = attack_engine(bad_selector, pursuer(), p0_energies=(inst(9001, energy()),))
    with pytest.raises(DslError, match="lock_retreat"):
        e.apply(0, Action(kind="attack", attack_index=0))

    bad_choose = parse_card_doc("""
card:
  name_group: 追猎兽
effects:
  - trigger: on_attack
    attack: 穷追不舍
    actions:
      - {action: lock_retreat, selector: opponent_active, choose: 1}
""")
    e2 = attack_engine(bad_choose, pursuer(), p0_energies=(inst(9001, energy()),))
    with pytest.raises(DslError, match="lock_retreat"):
        e2.apply(0, Action(kind="attack", attack_index=1 - 1))


# ── protection + own_attached_energy choose=1（火恐龙）（清单 25-28）────────────────

PROTECT_DOC = parse_card_doc("""
card:
  name_group: 火恐龙
effects:
  - trigger: passive_static
    actions:
      - {action: protection, args: {scope: opponent_attack_effects}}
""")


def charmeleon_protect() -> CardDef:
    return CardDef(
        card_id="stub-火恐龙", name="火恐龙", supertype="pokemon",
        hp=90, stage=1, evolves_from="小火龙", energy_type="火",
        attacks=(AttackDef(name="烈焰", cost=("火", "火"), damage=50),),
    )


def needle_attacker() -> CardDef:
    return CardDef(
        card_id="stub-针雨兽", name="针雨兽", supertype="pokemon",
        hp=200, stage=0, attacks=(AttackDef(name="针雨", cost=("无",), damage=None),),
    )


NEEDLE_DOC = parse_card_doc("""
card:
  name_group: 针雨兽
effects:
  - trigger: on_attack
    attack: 针雨
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 10}}
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 3}}
""")


def test_protection_skips_attack_counters_damage_applies():
    """清单25：对手招式指示物被免疫（skipped_protected），招式伤害本体不免疫（10 照算）。"""
    e = attack_engine(NEEDLE_DOC, needle_attacker(), p0_energies=(inst(9001, energy()),),
                      p1_active=in_play(2, charmeleon_protect()),
                      p1_bench=(in_play(80, basic("对手备战")),),
                      extra_effects={"火恐龙": PROTECT_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(2,)))  # 指示物指战斗场
    p1 = e.state.players[1]
    assert p1.active.damage == 10  # 仅招式伤害；3 指示物被免疫
    results = prim_results(e, "place_damage_counters")
    assert results[0]["placed"] == 0
    assert results[0]["skipped_protected"] == [2]


def test_protection_blocks_attack_apply_status():
    """清单25：对手招式施加的特殊状态不适用（applied=None/protected）。"""
    burn_doc = parse_card_doc("""
card:
  name_group: 针雨兽
effects:
  - trigger: on_attack
    attack: 针雨
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 10}}
      - {action: apply_status, selector: opponent_active, args: {status: burned}}
""")
    e = attack_engine(burn_doc, needle_attacker(), p0_energies=(inst(9001, energy()),),
                      p1_active=in_play(2, charmeleon_protect()),
                      extra_effects={"火恐龙": PROTECT_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    assert p1.active.damage == 10  # 伤害照算
    assert p1.active.conditions == frozenset()  # 灼伤被免疫
    results = prim_results(e, "apply_status")
    assert results[0] == {"applied": None, "reason": "protected"}


def test_protection_item_counters_not_blocked():
    """清单26：训练家卡（非招式）指示物不受保护，照常放置。"""
    counters_doc = parse_card_doc("""
card:
  name_group: 测试指示物
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 2}}
""")
    e = play_engine(counters_doc, "测试指示物",
                    p1_active=in_play(2, charmeleon_protect()))
    e.card_effects["火恐龙"] = PROTECT_DOC
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[1].active.damage == 20  # 2 指示物照常


def test_protection_unknown_scope_dsl_error():
    """清单26：未知 scope → DslError（求值点不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 火恐龙
effects:
  - trigger: passive_static
    actions:
      - {action: protection, args: {scope: everything}}
""")
    e = attack_engine(NEEDLE_DOC, needle_attacker(), p0_energies=(inst(9001, energy()),),
                      p1_active=in_play(2, charmeleon_protect()),
                      extra_effects={"火恐龙": bad})
    with pytest.raises(DslError, match="protection"):
        e.apply(0, Action(kind="attack", attack_index=0))
        e.apply(0, Action(kind="choose", choices=(2,)))


BLAZE_DOC = parse_card_doc("""
card:
  name_group: 火恐龙
effects:
  - trigger: on_attack
    attack: 大字爆炎
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 90}}
      - {action: discard, selector: own_attached_energy, choose: 1}
""")


def charmeleon_blaze() -> CardDef:
    return CardDef(
        card_id="stub-火恐龙", name="火恐龙", supertype="pokemon",
        hp=100, stage=1, evolves_from="小火龙", energy_type="火",
        weakness="水", retreat_cost=2,
        attacks=(
            AttackDef(name="烈焰", cost=("火",), damage=20),
            AttackDef(name="大字爆炎", cost=("火", "火", "火"), damage=None),
        ),
    )


def test_discard_own_attached_choose1_source_only():
    """清单27：大字爆炎弃置池收窄为来源宝可梦（「这只宝可梦身上」）附着能量——
    备战区能量不进池；弃 1 → 伤害 90。"""
    energies = tuple(inst(9001 + i, energy("火能量", "火")) for i in range(3))
    bench = in_play(70, basic("备战兽")).model_copy(update={
        "attached_energy": (inst(9070, energy("火能量", "火")),),
    })
    e = attack_engine(BLAZE_DOC, charmeleon_blaze(), p0_energies=energies,
                      p0_bench=(bench,))
    e.apply(0, Action(kind="attack", attack_index=1))
    pc = e.state.pending_choice
    assert pc.pool == "own_attached_energy"
    assert pc.pool_iids == (9001, 9002, 9003)  # 备战 9070 经 exclude 剔除
    e.apply(0, Action(kind="choose", choices=(9002,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [9001, 9003]
    assert [c.iid for c in p0.bench[0].attached_energy] == [9070]  # 备战能量不动
    assert 9002 in [c.iid for c in p0.discard]
    assert e.state.players[1].active.damage == 90


def test_discard_own_attached_choose1_no_energy_noop():
    """清单28：来源无附着能量 → 弃置 no-op（discarded=0 不挂起），伤害 90 照算。"""
    e = attack_engine(BLAZE_DOC, charmeleon_blaze())  # 无能量（直跑绕过能量枚举门）
    run_doc(e, BLAZE_DOC, e.state.players[0].active.current)
    assert e.state.players[1].active.damage == 90
    assert e.state.pending_choice is None
    results = prim_results(e, "discard")
    assert results[0]["discarded"] == 0


# ── devolve（招式学习器 退化）（清单 29-32）──────────────────────────────────────

DEVOLVE_DOC = parse_card_doc("""
card:
  name_group: 退化兽
effects:
  - trigger: on_attack
    attack: 退化
    actions:
      - {action: devolve, selector: opponent_pokemon_all}
""")


def devolver() -> CardDef:
    return CardDef(
        card_id="stub-退化兽", name="退化兽", supertype="pokemon",
        hp=150, stage=0, attacks=(AttackDef(name="退化", cost=("无",), damage=None),),
    )


def test_devolve_full_field():
    """清单29：对手全场各退栈顶 1 张回其手牌（战斗场先、备战后）；2 阶只退 1 张；
    伤害保留、特殊状态恢复、未进化不动；能量/道具不动。"""
    active = stacked(inst(2, basic("底甲", hp=70)), inst(20, stage1("顶甲", "底甲", hp=90)),
                     damage=30, conditions=frozenset({SpecialCondition.POISONED}))
    bench_two = stacked(inst(70, basic("底乙", hp=60)), inst(71, stage1("中乙", "底乙", hp=80)),
                        inst(72, stage2("顶乙", "中乙", hp=100)))
    bench_two = bench_two.model_copy(update={
        "attached_energy": (inst(9070, energy()),),
    })
    bench_plain = in_play(80, basic("底丙"))
    e = attack_engine(DEVOLVE_DOC, devolver(), p0_energies=(inst(9001, energy()),),
                      p1_active=active, p1_bench=(bench_two, bench_plain))
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    assert [c.iid for c in p1.active.stack] == [2]  # 退 1 张
    assert p1.active.damage == 30  # 伤害保留
    assert p1.active.conditions == frozenset()  # 状态恢复
    assert [c.iid for c in p1.bench[0].stack] == [70, 71]  # 2 阶只退栈顶 1 张
    assert [c.iid for c in p1.bench[0].attached_energy] == [9070]  # 能量不动
    assert [c.iid for c in p1.bench[1].stack] == [80]  # 未进化不动
    assert [c.iid for c in p1.hand] == [20, 72, 300]  # 退化回手（战斗场先、备战后）+ 对手回合开始抽 1（牌库顶 300）
    results = prim_results(e, "devolve")
    assert results[0]["devolved"] == 2
    assert e.state.phase == "main" and e.state.current_player == 1


def test_devolve_hp_over_ko_prize_promote():
    """清单30：退化后 HP 超限 → 昏厥/拿奖/换上走既有 check_knockouts。"""
    active = stacked(inst(2, basic("底甲", hp=70)), inst(20, stage1("顶甲", "底甲", hp=90)),
                     damage=80)
    e = attack_engine(DEVOLVE_DOC, devolver(), p0_energies=(inst(9001, energy()),),
                      p1_active=active, p1_bench=(in_play(80, basic("对手备战")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert any(ev.kind == "knockout" for ev in e.events)
    assert len(e.state.players[0].prizes) == 5  # 攻击方拿 1 奖
    assert 2 in [c.iid for c in e.state.players[1].discard]  # 退化后整叠进弃牌
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 1


def test_devolve_no_evolved_noop():
    """清单31：对手无已进化宝可梦 → no-op（devolved=0），回合照常推进。"""
    e = attack_engine(DEVOLVE_DOC, devolver(), p0_energies=(inst(9001, energy()),),
                      p1_bench=(in_play(80, basic("对手备战")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert prim_results(e, "devolve")[0]["devolved"] == 0
    assert [c.iid for c in e.state.players[1].hand] == [300]  # 对手回合开始抽 1（牌库顶 300）
    assert e.state.phase == "main" and e.state.current_player == 1


def test_devolve_bad_forms_dsl_error():
    """清单32：selector 非 opponent_pokemon_all / 带 choose → DslError（不猜）。"""
    bad_selector = parse_card_doc("""
card:
  name_group: 退化兽
effects:
  - trigger: on_attack
    attack: 退化
    actions:
      - {action: devolve, selector: own_pokemon_in_play}
""")
    e = attack_engine(bad_selector, devolver(), p0_energies=(inst(9001, energy()),))
    with pytest.raises(DslError, match="devolve"):
        e.apply(0, Action(kind="attack", attack_index=0))

    bad_choose = parse_card_doc("""
card:
  name_group: 退化兽
effects:
  - trigger: on_attack
    attack: 退化
    actions:
      - {action: devolve, selector: opponent_pokemon_all, choose: 1}
""")
    e2 = attack_engine(bad_choose, devolver(), p0_energies=(inst(9001, energy()),))
    with pytest.raises(DslError, match="devolve"):
        e2.apply(0, Action(kind="attack", attack_index=0))


# ── 质量复核补测（2026-09-15）：I-1 protection 守卫扩面 / I-2 失效触点 / I-3 挂起穿透 ──


def ability_engine(doc, name: str, mon: CardDef, *, p0_bench: tuple = (),
                   deck=None, turn: int = 1):
    """main 阶段：p0 战斗场特性持有兽（iid 1）（仿 WP5 ability_engine）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, mon), "bench": p0_bench,
    })
    if deck is not None:
        p0 = p0.model_copy(update={"deck": deck})
    e = engine_at_seed(state.model_copy(update={
        "players": (p0, state.players[1]), "turn": turn,
    }), 0)
    e.card_effects = {name: doc}
    return e


def with_hole(e, owner: int = 0):
    """场上挂零之大空洞（iid 399）并挂 DSL 文档（play/ability 引擎不带竞技场）。"""
    e.state = e.state.model_copy(update={
        "stadium": inst(399, stadium_card("大空洞")), "stadium_owner": owner,
    })
    e.card_effects["大空洞"] = HOLE_DOC
    return e


def test_protection_blocks_attack_lock_retreat():
    """I-1（D-WP6-7「效果影响」= 招式附加效果全类）：穷追不舍（on_attack lock_retreat）
    对持有闪焰之幕的火恐龙 → 锁不适用；伤害本体不免疫（20 照算）。"""
    e = attack_engine(PURSUIT_DOC, pursuer(), p0_energies=(inst(9001, energy()),),
                      p1_active=in_play(2, charmeleon_protect()),
                      p1_bench=(in_play(80, basic("对手备战")),),
                      extra_effects={"火恐龙": PROTECT_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    assert p1.active.damage == 20  # 伤害照算
    assert p1.active.retreat_lock is False  # 撤退锁被免疫
    results = prim_results(e, "lock_retreat")
    assert results[0] == {"locked": False, "reason": "protected"}
    assert [a for a in e.legal_actions(1) if a.kind == "retreat"]  # 未锁可撤退


def test_protection_blocks_attack_devolve_target():
    """I-1：devolve 招式对保护目标 → 该目标不退化（skipped_protected），其余照常。"""
    active = stacked(inst(2, basic("小火龙", hp=70)), inst(20, charmeleon_protect()))
    bench_evo = stacked(inst(70, basic("底乙", hp=60)),
                        inst(71, stage1("中乙", "底乙", hp=80)))
    e = attack_engine(DEVOLVE_DOC, devolver(), p0_energies=(inst(9001, energy()),),
                      p1_active=active, p1_bench=(bench_evo,),
                      extra_effects={"火恐龙": PROTECT_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    assert [c.iid for c in p1.active.stack] == [2, 20]  # 保护目标不退化
    assert [c.iid for c in p1.bench[0].stack] == [70]  # 备战进化体照常退化
    assert [c.iid for c in p1.hand] == [71, 300]  # 退化回手 + 对手回合开始抽 1
    results = prim_results(e, "devolve")
    assert results[0]["devolved"] == 1
    assert results[0]["skipped_protected"] == [20]


def test_bench_shrink_bench_tera_ko_triggers():
    """I-2 触点①（D-WP6-2「太晶离场立即缩减」）：备战区唯一太晶被指示物效果昏厥
    → 效果结算完毕后立即进 bench_shrink（超容方逐只自选弃至 5）→ 回出牌方主阶段。"""
    counters_doc = parse_card_doc("""
card:
  name_group: 测试指示物
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 5}}
""")
    p1_bench = bench_mons(80, 7) + (in_play(87, tera_mon("备战太晶", hp=30)),)
    e = play_engine(counters_doc, "测试指示物", p1_bench=p1_bench)
    with_hole(e)
    assert len(e.state.players[1].bench) == 8  # 太晶在场容量 8
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(87,)))  # 50 伤害昏厥备战太晶
    assert any(ev.kind == "knockout" for ev in e.events)
    assert e.state.phase == "bench_shrink" and e.state.current_player == 1
    e.apply(1, Action(kind="shrink_bench", choices=(80,)))
    assert e.state.phase == "bench_shrink"  # 7→6 仍超容，继续缩减
    e.apply(1, Action(kind="shrink_bench", choices=(81,)))
    assert len(e.state.players[1].bench) == 5
    assert e.state.phase == "main" and e.state.current_player == 0  # resume 出牌方主阶段


def test_bench_shrink_transform_tera_leaves():
    """I-2 触点②：transform 替换掉自己唯一太晶 → 失效缩减立即触发。"""
    doc = parse_card_doc("""
card:
  name_group: 太晶百变怪
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: transform, selector: self, choose: 1, filters: [basic_pokemon]}
      - {action: shuffle_deck}
""")
    mon = CardDef(
        card_id="stub-太晶百变怪", name="太晶百变怪", supertype="pokemon",
        hp=70, stage=0, is_tera=True,
        attacks=(AttackDef(name="打击", cost=("无",), damage=10),),
    )
    e = ability_engine(doc, "太晶百变怪", mon,
                       p0_bench=bench_mons(80, 6),
                       deck=(inst(100, basic("替换兽")),))
    with_hole(e)
    assert len(e.state.players[0].bench) == 6  # 太晶在场容量 8，6 只合法
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(100,)))  # 替换为非太晶基础
    assert e.state.players[0].active.current.iid == 100  # 太晶已离场
    assert e.state.phase == "bench_shrink" and e.state.current_player == 0
    e.apply(0, Action(kind="shrink_bench", choices=(80,)))
    assert len(e.state.players[0].bench) == 5
    assert e.state.phase == "main" and e.state.current_player == 0


def test_bench_shrink_bounce_tera_leaves():
    """I-2 触点③：bounce 回手自己唯一太晶（备战区）→ 失效缩减立即触发。"""
    doc = parse_card_doc("""
card:
  name_group: 测试剧本
effects:
  - trigger: on_play
    actions:
      - {action: bounce, selector: own_pokemon_in_play, choose: 1}
""")
    e = play_engine(doc, "测试剧本",
                    p0_bench=bench_mons(80, 6) + (in_play(86, tera_mon("备战太晶")),))
    with_hole(e)
    assert len(e.state.players[0].bench) == 7
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(86,)))  # 备战太晶整叠回手
    p0 = e.state.players[0]
    assert 86 in [c.iid for c in p0.hand]
    assert e.state.phase == "bench_shrink" and e.state.current_player == 0
    e.apply(0, Action(kind="shrink_bench", choices=(80,)))
    assert len(e.state.players[0].bench) == 5
    assert e.state.phase == "main" and e.state.current_player == 0


def test_own_ko_by_attack_attacker_iid_survives_suspend():
    """I-3：attacker_iid 挂起穿透（WP4/WP5 flip/cost_discarded/discarded_count
    三件套同口径）——触发效果在 opponent_attacker 落点前先挂起一个选择节点，
    恢复后攻击方上下文仍可用。"""
    suspend_doc = parse_card_doc("""
card:
  name_group: 沙铃仙人掌
effects:
  - trigger: trigger_on_event
    event: own_ko_by_attack
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_energy], choose: 1, destination: hand}
      - {action: place_damage_counters, selector: opponent_attacker, args: {counters: 6}}
""")
    e = attack_engine(None, basic("攻击兽", hp=200, damage=100, cost=1),
                      p0_energies=(inst(9001, energy()),),
                      p1_active=in_play(2, cactus(hp=50)),
                      p1_bench=(in_play(80, basic("对手备战")),),
                      p1_deck=(inst(300, energy()), inst(301, basic("库底")),),
                      extra_effects={"沙铃仙人掌": suspend_doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    # 触发效果发动并在检索节点挂起（选择权属被昏厥方）
    assert e.state.phase == "choice" and e.state.current_player == 1
    e.apply(1, Action(kind="choose", choices=(300,)))
    assert 300 in [c.iid for c in e.state.players[1].hand]  # 检索入手
    assert e.state.players[0].active.damage == 60  # 恢复后攻击方落点正常（穿透成功）
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 1
