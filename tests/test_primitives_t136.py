"""原语扩展测试（task 136）：passive_static lock_play 广义门类 / 节点条件
if_attached_energy_ge / discard selector=tools_attached_both——只加不改
（既有测试零改动证明，见全量 pytest）。

- 胖嘟嘟ex 特性 海之咒术：passive_static lock_play category=item/tool +
  condition holder_is_active（task 069 ACE 锁机制广义化，D-136-1）。
- 胖嘟嘟ex 招式 力量压制：节点条件 if_attached_energy_ge:N
  （「附着能量比所需多2个」= 本卡费用 2 + 2 = 4，D-136-2）。
- 道具拆除器：discard selector=tools_attached_both choose=2 args.up_to
  （双方场上宝可梦身上道具 → 各持有者弃牌区，D-136-3）。
"""

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef, InPlayPokemon

HEXDOC = parse_card_doc("""
card:
  name_group: 咒术兽
effects:
  - trigger: passive_static
    condition: holder_is_active
    actions:
      - {action: lock_play, args: {category: item}}
      - {action: lock_play, args: {category: tool}}
""")

HEXDOC_BENCH = parse_card_doc("""
card:
  name_group: 咒术兽
effects:
  - trigger: passive_static
    actions:
      - {action: lock_play, args: {category: item}}
      - {action: lock_play, args: {category: tool}}
""")

BAD_CATEGORY_DOC = parse_card_doc("""
card:
  name_group: 坏锁兽
effects:
  - trigger: passive_static
    actions:
      - {action: lock_play, args: {category: spell}}
""")

TRIALDOC = parse_card_doc("""
card:
  name_group: 试炼兽
effects:
  - trigger: on_attack
    attack: 试炼
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 80}}
      - {action: damage, selector: opponent_active, condition: if_attached_energy_ge:4, args: {amount: 80}}
""")

REMOVERDOC = parse_card_doc("""
card:
  name_group: 拆除器
effects:
  - trigger: on_play
    actions:
      - {action: discard, selector: tools_attached_both, choose: 2, args: {up_to: true}}
""")

DRAW_ITEM_DOC = parse_card_doc("""
card:
  name_group: 抽牌物品
effects:
  - trigger: on_play
    actions:
      - {action: draw, selector: own_deck, count: 1}
""")


def hexxer(has_ability: bool = True) -> CardDef:
    return CardDef(card_id="stub-咒术兽", name="咒术兽", supertype="pokemon",
                   hp=100, stage=0, has_ability=has_ability)


def trial_mon() -> CardDef:
    from battlefrontier.engine.state import AttackDef
    return CardDef(card_id="stub-试炼兽", name="试炼兽", supertype="pokemon",
                   hp=100, stage=0,
                   attacks=(AttackDef(name="试炼", cost=("无", "无"), damage=80),),
                   retreat_cost=1)


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def tool_mon(iid: int, tool_iid: int, card: CardDef | None = None) -> InPlayPokemon:
    m = in_play(iid, card or basic(f"载体{iid}"))
    return m.model_copy(update={"attached_tool": inst(tool_iid, tool_card(f"道具{tool_iid}"))})


def lock_engine(*, hexxer_bench: bool) -> object:
    """p1 场上咒术兽（战斗场或备战区），p0 手牌含物品（60）与道具（61）。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("抽牌物品")),
                                      inst(61, tool_card("勇气护符"))))
    p1 = state.players[1]
    hx = tool_mon(2, 700, hexxer()) if hexxer_bench else in_play(2, hexxer())
    p1 = p1.model_copy(update={"active": None, "bench": (hx,)})
    if not hexxer_bench:
        p1 = p1.model_copy(update={"active": hx, "bench": ()})
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.card_effects = {"咒术兽": HEXDOC, "抽牌物品": DRAW_ITEM_DOC}
    return e


# ── passive_static lock_play：item/tool 门类（胖嘟嘟ex 海之咒术）──────────────


def test_被动物品锁_持有者在战斗场_对手物品不枚举() -> None:
    e = lock_engine(hexxer_bench=False)
    kinds = {(a.kind, a.iid) for a in e.legal_actions(0)}
    assert ("play_trainer", 60) not in kinds


def test_被动物品锁_持有者退到备战区_对手物品恢复枚举() -> None:
    e = lock_engine(hexxer_bench=True)
    kinds = {(a.kind, a.iid) for a in e.legal_actions(0)}
    assert ("play_trainer", 60) in kinds


def test_被动物品锁_持有者无战斗场条件词_备战也锁() -> None:
    """对照：无 condition 的声明在备战区同样生效（条件门逐声明求值）。"""
    e = lock_engine(hexxer_bench=True)
    e.card_effects = {"咒术兽": HEXDOC_BENCH, "抽牌物品": DRAW_ITEM_DOC}
    kinds = {(a.kind, a.iid) for a in e.legal_actions(0)}
    assert ("play_trainer", 60) not in kinds


def test_被动道具锁_持有者在战斗场_对手道具附着不枚举() -> None:
    e = lock_engine(hexxer_bench=False)
    attaches = {a.iid for a in e.legal_actions(0) if a.kind == "attach_tool"}
    assert 61 not in attaches


def test_被动道具锁_持有者退到备战区_对手道具附着恢复() -> None:
    e = lock_engine(hexxer_bench=True)
    attaches = {a.iid for a in e.legal_actions(0) if a.kind == "attach_tool"}
    assert 61 in attaches


def test_被动锁_未知category仍DslError() -> None:
    state = main_state()
    p1 = state.players[1].model_copy(update={"active": in_play(2, basic("坏锁兽"))})
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.card_effects = {"坏锁兽": BAD_CATEGORY_DOC}
    try:
        e.legal_actions(0)
    except DslError as exc:
        assert "lock_play" in str(exc)
    else:
        raise AssertionError("未知 category 应 DslError")


# ── 节点条件 if_attached_energy_ge（胖嘟嘟ex 力量压制 +80 门槛）────────────────


def trial_engine(n_energy: int) -> object:
    """p0 战斗场试炼兽（iid 1，附着 n 个无色能量），p1 战斗场 hp300。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, trial_mon(), n_energy),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, basic("厚皮兽", hp=300))})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"试炼兽": TRIALDOC}
    return e


def test_附着能量不足4_不追加() -> None:
    e = trial_engine(3)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 80


def test_附着能量满4_追加80() -> None:
    e = trial_engine(4)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 160


def test_附着能量超过4_照常追加() -> None:
    e = trial_engine(6)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 160


# ── discard selector=tools_attached_both（道具拆除器）──────────────────────────


def remover_engine(*, with_tools: bool) -> object:
    """p0 手牌含拆除器（iid 60）；双方场上各挂道具。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("拆除器")),))
    p0 = state.players[0].model_copy(update={
        "active": tool_mon(1, 500) if with_tools else in_play(1, basic("载体甲")),
    })
    p1 = state.players[1].model_copy(update={
        "active": tool_mon(2, 501) if with_tools else in_play(2, basic("载体乙")),
        "bench": (tool_mon(80, 502),) if with_tools else (),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"拆除器": REMOVERDOC}
    return e


def test_拆除器_池含双方场上道具_最多2张() -> None:
    e = remover_engine(with_tools=True)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert set(pc.pool_iids) == {500, 501, 502}
    assert pc.min_choose == 0 and pc.max_choose == 2


def test_拆除器_所选道具进各持有者弃牌区() -> None:
    e = remover_engine(with_tools=True)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(500, 501)))
    p0, p1 = e.state.players
    assert 500 in [c.iid for c in p0.discard]
    assert 501 in [c.iid for c in p1.discard]
    assert p0.active.attached_tool is None
    assert p1.active.attached_tool is None
    assert p1.bench[0].attached_tool is not None  # 未选的不动
    assert e.state.phase == "main" and e.state.current_player == 0  # 物品不结束回合
    evs = [ev for ev in e.events if ev.kind == "discard_tool"]
    assert {ev.detail["iid"] for ev in evs} == {500, 501}


def test_拆除器_只选1张合法() -> None:
    e = remover_engine(with_tools=True)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(502,)))
    p1 = e.state.players[1]
    assert 502 in [c.iid for c in p1.discard]
    assert p1.bench[0].attached_tool is None


def test_拆除器_全场上无道具不可打出() -> None:
    """可行性门：双方场上均无道具 → 无效果不可使用（能量回收 up-to 先例）。"""
    e = remover_engine(with_tools=False)
    kinds = {(a.kind, a.iid) for a in e.legal_actions(0)}
    assert ("play_trainer", 60) not in kinds


def test_拆除器_仅对手场上有道具也可打出() -> None:
    """池跨双方：仅对手场有道具即可打出，所选进对手弃牌区。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("拆除器")),))
    p1 = state.players[1].model_copy(update={"active": tool_mon(2, 501)})
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.card_effects = {"拆除器": REMOVERDOC}
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    e.apply(0, Action(kind="choose", choices=(501,)))
    assert 501 in [c.iid for c in e.state.players[1].discard]
