"""task 026 WP8 机制测试：特殊能量被动框架——provide_energy 声明式提供值
（D-WP8-1/2）/ 喷射换位触发（D-WP8-3）/ 薄雾 protection 能量来源（D-WP8-4）。

设计决议（tasks/task 026.md WP8 节，2026-09-20 定稿）：
- D-WP8-1 provide_energy 声明式框架：能量卡文档 passive_static + provide_energy
  原语，args.types=[无]（单属性）/ all（彩虹：1 单元抵任意 1 个需求符号含有色）。
  求值点 = 引擎 _energy_units_satisfied（攻击枚举与执行共用，apply 经 legal_actions
  门控）；无文档 → 既有行为（energy_type，None 仅抵无色）；有条件块覆盖无条件块，
  同层 ≥2 条 = DslError（不猜）。匹配算法：有色先精确匹配非彩虹单元、再以彩虹抵、
  余下单元抵无色（彩虹全程只算 1 个单元）。
- D-WP8-2 夜光降级：holder_special_energy_count_ge:2（含自身；特殊能量 =
  supertype=energy 且非 is_basic_energy；基本能量不计）。
- D-WP8-3 喷射换位：own_attach_from_hand_to_bench 目标为备战区时分发——手动
  附着行动（每回合 1 次权）直发；效果附着中 discard/deck 来源不触发（清单 7），
  own_hand 来源触发（task 027 归正，见 tests/test_primitives_t27.py）。
- D-WP8-4 薄雾 protection：_protected_from_attack_effects 并集读取持有者附着
  能量卡文档的 scope=opponent_attack_effects 声明；「已经受到的效果不会消失」
  = 落点守卫天然满足（不做回顾性清除）。
- D-WP8-5 Agent 侧三处 _energy_satisfied 保持自由函数旧口径（本文件不覆盖，
  由 agent 测试既有断言守护）。
"""

import pytest
from helpers import basic, energy, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.chooser import condition_met
from battlefrontier.dsl.loader import DslError, load_vocabularies
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    InPlayPokemon,
    SpecialCondition,
)

# ── 夹具 ─────────────────────────────────────────────────────────────


def pokemon(
    name: str, *, hp: int = 70, attacks: tuple | None = None, damage: int = 20,
    cost: int = 1, retreat: int = 1, rule_box: str | None = None,
    energy_type: str | None = None,
) -> CardDef:
    if attacks is None:
        attacks = (AttackDef(name="打击", cost=("无",) * cost, damage=damage),)
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, attacks=attacks, retreat_cost=retreat,
        rule_box=rule_box, energy_type=energy_type,
    )


def special_energy(name: str) -> CardDef:
    """特殊能量 stub（db 口径：types/provides 为 null → energy_type None、非基本）。"""
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy",
                   is_basic_energy=False)


def mon(
    iid: int, card: CardDef | None = None, *, damage: int = 0,
    conditions: frozenset = frozenset(), energies: int = 0,
    attached: tuple[CardInstance, ...] = (),
    paralyzed_mark: tuple[int, int] | None = None,
) -> InPlayPokemon:
    card = card or pokemon(f"兽{iid}", hp=500)
    return InPlayPokemon(
        stack=(inst(iid, card),),
        attached_energy=(
            tuple(inst(9000 + iid * 10 + j, energy()) for j in range(energies))
            + attached
        ),
        damage=damage, conditions=conditions, paralyzed_mark=paralyzed_mark,
    )


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def board_engine(
    *, p0_active=None, p0_bench: tuple = (), p1_active=None, p1_bench: tuple = (),
    p0_extra_hand: tuple = (), p0_deck=None, p1_deck=None, p1_hand=None,
    turn: int = 2, current: int = 0, seed: int = 0, effects: dict | None = None,
) -> GameEngine:
    """main 阶段局面：current=0（p0 回合，turn=2，先攻 p0），双方战斗场默认 500HP 白板。"""
    state = main_state(p0_extra_hand=p0_extra_hand)
    p0 = state.players[0].model_copy(update={
        "active": p0_active if p0_active is not None else mon(1),
        "bench": p0_bench,
    })
    if p0_deck is not None:
        p0 = p0.model_copy(update={"deck": p0_deck})
    p1 = state.players[1].model_copy(update={
        "active": p1_active if p1_active is not None else mon(2),
        "bench": p1_bench,
    })
    if p1_deck is not None:
        p1 = p1.model_copy(update={"deck": p1_deck})
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
    e = GameEngine(RandomSource(seed))
    e.state = state.model_copy(update={
        "players": (p0, p1), "turn": turn, "current_player": current,
    })
    e.card_effects = effects or {}
    return e


def prim_results(e: GameEngine, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


def attack_kinds(e: GameEngine, player: int = 0) -> list[int]:
    """本回合可枚举的 attack_index 列表。"""
    return [a.attack_index for a in e.legal_actions(player) if a.kind == "attack"]


# ── 内联文档（机制层 stub；卡级真实 YAML 见 test_dsl_cards_b8_wp8.py）──────

JET_DOC = parse_card_doc("""
card:
  name_group: 喷射能量
effects:
  - trigger: passive_static
    actions:
      - {action: provide_energy, args: {types: [无]}}
  - trigger: trigger_on_event
    event: own_attach_from_hand_to_bench
    actions:
      - {action: switch, selector: self}
""")

NIGHT_DOC = parse_card_doc("""
card:
  name_group: 夜光能量
effects:
  - trigger: passive_static
    condition: holder_special_energy_count_ge:2
    actions:
      - {action: provide_energy, args: {types: [无]}}
  - trigger: passive_static
    actions:
      - {action: provide_energy, args: {types: all}}
""")

MIST_DOC = parse_card_doc("""
card:
  name_group: 薄雾能量
effects:
  - trigger: passive_static
    actions:
      - {action: provide_energy, args: {types: [无]}}
  - trigger: passive_static
    actions:
      - {action: protection, args: {scope: opponent_attack_effects}}
""")


def jet(iid: int) -> CardInstance:
    return inst(iid, special_energy("喷射能量"))


def night(iid: int) -> CardInstance:
    return inst(iid, special_energy("夜光能量"))


def mist(iid: int) -> CardInstance:
    return inst(iid, special_energy("薄雾能量"))


ENERGY_FX = {"喷射能量": JET_DOC, "夜光能量": NIGHT_DOC, "薄雾能量": MIST_DOC}


def fire_attacker(name: str = "火兽", cost: tuple = ("火",)) -> CardDef:
    return pokemon(name, attacks=(AttackDef(name="火击", cost=cost, damage=30),))


# ── provide_energy 框架（清单 1-5，D-WP8-1/2）────────────────────────────


def test_no_doc_energy_behavior_regression() -> None:
    """清单1：无 DSL 文档能量行为回归——基本火能量抵【火】/【无】；无属性
    （energy_type None）仅抵无色，不抵有色。"""
    fire = pokemon("火兽", attacks=(AttackDef(name="火击", cost=("火",), damage=30),))
    e = board_engine(p0_active=mon(1, fire, attached=(inst(90, energy("基本火能量", "火")),)))
    assert 0 in attack_kinds(e)  # 1 张基本火 → 【火】可满足
    e = board_engine(p0_active=mon(1, fire, attached=(inst(90, energy()),)))
    assert 0 not in attack_kinds(e)  # None 属性不抵有色
    plain = pokemon("无兽", attacks=(AttackDef(name="打击", cost=("无",), damage=30),))
    e = board_engine(p0_active=mon(1, plain, attached=(inst(90, energy()),)))
    assert 0 in attack_kinds(e)  # None 计入无色（既有口径）


def test_provide_energy_colorless_and_rainbow() -> None:
    """清单2：types=[无] 计入无色不抵有色；types=all 抵任意 1 个有色符号，
    1 张彩虹只抵 1 个符号；彩虹 + 普通混合抵费。"""
    # 喷射（[无]）：【无】可攻、【火】不可
    e = board_engine(p0_active=mon(1, attached=(jet(90),)), effects=ENERGY_FX)
    assert 0 in attack_kinds(e)  # 默认白板 cost=1【无】
    e = board_engine(p0_active=mon(1, fire_attacker(), attached=(jet(90),)),
                     effects=ENERGY_FX)
    assert attack_kinds(e) == []
    # 夜光（all）单独附着：抵【火】
    e = board_engine(p0_active=mon(1, fire_attacker(), attached=(night(90),)),
                     effects=ENERGY_FX)
    assert 0 in attack_kinds(e)
    # 1 张彩虹只抵 1 个符号：【火】【火】需 2 单元
    e = board_engine(
        p0_active=mon(1, fire_attacker(cost=("火", "火")), attached=(night(90),)),
        effects=ENERGY_FX,
    )
    assert attack_kinds(e) == []
    # 彩虹 + 普通混合：夜光 + 基本火 → 【火】【火】可满足
    e = board_engine(
        p0_active=mon(1, fire_attacker(cost=("火", "火")),
                      attached=(night(90), inst(91, energy("基本火能量", "火")))),
        effects=ENERGY_FX,
    )
    assert 0 in attack_kinds(e)
    # 彩虹抵有色后普通单元抵无色：夜光 + 基本水 → 【火】【无】
    e = board_engine(
        p0_active=mon(1, fire_attacker(cost=("火", "无")),
                      attached=(night(90), inst(91, energy("基本水能量", "水")))),
        effects=ENERGY_FX,
    )
    assert 0 in attack_kinds(e)


def test_provide_energy_multi_declaration_rules() -> None:
    """清单3：多声明求值纪律——条件均未通过且无无条件块 → 回退默认；
    同层 ≥2 条通过 → DslError（不猜）；args 畸形 → DslError。"""
    # 0 条通过（条件恒假 + 无无条件块）→ 回退默认（None → 仅无色）
    cond_only = parse_card_doc("""
card:
  name_group: 条件能量
effects:
  - trigger: passive_static
    condition: opponent_prizes_eq:1
    actions:
      - {action: provide_energy, args: {types: all}}
""")
    e = board_engine(p0_active=mon(1, fire_attacker(),
                                   attached=(inst(90, special_energy("条件能量")),)),
                     effects={"条件能量": cond_only})
    assert attack_kinds(e) == []  # 回退默认：None 不抵【火】
    plain = pokemon("无兽", attacks=(AttackDef(name="打击", cost=("无",), damage=30),))
    e = board_engine(p0_active=mon(1, plain,
                                   attached=(inst(90, special_energy("条件能量")),)),
                     effects={"条件能量": cond_only})
    assert 0 in attack_kinds(e)  # 回退默认：None 计入无色
    # ≥2 条有条件通过 → DslError
    two_cond = parse_card_doc("""
card:
  name_group: 双条件能量
effects:
  - trigger: passive_static
    condition: opponent_prizes_eq:6
    actions:
      - {action: provide_energy, args: {types: all}}
  - trigger: passive_static
    condition: opponent_prizes_eq:6
    actions:
      - {action: provide_energy, args: {types: [无]}}
""")
    e = board_engine(p0_active=mon(1, attached=(inst(90, special_energy("双条件能量")),)),
                     effects={"双条件能量": two_cond})
    with pytest.raises(DslError, match="provide_energy"):
        e.legal_actions(0)
    # ≥2 条无条件 → DslError
    two_base = parse_card_doc("""
card:
  name_group: 双基础能量
effects:
  - trigger: passive_static
    actions:
      - {action: provide_energy, args: {types: all}}
  - trigger: passive_static
    actions:
      - {action: provide_energy, args: {types: [无]}}
""")
    e = board_engine(p0_active=mon(1, attached=(inst(90, special_energy("双基础能量")),)),
                     effects={"双基础能量": two_base})
    with pytest.raises(DslError, match="provide_energy"):
        e.legal_actions(0)
    # args 畸形（缺 types / 多属性 / 未知值）→ DslError
    for bad_args in ("{}", "{types: [火, 水]}", "{types: bogus}"):
        bad = parse_card_doc(f"""
card:
  name_group: 坏能量
effects:
  - trigger: passive_static
    actions:
      - {{action: provide_energy, args: {bad_args}}}
""")
        e = board_engine(p0_active=mon(1, attached=(inst(90, special_energy("坏能量")),)),
                         effects={"坏能量": bad})
        with pytest.raises(DslError, match="provide_energy"):
            e.legal_actions(0)


def test_vocab_wp8_words_registered_and_unknown_rejected() -> None:
    """清单3/7：词表同步——actions +provide_energy、events
    +own_attach_from_hand_to_bench 注册；未知词 DslError 不猜。"""
    v = load_vocabularies()
    assert "provide_energy" in v.actions
    assert "own_attach_from_hand_to_bench" in v.events
    with pytest.raises(DslError, match="events"):
        parse_card_doc("""
card:
  name_group: 坏事件卡
effects:
  - trigger: trigger_on_event
    event: own_attach_from_hand_bogus
    actions:
      - {action: switch, selector: self}
""")


def test_night_light_degradation() -> None:
    """清单4：夜光降级——单独附着=彩虹；+任意 1 张其他特殊能量 →【无】；
    2 张夜光互相降级；基本能量不影响计数；condition 词注册。"""
    # 单独附着 = 彩虹（抵【火】）
    e = board_engine(p0_active=mon(1, fire_attacker(), attached=(night(90),)),
                     effects=ENERGY_FX)
    assert 0 in attack_kinds(e)
    # +喷射（其他特殊能量）→ 降级【无】：不抵【火】，可抵【无】
    e = board_engine(p0_active=mon(1, fire_attacker(), attached=(night(90), jet(91))),
                     effects=ENERGY_FX)
    assert attack_kinds(e) == []
    plain = pokemon("无兽", attacks=(AttackDef(name="打击", cost=("无", "无"), damage=30),))
    e = board_engine(p0_active=mon(1, plain, attached=(night(90), jet(91))),
                     effects=ENERGY_FX)
    assert 0 in attack_kinds(e)  # 降级夜光【无】+ 喷射【无】= 2 无色
    # 2 张夜光互相降级（含自身计数）：2 夜光不抵【火】【火】
    e = board_engine(
        p0_active=mon(1, fire_attacker(cost=("火", "火")), attached=(night(90), night(91))),
        effects=ENERGY_FX,
    )
    assert attack_kinds(e) == []
    # 基本能量不影响计数：夜光 + 基本火 → 夜光仍彩虹，【火】【火】可满足
    e = board_engine(
        p0_active=mon(1, fire_attacker(cost=("火", "火")),
                      attached=(night(90), inst(91, energy("基本火能量", "火")))),
        effects=ENERGY_FX,
    )
    assert 0 in attack_kinds(e)
    # condition 词注册（含自身计数：仅 1 张特殊能量时 ge:2 为假）
    e = board_engine(p0_active=mon(1, attached=(night(90),)), effects=ENERGY_FX)
    holder = e.state.players[0].active
    assert condition_met("holder_special_energy_count_ge:2", e, 0, holder) is False
    assert condition_met("holder_special_energy_count_ge:1", e, 0, holder) is True
    assert condition_met("holder_special_energy_count_ge:2", e, 0, None) is False
    with pytest.raises(DslError, match="holder_special_energy_count_ge"):
        condition_met("holder_special_energy_count_ge:x", e, 0, holder)


def test_energy_evaluation_point_consistency() -> None:
    """清单5：求值点一致性——枚举出的彩虹抵费招式可正常执行（apply 经
    legal_actions 门控，枚举与执行同一求值点）；同种子对局不发散。"""
    def run_once() -> list:
        e = board_engine(p0_active=mon(1, fire_attacker(), attached=(night(90),)),
                         effects=ENERGY_FX, seed=5)
        assert 0 in attack_kinds(e)
        e.apply(0, Action(kind="attack", attack_index=0))  # 不抛 IllegalActionError
        assert e.state.players[1].active.damage == 30
        return [(ev.kind, ev.player, tuple(sorted(ev.detail.items())))
                for ev in e.events]
    assert run_once() == run_once()


# ── 喷射换位（清单 6-7，D-WP8-3）─────────────────────────────────────────


def test_jet_switch_on_manual_attach_to_bench() -> None:
    """清单6：手动从手牌附着喷射于备战宝可梦 → 该宝可梦与战斗场互换（事件流
    锚点）；附着权正常消耗；换位后特殊状态按既有口径（回备战方清除）。"""
    statused = mon(1, pokemon("状态兽", hp=300),
                   conditions=frozenset({SpecialCondition.ASLEEP,
                                         SpecialCondition.PARALYZED,
                                         SpecialCondition.CONFUSED}),
                   paralyzed_mark=(1, 1))
    e = board_engine(
        p0_active=statused,
        p0_bench=(mon(70, pokemon("备战兽", hp=300)),),
        p0_extra_hand=(jet(60),),
        effects=ENERGY_FX,
    )
    e.apply(0, Action(kind="attach_energy", iid=60, target_iid=70))
    p0 = e.state.players[0]
    assert p0.active.current.iid == 70          # 备战兽上战斗场
    assert p0.bench[0].current.iid == 1         # 状态兽回备战
    assert p0.active.attached_energy[0].iid == 60  # 喷射随宝可梦上战斗场
    # 回备战方特殊状态清除（既有换位口径，rules-manual §7.1）
    assert p0.bench[0].conditions == frozenset()
    assert p0.bench[0].paralyzed_mark is None
    # 附着权正常消耗 + 事件流锚点
    assert p0.energy_attached_this_turn is True
    triggers = [ev for ev in e.events
                if ev.kind == "trigger_on_event"
                and ev.detail.get("event") == "own_attach_from_hand_to_bench"]
    assert len(triggers) == 1 and triggers[0].detail.get("name") == "喷射能量"
    assert all(a.kind != "attach_energy" for a in e.legal_actions(0))
    assert e.state.phase == "main" and e.state.current_player == 0  # 不翻阶段


def test_jet_attach_to_active_no_trigger() -> None:
    """清单6：附着战斗场不触发（无换位、无事件）；附着无文档能量到备战也不触发。"""
    e = board_engine(p0_extra_hand=(jet(60),), effects=ENERGY_FX)
    e.apply(0, Action(kind="attach_energy", iid=60, target_iid=1))
    p0 = e.state.players[0]
    assert p0.active.current.iid == 1
    assert not any(ev.kind == "trigger_on_event" for ev in e.events)
    # 无 DSL 文档的能量附着备战：无事件、不报错
    e = board_engine(p0_bench=(mon(70),),
                     p0_extra_hand=(inst(60, energy("基本火能量", "火")),))
    e.apply(0, Action(kind="attach_energy", iid=60, target_iid=70))
    assert e.state.players[0].bench[0].attached_energy[0].iid == 60
    assert not any(ev.kind == "trigger_on_event" for ev in e.events)


def test_effect_attach_does_not_trigger_jet() -> None:
    """清单7：效果附着（attach_energy 原语，牌库来源）不触发
    own_attach_from_hand_to_bench（task 027 归正后口径：discard/deck 来源仍不触发，
    own_hand 来源触发——见 test_primitives_t27.py）。"""
    ramp_doc = parse_card_doc("""
card:
  name_group: 测试附能
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_deck, choose: 1, destination: attach}
""")
    deck = (jet(100), inst(101, basic("填充兽")), inst(102, basic("填充兽")))
    e = board_engine(
        p0_bench=(mon(70, pokemon("备战兽", hp=300)),),
        p0_extra_hand=(inst(60, item_card("测试附能")),),
        p0_deck=deck, effects={**ENERGY_FX, "测试附能": ramp_doc}, seed=0,
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(100,)))  # 选牌库中喷射
    e.apply(0, Action(kind="choose", choices=(70,)))   # 附着备战兽
    p0 = e.state.players[0]
    assert p0.bench[0].attached_energy[0].iid == 100  # 已附着
    assert p0.active.current.iid == 1                 # 未换位
    assert not any(ev.kind == "trigger_on_event" for ev in e.events)
    assert p0.energy_attached_this_turn is False      # 效果附着不占每回合并发权


# ── 薄雾 protection（清单 8，D-WP8-4）────────────────────────────────────

COUNTER_ATTACK_DOC = parse_card_doc("""
card:
  name_group: 撒菱兽
effects:
  - trigger: on_attack
    attack: 撒菱
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 30}}
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 2}}
""")

STATUS_ATTACK_DOC = parse_card_doc("""
card:
  name_group: 麻痹兽
effects:
  - trigger: on_attack
    attack: 麻痹击
    actions:
      - {action: apply_status, selector: opponent_active, args: {status: paralyzed}}
""")

LOCK_ATTACK_DOC = parse_card_doc("""
card:
  name_group: 锁链兽
effects:
  - trigger: on_attack
    attack: 锁链
    actions:
      - {action: lock_retreat, selector: opponent_active}
""")


def attack_against(attack_doc, *, mist_attached: bool,
                   defender_conditions: frozenset = frozenset(),
                   defender_hp: int = 300) -> GameEngine:
    """p0 攻击桩以 attack_doc 绑定招式打 p1 战斗场防守兽（可选附着薄雾/已有状态）。"""
    atk_name = attack_doc.effects[0].attack
    attacker = pokemon(attack_doc.card.name_group,
                       attacks=(AttackDef(name=atk_name, cost=("无",), damage=None),))
    attached = (mist(90),) if mist_attached else ()
    defender = mon(2, pokemon("防守兽", hp=defender_hp), attached=attached,
                   conditions=defender_conditions)
    e = board_engine(
        p0_active=mon(1, attacker, energies=1),
        p1_active=defender,
        effects={**ENERGY_FX, attack_doc.card.name_group: attack_doc},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    if e.state.phase == "choice":
        e.apply(0, Action(kind="choose", choices=(2,)))  # 落点选对手战斗场
    return e


def test_mist_protection_counters_status_lock() -> None:
    """清单8：薄雾持有者不受对手招式附加效果——指示物/特殊状态/撤退锁落点抽查；
    伤害照算；能量离场即失效（求值点实时读声明）。"""
    # 指示物落点：伤害 30 照算、2 指示物被挡
    e = attack_against(COUNTER_ATTACK_DOC, mist_attached=True)
    assert e.state.players[1].active.damage == 30
    counter_result = prim_results(e, "place_damage_counters")[0]
    assert counter_result["placed"] == 0
    # 无薄雾：指示物照常（30 伤害 + 20 指示物）
    e = attack_against(COUNTER_ATTACK_DOC, mist_attached=False)
    assert e.state.players[1].active.damage == 50
    # 特殊状态落点：麻痹被挡
    e = attack_against(STATUS_ATTACK_DOC, mist_attached=True)
    assert e.state.players[1].active.conditions == frozenset()
    assert prim_results(e, "apply_status")[0]["reason"] == "protected"
    e = attack_against(STATUS_ATTACK_DOC, mist_attached=False)
    assert SpecialCondition.PARALYZED in e.state.players[1].active.conditions
    # 撤退锁落点：锁被挡（次回合可撤退）
    e = attack_against(LOCK_ATTACK_DOC, mist_attached=True)
    assert e.state.players[1].active.retreat_lock is False
    e = attack_against(LOCK_ATTACK_DOC, mist_attached=False)
    assert e.state.players[1].active.retreat_lock is True


def test_mist_existing_effects_not_cleared() -> None:
    """清单8：「已经受到的效果，不会消失」——附着前已中的特殊状态保留
    （落点守卫不做回顾性清除）。用混乱作既有状态（检查阶段不结算混乱，
    D-WP7-1——不受攻击后回合结束检查掷币影响）。"""
    confused = frozenset({SpecialCondition.CONFUSED})
    e = attack_against(STATUS_ATTACK_DOC, mist_attached=True,
                       defender_conditions=confused)
    p1_active = e.state.players[1].active
    assert SpecialCondition.CONFUSED in p1_active.conditions         # 旧状态保留
    assert SpecialCondition.PARALYZED not in p1_active.conditions   # 新施加被挡
