"""原语扩展测试（task 139 池阻断卡引擎扩展批）：只加不改（既有测试零改动
证明，见全量 pytest）。

- D-139-1 apply_status selector=own_active（桃歹郎ex 支配锁链「令新的战斗
  宝可梦陷入【中毒】」——己方效果自毒，status_immunity 对己同守）。
- D-139-2 ability_feasible switch 分支（own_bench choose=1 + filters，
  过滤后池空 → 特性不枚举；switch 原语 filters 透传 chooser）。
- D-139-3 suppress_ability args.stage/except_ability + effect.condition
  （钥圈儿 恶作剧之锁：holder_is_active + 【基础】宝可梦特性消除，除
  「恶作剧之锁」外——无豁免即自我封存）。
- D-139-4 CardDef.ability_names（db abilities 名物化投影，具名豁免数据底座）。
- D-139-5 discard selector=opponent_active_tool（钥圈儿 狙落：伤害前确定目标
  弃对手战斗场道具，无道具 no-op；on_attack 受 protection 守卫 D-WP6-7）。
- D-139-6 choose_mode 模式二选一 + if_mode 节点条件（乌栗：args.options
  声明模式池，不可行模式不进池/恰 1 可行自动选定，选择随挂起冻结穿透）。
- D-139-7 modify_damage args.target_rule_box 列表（乌栗 +30 vs [ex, v]）。
- D-139-8 modify_hp 竞技场来源 + args.target_filters（重力山：双方 2 阶
  最大 HP -30，打出后按新有效 HP 判昏厥 = 既有 _do_play_stadium 触点）。
- D-139-9 节点条件 if_opponent_active_type:<属性>（雪童子-冰砾）。
"""

import pytest
from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    InPlayPokemon,
    SpecialCondition,
)

# ── D-139-1/2：桃歹郎ex 支配锁链（apply_status own_active + switch filters）──

CHAIN_DOC = parse_card_doc("""
card:
  name_group: 链兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: switch, selector: own_bench, choose: 1, filters: [pokemon_恶, not_name:链兽ex]}
      - {action: apply_status, selector: own_active, args: {status: poisoned}}
""")


def chain_ex(iid: int) -> InPlayPokemon:
    card = CardDef(card_id="stub-链兽ex", name="链兽ex", supertype="pokemon",
                   hp=190, stage=0, energy_type="恶", rule_box="ex",
                   has_ability=True, ability_names=("支配锁链",))
    return in_play(iid, card)


def type_mon(iid: int, name: str, energy_type: str) -> InPlayPokemon:
    card = CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=100, stage=0, energy_type=energy_type)
    return in_play(iid, card)


def chain_game(*, bench: tuple[InPlayPokemon, ...]) -> object:
    """p0 战斗场链兽ex + 指定备战；主阶段。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": chain_ex(1),
        "bench": bench,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"链兽ex": CHAIN_DOC}
    return e


def test_支配锁链_备战池按属性与排除名过滤() -> None:
    """池 = 备战区【恶】且非链兽ex：恶兽(80) 入选；雷兽(81)/链兽ex(82) 剔除。"""
    e = chain_game(bench=(type_mon(80, "恶兽", "恶"), type_mon(81, "雷兽", "雷"),
                          chain_ex(82)))
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.pool == "own_bench"
    assert pc.filters == ("pokemon_恶", "not_name:链兽ex")
    assert set(pc.pool_iids) == {80}


def test_支配锁链_换位后新战斗场中毒() -> None:
    """D-139-1：apply_status selector=own_active——「然后，令新的战斗宝可梦
    陷入【中毒】状态」。"""
    e = chain_game(bench=(type_mon(80, "恶兽", "恶"),))
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(80,)))
    p0 = e.state.players[0]
    assert p0.active.current.iid == 80
    assert SpecialCondition.POISONED in p0.active.conditions
    assert p0.bench[0].current.iid == 1  # 原战斗场退备战


def test_支配锁链_过滤后无目标_特性不枚举() -> None:
    e = chain_game(bench=(type_mon(80, "雷兽", "雷"),))
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


# ── D-139-3/4：钥圈儿 恶作剧之锁（suppress stage/except + condition）────────

KLEFKI_DOC = parse_card_doc("""
card:
  name_group: 锁兽
effects:
  - trigger: passive_static
    condition: holder_is_active
    actions:
      - {action: suppress_ability, args: {stage: basic, except_ability: 恶作剧之锁}}
""")

KLEFKI_NOCOND_DOC = parse_card_doc("""
card:
  name_group: 锁兽
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_ability, args: {stage: basic, except_ability: 恶作剧之锁}}
""")

MANUAL_DOC = parse_card_doc("""
card:
  name_group: 锁靶兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: draw, count: 1}
""")


def klefki(iid: int) -> InPlayPokemon:
    card = CardDef(card_id="stub-锁兽", name="锁兽", supertype="pokemon",
                   hp=70, stage=0, energy_type="超",
                   ability_names=("恶作剧之锁",))
    return in_play(iid, card)


def lock_target(iid: int, *, stage: int = 0,
                ability_names: tuple[str, ...] = ("别的特性",)) -> InPlayPokemon:
    card = CardDef(card_id=f"stub-锁靶{iid}", name=f"锁靶{iid}", supertype="pokemon",
                   hp=80, stage=stage, has_ability=True, ability_names=ability_names)
    return in_play(iid, card)


def lock_game(*, klefki_active: bool) -> object:
    """p1 场上锁兽（战斗场=锁生效 / 备战区=锁失效）；p0 战斗场带特性基础兽。"""
    state = main_state()
    k = klefki(5)
    if klefki_active:
        p1 = state.players[1].model_copy(update={"active": k, "bench": ()})
    else:
        p1 = state.players[1].model_copy(update={"active": in_play(2, basic("占位")),
                                                 "bench": (k,)})
    p0 = state.players[0].model_copy(update={"active": lock_target(1)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"锁兽": KLEFKI_DOC, "锁靶1": MANUAL_DOC}
    return e


def test_恶作剧之锁_战斗中消除对方基础特性() -> None:
    e = lock_game(klefki_active=True)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


def test_恶作剧之锁_退备战区解锁() -> None:
    e = lock_game(klefki_active=False)
    assert [a.iid for a in e.legal_actions(0) if a.kind == "use_ability"] == [1]


def test_恶作剧之锁_无condition_备战区也锁() -> None:
    """对照：无 condition 的声明在备战区同样生效（条件门逐声明求值）。"""
    e = lock_game(klefki_active=False)
    e.card_effects = {"锁兽": KLEFKI_NOCOND_DOC, "锁靶1": MANUAL_DOC}
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


def test_恶作剧之锁_进化兽不受影响() -> None:
    e = lock_game(klefki_active=True)
    p0 = e.state.players[0].model_copy(update={"active": lock_target(1, stage=1)})
    e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    assert [a.iid for a in e.legal_actions(0) if a.kind == "use_ability"] == [1]


def test_恶作剧之锁_自身特性豁免_双锁兽同场不互锁() -> None:
    """「除『恶作剧之锁』外」：锁兽（基础）自己的同名特性不被消除——
    双锁兽同场时对方的锁仍生效（无自我封存/互锁停摆）。"""
    e = lock_game(klefki_active=True)
    p1 = e.state.players[1].model_copy(update={
        "active": klefki(5), "bench": (klefki(6),)})
    e.state = e.state.model_copy(update={"players": (e.state.players[0], p1)})
    assert not e._ability_suppressed(e.state.players[1].active)
    assert not e._ability_suppressed(e.state.players[1].bench[0])
    # 无同名特性的基础仍被消除
    assert e._ability_suppressed(e.state.players[0].active)
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


def test_恶作剧之锁_未知stage词_DslError() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏锁兽
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_ability, args: {stage: mega}}
""")
    state = main_state()
    p1 = state.players[1].model_copy(update={"active": in_play(2, basic("坏锁兽"))})
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.card_effects = {"坏锁兽": bad}
    with pytest.raises(DslError, match="basic"):
        e.legal_actions(0)


def test_恶作剧之锁_无types无stage_DslError() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏锁兽
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_ability, args: {except_ability: 恶作剧之锁}}
""")
    state = main_state()
    p1 = state.players[1].model_copy(update={"active": in_play(2, basic("坏锁兽"))})
    e = engine_at(state.model_copy(update={"players": (state.players[0], p1)}))
    e.card_effects = {"坏锁兽": bad}
    with pytest.raises(DslError, match="suppress_ability"):
        e.legal_actions(0)


# ── D-139-5：钥圈儿 狙落（discard opponent_active_tool）────────────────────

SNIPER_DOC = parse_card_doc("""
card:
  name_group: 狙落兽
effects:
  - trigger: on_attack
    attack: 狙落
    actions:
      - {action: discard, selector: opponent_active_tool}
      - {action: damage, selector: opponent_active, args: {amount: 10}}
""")


def sniper() -> CardDef:
    return CardDef(card_id="stub-狙落兽", name="狙落兽", supertype="pokemon",
                   hp=70, stage=0,
                   attacks=(AttackDef(name="狙落", cost=("无",), damage=10),))


def sniper_game(*, with_tool: bool, protection: bool = False) -> object:
    state = main_state()
    target = in_play(2, basic("厚皮兽", hp=300))
    if with_tool:
        tool = CardDef(card_id="stub-道具", name="被狙道具", supertype="trainer",
                       trainer_subtype="宝可梦道具")
        target = target.model_copy(update={"attached_tool": inst(500, tool)})
    if protection:
        target = target.model_copy(update={"stack": (inst(2, CardDef(
            card_id="stub-幕兽", name="幕兽", supertype="pokemon",
            hp=300, stage=0, has_ability=True)),)})
    p1 = state.players[1].model_copy(update={"active": target})
    p0 = state.players[0].model_copy(update={"active": in_play(1, sniper(), energies=1)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    docs = {"狙落兽": SNIPER_DOC}
    if protection:
        docs["幕兽"] = parse_card_doc("""
card:
  name_group: 幕兽
effects:
  - trigger: passive_static
    actions:
      - {action: protection, args: {scope: opponent_attack_effects}}
""")
    e.card_effects = docs
    return e


def test_狙落_伤害前弃对手战斗场道具_伤害照算() -> None:
    e = sniper_game(with_tool=True)
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    assert p1.active.attached_tool is None
    assert 500 in [c.iid for c in p1.discard]
    assert p1.active.damage == 10
    evs = [ev for ev in e.events if ev.kind == "discard_tool"]
    assert [ev.detail["iid"] for ev in evs] == [500]


def test_狙落_无道具_no_op() -> None:
    e = sniper_game(with_tool=False)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 10


def test_狙落_招式效果免疫守卫_道具不离身() -> None:
    """D-WP6-7 落点：protection（不受对手招式的效果影响）→ 弃道具不适用，
    伤害本体照算。"""
    e = sniper_game(with_tool=True, protection=True)
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    assert p1.active.attached_tool is not None
    assert 500 not in [c.iid for c in p1.discard]
    assert p1.active.damage == 10


# ── D-139-6：乌栗 choose_mode + if_mode ─────────────────────────────────────

MODE_DOC = parse_card_doc("""
card:
  name_group: 乌栗
effects:
  - trigger: on_play
    actions:
      - {action: choose_mode, args: {options: [换位, 增伤]}}
      - {action: switch, selector: own_bench, choose: 1, condition: if_mode:换位}
      - {action: modify_damage, args: {amount: 30, target_rule_box: [ex, v]}, condition: if_mode:增伤}
""")


def mode_card() -> CardDef:
    return CardDef(card_id="stub-乌栗", name="乌栗", supertype="trainer",
                   trainer_subtype="支援者")


def mode_game(*, with_bench: bool = True) -> object:
    state = main_state(p0_extra_hand=(inst(60, mode_card()),))
    p0 = state.players[0].model_copy(update={
        "bench": (in_play(80, basic("备战兽")),) if with_bench else (),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"乌栗": MODE_DOC}
    return e


def test_乌栗_模式池冻结_双模式() -> None:
    e = mode_game()
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.mode_options == ("换位", "增伤")
    assert pc.min_choose == 1 and pc.max_choose == 1
    assert {a.choices for a in e.legal_actions(0) if a.kind == "choose"} == {(0,), (1,)}


def test_乌栗_选增伤_仅执行增伤分支() -> None:
    e = mode_game()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(1,)))
    assert e.state.players[0].turn_damage_mods == ((30, ["ex", "v"]),)
    assert e.state.phase == "main"


def test_乌栗_选换位_分支内二次选择_模式穿透恢复() -> None:
    """模式选择 → 换位分支挂起选备战 → 恢复时 ctx.mode 穿透重建（冻结口径）。"""
    e = mode_game()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(0,)))
    assert e.state.phase == "choice"
    pc = e.state.pending_choice
    assert pc.pool == "own_bench" and set(pc.pool_iids) == {80}
    e.apply(0, Action(kind="choose", choices=(80,)))
    p0 = e.state.players[0]
    assert p0.active.current.iid == 80
    assert p0.turn_damage_mods == ()  # 增伤分支未执行


def test_乌栗_无可行模式_不可打出() -> None:
    """两分支都是换位且无备战 → 打出可行性门拦截（存在可行模式才可打出）。"""
    bad = parse_card_doc("""
card:
  name_group: 乌栗
effects:
  - trigger: on_play
    actions:
      - {action: choose_mode, args: {options: [甲, 乙]}}
      - {action: switch, selector: own_bench, choose: 1, condition: if_mode:甲}
      - {action: switch, selector: own_bench, choose: 1, condition: if_mode:乙}
""")
    e = mode_game(with_bench=False)
    e.card_effects = {"乌栗": bad}
    assert not [a for a in e.legal_actions(0)
                if a.kind == "play_trainer" and a.iid == 60]


def test_乌栗_恰一可行模式_自动选定不挂起() -> None:
    """不可行模式不进池；恰剩 1 个可行模式 = 无选择交互，直接结算。"""
    e = mode_game(with_bench=False)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "main"
    assert e.state.players[0].turn_damage_mods == ((30, ["ex", "v"]),)


def test_乌栗_空options_DslError() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏支援
effects:
  - trigger: on_play
    actions:
      - {action: choose_mode, args: {options: []}}
""")
    state = main_state(p0_extra_hand=(inst(60, mode_card()),))
    e = engine_at(state)
    e.card_effects = {"乌栗": bad}
    with pytest.raises(DslError, match="options"):
        e.legal_actions(0)


def test_乌栗_重复option_DslError() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏支援
effects:
  - trigger: on_play
    actions:
      - {action: choose_mode, args: {options: [换位, 换位]}}
""")
    state = main_state(p0_extra_hand=(inst(60, mode_card()),))
    e = engine_at(state)
    e.card_effects = {"乌栗": bad}
    with pytest.raises(DslError, match="options"):
        e.legal_actions(0)


def test_乌栗_if_mode引用未声明选项_DslError() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏支援
effects:
  - trigger: on_play
    actions:
      - {action: choose_mode, args: {options: [换位]}}
      - {action: draw, count: 1, condition: if_mode:不存在的模式}
""")
    state = main_state(p0_extra_hand=(inst(60, mode_card()),))
    e = engine_at(state)
    e.card_effects = {"乌栗": bad}
    with pytest.raises(DslError, match="if_mode"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_乌栗_双choose_mode_DslError() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏支援
effects:
  - trigger: on_play
    actions:
      - {action: choose_mode, args: {options: [甲]}}
      - {action: choose_mode, args: {options: [乙]}}
""")
    state = main_state(p0_extra_hand=(inst(60, mode_card()),))
    e = engine_at(state)
    e.card_effects = {"乌栗": bad}
    with pytest.raises(DslError, match="choose_mode"):
        e.apply(0, Action(kind="play_trainer", iid=60))


# ── D-139-7：modify_damage target_rule_box 列表 ─────────────────────────────


def boost_game(defender_rule_box: str | None) -> object:
    state = main_state(p0_extra_hand=(inst(60, mode_card()),))
    p0 = state.players[0].model_copy(update={
        "bench": (in_play(80, basic("备战兽")),),  # 换位分支可行 → 双模式进池
    })
    defender = CardDef(card_id="stub-防守兽", name="防守兽", supertype="pokemon",
                       hp=300, stage=0, rule_box=defender_rule_box)
    p1 = state.players[1].model_copy(update={"active": in_play(2, defender)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"乌栗": MODE_DOC}
    return e


def _play_boost(e: object) -> None:
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(1,)))  # 增伤模式


def test_增伤_ex防守方加30() -> None:
    e = boost_game("ex")
    _play_boost(e)
    e.apply(0, Action(kind="attack", attack_index=0))  # 打击 20 + 30
    assert e.state.players[1].active.damage == 50


def test_增伤_v防守方加30() -> None:
    e = boost_game("v")
    _play_boost(e)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50


def test_增伤_无规则盒防守方不加() -> None:
    e = boost_game(None)
    _play_boost(e)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20


# ── D-139-8：重力山（竞技场 modify_hp + target_filters）────────────────────

MOUNTAIN_DOC = parse_card_doc("""
card:
  name_group: 重力山
effects:
  - trigger: passive_static
    actions:
      - {action: modify_hp, args: {amount: -30, target_filters: [stage2_pokemon]}}
""")


def stage2_mon(iid: int, hp: int = 150, damage: int = 0) -> InPlayPokemon:
    m = in_play(iid, CardDef(card_id=f"stub-二阶{iid}", name=f"二阶{iid}",
                             supertype="pokemon", hp=hp, stage=2))
    return m.model_copy(update={"damage": damage}) if damage else m


def mountain_game(*, p1_damage: int = 0) -> object:
    state = main_state()
    p1 = state.players[1].model_copy(update={
        "active": stage2_mon(2, damage=p1_damage)})
    p0 = state.players[0].model_copy(update={
        "hand": state.players[0].hand + (inst(60, CardDef(
            card_id="stub-重力山", name="重力山", supertype="trainer",
            trainer_subtype="竞技场")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"重力山": MOUNTAIN_DOC}
    return e


def test_重力山_双方2阶最大HP减30_基础不受影响() -> None:
    e = mountain_game()
    e.apply(0, Action(kind="play_stadium", iid=60))
    assert e._effective_hp(e.state.players[1].active, 1) == 120  # 150-30
    assert e._effective_hp(e.state.players[0].active, 0) == 70  # 基础 70 不变


def test_重力山_伤害达新HP_打出即昏厥() -> None:
    """rules-manual §8：剩余 HP ≤ 0 昏厥——打出后按新有效 HP 判（既有
    _do_play_stadium 触点，同阻碍之塔 D-029-2 口径）。"""
    e = mountain_game(p1_damage=130)
    e.apply(0, Action(kind="play_stadium", iid=60))
    p1 = e.state.players[1]
    assert 2 in [c.iid for c in p1.discard]
    assert e.state.phase in ("promote", "game_over")


def test_重力山_场被顶_修正即时消失() -> None:
    e = mountain_game()
    e.apply(0, Action(kind="play_stadium", iid=60))
    plain = CardDef(card_id="stub-空场", name="空场", supertype="trainer",
                    trainer_subtype="竞技场")
    e.state = e.state.model_copy(update={"stadium": inst(61, plain)})
    assert e._effective_hp(e.state.players[1].active, 1) == 150


# ── D-139-9：节点条件 if_opponent_active_type ───────────────────────────────

ICE_DOC = parse_card_doc("""
card:
  name_group: 冰砾兽
effects:
  - trigger: on_attack
    attack: 冰砾
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 10}}
      - {action: damage, selector: opponent_active, condition: if_opponent_active_type:斗, args: {amount: 30}}
""")


def ice_mon() -> CardDef:
    return CardDef(card_id="stub-冰砾兽", name="冰砾兽", supertype="pokemon",
                   hp=70, stage=0,
                   attacks=(AttackDef(name="冰砾", cost=("无",), damage=10),))


def ice_game(defender_type: str) -> object:
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, ice_mon(), energies=1)})
    defender = CardDef(card_id="stub-防守兽", name="防守兽", supertype="pokemon",
                       hp=300, stage=0, energy_type=defender_type)
    p1 = state.players[1].model_copy(update={"active": in_play(2, defender)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"冰砾兽": ICE_DOC}
    return e


def test_冰砾_对手斗属性_追加30() -> None:
    e = ice_game("斗")
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 40


def test_冰砾_对手非斗属性_不追加() -> None:
    e = ice_game("火")
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 10
