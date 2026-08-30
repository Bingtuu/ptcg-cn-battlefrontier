"""task 017（2/2）：化危为吉跨回合 / 亢奋脑力转伤 / 妖精领域弱点改写 /
基因侵入 copy / 奇树 / 派帕 / 特性 condition 门。

text_raw 原文见各 cards/*.yml 注释引用。降级决策：亢奋脑力「最多3个」转放数量
= min(3, 来源指示物数) 全转（chooser 不建模数值选择；rules-reference 附录 A 决议）。
"""

import pytest
from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import load_card_dir, parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

JIJI_DOC = parse_card_doc("""
card:
  name_group: 吉雉鸡ex
effects:
  - trigger: ability_manual
    limit: once_per_turn_shared
    condition: own_ko_during_opponent_turn
    actions:
      - {action: draw, count: 3}
""")

MONKEY_DOC = parse_card_doc("""
card:
  name_group: 愿增猿
effects:
  - trigger: ability_manual
    limit: once_per_turn
    condition: holder_has_energy:恶
    actions:
      - {action: move_damage_counters, selector: own_pokemon_in_play, choose: 1, args: {max_counters: 3, target_pool: opponent_pokemon_any}}
""")

FAIRY_DOC = parse_card_doc("""
card:
  name_group: 莉莉艾的皮皮ex
effects:
  - trigger: passive_static
    actions:
      - {action: modify_weakness, args: {scope: opponent_field, target_type: 龙, becomes: 超}}
""")

MEW_COPY_DOC = parse_card_doc("""
card:
  name_group: 梦幻ex
effects:
  - trigger: on_attack
    attack: 基因侵入
    actions:
      - {action: copy_attack, selector: opponent_active_attack, choose: 1}
""")

IONO_DOC = parse_card_doc("""
card:
  name_group: 奇树
effects:
  - trigger: on_play
    actions:
      - {action: hand_to_deck_bottom, selector: own_hand, count: all}
      - {action: hand_to_deck_bottom, selector: opponent_hand, count: all}
      - {action: draw, count: own_remaining_prizes}
      - {action: draw, selector: opponent_deck, count: opponent_remaining_prizes}
""")

ARVEN_DOC = parse_card_doc("""
card:
  name_group: 派帕
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [trainer_item], choose: 1, destination: hand}
      - {action: search_deck, selector: own_deck, filters: [trainer_tool], choose: 1, destination: hand}
      - {action: shuffle_deck}
""")


def jiji() -> CardDef:
    return CardDef(card_id="stub-吉雉鸡ex", name="吉雉鸡ex", supertype="pokemon",
                   hp=210, stage=0, rule_box="ex",
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),), retreat_cost=1)


def monkey() -> CardDef:
    return CardDef(card_id="stub-愿增猿", name="愿增猿", supertype="pokemon",
                   hp=110, stage=0,
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),), retreat_cost=1)


def piplup_ex() -> CardDef:
    return CardDef(card_id="stub-莉莉艾的皮皮ex", name="莉莉艾的皮皮ex", supertype="pokemon",
                   hp=190, stage=0, rule_box="ex", energy_type="超",
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),), retreat_cost=1)


def mew() -> CardDef:
    return CardDef(card_id="stub-梦幻ex", name="梦幻ex", supertype="pokemon",
                   hp=180, stage=0, rule_box="ex", energy_type="超",
                   attacks=(AttackDef(name="基因侵入", cost=("无", "无", "无"), damage=None),),
                   retreat_cost=0)


def dragon(hp: int = 130, weakness: str | None = None) -> CardDef:
    return CardDef(card_id="stub-龙兽", name="龙兽", supertype="pokemon",
                   hp=hp, stage=0, energy_type="龙", weakness=weakness,
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),), retreat_cost=1)


def supporter(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def item(name: str = "高级球") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def tool_c(name: str = "勇气护符") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def use_abilities(e, player=0):
    return [a for a in e.legal_actions(player) if a.kind == "use_ability"]


# ── 化危为吉：跨回合 KO 标记 ─────────────────────────────────────────────

def _ko_flow(*, ko_victim_on_p0: bool = True, current: int = 1):
    """构造：current 方回合中 p0 战斗场濒死，check_knockouts 触发昏厥→换上。"""
    state = main_state()
    dead = in_play(1, jiji()).model_copy(update={"damage": 999})
    bench = (in_play(70, jiji()),)
    p0 = state.players[0].model_copy(update={"active": dead, "bench": bench})
    state = state.model_copy(update={
        "players": (p0, state.players[1]), "current_player": current,
    })
    e = engine_at(state)
    e.card_effects = {"吉雉鸡ex": JIJI_DOC}
    e.check_knockouts()  # p0 战斗场昏厥 → phase promote
    return e


def test_lucky_find_after_opponent_turn_ko() -> None:
    """对手回合内我方宝可梦昏厥 → 我方回合「化危为吉」可枚举，抽 3 张。"""
    e = _ko_flow(current=1)
    assert e.state.players[0].own_ko_during_opponent_turn
    e.apply(0, Action(kind="promote", bench_index=0))  # 换上后回合权归 p0
    assert e.state.current_player == 0 and e.state.phase == "main"
    acts = use_abilities(e)
    assert acts == [Action(kind="use_ability", iid=70)]
    hand_before = len(e.state.players[0].hand)
    e.apply(0, acts[0])
    assert len(e.state.players[0].hand) == hand_before + 3
    # once_per_turn_shared：本回合第二只同名也不可用
    assert use_abilities(e) == []


def test_lucky_find_not_available_without_ko() -> None:
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, jiji())})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"吉雉鸡ex": JIJI_DOC}
    assert use_abilities(e) == []


def test_lucky_find_not_available_for_own_turn_ko() -> None:
    """昏厥发生在自己回合（如混乱自我昏厥）→ 不满足「上一个对手的回合」。"""
    e = _ko_flow(current=0)
    assert not e.state.players[0].own_ko_during_opponent_turn
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.current_player == 0  # 自己回合继续
    assert use_abilities(e) == []


def test_lucky_find_flag_cleared_after_own_turn_end() -> None:
    """标记在我方回合结束清除：隔回合（对手未再昏厥我方）不可用。"""
    e = _ko_flow(current=1)
    e.apply(0, Action(kind="promote", bench_index=0))
    e.apply(0, Action(kind="end_turn"))  # p0 回合结束 → 清除
    assert not e.state.players[0].own_ko_during_opponent_turn
    e.apply(1, Action(kind="end_turn"))
    assert use_abilities(e) == []


# ── 亢奋脑力：附着恶能量条件 + 转放伤害指示物 ────────────────────────────

def _monkey_engine(*, dark_energy: bool = True, wounded: bool = True):
    state = main_state()
    m = in_play(1, monkey())
    if dark_energy:
        m = m.model_copy(update={
            "attached_energy": m.attached_energy + (inst(9500, energy("基本恶能量", "恶")),),
        })
    bench = (in_play(70, basic("小火龙")).model_copy(update={"damage": 30}),) if wounded else ()
    p0 = state.players[0].model_copy(update={"active": m, "bench": bench})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"愿增猿": MONKEY_DOC}
    return e


def test_brainwave_requires_dark_energy() -> None:
    assert use_abilities(_monkey_engine(dark_energy=True)) == [Action(kind="use_ability", iid=1)]
    assert use_abilities(_monkey_engine(dark_energy=False)) == []


def test_brainwave_moves_three_counters() -> None:
    """转放 min(3, 来源) 个：30 伤害 → 对手 +30；降级决策见模块 docstring。"""
    e = _monkey_engine()
    e.apply(0, Action(kind="use_ability", iid=1))
    # 第一段：选自己身上有指示物的宝可梦（只有 bench 70 有伤）
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert picks == [(70,)]
    e.apply(0, Action(kind="choose", choices=(70,)))
    # 第二段：选对手场上 1 只
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert picks == [(2,)]
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[0].bench[0].damage == 0
    assert e.state.players[1].active.damage == 30
    assert use_abilities(e) == []  # once_per_turn


def test_brainwave_no_wounded_source_not_enumerated() -> None:
    assert use_abilities(_monkey_engine(wounded=False)) == []


# ── 妖精领域：对手龙弱点改写为超 ─────────────────────────────────────────

def _fairy_engine(*, pipi_on_bench: bool = True, defender=None, atk_damage=30):
    state = main_state(p0_active_energies=3)
    atk = state.players[0].active.model_copy(update={
        "stack": (inst(1, CardDef(card_id="stub-超兽", name="超兽", supertype="pokemon",
                                  hp=100, stage=0, energy_type="超",
                                  attacks=(AttackDef(name="念力", cost=("无",), damage=atk_damage),),
                                  retreat_cost=1)),),
    })
    bench = (in_play(70, piplup_ex()),) if pipi_on_bench else ()
    p0 = state.players[0].model_copy(update={"active": atk, "bench": bench})
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, defender or dragon()),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"莉莉艾的皮皮ex": FAIRY_DOC}
    return e


def test_fairy_domain_grants_weakness_to_dragon() -> None:
    """龙卡面无弱点（None）：领域在场 → 超攻击 ×2；不在场 → 原伤害。"""
    e = _fairy_engine(pipi_on_bench=True)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 60  # 30 ×2
    e = _fairy_engine(pipi_on_bench=False)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 30


def test_fairy_domain_non_dragon_unaffected() -> None:
    """防守非龙（小火龙 无属性）：领域不改写。"""
    e = _fairy_engine(pipi_on_bench=True, defender=basic("火兽"))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 30


def test_fairy_domain_dsl_damage_path() -> None:
    """DSL damage 原语同样走有效弱点（贯穿一致性）。"""
    doc = parse_card_doc("""
card:
  name_group: 超兽
effects:
  - trigger: on_attack
    attack: 念力
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 30}}
""")
    e = _fairy_engine(pipi_on_bench=True)
    e.card_effects["超兽"] = doc
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 60


# ── 基因侵入：复制对手战斗场招式 ─────────────────────────────────────────

OPP_DOC = parse_card_doc("""
card:
  name_group: 对手兽
effects:
  - trigger: on_attack
    attack: 咒术
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 70}}
""")


def opp_beast() -> CardDef:
    return CardDef(card_id="stub-对手兽", name="对手兽", supertype="pokemon",
                   hp=200, stage=0, weakness="超",
                   attacks=(AttackDef(name="重拳", cost=("斗", "斗"), damage=50),
                            AttackDef(name="咒术", cost=("超",), damage=None),
                            AttackDef(name="空招", cost=("无",), damage=None)),
                   retreat_cost=1)


def _mew_engine():
    state = main_state(p0_active_energies=3)
    p0 = state.players[0].model_copy(update={"active": in_play(1, mew(), 3)})
    p1 = state.players[1].model_copy(update={"active": in_play(2, opp_beast())})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"梦幻ex": MEW_COPY_DOC, "对手兽": OPP_DOC}
    return e


def test_gene_hack_pool_and_whiteboard_copy() -> None:
    """池 = 有伤害或有 DSL 绑定的招式（空招不进池）；复制白板按梦幻属性结算弱点。"""
    e = _mew_engine()
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert [a.attack_index for a in attacks] == [0]  # 基因侵入
    e.apply(0, attacks[0])
    picks = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert picks == [(0,), (1,)]  # 重拳(0) / 咒术(1)；空招(2) 不进池
    e.apply(0, Action(kind="choose", choices=(0,)))  # 复制重拳 50
    # 对手兽 weakness=超，梦幻 超属性 → ×2 = 100；被复制招式不付能量（斗斗不需有）
    assert e.state.players[1].active.damage == 100
    assert e.state.current_player == 1  # 攻击后回合结束


def test_gene_hack_copy_dsl_attack() -> None:
    """复制 DSL 绑定招式：以我方视角跑对方效果块（opponent_active = 原持有者）。"""
    e = _mew_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(1,)))  # 复制咒术
    # 咒术 70 打回原持有者；对手兽 weakness=超、梦幻 超属性 → ×2 = 140
    assert e.state.players[1].active.damage == 140
    assert e.state.current_player == 1


# ── 奇树 / 派帕 ──────────────────────────────────────────────────────────

def test_iono_both_shuffle_and_draw_prizes() -> None:
    """双方手牌洗回库底，各抽=自身剩余奖赏数（p0 奖 6 / p1 奖 4 → 各抽 6/4）。"""
    state = main_state(p0_extra_hand=(inst(60, supporter("奇树")),))
    p1 = state.players[1].model_copy(update={
        "hand": (inst(90, basic("小火龙")), inst(91, basic("小火龙"))),
        "prizes": state.players[1].prizes[:4],
    })
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.card_effects = {"奇树": IONO_DOC}
    p0_deck_before = len(e.state.players[0].deck)
    p1_deck_before = len(e.state.players[1].deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    p0s, p1s = e.state.players
    assert len(p0s.hand) == 6  # 抽 6（剩余奖赏）
    assert len(p0s.deck) == p0_deck_before + 2 - 6  # 洗回 2（手牌 3 - 本体 1）再抽 6
    assert len(p1s.hand) == 4
    assert len(p1s.deck) == p1_deck_before + 2 - 4
    assert 60 in [c.iid for c in p0s.discard]


def test_arven_two_search_then_shuffle() -> None:
    """派帕：牌库选物品 + 道具各 1 入手（给对手看过），再洗牌。"""
    deck = (inst(100, item()), inst(101, tool_c()),
            *(inst(110 + i, basic("妙蛙种子")) for i in range(5)))
    state = main_state(p0_extra_hand=(inst(60, supporter("派帕")),))
    p0 = state.players[0].model_copy(update={"deck": deck})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"派帕": ARVEN_DOC}
    e.apply(0, Action(kind="play_trainer", iid=60))
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert (100,) in picks and (101,) not in picks  # 第一段只给物品
    e.apply(0, Action(kind="choose", choices=(100,)))
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert (101,) in picks and (100,) not in picks  # 第二段只给道具
    e.apply(0, Action(kind="choose", choices=(101,)))
    hand_iids = [c.iid for c in e.state.players[0].hand]
    assert 100 in hand_iids and 101 in hand_iids


# ── 特性 condition 门：未知词不猜 ────────────────────────────────────────

def test_ability_unknown_condition_raises() -> None:
    doc = parse_card_doc("""
card:
  name_group: 妙蛙种子
effects:
  - trigger: ability_manual
    limit: once_per_turn
    condition: 不存在的词
    actions:
      - {action: draw, count: 1}
""")
    e = engine_at(main_state())
    e.card_effects = {"妙蛙种子": doc}
    with pytest.raises(DslError):
        e.legal_actions(0)


# ── 定义库与对局级确定性 ────────────────────────────────────────────────

def test_card_library_m2_closeout() -> None:
    docs = load_card_dir("cards")
    for name in ("深钵镇", "奇树", "派帕"):
        assert name in docs
    assert len(docs) == 24  # M2 收口 23 + task 024 自验卡（友好宝芬）
    assert any(e.condition == "own_ko_during_opponent_turn" for e in docs["吉雉鸡ex"].effects)
    assert any(e.trigger == "passive_static" for e in docs["莉莉艾的皮皮ex"].effects)
    assert any(e.trigger == "on_attack" and e.attack == "基因侵入"
               for e in docs["梦幻ex"].effects)
    assert any(e.trigger == "stadium_grant" for e in docs["深钵镇"].effects)


def test_play_game_m2_full_coverage_deterministic() -> None:
    """沙奈朵卡组全机制 stub 卡组：同种子事件流 hash 一致。"""
    from battlefrontier.runner.play import play_game

    def mon(name: str, **kw) -> CardDef:
        attacks = kw.pop("attacks", (AttackDef(name="打击", cost=("无",), damage=20),))
        return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                       hp=kw.pop("hp", 100), stage=kw.pop("stage", 0),
                       attacks=attacks,
                       retreat_cost=1, **kw)

    deck = ([mon("拉鲁拉丝")] * 10 + [mon("吉雉鸡ex", hp=210, rule_box="ex")] * 3
            + [mon("愿增猿", hp=110)] * 3 + [mon("梦幻ex", hp=180, rule_box="ex",
              energy_type="超", attacks=(AttackDef(name="基因侵入", cost=("无",), damage=None),))] * 2
            + [CardDef(card_id="stub-深钵镇", name="深钵镇", supertype="trainer",
                       trainer_subtype="竞技场")] * 2
            + [supporter("奇树")] * 2 + [supporter("派帕")] * 2
            + [energy("基本超能量", "超")] * 18 + [energy("基本恶能量", "恶")] * 18)
    assert len(deck) == 60
    effects = load_card_dir("cards")
    r1 = play_game(deck, deck, seed=31, card_effects=effects)
    r2 = play_game(deck, deck, seed=31, card_effects=effects)
    assert r1.events_hash == r2.events_hash
