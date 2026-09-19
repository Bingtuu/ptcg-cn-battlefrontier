"""task 026 WP4 机制测试：top_n rest=shuffle / attach bench-only+能量 up-to /
modify_retreat_cost 声明式 / cost 弃置排除。

设计决议（tasks/task 026.md WP4 节）：
- D-WP4-1 撤退费修正语义：modify_retreat_cost 声明式（passive_static，引擎读声明，
  _effective_retreat_cost 求值，撤退枚举与执行两触点接入）；value = 非负 int（减少量，
  加总后 clamp 下限 0）或 "all"（直接归零）；条件式修正由 effect.condition 判定。🔲 待核。
- D-WP4-2 拉帝亚斯ex 作用域：passive_static + scope=own_basic_all（自己全场 stage==0
  撤退费归零）；离场即失效（引擎实时读声明）。🔲 待核。
- D-WP4-3 超级能量回收的成本排除：cost 段弃置 iid 记入执行上下文（挂起/恢复经
  PendingChoice.cost_discarded 穿透），recover args.exclude_cost_discarded=true 时池剔除。
- D-WP4-4 鼓足干劲能量选择：「最多2张」= energy_up_to（段1 min_choose=0）；
  目标「1只备战宝可梦」= 段2 own_bench 必选 1 只（选能量 0 张时不进段2，no-op）。🔲 待核。
- top_n rest=shuffle：「剩余放回牌库并重洗」= 未选卡与牌库其余合并后整库重洗
  （本节点直接洗牌，DSL 不再写 shuffle_deck 节点——重复洗牌 = 种子消耗差异）。
"""

import json

import pytest
from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import ExecutionContext, parse_card_doc, run_effect
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def run_doc(e, doc, source, player: int = 0):
    """直接跑效果（绕过可行性门）：池空 no-op / DslError 等原语层语义用。"""
    ctx = ExecutionContext(engine=e, player=player, source=source,
                           effect_id="test", trigger=doc.effects[0].trigger)
    return run_effect(ctx, doc.effects[0])


def play_engine(doc, name: str = "测试卡", *, p0_bench: tuple = (), discard: tuple = (),
                deck=None, extra_hand: tuple = (), kind="item"):
    """main 阶段：p0 手牌含测试训练家卡（iid 60），弃牌区/备战区/牌库可调。"""
    card_fn = item_card if kind == "item" else supporter_card
    state = main_state(p0_extra_hand=(inst(60, card_fn(name)),) + extra_hand)
    p0 = state.players[0].model_copy(update={"bench": p0_bench, "discard": discard})
    if deck is not None:
        p0 = p0.model_copy(update={"deck": deck})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {name: doc}
    return e


def ability_engine(doc, name: str, *, p0_bench: tuple = (), discard: tuple = (), deck=None):
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, basic(name)), "bench": p0_bench, "discard": discard,
    })
    if deck is not None:
        p0 = p0.model_copy(update={"deck": deck})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {name: doc}
    return e


# ── search_deck top_n rest=shuffle（清单 1-3）────────────────────────────────

SEARCH_SHUFFLE_DOC = parse_card_doc("""
card:
  name_group: 测试重洗
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [trainer_supporter], choose: 1, destination: hand, args: {top_n: 2, rest: shuffle}}
""")

SEARCH_BOTTOM_DOC = parse_card_doc("""
card:
  name_group: 测试重洗
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [trainer_supporter], choose: 1, destination: hand, args: {top_n: 2, rest: deck_bottom}}
""")


def shuffle_deck8() -> tuple:
    """顶 2 张 = 支援者(100) + 宝可梦(101)，其余 6 张宝可梦。"""
    return (inst(100, supporter_card("支援者甲")),) + tuple(
        inst(101 + i, basic(f"库{chr(19968 + i)}")) for i in range(7)
    )


def test_search_top_n_rest_shuffle_reshuffles_whole_deck():
    """清单1：rest=shuffle 检视顶 2 选 1 入手，未选卡与牌库其余合并后整库重洗
    （同种子下牌库序与 rest=deck_bottom 路径不同；多重集不变）。"""
    deck = shuffle_deck8()
    e = play_engine(SEARCH_SHUFFLE_DOC, "测试重洗", deck=deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool_iids == (100,)  # 窗内仅支援者进池
    e.apply(0, Action(kind="choose", choices=(100,)))
    p0 = e.state.players[0]
    assert 100 in [c.iid for c in p0.hand]
    assert sorted(c.iid for c in p0.deck) == [101, 102, 103, 104, 105, 106, 107]

    e2 = play_engine(SEARCH_BOTTOM_DOC, "测试重洗", deck=deck)
    e2.apply(0, Action(kind="play_trainer", iid=60))
    e2.apply(0, Action(kind="choose", choices=(100,)))
    deck_bottom_order = [c.iid for c in e2.state.players[0].deck]
    assert deck_bottom_order == [102, 103, 104, 105, 106, 107, 101]  # 不洗牌对照
    shuffle_order = [c.iid for c in p0.deck]
    assert shuffle_order != deck_bottom_order  # 重洗路径牌库序不同（同种子确定性）


def test_search_top_n_rest_shuffle_no_deck_order_leak():
    """清单1（观测纪律）：事件流只落选择结果，未选卡（iid/卡名）不出现在任何事件。"""
    e = play_engine(SEARCH_SHUFFLE_DOC, "测试重洗", deck=shuffle_deck8())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(100,)))
    payload = json.dumps([ev.detail for ev in e.events], ensure_ascii=False, default=str)
    assert "101" not in payload and "库丁" not in payload  # 未选卡零泄露
    assert "100" in payload  # 选择结果正常落流（choose 事件）


def test_search_top_n_rest_bad_word_dsl_error():
    """清单2：rest 非 deck_top/deck_bottom/shuffle → DslError（不猜）。"""
    doc = parse_card_doc("""
card:
  name_group: 测试重洗
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, choose: 1, destination: hand, args: {top_n: 2, rest: upside_down}}
""")
    e = play_engine(doc, "测试重洗", deck=shuffle_deck8())
    with pytest.raises(DslError, match="search_deck"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_search_top_n_rest_shuffle_short_deck_best_effort():
    """清单3：牌库不足 N（仅 1 张）→ 检视 1 张尽力而为，选走后牌库空。"""
    e = play_engine(SEARCH_SHUFFLE_DOC, "测试重洗",
                    deck=(inst(100, supporter_card("独苗支援者")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool_iids == (100,)
    e.apply(0, Action(kind="choose", choices=(100,)))
    assert [c.iid for c in e.state.players[0].deck] == []
    assert 100 in [c.iid for c in e.state.players[0].hand]


def test_search_top_n_rest_shuffle_choose_zero_still_shuffles():
    """清单3：空选（选 0 张）→ 窗内全部视为剩余，整库重洗（多重集不变、序变）。"""
    deck = shuffle_deck8()
    e = play_engine(SEARCH_SHUFFLE_DOC, "测试重洗", deck=deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51]  # 手牌不变
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 104, 105, 106, 107]
    assert [c.iid for c in p0.deck] != [c.iid for c in deck]  # 整库重洗（序变）


def test_search_top_n_rest_shuffle_empty_window_pool_still_shuffles():
    """清单3：窗内无匹配（池空）→ no-op 不挂起，但「剩余放回并重洗」依然成立。"""
    deck = tuple(inst(100 + i, basic(f"库{chr(19968 + i)}")) for i in range(8))
    e = play_engine(SEARCH_SHUFFLE_DOC, "测试重洗", deck=deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "main" and e.state.pending_choice is None  # 不挂起
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51]
    assert sorted(c.iid for c in p0.deck) == [100, 101, 102, 103, 104, 105, 106, 107]
    assert [c.iid for c in p0.deck] != [c.iid for c in deck]  # 整库重洗（序变）


# ── attach_energy target_pool=own_bench + energy_up_to（清单 4-8）─────────────

ATTACH_BENCH_UPTO_DOC = parse_card_doc("""
card:
  name_group: 测试附着
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: attach_energy, selector: own_discard, filters: [basic_energy], choose: 2, destination: attach, args: {target_pool: own_bench, energy_up_to: true}}
""")

ATTACH_BENCH_ONE_DOC = parse_card_doc("""
card:
  name_group: 测试附着
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: attach_energy, selector: own_discard, filters: [basic_energy, energy_草], choose: 1, destination: attach, args: {target_pool: own_bench}}
""")

ATTACH_BENCH_ITEM_DOC = parse_card_doc("""
card:
  name_group: 测试附着
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_discard, filters: [basic_energy], choose: 1, destination: attach, args: {target_pool: own_bench}}
""")


def test_attach_bench_target_pool_excludes_active():
    """清单4：段2 目标池 = 备战区（战斗场不可选）；能量附着到所选备战宝可梦。"""
    bench = (in_play(70, basic("备战兽")), in_play(71, basic("备战兽乙")))
    discard = (inst(80, energy()), inst(81, energy()))
    e = ability_engine(ATTACH_BENCH_UPTO_DOC, "附着兽", p0_bench=bench, discard=discard)
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(80, 81)))  # 段1：能量
    pc2 = e.state.pending_choice
    assert pc2 is not None and pc2.pool == "own_bench"
    assert pc2.pool_iids == (70, 71)  # 战斗场（iid 1）不可选
    e.apply(0, Action(kind="choose", choices=(71,)))
    p0 = e.state.players[0]
    assert [e_.iid for e_ in p0.bench[1].attached_energy] == [80, 81]
    assert p0.bench[0].attached_energy == ()
    assert [c.iid for c in p0.discard] == []


def test_attach_bench_no_bench_noop_no_suspend():
    """清单4：无备战（目标空）→ no-op 不挂起（原语层语义；可行性门另行拦截枚举）。"""
    e = ability_engine(ATTACH_BENCH_UPTO_DOC, "附着兽", discard=(inst(80, energy()),))
    assert run_doc(e, ATTACH_BENCH_UPTO_DOC, inst(1, basic("附着兽"))) is None
    prim = next(ev for ev in e.events
                if ev.kind == "effect_primitive" and ev.detail["action"] == "attach_energy")
    assert prim.detail["result"]["attached"] == 0
    assert [c.iid for c in e.state.players[0].discard] == [80]  # 能量留弃牌区


def test_attach_energy_up_to_min_zero_and_choose_zero_skips_target():
    """清单5：energy_up_to=true → 段1 min_choose=0；选 0 张 → 不进段2 直接完成。"""
    bench = (in_play(70, basic("备战兽")),)
    discard = (inst(80, energy()), inst(81, energy()))
    e = ability_engine(ATTACH_BENCH_UPTO_DOC, "附着兽", p0_bench=bench, discard=discard)
    e.apply(0, Action(kind="use_ability", iid=1))
    pc1 = e.state.pending_choice
    assert pc1.min_choose == 0 and pc1.max_choose == 2  # up-to
    e.apply(0, Action(kind="choose", choices=()))
    assert e.state.phase == "main" and e.state.pending_choice is None  # 不进段2
    p0 = e.state.players[0]
    assert p0.bench[0].attached_energy == ()
    assert [c.iid for c in p0.discard] == [80, 81]  # 能量留弃牌区


def test_attach_energy_default_min_choose_regression():
    """清单5 回归：未指定 energy_up_to 时保持既有段1 min_choose=choose 行为。"""
    bench = (in_play(70, basic("备战兽")),)
    discard = (inst(80, energy("草能量", "草")), inst(81, energy("草能量", "草")))
    e = ability_engine(ATTACH_BENCH_ONE_DOC, "附着兽", p0_bench=bench, discard=discard)
    e.apply(0, Action(kind="use_ability", iid=1))
    pc1 = e.state.pending_choice
    assert pc1.min_choose == 1 and pc1.max_choose == 1
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert () not in picks  # 无空集选项


def test_attach_bench_single_grass_energy_filter():
    """清单6：choose=1 + target_pool=own_bench + energy_草 过滤（飞天螳螂 辅助斩形态）。"""
    bench = (in_play(70, basic("备战兽")),)
    discard = (inst(80, energy("草能量", "草")), inst(81, energy("火能量", "火")))
    e = ability_engine(ATTACH_BENCH_ONE_DOC, "附着兽", p0_bench=bench, discard=discard)
    e.apply(0, Action(kind="use_ability", iid=1))
    pc1 = e.state.pending_choice
    assert pc1.pool_iids == (80,)  # 火能量被 basic_energy+energy_草 过滤
    e.apply(0, Action(kind="choose", choices=(80,)))
    pc2 = e.state.pending_choice
    assert pc2.pool_iids == (70,)
    e.apply(0, Action(kind="choose", choices=(70,)))
    assert [e_.iid for e_ in e.state.players[0].bench[0].attached_energy] == [80]


def test_attach_bad_params_dsl_error():
    """清单7：target_pool 未知词 / multi_target × target_pool=own_bench → DslError（不猜）。"""
    for args in ("{target_pool: opponent_bench}", "{target_pool: bogus}",
                 "{target_pool: own_bench, multi_target: true}"):
        doc = parse_card_doc(f"""
card:
  name_group: 测试附着
effects:
  - trigger: on_play
    actions:
      - {{action: attach_energy, selector: own_discard, choose: 1, destination: attach, args: {args}}}
""")
        e = play_engine(doc, "测试附着", p0_bench=(in_play(70, basic("备战兽")),),
                        discard=(inst(80, energy()),))
        with pytest.raises(DslError, match="attach_energy"):
            e.apply(0, Action(kind="play_trainer", iid=60))


def test_attach_bench_feasibility_gates():
    """清单8：ability_feasible / playable_feasible 补新形式——能量池或备战池为空不可行。"""
    bench = (in_play(70, basic("备战兽")),)
    discard = (inst(80, energy()),)
    # ability：双侧非空 → 枚举；备战空 / 能量空 → 不枚举
    e = ability_engine(ATTACH_BENCH_UPTO_DOC, "附着兽", p0_bench=bench, discard=discard)
    assert Action(kind="use_ability", iid=1) in e.legal_actions(0)
    e2 = ability_engine(ATTACH_BENCH_UPTO_DOC, "附着兽", discard=discard)
    assert not [a for a in e2.legal_actions(0) if a.kind == "use_ability"]
    e3 = ability_engine(ATTACH_BENCH_UPTO_DOC, "附着兽", p0_bench=bench,
                        discard=(inst(82, basic("喵喵")),))
    assert not [a for a in e3.legal_actions(0) if a.kind == "use_ability"]
    # playable：同口径
    e4 = play_engine(ATTACH_BENCH_ITEM_DOC, "测试附着", p0_bench=bench, discard=discard)
    assert Action(kind="play_trainer", iid=60) in e4.legal_actions(0)
    e5 = play_engine(ATTACH_BENCH_ITEM_DOC, "测试附着", discard=discard)
    assert not [a for a in e5.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]
    e6 = play_engine(ATTACH_BENCH_ITEM_DOC, "测试附着", p0_bench=bench,
                     discard=(inst(82, basic("喵喵")),))
    assert not [a for a in e6.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]


def test_attach_bench_unknown_target_pool_gate_dsl_error():
    """清单8：可行性门遇未知 target_pool 词 → DslError（不猜）。"""
    doc = parse_card_doc("""
card:
  name_group: 测试附着
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: attach_energy, selector: own_discard, choose: 1, destination: attach, args: {target_pool: opponent_bench}}
""")
    e = ability_engine(doc, "附着兽", discard=(inst(80, energy()),))
    with pytest.raises(DslError, match="attach_energy"):
        e.legal_actions(0)


# ── modify_retreat_cost 声明式（清单 9-12）────────────────────────────────────

SKATE_DOC = parse_card_doc("""
card:
  name_group: 测试滑板
effects:
  - trigger: passive_static
    actions:
      - {action: modify_retreat_cost, args: {value: 1}}
  - trigger: passive_static
    condition: holder_hp_le:30
    actions:
      - {action: modify_retreat_cost, args: {value: "all"}}
""")

SKYLINE_DOC = parse_card_doc("""
card:
  name_group: 测试天际线
effects:
  - trigger: passive_static
    actions:
      - {action: modify_retreat_cost, args: {value: "all", scope: own_basic_all}}
""")


def retreat_engine(*, active_card=None, energies: int = 0, tool_doc=None,
                   damage: int = 0, p0_extra_bench: tuple = (),
                   extra_effects: dict | None = None):
    """main 阶段：p0 战斗场（撤退费/能量/道具/伤害可调）+ 备战 1 只占位兽。"""
    mon_card = active_card if active_card is not None else basic("撤退兽", retreat=2)
    active = in_play(1, mon_card, energies).model_copy(update={"damage": damage})
    if tool_doc is not None:
        active = active.model_copy(update={
            "attached_tool": inst(90, tool_card("测试滑板")),
        })
    state = main_state(p0_active_energies=0)
    p0 = state.players[0].model_copy(update={
        "active": active,
        "bench": (in_play(70, basic("占位兽")),) + p0_extra_bench,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = dict(extra_effects or {})
    if tool_doc is not None:
        e.card_effects["测试滑板"] = tool_doc
    return e


def test_modify_retreat_cost_tool_minus_one():
    """清单9：道具 modify_retreat_cost value=1 → 撤退费 -1（枚举层与执行层两触点生效）。"""
    e = retreat_engine(energies=2, tool_doc=SKATE_DOC)
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats  # 2 能量 ≥ 有效费用 1
    e.apply(0, retreats[0])
    p0 = e.state.players[0]
    assert len(p0.bench[0].attached_energy) == 1  # 只弃 1 张（卡面 2 − 修正 1）
    assert len(p0.discard) == 1
    assert any(ev.kind == "retreat" and ev.detail["paid"] == 1 for ev in e.events)


def test_modify_retreat_cost_tool_all_when_hp_le_30():
    """清单9：holder_hp_le:30 满足（HP 70−40=30）→ value="all" 全免（0 能量可撤退）。"""
    e = retreat_engine(energies=0, tool_doc=SKATE_DOC, damage=40)
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats
    e.apply(0, retreats[0])
    p0 = e.state.players[0]
    assert p0.bench[0].attached_energy == () and p0.discard == ()
    assert any(ev.kind == "retreat" and ev.detail["paid"] == 0 for ev in e.events)


def test_modify_retreat_cost_tool_hp_above_30_only_minus_one():
    """清单9：HP>30（70−10=60）→ 只 -1 不全免（1 能量付 1 费撤退）。"""
    e = retreat_engine(energies=1, tool_doc=SKATE_DOC, damage=10)
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats  # 有效费用 1
    e.apply(0, retreats[0])
    assert len(e.state.players[0].bench[0].attached_energy) == 0
    assert len(e.state.players[0].discard) == 1


def test_modify_retreat_cost_tool_removed_inactive():
    """清单9：道具离场即失效（引擎实时读声明）——无道具时按卡面撤退费。"""
    e = retreat_engine(energies=1)  # 无道具，卡面费用 2 > 1 能量
    assert not [a for a in e.legal_actions(0) if a.kind == "retreat"]


def skyline_mon() -> CardDef:
    return CardDef(card_id="stub-测试天际线", name="测试天际线", supertype="pokemon",
                   hp=210, stage=0, rule_box="ex", retreat_cost=2)


def test_modify_retreat_cost_scope_own_basic_all():
    """清单10/D-WP4-2：天际线在场 → 自己全体 stage==0 撤退费归零（战斗场生效）。"""
    e = retreat_engine(energies=0,
                       p0_extra_bench=(in_play(71, skyline_mon()),),
                       extra_effects={"测试天际线": SKYLINE_DOC})
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats  # 0 能量免费撤退
    e.apply(0, retreats[0])
    assert e.state.players[0].discard == ()


def test_modify_retreat_cost_scope_own_basic_all_evolved_not_free():
    """清单10：进化体（stage>=1）不免——天际线只作用【基础】宝可梦。"""
    evolved = CardDef(card_id="stub-进化兽", name="进化兽", supertype="pokemon",
                      hp=90, stage=1, evolves_from="撤退兽", retreat_cost=1)
    e = retreat_engine(active_card=evolved, energies=0,
                       p0_extra_bench=(in_play(71, skyline_mon()),),
                       extra_effects={"测试天际线": SKYLINE_DOC})
    assert not [a for a in e.legal_actions(0) if a.kind == "retreat"]  # 卡面 1 > 0 能量


def test_modify_retreat_cost_scope_own_basic_all_opponent_unaffected():
    """清单10：对手不受影响（对手战斗宝可梦撤退费按卡面）。"""
    state = main_state(p0_active_energies=0, p1_bench=(in_play(72, basic("对手占位")),))
    p0 = state.players[0].model_copy(update={
        "bench": (in_play(70, basic("占位兽")), in_play(71, skyline_mon())),
    })
    # 对手战斗场：撤退费 2、只附 1 能量 → 不免则不可撤退
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("小火龙", retreat=2), 1),
    })
    e = engine_at(state.model_copy(update={
        "players": (p0, p1), "current_player": 1,
    }))
    e.card_effects = {"测试天际线": SKYLINE_DOC}
    assert not [a for a in e.legal_actions(1) if a.kind == "retreat"]


def test_modify_retreat_cost_scope_own_basic_all_source_leaves_inactive():
    """清单10/D-WP4-2：来源离场即失效——备战区无天际线时按卡面费用。"""
    e = retreat_engine(energies=0)  # 无天际线在场
    assert not [a for a in e.legal_actions(0) if a.kind == "retreat"]


def test_modify_retreat_cost_stacking_all_wins():
    """清单11：滑板(-1) + 天际线(all) 并存 → 0（规约无顺序依赖，可交换）。"""
    e = retreat_engine(energies=0, tool_doc=SKATE_DOC,  # HP>30：滑板只 -1
                       p0_extra_bench=(in_play(71, skyline_mon()),),
                       extra_effects={"测试天际线": SKYLINE_DOC})
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats  # all 归零
    e.apply(0, retreats[0])
    assert e.state.players[0].discard == ()


def test_modify_retreat_cost_bad_value_dsl_error():
    """清单11：value 非法（负 int / 未知字符串）→ DslError（不猜）。"""
    for value in ("-1", '"half"'):
        doc = parse_card_doc(f"""
card:
  name_group: 测试滑板
effects:
  - trigger: passive_static
    actions:
      - {{action: modify_retreat_cost, args: {{value: {value}}}}}
""")
        e = retreat_engine(energies=2, tool_doc=doc)
        with pytest.raises(DslError, match="modify_retreat_cost"):
            e.legal_actions(0)


def test_retreat_vanilla_zero_regression():
    """清单12：无声明时撤退行为零回归（卡面费用原值，枚举 + 执行）。"""
    e = retreat_engine(energies=2)
    retreats = [a for a in e.legal_actions(0) if a.kind == "retreat"]
    assert retreats
    e.apply(0, retreats[0])
    p0 = e.state.players[0]
    assert len(p0.bench[0].attached_energy) == 0  # 卡面 2 费全弃
    assert len(p0.discard) == 2
    assert any(ev.kind == "retreat" and ev.detail["paid"] == 2 for ev in e.events)


# ── cost 弃置排除（清单 13-15）────────────────────────────────────────────────

SUPER_RECOVER_DOC = parse_card_doc("""
card:
  name_group: 测试超回收
effects:
  - trigger: on_play
    cost:
      - {action: discard, selector: own_hand, choose: 2}
    actions:
      - {action: recover_from_discard, selector: own_discard, filters: [basic_energy], choose: 4, destination: hand, args: {up_to: true, exclude_cost_discarded: true}}
""")


def test_cost_discarded_excluded_from_recover_pool():
    """清单13：cost 弃置的 2 张基本能量进弃牌区后不可回选（穿透挂起/恢复）。"""
    extra_hand = (inst(80, energy("草能量", "草")), inst(81, energy("火能量", "火")))
    discard = (inst(82, energy("水能量", "水")),)
    e = play_engine(SUPER_RECOVER_DOC, "测试超回收", discard=discard, extra_hand=extra_hand)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc1 = e.state.pending_choice
    assert pc1.pool == "own_hand" and pc1.min_choose == 2  # cost 选择
    e.apply(0, Action(kind="choose", choices=(80, 81)))  # 弃 2 能量
    pc2 = e.state.pending_choice
    assert pc2.pool == "own_discard"
    assert pc2.pool_iids == (82,)  # cost 弃置的 80/81 被剔除（iid 穿透恢复）
    e.apply(0, Action(kind="choose", choices=(82,)))
    p0 = e.state.players[0]
    assert 82 in [c.iid for c in p0.hand]
    assert sorted(c.iid for c in p0.discard) == [60, 80, 81]


def test_cost_discarded_non_energy_normal_recover():
    """清单13 双路径：cost 弃置非能量（本就不匹配过滤器）→ recover 池照常。"""
    extra_hand = (inst(84, item_card("测试物品甲")), inst(85, item_card("测试物品乙")))
    discard = (inst(82, energy("草能量", "草")), inst(86, energy("火能量", "火")))
    e = play_engine(SUPER_RECOVER_DOC, "测试超回收", discard=discard, extra_hand=extra_hand)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(84, 85)))  # 弃 2 非能量
    pc2 = e.state.pending_choice
    assert pc2.pool_iids == (82, 86)  # 既有能量全部可选
    e.apply(0, Action(kind="choose", choices=(82, 86)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51, 82, 86]  # 既有手牌保留 + 回收 2 张
    assert sorted(c.iid for c in p0.discard) == [60, 84, 85]


def test_cost_discarded_gate_hand_lt_2_unplayable():
    """清单14：手牌（除本体）<2 张 → 整卡不可使用（playable_feasible 门）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": (inst(60, item_card("测试超回收")), inst(80, energy("草能量", "草"))),
        "discard": (inst(82, energy("水能量", "水")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"测试超回收": SUPER_RECOVER_DOC}
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]


def test_exclude_cost_discarded_without_cost_section_noop():
    """清单15：无 cost 段 → 空集合无影响（recover 池照常）。"""
    doc = parse_card_doc("""
card:
  name_group: 测试超回收
effects:
  - trigger: on_play
    actions:
      - {action: recover_from_discard, selector: own_discard, filters: [basic_energy], choose: 2, destination: hand, args: {up_to: true, exclude_cost_discarded: true}}
""")
    discard = (inst(82, energy("草能量", "草")),)
    e = play_engine(doc, "测试超回收", discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.pool_iids == (82,)
    e.apply(0, Action(kind="choose", choices=(82,)))
    assert 82 in [c.iid for c in e.state.players[0].hand]


def test_exclude_cost_discarded_bad_flag_dsl_error():
    """清单15：exclude_cost_discarded 非 bool → DslError（不猜）。"""
    doc = parse_card_doc("""
card:
  name_group: 测试超回收
effects:
  - trigger: on_play
    actions:
      - {action: recover_from_discard, selector: own_discard, choose: 1, destination: hand, args: {up_to: true, exclude_cost_discarded: "yes"}}
""")
    e = play_engine(doc, "测试超回收", discard=(inst(82, energy()),))
    with pytest.raises(DslError, match="exclude_cost_discarded"):
        e.apply(0, Action(kind="play_trainer", iid=60))


# ── 攻击宣言口径（清单 18 机制面，2026-09-14 用户裁决：效果无法执行不阻却宣言）───

ATTACK_ATTACH_BENCH_DOC = parse_card_doc("""
card:
  name_group: 干劲兽
effects:
  - trigger: on_attack
    attack: 鼓足干劲
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 20}}
      - {action: attach_energy, selector: own_discard, filters: [basic_energy], choose: 2, destination: attach, args: {target_pool: own_bench, energy_up_to: true}}
""")


def attack_attach_engine(*, p0_bench: tuple = (), discard: tuple = ()):
    """main 阶段（turn=2）：p0 战斗场干劲兽（鼓足干劲 20 + attach bench-only up-to 2）。"""
    from battlefrontier.engine.state import AttackDef
    mon = CardDef(
        card_id="stub-干劲兽", name="干劲兽", supertype="pokemon", hp=160, stage=0,
        attacks=(AttackDef(name="鼓足干劲", cost=("无",), damage=20),),
        retreat_cost=1,
    )
    state = main_state()
    active = in_play(1, mon).model_copy(update={
        "attached_energy": (inst(9001, energy()),),
    })
    p0 = state.players[0].model_copy(update={
        "active": active, "bench": p0_bench, "discard": discard,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"干劲兽": ATTACK_ATTACH_BENCH_DOC}
    return e


def test_attack_attach_bench_empty_bench_still_declarable():
    """裁决（2026-09-14）：招式附加效果无法执行不阻却宣言——无备战仍可宣言，
    伤害照算、attach bench-only 效果 no-op（原语层不挂起）。"""
    e = attack_attach_engine(discard=(inst(80, energy()),))
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert attacks  # 无备战仍可宣言
    e.apply(0, attacks[0])
    assert e.state.phase == "main" and e.state.current_player == 1  # 回合正常推进
    assert e.state.players[1].active.damage == 20  # 伤害照算
    assert e.state.players[0].discard and e.state.players[0].bench == ()  # 附着 no-op


def test_attack_attach_bench_empty_energy_still_declarable_damage_applies():
    """清单18/19 口径：弃牌区无能量仍可宣言——伤害照算、附着效果 no-op。"""
    e = attack_attach_engine(p0_bench=(in_play(70, basic("备战兽")),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "main" and e.state.current_player == 1  # 回合正常推进
    assert e.state.players[1].active.damage == 20  # 伤害照算
    assert e.state.players[0].bench[0].attached_energy == ()
