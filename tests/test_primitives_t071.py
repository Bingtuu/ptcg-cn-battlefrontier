"""task 071 阶段 1：blocked 19 张所需的引擎/DSL 扩展（WP1–17）。

每 WP：正向 + 抑制交互（监视塔/阻碍之塔）+ 边界。规则口径见 tasks/task 071.md。
"""

import pytest
from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.chooser import condition_met, matches
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import AttackDef, CardDef


def mon_card(name: str, **kw) -> CardDef:
    attacks = kw.pop("attacks", (AttackDef(name="打击", cost=("无",), damage=20),))
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=kw.pop("hp", 200), stage=kw.pop("stage", 0), attacks=attacks, **kw,
    )


def item(name: str) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品",
    )


def tool(name: str, attacks: tuple = ()) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="trainer",
        trainer_subtype="宝可梦道具", attacks=attacks,
    )


def stadium(name: str) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="trainer",
        trainer_subtype="竞技场",
    )


def with_effects(state, effects: dict):
    e = engine_at(state)
    e.card_effects = effects
    return e


WATCH = parse_card_doc("""
card:
  name_group: 监视塔
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_ability, args: {types: [无]}}
""")

BLOCKER = parse_card_doc("""
card:
  name_group: 阻碍之塔
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_tool}
""")


def test_wp1_card_filters_positive_and_edges() -> None:
    """WP1：pokemon_no_rule 任意阶段 / rule_box:ex / pokemon_tera。"""
    plain = inst(1, mon_card("普通", stage=1))
    ex = inst(2, mon_card("席ex", rule_box="ex"))
    tera = inst(3, mon_card("珠", is_tera=True))
    basic_ex = inst(4, mon_card("基础ex", rule_box="ex", stage=0))
    assert matches(plain, ("pokemon_no_rule",))
    assert not matches(ex, ("pokemon_no_rule",))
    assert not matches(basic_ex, ("pokemon_no_rule",))
    assert matches(ex, ("rule_box:ex",))
    assert not matches(plain, ("rule_box:ex",))
    assert matches(tera, ("pokemon_tera",))
    assert not matches(plain, ("pokemon_tera",))
    assert not matches(inst(5, energy()), ("pokemon_no_rule",))


def test_wp1_pokemon_prefix_still_means_type() -> None:
    """pokemon_<属性> 存量口径不被 pokemon_no_rule 抢走。"""
    grass = inst(1, mon_card("草", energy_type="草"))
    assert matches(grass, ("pokemon_草",))
    assert not matches(grass, ("pokemon_火",))


def test_wp2_holder_trait_condition() -> None:
    """WP2：holder_trait 读 labels；空标签畸形；无持有者不通过。"""
    future = in_play(1, mon_card("驱", labels=("未来",)))
    e = engine_at(main_state())
    assert condition_met("holder_trait:未来", e, 0, future)
    assert not condition_met("holder_trait:古代", e, 0, future)
    assert not condition_met("holder_trait:未来", e, 0, None)
    with pytest.raises(DslError, match="holder_trait"):
        condition_met("holder_trait:", e, 0, future)


def test_wp2_node_prize_gate_and_energy_gate() -> None:
    """WP2：奖赏恰 6 再抽；节点 holder_has_energy:雷 追加伤害；属性不符不加。"""
    doc = parse_card_doc("""
card:
  name_group: 决心
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
      - {action: draw, count: 1, condition: "if_own_prizes_eq:6"}
""")
    state = main_state(p0_extra_hand=(inst(60, item("决心")),))
    e = with_effects(state, {"决心": doc})
    deck_before = len(e.state.players[0].deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert len(e.state.players[0].deck) == deck_before - 2

    state = main_state(p0_extra_hand=(inst(60, item("决心")),))
    p0 = state.players[0].model_copy(update={"prizes": state.players[0].prizes[:5]})
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"决心": doc})
    deck_before = len(e.state.players[0].deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert len(e.state.players[0].deck) == deck_before - 1

    atk = mon_card("电蜘蛛", energy_type="雷", attacks=(
        AttackDef(name="麻麻网", cost=("无",), damage=None),))
    net = parse_card_doc("""
card:
  name_group: 电蜘蛛
effects:
  - trigger: on_attack
    attack: 麻麻网
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 10}}
      - {action: damage, selector: opponent_active, args: {amount: 20}, condition: "holder_has_energy:雷"}
""")
    bolt = in_play(1, atk, energies=0)
    bolt = bolt.model_copy(update={
        "attached_energy": (inst(9, energy("雷", "雷")),),
    })
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": bolt})
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"电蜘蛛": net})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 30

    grass = bolt.model_copy(update={
        "attached_energy": (inst(9, energy("草", "草")),),
    })
    p0 = state.players[0].model_copy(update={"active": grass})
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"电蜘蛛": net})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 10


def test_wp2_malformed_prize_condition() -> None:
    doc = parse_card_doc("""
card:
  name_group: 坏
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1, condition: "if_own_prizes_eq:x"}
""")
    state = main_state(p0_extra_hand=(inst(60, item("坏")),))
    e = with_effects(state, {"坏": doc})
    with pytest.raises(DslError, match="if_own_prizes_eq"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_wp3_ability_discard_hand_choose_and_watchtower() -> None:
    """WP3：特性成本 discard own_hand choose=N；手牌不足不枚举；监视塔消除。"""
    doc = parse_card_doc("""
card:
  name_group: 索罗
effects:
  - trigger: ability_manual
    limit: once_per_turn
    cost:
      - {action: discard, selector: own_hand, choose: 2}
    actions:
      - {action: draw, count: 1}
""")
    fox = mon_card("索罗", energy_type="恶", has_ability=True)
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, fox)})
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"索罗": doc})
    assert any(a.kind == "use_ability" for a in e.legal_actions(0))
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "choice"
    e.apply(0, Action(kind="choose", choices=(50, 51)))
    assert len(e.state.players[0].hand) == 1  # 弃 2 再抽 1

    poor = p0.model_copy(update={"hand": (inst(50, basic("仅一张")),)})
    e = with_effects(
        state.model_copy(update={"players": (poor, state.players[1])}), {"索罗": doc},
    )
    assert not any(a.kind == "use_ability" for a in e.legal_actions(0))

    watched = mon_card("索罗", energy_type="无", has_ability=True)
    p0 = state.players[0].model_copy(update={"active": in_play(1, watched)})
    st = state.model_copy(update={
        "players": (p0, state.players[1]),
        "stadium": inst(7, stadium("监视塔")),
    })
    e = with_effects(st, {"索罗": doc, "监视塔": WATCH})
    assert not any(a.kind == "use_ability" for a in e.legal_actions(0))


def test_wp4_multi_target_bench_and_deck_bench() -> None:
    """WP4：弃牌区 multi × 备战；牌库段 2 只落备战；备战空 no-op。"""
    horn = parse_card_doc("""
card:
  name_group: 玻璃喇叭
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_discard, filters: [basic_energy], choose: 2, destination: attach, args: {multi_target: true, target_pool: own_bench}}
""")
    b1, b2 = in_play(70, basic("备1")), in_play(71, basic("备2"))
    disc = (inst(80, energy("草", "草")), inst(81, energy("火", "火")))
    state = main_state(p0_extra_hand=(inst(60, item("玻璃喇叭")),))
    p0 = state.players[0].model_copy(update={"bench": (b1, b2), "discard": disc})
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"玻璃喇叭": horn})
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.pending_choice.pool == "own_discard"
    e.apply(0, Action(kind="choose", choices=(80, 81)))
    assert e.state.pending_choice.pool == "own_bench"
    assert set(e.state.pending_choice.pool_iids) == {70, 71}
    e.apply(0, Action(kind="choose", choices=(70, 71)))
    bench = e.state.players[0].bench
    assert {c.iid for c in bench[0].attached_energy} | {
        c.iid for c in bench[1].attached_energy
    } == {80, 81}

    empty = state.players[0].model_copy(update={"bench": (), "discard": disc})
    e = with_effects(
        state.model_copy(update={"players": (empty, state.players[1])}),
        {"玻璃喇叭": horn},
    )
    assert not any(a.kind == "play_trainer" for a in e.legal_actions(0))

    turbo = parse_card_doc("""
card:
  name_group: 涡轮
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_deck, filters: [basic_energy], choose: 1, destination: attach, args: {target_pool: own_bench}}
""")
    deck = (inst(90, energy("雷", "雷")),) + state.players[0].deck
    p0 = state.players[0].model_copy(update={
        "hand": (inst(60, item("涡轮")),),
        "bench": (b1,),
        "deck": deck,
    })
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"涡轮": turbo})
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(90,)))
    assert e.state.pending_choice.pool == "own_bench"
    assert e.state.pending_choice.pool_iids == (70,)


def test_wp5_move_any_count_to_self() -> None:
    """WP5：任意数量场上能量转附自身；选 0 不移动；自身能量不进池。"""
    doc = parse_card_doc("""
card:
  name_group: 斑叶
effects:
  - trigger: on_attack
    attack: 游标
    actions:
      - {action: move_energy, selector: own_attached_energy, args: {any_count: true, target_pool: self}}
""")
    atk = mon_card("斑叶", attacks=(AttackDef(name="游标", cost=("无",), damage=None),))
    active = in_play(1, atk, energies=1)
    bench = in_play(70, basic("备"), energies=2)
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": active, "bench": (bench,)})
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"斑叶": doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    pool = set(e.state.pending_choice.pool_iids)
    self_ids = {c.iid for c in e.state.players[0].active.attached_energy}
    assert pool.isdisjoint(self_ids) and len(pool) == 2
    picked = next(iter(pool))
    e.apply(0, Action(kind="choose", choices=(picked,)))
    assert any(c.iid == picked for c in e.state.players[0].active.attached_energy)
    assert all(c.iid != picked for c in e.state.players[0].bench[0].attached_energy)

    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"斑叶": doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=()))
    assert len(e.state.players[0].active.attached_energy) == 1
    assert len(e.state.players[0].bench[0].attached_energy) == 2


def test_wp6_opponent_energy_and_self_all() -> None:
    """WP6：正面弃对手能量进对手弃牌区；反面不弃；来源全弃不动同伴。"""
    hammer = parse_card_doc("""
card:
  name_group: 粉碎之锤
effects:
  - trigger: on_play
    actions:
      - {action: coin_flip}
      - {action: discard, selector: opponent_attached_energy, choose: 1, condition: if_flip_heads}
""")
    heads = next(s for s in range(30) if RandomSource(s).flip_coin())
    tails = next(s for s in range(30) if not RandomSource(s).flip_coin())
    state = main_state(p0_extra_hand=(inst(60, item("粉碎之锤")),),
                       p1_active_energies=2)
    e = with_effects(state, {"粉碎之锤": hammer})
    e.rng = RandomSource(heads)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    iid = e.state.pending_choice.pool_iids[0]
    e.apply(0, Action(kind="choose", choices=(iid,)))
    opp = e.state.players[1]
    assert any(c.iid == iid for c in opp.discard)
    assert all(c.iid != iid for c in opp.active.attached_energy)

    e = with_effects(state, {"粉碎之锤": hammer})
    e.rng = RandomSource(tails)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase != "choice"
    assert len(e.state.players[1].active.attached_energy) == 2

    bare = main_state(p0_extra_hand=(inst(60, item("粉碎之锤")),),
                      p1_active_energies=0)
    e = with_effects(bare, {"粉碎之锤": hammer})
    e.rng = RandomSource(heads)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase != "choice"

    cannon = parse_card_doc("""
card:
  name_group: 达摩
effects:
  - trigger: on_attack
    attack: 焚身
    actions:
      - {action: discard, selector: own_attached_energy, count: all, args: {scope: self}}
""")
    atk = mon_card("达摩", attacks=(AttackDef(name="焚身", cost=("无",), damage=None),))
    active = in_play(1, atk, energies=2)
    bench = in_play(70, basic("同伴"), energies=1)
    p0 = state.players[0].model_copy(update={"active": active, "bench": (bench,)})
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"达摩": cannon})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[0].active.attached_energy == ()
    assert len(e.state.players[0].bench[0].attached_energy) == 1
    assert len(e.state.players[0].discard) == 2


def test_wp6_item_not_suppressed_by_watchtower() -> None:
    """粉碎之锤是物品：监视塔在场仍可弃对手能量。"""
    hammer = parse_card_doc("""
card:
  name_group: 粉碎之锤
effects:
  - trigger: on_play
    actions:
      - {action: coin_flip}
      - {action: discard, selector: opponent_attached_energy, choose: 1, condition: if_flip_heads}
""")
    heads = next(s for s in range(30) if RandomSource(s).flip_coin())
    state = main_state(p0_extra_hand=(inst(60, item("粉碎之锤")),),
                       p1_active_energies=1)
    st = state.model_copy(update={"stadium": inst(7, stadium("监视塔"))})
    e = with_effects(st, {"粉碎之锤": hammer, "监视塔": WATCH})
    e.rng = RandomSource(heads)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"


def test_wp7_wp16_return_energy_gates_followup() -> None:
    """WP7+WP16：放回牌库并重洗；选 0 不洗且后段跳过；选了才打备战。"""
    doc = parse_card_doc("""
card:
  name_group: 水井
effects:
  - trigger: on_attack
    attack: 激流
    actions:
      - {action: move_energy, selector: own_attached_energy, choose: 3, destination: deck, args: {up_to: true, scope: self}}
      - {action: damage, selector: opponent_bench, choose: 1, args: {amount: 120}, condition: if_prev_optional_done}
""")
    atk = mon_card("水井", attacks=(AttackDef(name="激流", cost=("无",), damage=None),))
    energies = tuple(inst(20 + i, energy()) for i in range(2))
    active = in_play(1, atk).model_copy(update={"attached_energy": energies})
    bench = in_play(80, mon_card("敌备", hp=400))
    state = main_state(p1_bench=(bench,))
    p0 = state.players[0].model_copy(update={"active": active})
    deck_n = len(p0.deck)
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"水井": doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=()))
    assert len(e.state.players[0].active.attached_energy) == 2
    assert len(e.state.players[0].deck) == deck_n
    assert e.state.players[1].bench[0].damage == 0

    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"水井": doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(20,)))
    assert e.state.phase == "choice"
    assert e.state.pending_choice.pool == "opponent_bench"
    assert e.state.pending_choice.prev_optional_done is True
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 120
    assert len(e.state.players[0].deck) == deck_n + 1
    assert len(e.state.players[0].active.attached_energy) == 1


def test_wp16_errors_without_prior_optional() -> None:
    doc = parse_card_doc("""
card:
  name_group: 裸门
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1, condition: if_prev_optional_done}
""")
    state = main_state(p0_extra_hand=(inst(60, item("裸门")),))
    e = with_effects(state, {"裸门": doc})
    with pytest.raises(DslError, match="if_prev_optional_done"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_wp8_reveal_opponent_hand_event_only() -> None:
    """WP8 / D-071-3：reveal 事件含对手手牌名；可见视图仍只有张数。"""
    doc = parse_card_doc("""
card:
  name_group: 咕咕
effects:
  - trigger: on_attack
    attack: 寂静
    actions:
      - {action: reveal, selector: opponent_hand}
""")
    atk = mon_card("咕咕", attacks=(AttackDef(name="寂静", cost=("无",), damage=None),))
    state = main_state()
    secret = inst(77, basic("秘密"))
    p0 = state.players[0].model_copy(update={"active": in_play(1, atk, energies=1)})
    p1 = state.players[1].model_copy(update={"hand": (secret,)})
    e = with_effects(state.model_copy(update={"players": (p0, p1)}), {"咕咕": doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    revealed = [ev for ev in e.events if ev.kind == "reveal"]
    assert revealed and revealed[-1].detail["names"] == ["秘密"]
    view = e.state.visible_state(0)
    assert "秘密" not in str(view.opponent)
    assert not hasattr(view.opponent, "hand")


def test_wp9_opponent_discard_basic_energy_count() -> None:
    """WP9：只数对手弃牌区基本能量；特殊能量不计。"""
    doc = parse_card_doc("""
card:
  name_group: 达摩
effects:
  - trigger: on_attack
    attack: 复燃
    actions:
      - {action: damage, selector: opponent_active, count: opponent_discard_basic_energy_count, args: {op: "×", per: 30}}
""")
    atk = mon_card("达摩", attacks=(AttackDef(name="复燃", cost=("无",), damage=None),))
    special = CardDef(card_id="stub-特", name="特能", supertype="energy",
                      is_basic_energy=False, energy_type="火")
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, atk, energies=1)})
    p1 = state.players[1].model_copy(update={"discard": (
        inst(10, energy()), inst(11, energy()), inst(12, special),
        inst(13, basic("废")),
    )})
    e = with_effects(state.model_copy(update={"players": (p0, p1)}), {"达摩": doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 60


def test_wp10_copy_bench_attack_owner_filter() -> None:
    """WP10：复制自己备战 N 的宝可梦招式；主人不符不进池；空备战 no-op。"""
    doc = parse_card_doc("""
card:
  name_group: 索罗ex
effects:
  - trigger: on_attack
    attack: 暗夜
    actions:
      - {action: copy_attack, selector: own_bench_attack, choose: 1, filters: ["owner_pokemon:N"]}
""")
    copier = mon_card(
        "索罗ex", rule_box="ex",
        attacks=(AttackDef(name="暗夜", cost=("无",), damage=None),),
    )
    donor = mon_card(
        "莱希", owner="N",
        attacks=(AttackDef(name="火焰", cost=("火", "火"), damage=40),),
    )
    other = mon_card("路人", owner="玛俐", attacks=(
        AttackDef(name="撞", cost=("无",), damage=90),))
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, copier, energies=1),
        "bench": (in_play(70, donor), in_play(71, other)),
    })
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"索罗ex": doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.pending_choice.pool_iids == (70,)
    e.apply(0, Action(kind="choose", choices=(70,)))
    assert e.state.pending_choice.pool == "anchored_pokemon_attack"
    e.apply(0, Action(kind="choose", choices=(0,)))
    assert e.state.players[1].active.damage == 40

    empty = state.players[0].model_copy(update={"active": in_play(1, copier, energies=1)})
    e = with_effects(state.model_copy(update={"players": (empty, state.players[1])}),
                     {"索罗ex": doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase != "choice"
    assert e.state.players[1].active.damage == 0


def test_wp10_copy_not_blocked_by_watchtower() -> None:
    """复制是招式不是特性：监视塔不拦截暗夜王牌。"""
    doc = parse_card_doc("""
card:
  name_group: 索罗ex
effects:
  - trigger: on_attack
    attack: 暗夜
    actions:
      - {action: copy_attack, selector: own_bench_attack, choose: 1, filters: ["owner_pokemon:N"]}
""")
    copier = mon_card(
        "索罗ex", energy_type="无", rule_box="ex", has_ability=True,
        attacks=(AttackDef(name="暗夜", cost=("无",), damage=None),),
    )
    donor = mon_card("莱希", owner="N", energy_type="火", attacks=(
        AttackDef(name="火焰", cost=(), damage=15),))
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, copier, energies=1),
        "bench": (in_play(70, donor),),
    })
    st = state.model_copy(update={
        "players": (p0, state.players[1]),
        "stadium": inst(7, stadium("监视塔")),
    })
    e = with_effects(st, {"索罗ex": doc, "监视塔": WATCH})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"


def test_wp11_stadium_retreat_owner_and_stack() -> None:
    """WP11：N 的宝可梦撤退归零（双方）；非 N 不变；all 压过数值减免。"""
    castle = parse_card_doc("""
card:
  name_group: N的城堡
effects:
  - trigger: passive_static
    condition: "holder_owner:N"
    actions:
      - {action: modify_retreat_cost, args: {value: all}}
""")
    nmon = mon_card("N兽", owner="N", retreat_cost=3)
    other = mon_card("路人", owner="玛俐", retreat_cost=3)
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, nmon),
        "bench": (in_play(70, basic("换")),),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, other)})
    st = state.model_copy(update={
        "players": (p0, p1),
        "stadium": inst(8, stadium("N的城堡")),
    })
    e = with_effects(st, {"N的城堡": castle})
    assert e._effective_retreat_cost(e.state.players[0].active, 0) == 0
    assert e._effective_retreat_cost(e.state.players[1].active, 1) == 3
    assert any(a.kind == "retreat" for a in e.legal_actions(0))

    charm = parse_card_doc("""
card:
  name_group: 滑板
effects:
  - trigger: passive_static
    actions:
      - {action: modify_retreat_cost, args: {value: 1}}
""")
    held = in_play(1, nmon).model_copy(update={
        "attached_tool": inst(9, tool("滑板")),
    })
    p0 = p0.model_copy(update={"active": held})
    e = with_effects(state.model_copy(update={
        "players": (p0, p1), "stadium": inst(8, stadium("N的城堡")),
    }), {"N的城堡": castle, "滑板": charm})
    assert e._effective_retreat_cost(e.state.players[0].active, 0) == 0

    blocker_state = state.model_copy(update={
        "players": (p0, p1),
        "stadium": inst(8, stadium("阻碍之塔")),
    })
    e = with_effects(blocker_state, {"阻碍之塔": BLOCKER, "滑板": charm})
    assert e._effective_retreat_cost(e.state.players[0].active, 0) == 3


def test_wp12_rush_evolution_active_only_and_watchtower() -> None:
    """WP12：战斗场跳过登场门；备战不跳；监视塔取消放宽；已进化当回合仍锁。"""
    doc = parse_card_doc("""
card:
  name_group: 伊布
effects:
  - trigger: passive_static
    actions:
      - {action: modify_evolution, args: {skip_play_gates: true}}
""")
    eevee = mon_card("伊布", energy_type="无", has_ability=True)
    flare = mon_card("火伊布", stage=1, evolves_from="伊布")
    state = main_state()
    active = in_play(1, eevee)
    p0 = state.players[0].model_copy(update={
        "active": active,
        "hand": (inst(60, flare),),
        "entered_play_this_turn": frozenset({1}),
    })
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"伊布": doc})
    assert any(a.kind == "evolve" for a in e.legal_actions(0))

    benched = state.players[0].model_copy(update={
        "active": in_play(3, basic("别的")),
        "bench": (active,),
        "hand": (inst(60, flare),),
        "entered_play_this_turn": frozenset({1}),
    })
    e = with_effects(state.model_copy(update={"players": (benched, state.players[1])}),
                     {"伊布": doc})
    assert not any(a.kind == "evolve" for a in e.legal_actions(0))

    st = state.model_copy(update={
        "players": (p0, state.players[1]),
        "stadium": inst(7, stadium("监视塔")),
    })
    e = with_effects(st, {"伊布": doc, "监视塔": WATCH})
    assert not any(a.kind == "evolve" for a in e.legal_actions(0))

    locked = p0.model_copy(update={"evolved_this_turn": frozenset({1})})
    e = with_effects(state.model_copy(update={"players": (locked, state.players[1])}),
                     {"伊布": doc})
    assert not any(a.kind == "evolve" for a in e.legal_actions(0))


def test_wp13_suppress_ko_self_and_watchtower_lifts() -> None:
    """WP13：湿气消除含 ko_self 的特性；普通特性仍在；监视塔压掉湿气来源后恢复。"""
    suicide = parse_card_doc("""
card:
  name_group: 自爆兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: ko_self}
""")
    normal = parse_card_doc("""
card:
  name_group: 普通兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: draw, count: 1}
""")
    mist = parse_card_doc("""
card:
  name_group: 可达鸭
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_ability, args: {with_primitive: ko_self}}
""")
    state = main_state()
    bomber = mon_card("自爆兽", energy_type="火", has_ability=True)
    duck = mon_card("可达鸭", energy_type="水", has_ability=True)
    plain = mon_card("普通兽", energy_type="无", has_ability=True)
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, bomber),
        "bench": (in_play(70, duck), in_play(71, plain)),
    })
    effects = {"自爆兽": suicide, "可达鸭": mist, "普通兽": normal}
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     effects)
    kinds = {(a.kind, a.iid) for a in e.legal_actions(0) if a.kind == "use_ability"}
    assert ( "use_ability", 1) not in kinds
    assert ("use_ability", 71) in kinds

    water_duck = mon_card("可达鸭", energy_type="无", has_ability=True)
    p0 = p0.model_copy(update={"bench": (in_play(70, water_duck), in_play(71, plain))})
    st = state.model_copy(update={
        "players": (p0, state.players[1]),
        "stadium": inst(7, stadium("监视塔")),
    })
    e = with_effects(st, {**effects, "监视塔": WATCH})
    ids = {a.iid for a in e.legal_actions(0) if a.kind == "use_ability"}
    assert 1 in ids  # 湿气来源被监视塔消除，自爆恢复
    assert 71 not in ids  # 普通兽是无属性，监视塔直接消掉


def test_wp14_prize_bonus_non_tera_and_tera_unchanged() -> None:
    """WP14：attack_ko 非太晶多拿 1；太晶旗标仍要求 is_tera；备战昏厥不加。"""
    def attack_doc(scope: str) -> object:
        return parse_card_doc(f"""
card:
  name_group: 臂
effects:
  - trigger: on_attack
    attack: 款待
    actions:
      - {{action: prize_bonus, args: {{amount: 1, scope: {scope}}}}}
      - {{action: damage, selector: opponent_active, args: {{amount: 200}}}}
""")
    atk = mon_card("臂", is_tera=False, attacks=(
        AttackDef(name="款待", cost=("无",), damage=None),))
    foe = mon_card("靶", hp=50)
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, atk, energies=1)})
    p1 = state.players[1].model_copy(update={"active": in_play(2, foe)})
    e = with_effects(
        state.model_copy(update={"players": (p0, p1)}),
        {"臂": attack_doc("attack_ko")},
    )
    prizes_before = len(e.state.players[0].prizes)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert len(e.state.players[0].prizes) == prizes_before - 2

    tera_only = attack_doc("tera_attack_ko")
    e = with_effects(
        state.model_copy(update={"players": (p0, p1)}),
        {"臂": tera_only},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert len(e.state.players[0].prizes) == prizes_before - 1

    bench_doc = parse_card_doc("""
card:
  name_group: 臂
effects:
  - trigger: on_attack
    attack: 款待
    actions:
      - {action: prize_bonus, args: {amount: 1, scope: attack_ko}}
      - {action: damage, selector: opponent_bench, choose: 1, args: {amount: 200}}
""")
    p1b = p1.model_copy(update={
        "active": in_play(2, mon_card("墙", hp=500)),
        "bench": (in_play(80, foe),),
    })
    e = with_effects(
        state.model_copy(update={"players": (p0, p1b)}), {"臂": bench_doc},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert len(e.state.players[0].prizes) == prizes_before - 1


def test_wp15_lock_all_attacks_and_watchtower() -> None:
    """WP15：scope=all 锁双招式与授予招式；下下回合解开；监视塔消掉特性则不上锁。"""
    doc = parse_card_doc("""
card:
  name_group: 火伊布
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: lock_attack, selector: self, args: {scope: all}}
  - trigger: on_attack
    attack: 甲
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 10}}
""")
    flare = mon_card(
        "火伊布", energy_type="火", has_ability=True,
        attacks=(
            AttackDef(name="甲", cost=("无",), damage=None),
            AttackDef(name="乙", cost=("无",), damage=30),
        ),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, flare, energies=1)})
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"火伊布": doc})
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.players[0].active.attack_lock_all
    assert not any(a.kind == "attack" for a in e.legal_actions(0))

    locked = mon_card("火伊布", energy_type="无", has_ability=True, attacks=(
        AttackDef(name="甲", cost=("无",), damage=10),))
    p0 = state.players[0].model_copy(update={"active": in_play(1, locked, energies=1)})
    st = state.model_copy(update={
        "players": (p0, state.players[1]),
        "stadium": inst(7, stadium("监视塔")),
    })
    e = with_effects(st, {"火伊布": doc, "监视塔": WATCH})
    assert not any(a.kind == "use_ability" for a in e.legal_actions(0))
    assert any(a.kind == "attack" for a in e.legal_actions(0))


def test_wp17_grant_attack_synthesizes_when_card_has_no_attacks() -> None:
    """WP17：卡面无招式时按 cost/damage 合成；阻碍之塔不枚举；卡面有招式则不合成。"""
    doc = parse_card_doc("""
card:
  name_group: 能量涡轮
effects:
  - trigger: passive_static
    actions:
      - {action: grant_attack, args: {attack: 能量涡轮, cost: [无], damage: null, discard_at_turn_end: true}}
  - trigger: on_attack
    attack: 能量涡轮
    actions:
      - {action: draw, count: 1}
""")
    learner = tool("能量涡轮")
    holder = in_play(1, basic("持"), energies=1).model_copy(update={
        "attached_tool": inst(90, learner),
    })
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": holder})
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"能量涡轮": doc})
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert [a.attack_index for a in attacks] == [0, 1]
    deck_before = len(e.state.players[0].deck)
    e.apply(0, Action(kind="attack", attack_index=1))
    assert len(e.state.players[0].deck) == deck_before - 1

    st = state.model_copy(update={
        "players": (p0, state.players[1]),
        "stadium": inst(7, stadium("阻碍之塔")),
    })
    e = with_effects(st, {"能量涡轮": doc, "阻碍之塔": BLOCKER})
    assert [a.attack_index for a in e.legal_actions(0) if a.kind == "attack"] == [0]

    faced = tool("学习器", attacks=(AttackDef(name="进化", cost=("无",), damage=None),))
    old = parse_card_doc("""
card:
  name_group: 学习器
effects:
  - trigger: passive_static
    actions:
      - {action: grant_attack, args: {attack: 进化, discard_at_turn_end: true}}
  - trigger: on_attack
    attack: 进化
    actions:
      - {action: draw, count: 1}
""")
    held = in_play(1, basic("持"), energies=1).model_copy(update={
        "attached_tool": inst(91, faced),
    })
    p0 = state.players[0].model_copy(update={"active": held})
    e = with_effects(state.model_copy(update={"players": (p0, state.players[1])}),
                     {"学习器": old})
    assert [a.attack_index for a in e.legal_actions(0) if a.kind == "attack"] == [0, 1]


def test_compound_eye_damage_aura() -> None:
    """电蜘蛛 复眼：战斗场来源才加成，且只打有特性的对手；监视塔消除来源。"""
    eye = parse_card_doc("""
card:
  name_group: 电蜘蛛
effects:
  - trigger: passive_static
    actions:
      - {action: modify_damage, args: {amount: 50, scope: self, target_has_ability: true}}
""")
    spider = mon_card("电蜘蛛", energy_type="雷", has_ability=True)
    friend = mon_card("同伴", energy_type="草")
    able = mon_card("有特", has_ability=True, hp=300)
    plain = mon_card("无特", has_ability=False, hp=300)
    state = main_state()

    def damage_of(attacker, defender_card: CardDef, *, tower: bool = False) -> int:
        p0 = state.players[0].model_copy(update={"active": attacker})
        p1 = state.players[1].model_copy(update={"active": in_play(2, defender_card)})
        st = state.model_copy(update={"players": (p0, p1)})
        effects = {"电蜘蛛": eye}
        if tower:
            st = st.model_copy(update={"stadium": inst(7, stadium("监视塔"))})
            effects["监视塔"] = WATCH
        e = with_effects(st, effects)
        e.apply(0, Action(kind="attack", attack_index=0))
        return e.state.players[1].active.damage

    active = in_play(1, spider, energies=1)
    assert damage_of(active, able) == 70
    assert damage_of(active, plain) == 20
    # 蜘蛛在备战：攻击方是同伴，复眼不生效
    p0 = state.players[0].model_copy(update={
        "active": in_play(3, friend, energies=1),
        "bench": (in_play(1, spider),),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, able)})
    e = with_effects(state.model_copy(update={"players": (p0, p1)}), {"电蜘蛛": eye})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
    muted = in_play(1, mon_card("电蜘蛛", energy_type="无", has_ability=True), energies=1)
    assert damage_of(muted, able, tower=True) == 20
