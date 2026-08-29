"""task 014：物品批 e2e——大地容器 / 秘密箱 / 厉害钓竿 / 反击捕捉器 / 能量转移。

规则出处：rules-manual §3（牌库检索 up-to 语义、检索后必洗）/§5（训练家卡用完
放弃牌区；「只有…时才可使用」= 条件/可行性门，无效果不可使用）；§4（回备战区
清除特殊状态）。
"""

import pytest
from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import load_card_dir, parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef, SpecialCondition

VESSEL_DOC = parse_card_doc("""
card:
  name_group: 大地容器
effects:
  - trigger: on_play
    cost:
      - {action: discard, selector: own_hand, choose: 1}
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_energy], choose: 2, destination: hand}
      - {action: shuffle_deck}
""")

SECRET_BOX_DOC = parse_card_doc("""
card:
  name_group: 秘密箱
effects:
  - trigger: on_play
    cost:
      - {action: discard, selector: own_hand, choose: 3}
    actions:
      - {action: search_deck, selector: own_deck, filters: [trainer_item], choose: 1, destination: hand}
      - {action: search_deck, selector: own_deck, filters: [trainer_tool], choose: 1, destination: hand}
      - {action: search_deck, selector: own_deck, filters: [trainer_supporter], choose: 1, destination: hand}
      - {action: search_deck, selector: own_deck, filters: [trainer_stadium], choose: 1, destination: hand}
      - {action: shuffle_deck}
""")

ROD_DOC = parse_card_doc("""
card:
  name_group: 厉害钓竿
effects:
  - trigger: on_play
    actions:
      - {action: recover_from_discard, selector: own_discard, filters: [pokemon_or_basic_energy], choose: 3, destination: deck}
      - {action: shuffle_deck}
""")

CATCHER_DOC = parse_card_doc("""
card:
  name_group: 反击捕捉器
effects:
  - trigger: on_play
    condition: own_prizes_more_than_opponent
    actions:
      - {action: switch, selector: opponent_bench, choose: 1}
""")

MOVE_DOC = parse_card_doc("""
card:
  name_group: 能量转移
effects:
  - trigger: on_play
    actions:
      - {action: move_energy, selector: own_attached_energy, filters: [basic_energy], choose: 1}
""")


def trainer(name: str, subtype: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype=subtype)


def item_engine(name: str, doc, hand_extras: tuple = (), **updates):
    """main 局面、p0 手牌 = 默认 2 张 + 物品本体（iid 60）+ extras。"""
    state = main_state(p0_extra_hand=(inst(60, trainer(name, "物品")),) + hand_extras)
    p0 = state.players[0].model_copy(update={k: v for k, v in updates.items() if v is not None})
    players = (p0, state.players[1])
    e = engine_at(state.model_copy(update={"players": players}))
    e.card_effects = {name: doc}
    return e


def choose(e, player, iids):
    e.apply(player, next(a for a in e.legal_actions(player) if a.kind == "choose" and a.choices == iids))


def play(e, iid=60):
    e.apply(0, Action(kind="play_trainer", iid=iid))


# ── 大地容器（cost 弃 1 + 检索 ≤2 基本能量）──────────────────────────────

def test_earth_vessel_full_flow() -> None:
    deck = (inst(100, energy("基本超能量", "超")), inst(101, energy()),
            inst(102, basic("妙蛙种子")))
    e = item_engine("大地容器", VESSEL_DOC, deck=deck)
    play(e)
    choose(e, 0, (50,))  # cost：弃小火龙
    choices = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert choices == [(), (100,), (100, 101), (101,)]  # ≤2 up-to，宝可梦被过滤
    choose(e, 0, (100, 101))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert sorted(c.iid for c in p0.hand) == [51, 100, 101]  # 默认能量 51 + 检索 2 张
    assert sorted(c.iid for c in p0.discard) == [50, 60]  # cost + 本体
    assert [c.iid for c in p0.deck] == [102]  # 取走 2 张且已洗牌（单元素洗牌不变）


# ── 秘密箱（ACE：四类各 ≤1 顺序检索）─────────────────────────────────────

def test_secret_box_four_subtype_searches() -> None:
    deck = (
        inst(100, trainer("高级球", "物品")), inst(101, trainer("勇气护符", "宝可梦道具")),
        inst(102, trainer("博士的研究", "支援者")), inst(103, trainer("深钵镇", "竞技场")),
        inst(104, basic("妙蛙种子")), inst(105, energy()),
    )
    hand_extras = (inst(50, basic("小火龙")), inst(51, energy()), inst(52, energy()))
    e = item_engine("秘密箱", SECRET_BOX_DOC, hand_extras=(), deck=deck)
    # 默认手牌已含 50/51，加 52 → 本体 60 + 恰好 3 张 cost
    p0 = e.state.players[0].model_copy(update={"hand": e.state.players[0].hand + hand_extras[2:]})
    e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    play(e)
    choose(e, 0, (50, 51, 52))  # cost：弃 3 张
    for iids in [(100,), (101,), (102,), (103,)]:
        choose(e, 0, iids)
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert sorted(c.iid for c in p0.hand) == [100, 101, 102, 103]
    assert sorted(c.iid for c in p0.discard) == [50, 51, 52, 60]
    assert sorted(c.iid for c in p0.deck) == [104, 105]  # 宝可梦/能量不被四类过滤器命中
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive"
                and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1  # 只洗一次


# ── 厉害钓竿（弃牌区 ≤3 回牌库，up-to）──────────────────────────────────

def test_rod_recover_up_to_three_to_deck() -> None:
    discard = (inst(80, basic("拉鲁拉丝")), inst(81, basic("妙蛙种子")),
               inst(82, energy()), inst(83, trainer("高级球", "物品")))
    e = item_engine("厉害钓竿", ROD_DOC, discard=discard)
    play(e)
    choices = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert () in choices and (83,) not in choices  # up-to（可少选）；训练家被过滤
    choose(e, 0, (80, 82))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert sorted(c.iid for c in p0.discard) == [60, 81, 83]  # 剩余 + 本体
    assert sorted(c.iid for c in p0.deck) >= [80, 82]  # 回牌库（已洗牌，断集合）


# ── 反击捕捉器（condition 门 + gust 互换）────────────────────────────────

def test_catcher_condition_gate() -> None:
    """「只有剩余奖赏比对手多时才可使用」：6v6 不枚举；6v5 可枚举。"""
    e = item_engine("反击捕捉器", CATCHER_DOC,
                    p1_bench=None)  # 默认无备战也不可用，但先验 condition
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]
    # 对手少 1 张奖赏 → 条件满足；给对手备战区放 1 只 → 可枚举
    state = e.state
    p1 = state.players[1].model_copy(update={
        "prizes": state.players[1].prizes[:5],
        "bench": (in_play(300, basic("小火龙")),),
    })
    e.state = state.model_copy(update={"players": (state.players[0], p1)})
    assert any(a.kind == "play_trainer" and a.iid == 60 for a in e.legal_actions(0))


def test_catcher_switch_flow_and_status_cleared() -> None:
    """选对手备战 1 只与其战斗场互换；被换下的战斗宝可梦特殊状态清除。"""
    e = item_engine("反击捕捉器", CATCHER_DOC)
    state = e.state
    p1 = state.players[1].model_copy(update={
        "prizes": state.players[1].prizes[:5],
        "active": state.players[1].active.model_copy(update={
            "conditions": frozenset({SpecialCondition.CONFUSED}),
        }),
        "bench": (in_play(300, basic("小火龙")), in_play(301, basic("妙蛙种子"))),
    })
    e.state = state.model_copy(update={"players": (state.players[0], p1)})
    play(e)
    choices = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert choices == [(300,), (301,)]
    choose(e, 0, (300,))
    p1 = e.state.players[1]
    assert e.state.phase == "main"
    assert p1.active.current.iid == 300  # 备战 300 被换上场
    swapped_out = next(m for m in p1.bench if m.current.iid == 2)
    assert swapped_out.conditions == frozenset()  # 回备战区清状态
    assert 60 in [c.iid for c in e.state.players[0].discard]  # 本体进弃牌区


def test_unknown_condition_dsl_error() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏条件
effects:
  - trigger: on_play
    condition: not_a_condition
    actions:
      - {action: draw, count: 1}
""")
    e = item_engine("坏条件", bad)
    with pytest.raises(DslError, match="未知 condition"):
        e.legal_actions(0)


# ── 能量转移（两段式：选能量 → 选目标，排除来源）─────────────────────────

def test_move_energy_full_flow() -> None:
    active = in_play(1, basic("妙蛙种子"), energies=2)   # 附着 9000/9001
    bench = (in_play(5, basic("小火龙"), energies=1),)   # 附着 9050
    e = item_engine("能量转移", MOVE_DOC, active=active, bench=bench)
    play(e)
    choices = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert choices == [(9010,), (9011,), (9050,)]  # 池 = 全场已附着基本能量
    choose(e, 0, (9010,))
    choices = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert choices == [(5,)]  # 目标排除来源（iid 1）
    choose(e, 0, (5,))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert [c.iid for c in p0.active.attached_energy] == [9011]
    assert [c.iid for c in p0.bench[0].attached_energy] == [9050, 9010]
    assert 60 in [c.iid for c in p0.discard]


def test_move_energy_gate_no_attached_energy() -> None:
    """场上无已附着基本能量 → 不枚举（无效果不可使用）。"""
    active = in_play(1, basic("妙蛙种子"))  # 0 附着
    e = item_engine("能量转移", MOVE_DOC, active=active)
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]


# ── 定义库与对局级确定性 ────────────────────────────────────────────────

def test_card_library_seventeen() -> None:
    docs = load_card_dir("cards")
    for name in ("大地容器", "秘密箱", "厉害钓竿", "反击捕捉器", "能量转移"):
        assert name in docs
    # 定义库总数断言由最新入库任务的测试持有（当前 test_tools::test_card_library_tools）
    assert docs["秘密箱"].effects[0].cost[0].choose == 3
    assert docs["反击捕捉器"].effects[0].condition == "own_prizes_more_than_opponent"
    assert docs["能量转移"].effects[0].actions[0].action == "move_energy"


def test_play_game_with_items_deterministic() -> None:
    """含本批物品的整局对局：同种子事件流 hash 一致。"""
    from battlefrontier.runner.play import play_game

    deck = ([basic("妙蛙种子")] * 20
            + [trainer("大地容器", "物品")] * 4 + [trainer("厉害钓竿", "物品")] * 4
            + [trainer("能量转移", "物品")] * 4
            + [energy("基本超能量", "超")] * 20 + [energy()] * 8)
    effects = load_card_dir("cards")
    r1 = play_game(deck, deck, seed=17, card_effects=effects)
    r2 = play_game(deck, deck, seed=17, card_effects=effects)
    assert r1.events_hash == r2.events_hash
