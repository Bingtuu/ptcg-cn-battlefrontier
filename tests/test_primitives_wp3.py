"""task 026 WP3 机制测试：recover 去向扩展 / search_deck top_n 检视 / attach 多目标 / reveal。

设计决议（tasks/task 026.md WP3 节）：
- D-WP3-1 多目标各附1：先选能量（up-to N）再选等量目标，按选择顺序 FIFO 配对，
  N = min(目标数, 能量数, choose) 收缩。
- D-WP3-3 top_n 检视选择下限：检索统一 up-to 纪律（min_choose=0，牌库非公开区域）。
- D-WP3-4 reveal 一期口径：仅落结构化事件流（iids + 卡名），无状态变更。
- 备战容量：recover/search destination=bench 受备战区 5 只上限约束（池解析即截断）。
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


def ancient(name: str, hp: int = 90) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=hp, stage=0, labels=("古代",))


def run_doc(e, doc, source, player: int = 0):
    """直接跑效果（绕过可行性门）：池空 no-op / DslError 等原语层语义用。"""
    ctx = ExecutionContext(engine=e, player=player, source=source,
                           effect_id="test", trigger=doc.effects[0].trigger)
    return run_effect(ctx, doc.effects[0])


def play_engine(doc, name: str = "测试卡", *, p0_bench: tuple = (), discard: tuple = (),
                deck=None, extra_hand: tuple = (), kind="item"):
    """main 阶段：p0 手牌含测试训练家卡（iid 60），弃牌区/备战区/牌库可调。"""
    card_fn = item_card if kind == "item" else supporter_card
    state = main_state(p0_extra_hand=(inst(60, card_fn(name)),) + extra_hand,
                       )
    p0 = state.players[0].model_copy(update={"bench": p0_bench, "discard": discard})
    if deck is not None:
        p0 = p0.model_copy(update={"deck": deck})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {name: doc}
    return e


# ── recover_from_discard 去向扩展（清单 1-5）────────────────────────────────

RECOVER_BENCH_DOC = parse_card_doc("""
card:
  name_group: 测试回收
effects:
  - trigger: on_play
    actions:
      - {action: recover_from_discard, selector: own_discard, filters: ["name:夜巡灵"], choose: 3, destination: bench}
""")

RECOVER_HAND_UPTO_DOC = parse_card_doc("""
card:
  name_group: 测试回收
effects:
  - trigger: on_play
    actions:
      - {action: recover_from_discard, selector: own_discard, filters: [pokemon_no_rule_or_basic_energy], choose: 3, destination: hand, args: {up_to: true}}
""")

RECOVER_HAND_DOC = parse_card_doc("""
card:
  name_group: 测试回收
effects:
  - trigger: on_play
    actions:
      - {action: recover_from_discard, selector: own_discard, filters: [pokemon_or_basic_energy], choose: 1, destination: hand}
""")


def duskull(name: str = "夜巡灵") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon", hp=60, stage=0)


def test_recover_bench_up_to_and_entered_play():
    """destination=bench（清单1）：up-to（min_choose=0）所选入备战区为 InPlayPokemon、
    登记 entered_play_this_turn；过滤器（name:夜巡灵）生效。"""
    discard = (inst(80, duskull()), inst(81, duskull()), inst(82, duskull()),
               inst(83, basic("喵喵")))
    e = play_engine(RECOVER_BENCH_DOC, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.min_choose == 0 and pc.max_choose == 3
    assert pc.pool_iids == (80, 81, 82)  # 喵喵被 name 过滤器排除
    e.apply(0, Action(kind="choose", choices=(80, 82)))
    p0 = e.state.players[0]
    assert [b.current.iid for b in p0.bench] == [80, 82]
    assert all(isinstance(b.stack, tuple) for b in p0.bench)
    assert {80, 82} <= p0.entered_play_this_turn  # 当回合登场登记（不可进化联动）
    assert [c.iid for c in p0.discard] == [81, 83, 60]  # 未选留存 + 本体进弃牌区
    assert e.state.phase == "main" and e.state.current_player == 0


def test_recover_bench_choose_zero_up_to():
    """destination=bench up-to：选 0 张合法（空结算），效果照常完成。"""
    e = play_engine(RECOVER_BENCH_DOC, discard=(inst(80, duskull()),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    picks = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert picks == [(), (80,)]
    e.apply(0, Action(kind="choose", choices=()))
    assert e.state.players[0].bench == ()
    assert [c.iid for c in e.state.players[0].discard] == [80, 60]
    assert e.state.phase == "main"


def test_recover_bench_capacity_truncates_pool():
    """备战区 5 只容量：池按剩余容量截断（清单2；4 只在场 → 容量 1，池只留第 1 个匹配）。"""
    full4 = tuple(in_play(70 + i, basic("占位兽")) for i in range(4))
    discard = (inst(80, duskull()), inst(81, duskull()), inst(82, duskull()))
    e = play_engine(RECOVER_BENCH_DOC, p0_bench=full4, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool_iids == (80,) and pc.max_choose == 1
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert len(e.state.players[0].bench) == 5
    assert [c.iid for c in e.state.players[0].discard] == [81, 82, 60]


def test_recover_bench_full_noop_no_suspend():
    """备战区满（容量 0）：no-op 不挂起（原语层语义；可行性门另行拦截枚举）。"""
    full5 = tuple(in_play(70 + i, basic("占位兽")) for i in range(5))
    e = play_engine(RECOVER_BENCH_DOC, p0_bench=full5,
                    discard=(inst(80, duskull()),))
    assert run_doc(e, RECOVER_BENCH_DOC, inst(60, item_card("测试回收"))) is None
    assert len(e.state.players[0].bench) == 5
    assert [c.iid for c in e.state.players[0].discard] == [80]


def test_recover_bench_empty_pool_noop():
    """弃牌区无匹配：no-op 不挂起（原语层）。"""
    e = play_engine(RECOVER_BENCH_DOC, discard=(inst(83, basic("喵喵")),))
    assert run_doc(e, RECOVER_BENCH_DOC, inst(60, item_card("测试回收"))) is None
    prim = next(ev for ev in e.events
                if ev.kind == "effect_primitive" and ev.detail["action"] == "recover_from_discard")
    assert prim.detail["result"]["found"] == 0


def test_recover_hand_up_to_min_zero():
    """destination=hand + args.up_to=true（清单3）：min_choose=0，选 0~N 均合法。"""
    rule_box = CardDef(card_id="stub-规矩兽ex", name="规矩兽ex", supertype="pokemon",
                       hp=200, stage=0, rule_box="ex")
    discard = (inst(80, basic("拉鲁拉丝")), inst(81, energy()),
               inst(82, rule_box), inst(83, item_card("高级球")))
    e = play_engine(RECOVER_HAND_UPTO_DOC, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.min_choose == 0 and pc.max_choose == 3
    assert pc.pool_iids == (80, 81)  # 规则盒宝可梦与训练家被过滤
    e.apply(0, Action(kind="choose", choices=()))
    assert [c.iid for c in e.state.players[0].hand] == [50, 51]  # 选 0：手牌不变
    assert e.state.phase == "main"


def test_recover_hand_up_to_choose_some():
    """hand up-to 选 2 张入手。"""
    discard = (inst(80, basic("拉鲁拉丝")), inst(81, energy()))
    e = play_engine(RECOVER_HAND_UPTO_DOC, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(80, 81)))
    assert [c.iid for c in e.state.players[0].hand] == [50, 51, 80, 81]
    assert e.state.phase == "main"


def test_recover_hand_default_min_one_regression():
    """既有 hand 去向默认 min_choose=1 行为回归不变（清单3，夜间担架口径）。"""
    e = play_engine(RECOVER_HAND_DOC, discard=(inst(80, basic("拉鲁拉丝")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.min_choose == 1 and pc.max_choose == 1
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert picks == [(80,)]  # 无空集选项


def test_recover_bad_forms_dsl_error():
    """清单4：未知 destination / bench 去向缺 choose / up_to 用于非 hand → DslError（不猜）。"""
    bad_nodes = (
        # deck_bottom 在词表内但 recover 不支持
        "{action: recover_from_discard, selector: own_discard, choose: 1, destination: deck_bottom}",
        # bench 去向缺 choose（count 形式不猜）
        "{action: recover_from_discard, selector: own_discard, count: 2, destination: bench}",
        # up_to 仅 hand 去向
        "{action: recover_from_discard, selector: own_discard, choose: 1, destination: deck, args: {up_to: true}}",
    )
    for node in bad_nodes:
        doc = parse_card_doc(f"""
card:
  name_group: 测试回收
effects:
  - trigger: on_play
    actions:
      - {node}
""")
        e = play_engine(doc, discard=(inst(80, basic("拉鲁拉丝")),))
        with pytest.raises(DslError, match="recover_from_discard"):
            run_doc(e, doc, inst(60, item_card("测试回收")))


# ── 可行性门（清单5）─────────────────────────────────────────────────────────

RECOVER_BENCH_ABILITY_DOC = parse_card_doc("""
card:
  name_group: 回收兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: recover_from_discard, selector: own_discard, filters: [pokemon], choose: 1, destination: bench}
""")

SEARCH_TOPN_ABILITY_DOC = parse_card_doc("""
card:
  name_group: 检视兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: search_deck, selector: own_deck, choose: 1, destination: hand, args: {top_n: 2, rest: deck_bottom}}
""")


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


def test_playable_feasible_recover_hand_up_to_requires_pool():
    """playable_feasible：hand up-to 形式弃牌区无匹配 → 不可使用；有匹配 → 可使用。"""
    e = play_engine(RECOVER_HAND_UPTO_DOC, discard=(inst(83, item_card("高级球")),))
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]
    e2 = play_engine(RECOVER_HAND_UPTO_DOC, discard=(inst(80, basic("拉鲁拉丝")),))
    assert Action(kind="play_trainer", iid=60) in e2.legal_actions(0)


def test_playable_feasible_recover_bench_gates():
    """playable_feasible：bench 去向——弃牌区无匹配或备战区满 → 不可使用。"""
    e = play_engine(RECOVER_BENCH_DOC, discard=(inst(83, basic("喵喵")),))
    assert not [a for a in e.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]
    full5 = tuple(in_play(70 + i, basic("占位兽")) for i in range(5))
    e2 = play_engine(RECOVER_BENCH_DOC, p0_bench=full5, discard=(inst(80, duskull()),))
    assert not [a for a in e2.legal_actions(0) if a.kind == "play_trainer" and a.iid == 60]
    e3 = play_engine(RECOVER_BENCH_DOC, discard=(inst(80, duskull()),))
    assert Action(kind="play_trainer", iid=60) in e3.legal_actions(0)


def test_playable_feasible_recover_unknown_destination_dsl_error():
    """recover 未知 destination 形式过可行性门仍 DslError（不猜）。"""
    doc = parse_card_doc("""
card:
  name_group: 测试回收
effects:
  - trigger: on_play
    actions:
      - {action: recover_from_discard, selector: own_discard, choose: 1, destination: deck_bottom}
""")
    e = play_engine(doc, discard=(inst(80, basic("拉鲁拉丝")),))
    with pytest.raises(DslError, match="recover_from_discard"):
        e.legal_actions(0)


def test_ability_feasible_recover_bench():
    """ability_feasible 支持 recover bench 去向：弃牌区无匹配 / 备战满 → 特性不枚举。"""
    e = ability_engine(RECOVER_BENCH_ABILITY_DOC, "回收兽",
                       discard=(inst(83, item_card("高级球")),))
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    full5 = tuple(in_play(70 + i, basic("占位兽")) for i in range(5))
    e2 = ability_engine(RECOVER_BENCH_ABILITY_DOC, "回收兽", p0_bench=full5,
                        discard=(inst(80, basic("拉鲁拉丝")),))
    assert not [a for a in e2.legal_actions(0) if a.kind == "use_ability"]
    e3 = ability_engine(RECOVER_BENCH_ABILITY_DOC, "回收兽",
                        discard=(inst(80, basic("拉鲁拉丝")),))
    assert Action(kind="use_ability", iid=1) in e3.legal_actions(0)


def test_ability_feasible_search_top_n():
    """ability_feasible 支持 search_deck top_n 形式：牌库空 → 特性不枚举；非空 → 枚举。"""
    e = ability_engine(SEARCH_TOPN_ABILITY_DOC, "检视兽", deck=())
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    e2 = ability_engine(SEARCH_TOPN_ABILITY_DOC, "检视兽")
    assert Action(kind="use_ability", iid=1) in e2.legal_actions(0)


def test_ability_feasible_search_bench_full_and_unknown_form():
    """ability_feasible：search destination=bench 备战满 → 不枚举；未知 destination → DslError。"""
    bench_search_doc = parse_card_doc("""
card:
  name_group: 检索兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_pokemon], choose: 1, destination: bench}
""")
    full5 = tuple(in_play(70 + i, basic("占位兽")) for i in range(5))
    e = ability_engine(bench_search_doc, "检索兽", p0_bench=full5)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    bad_doc = parse_card_doc("""
card:
  name_group: 检索兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: search_deck, selector: own_deck, choose: 1, destination: deck}
""")
    e2 = ability_engine(bad_doc, "检索兽")
    with pytest.raises(DslError, match="search_deck"):
        e2.legal_actions(0)


# ── search_deck top_n 检视（清单 6-9）────────────────────────────────────────

TOP_N_DOC = parse_card_doc("""
card:
  name_group: 测试检视
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, choose: 1, destination: hand, args: {top_n: 2, rest: deck_bottom}}
""")


def top_n_engine(deck):
    return play_engine(TOP_N_DOC, "测试检视", deck=deck)


def test_search_top_n_pool_is_deck_top():
    """清单6：chooser 池 = 牌库顶 top_n 张；选 1 入手、剩余按原序放牌库下方、不洗牌。"""
    deck = tuple(inst(100 + i, basic(f"顶{chr(19968 + i)}")) for i in range(4))
    e = top_n_engine(deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool_iids == (100, 101)  # 仅顶 2 张
    assert pc.min_choose == 0 and pc.max_choose == 1  # D-WP3-3 从宽 up-to
    e.apply(0, Action(kind="choose", choices=(100,)))
    p0 = e.state.players[0]
    assert 100 in [c.iid for c in p0.hand]
    # 剩余 1 张按原序归库底，牌库其余不动（无 shuffle 节点 → 序列确定）
    assert [c.iid for c in p0.deck] == [102, 103, 101]


def test_search_top_n_rest_deck_top():
    """rest=deck_top：未选卡按原序放回牌库上方。"""
    doc = parse_card_doc("""
card:
  name_group: 测试检视
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, choose: 1, destination: hand, args: {top_n: 2, rest: deck_top}}
""")
    deck = tuple(inst(100 + i, basic(f"顶{chr(19968 + i)}")) for i in range(4))
    e = play_engine(doc, "测试检视", deck=deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(101,)))
    assert [c.iid for c in e.state.players[0].deck] == [100, 102, 103]


def test_search_top_n_short_deck_best_effort_and_empty_noop():
    """清单7：牌库仅 1 张 → 检视 1 张尽力而为；牌库空 → no-op 不挂起。"""
    e = top_n_engine((inst(100, basic("独苗")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc is not None and pc.pool_iids == (100,)
    e.apply(0, Action(kind="choose", choices=(100,)))
    assert [c.iid for c in e.state.players[0].deck] == []
    assert 100 in [c.iid for c in e.state.players[0].hand]
    e2 = top_n_engine(())
    e2.apply(0, Action(kind="play_trainer", iid=60))
    assert e2.state.phase == "main" and e2.state.pending_choice is None
    prim = next(ev for ev in e2.events
                if ev.kind == "effect_primitive" and ev.detail["action"] == "search_deck")
    assert prim.detail["result"]["found"] == 0


def test_search_top_n_bad_params_dsl_error():
    """清单8：top_n 非正 int / choose > top_n / rest 非 deck_top|deck_bottom / rest 缺 top_n
    → DslError（不猜）。"""
    bad_args = (
        "{top_n: 0, rest: deck_bottom}",
        "{top_n: -1, rest: deck_bottom}",
        "{top_n: '2', rest: deck_bottom}",
        "{top_n: true, rest: deck_bottom}",
        "{top_n: 2, rest: deck}",
        "{rest: deck_bottom}",  # rest 缺 top_n
    )
    for args in bad_args:
        doc = parse_card_doc(f"""
card:
  name_group: 测试检视
effects:
  - trigger: on_play
    actions:
      - {{action: search_deck, selector: own_deck, choose: 1, destination: hand, args: {args}}}
""")
        e = play_engine(doc, "测试检视")
        with pytest.raises(DslError, match="search_deck"):
            e.apply(0, Action(kind="play_trainer", iid=60))
    doc = parse_card_doc("""
card:
  name_group: 测试检视
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, choose: 3, destination: hand, args: {top_n: 2, rest: deck_bottom}}
""")
    e = play_engine(doc, "测试检视")
    with pytest.raises(DslError, match="search_deck"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_search_top_n_no_deck_order_leak():
    """清单9：事件流只落选择结果，未选卡（iid/卡名）不出现在任何事件 detail（观测性纪律）。"""
    deck = tuple(inst(100 + i, basic(f"顶{chr(19968 + i)}")) for i in range(4))
    e = top_n_engine(deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(100,)))
    payload = json.dumps([ev.detail for ev in e.events], ensure_ascii=False, default=str)
    assert "101" not in payload and "顶丁" not in payload  # 未选卡零泄露
    assert "100" in payload  # 选择结果正常落流（choose 事件）


# ── attach_energy 多目标各附1（清单 10-12）───────────────────────────────────

ATTACH_MULTI_DOC = parse_card_doc("""
card:
  name_group: 测试气魄
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_discard, filters: [basic_energy], choose: 2, destination: attach, args: {target_filters: ["trait:古代"], multi_target: true}}
""")


def attach_engine(*, p0_bench: tuple = (), discard: tuple = (), doc=ATTACH_MULTI_DOC):
    return play_engine(doc, "测试气魄", p0_bench=p0_bench, discard=discard, kind="supporter")


def test_attach_multi_two_targets_fifo_pairs():
    """清单10：段1 选能量 up-to 2 → 段2 选等量古代目标 → 按选择顺序 FIFO 各附 1。"""
    bench = (in_play(70, ancient("古代兽甲")), in_play(71, ancient("古代兽乙")),
             in_play(72, basic("喵喵")))
    discard = (inst(80, energy()), inst(81, energy()), inst(82, basic("拉鲁拉丝")))
    e = attach_engine(p0_bench=bench, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc1 = e.state.pending_choice
    assert pc1.pool_iids == (80, 81) and pc1.min_choose == 0 and pc1.max_choose == 2
    e.apply(0, Action(kind="choose", choices=(80, 81)))
    pc2 = e.state.pending_choice
    assert pc2.pool_iids == (70, 71)  # 非古代（喵喵/战斗场）被 target_filters 排除
    assert pc2.min_choose == 2 and pc2.max_choose == 2  # 等量目标
    e.apply(0, Action(kind="choose", choices=(70, 71)))
    p0 = e.state.players[0]
    assert [e_.iid for e_ in p0.bench[0].attached_energy] == [80]  # FIFO：80→70
    assert [e_.iid for e_ in p0.bench[1].attached_energy] == [81]  #       81→71
    assert [c.iid for c in p0.discard] == [82, 60]
    assert e.state.phase == "main" and e.state.current_player == 0


def test_attach_multi_shrinks_to_target_count():
    """清单11：目标 1 只 + 能量 2 张 → 收缩 1 对（D-WP3-1），未配对能量留弃牌区。"""
    bench = (in_play(70, ancient("古代兽甲")),)
    discard = (inst(80, energy()), inst(81, energy()))
    e = attach_engine(p0_bench=bench, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(80, 81)))
    pc2 = e.state.pending_choice
    assert pc2.min_choose == 1  # min 收缩至目标池大小
    picks = [a.choices for a in e.legal_actions(0) if a.kind == "choose"]
    assert picks == [(70,)]
    e.apply(0, Action(kind="choose", choices=(70,)))
    p0 = e.state.players[0]
    assert [e_.iid for e_ in p0.bench[0].attached_energy] == [80]
    assert [c.iid for c in p0.discard] == [81, 60]  # 未配对的 81 留弃牌区


def test_attach_multi_no_targets_noop_energies_stay():
    """清单11：目标空 → 段2 不挂起 no-op，已选能量留弃牌区（不消耗）。"""
    discard = (inst(80, energy()), inst(81, energy()))
    e = attach_engine(discard=discard)  # 场上无古代宝可梦
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(80, 81)))
    assert e.state.phase == "main"
    assert [c.iid for c in e.state.players[0].discard] == [80, 81, 60]
    prim = next(ev for ev in e.events
                if ev.kind == "effect_primitive" and ev.detail["action"] == "attach_energy")
    assert prim.detail["result"]["attached"] == 0


def test_attach_multi_choose_zero_energies_noop():
    """段1 选 0 张能量（up-to）→ 直接完成，不进段2。"""
    bench = (in_play(70, ancient("古代兽甲")),)
    discard = (inst(80, energy()),)
    e = attach_engine(p0_bench=bench, discard=discard)
    e.apply(0, Action(kind="play_trainer", iid=60))
    picks = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert picks == [(), (80,)]
    e.apply(0, Action(kind="choose", choices=()))
    assert e.state.phase == "main"
    assert e.state.players[0].bench[0].attached_energy == ()
    assert [c.iid for c in e.state.players[0].discard] == [80, 60]


def test_attach_multi_no_energies_noop_no_suspend():
    """能量空 → 段1 即 no-op 不挂起。"""
    bench = (in_play(70, ancient("古代兽甲")),)
    e = attach_engine(p0_bench=bench, discard=(inst(82, basic("拉鲁拉丝")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert e.state.players[0].bench[0].attached_energy == ()


def test_attach_multi_bad_flag_dsl_error():
    """multi_target 非 bool → DslError（不猜）。"""
    doc = parse_card_doc("""
card:
  name_group: 测试气魄
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_discard, choose: 2, destination: attach, args: {multi_target: yes}}
""")
    # YAML yes → bool True 是合法值；用字符串形式验证非 bool 拦截
    doc2 = parse_card_doc("""
card:
  name_group: 测试气魄
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_discard, choose: 2, destination: attach, args: {multi_target: "yes"}}
""")
    assert doc.effects[0].actions[0].args["multi_target"] is True  # YAML yes 即 True，合法
    e = attach_engine(doc=doc2, discard=(inst(80, energy()),))
    with pytest.raises(DslError, match="attach_energy"):
        e.apply(0, Action(kind="play_trainer", iid=60))


# ── reveal 原语（清单 15）────────────────────────────────────────────────────

REVEAL_DOC = parse_card_doc("""
card:
  name_group: 测试展示
effects:
  - trigger: on_play
    actions:
      - {action: reveal, selector: own_hand, filters: [trainer]}
""")


def test_reveal_event_iids_and_names_no_state_change():
    """reveal：selector 池 iids + 卡名落 reveal 事件，无状态变更（D-WP3-4）。"""
    extra = (inst(61, item_card("测试物品")), inst(62, basic("小火龙")))
    e = play_engine(REVEAL_DOC, "测试展示", extra_hand=extra)
    hand_before = [c.iid for c in e.state.players[0].hand]
    deck_before = [c.iid for c in e.state.players[0].deck]
    e.apply(0, Action(kind="play_trainer", iid=60))
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert reveal.detail["iids"] == [61]  # 仅训练家（filters 生效；本体已离手）
    assert reveal.detail["names"] == ["测试物品"]
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [i for i in hand_before if i != 60]
    assert [c.iid for c in p0.deck] == deck_before
    assert e.state.phase == "main"


def test_reveal_bad_forms_dsl_error():
    """未知/未支持 selector / 带 choose → DslError（不猜）。"""
    for node in (
        "{action: reveal, selector: opponent_hand}",
        "{action: reveal, selector: own_deck}",
        "{action: reveal, selector: own_hand, choose: 1}",
    ):
        doc = parse_card_doc(f"""
card:
  name_group: 测试展示
effects:
  - trigger: on_play
    actions:
      - {node}
""")
        e = play_engine(doc, "测试展示")
        with pytest.raises(DslError, match="reveal"):
            e.apply(0, Action(kind="play_trainer", iid=60))
