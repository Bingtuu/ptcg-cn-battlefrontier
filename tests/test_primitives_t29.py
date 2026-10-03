"""task 029 机制测试：suppression 声明式框架（火箭队的监视塔 suppress_ability /
阻碍之塔 suppress_tool）/ lock_play 物品锁（含羞苞 痒痒花粉）/ damage 备战狙击
（苍响 刹那斩）/ attach_energy own_deck distribute（长毛巨魔 庞克泵感）/ 小词
（stadium_in_play / pokemon_<属性> 泛化 / opponent_ability_pokemon_count）。

设计决议（tasks/task 029.md，2026-09-20 定稿）：
- D-029-1 suppress_ability：竞技场 passive_static 声明（args.types=[无]），引擎
  统一守卫 _ability_suppressed 单入口；消除面 = ability_manual 枚举门 + 宝可梦卡
  来源被动 aura + 宝可梦卡来源 trigger_on_event 分发；竞技场离场即恢复，无追溯。
- D-029-2 suppress_tool：消除面 = 道具全部引擎读点（_effective_hp /
  _effective_damage_modifier / _effective_retreat_cost / _effective_attack_cost
  道具分支 + grant_attack 授予招式枚举与执行双落点）；动态求值无追溯（HP 加成
  失效即按新有效 HP 判昏厥，走 check_knockouts）；能量卡 provide_energy 不受影响。
- D-029-3 lock_play：on_attack 原语 args{category: item}——受击方玩家侧回合标记
  (turn, 施加方)，下个自己回合物品打出枚举门控；撤退/离场不解锁；回合结束解除。
- D-029-4 damage selector opponent_bench choose=1：备战空 no-op 主战照算；弱抗
  不结算（§6 贯穿规则）；谢米 protection（D-WP7-5）与太晶备战免伤（D-027-1）
  既有守卫同落点生效。
- D-029-5 attach_energy own_deck + args.distribute：段1 选能量 up-to N → 段2 逐张
  挂起选目标（target_filters 如 owner_pokemon:玛俐，可集中可分散）→ 重洗；选 0
  仍重洗；与 multi_target/energy_up_to 互斥（DslError）；ability_feasible 双侧池门。
- D-029-6/7/8 小词：condition `stadium_in_play`（旋转洛托姆 突击登陆招式失败门
  ——WP1 古月鸟钩子「condition 不满足即失败」的成功前提正向词，卡面失败子句
  「如果场上没有竞技场的话」的正向形式，对齐古月鸟 opponent_prizes_in 正向
  挂载先例）；filter pokemon_<属性> 参数化泛化（pokemon_超 回归）；计数词
  opponent_ability_pokemon_count（对手场上 has_ability 宝可梦数）。
"""

import pytest
from helpers import energy, inst, main_state

from battlefrontier.dsl import ExecutionContext, parse_card_doc, run_effect
from battlefrontier.dsl.chooser import ability_feasible, matches, resolve_in_play_pool
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    InPlayPokemon,
    PlayerState,
)

# ── 夹具 ─────────────────────────────────────────────────────────────


def pokemon(
    name: str, *, hp: int = 500, attacks: tuple | None = None, damage: int = 20,
    cost: int = 1, stage: int = 0, energy_type: str | None = None,
    has_ability: bool = False, is_tera: bool = False, owner: str | None = None,
    evolves_from: str | None = None, retreat: int = 1, weakness: str | None = None,
) -> CardDef:
    if attacks is None:
        attacks = (AttackDef(name="打击", cost=("无",) * cost, damage=damage),)
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=stage, attacks=attacks, energy_type=energy_type,
        has_ability=has_ability, is_tera=is_tera, owner=owner,
        evolves_from=evolves_from, retreat_cost=retreat, weakness=weakness,
    )


def tool_card(name: str, *, attacks: tuple = ()) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具", attacks=attacks)


def stadium_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="竞技场")


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def mon(
    iid: int, card: CardDef | None = None, *, damage: int = 0,
    energies: int = 0, attached: tuple[CardInstance, ...] = (),
    tool: CardInstance | None = None,
) -> InPlayPokemon:
    card = card or pokemon(f"兽{iid}")
    return InPlayPokemon(
        stack=(inst(iid, card),),
        attached_energy=(
            tuple(inst(9000 + iid * 10 + j, energy()) for j in range(energies))
            + attached
        ),
        damage=damage,
        attached_tool=tool,
    )


def board_engine(
    *, p0_active=None, p0_bench: tuple = (), p1_active=None, p1_bench: tuple = (),
    p0_hand=None, p1_hand=None, p0_deck=None, p1_deck=None,
    stadium: CardInstance | None = None, stadium_owner: int = 0,
    turn: int = 2, current: int = 0, seed: int = 0, effects: dict | None = None,
) -> GameEngine:
    """main 阶段（默认 turn=2, current=0）：可调双方场上/手牌/牌库与公共竞技场。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": p0_active if p0_active is not None else mon(1),
        "bench": p0_bench,
    })
    if p0_hand is not None:
        p0 = p0.model_copy(update={"hand": p0_hand})
    if p0_deck is not None:
        p0 = p0.model_copy(update={"deck": p0_deck})
    p1 = state.players[1].model_copy(update={
        "active": p1_active if p1_active is not None else mon(2, pokemon("硬兽", hp=500)),
        "bench": p1_bench,
    })
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
    if p1_deck is not None:
        p1 = p1.model_copy(update={"deck": p1_deck})
    update: dict[str, object] = {
        "players": (p0, p1), "turn": turn, "current_player": current,
    }
    if stadium is not None:
        update["stadium"] = stadium
        update["stadium_owner"] = stadium_owner
    e = GameEngine(RandomSource(seed))
    e.state = state.model_copy(update=update)
    e.card_effects = effects or {}
    return e


def run_doc(e, doc, source, player: int = 0):
    """直接跑效果（绕过可行性门）：DslError/no-op 等原语层语义用。"""
    ctx = ExecutionContext(engine=e, player=player, source=source,
                           effect_id="test", trigger=doc.effects[0].trigger)
    return run_effect(ctx, doc.effects[0])


def prim_results(e: GameEngine, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


def ability_iids(e: GameEngine, player: int) -> list[int]:
    return [a.iid for a in e.legal_actions(player) if a.kind == "use_ability"]


def play_trainer_iids(e: GameEngine, player: int) -> list[int]:
    return [a.iid for a in e.legal_actions(player) if a.kind == "play_trainer"]


# ── suppression 共用文档 ─────────────────────────────────────────────

WATCHTOWER_DOC = parse_card_doc("""
card:
  name_group: 监视塔
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_ability, args: {types: [无]}}
""")

BLOCKER_DOC = parse_card_doc("""
card:
  name_group: 阻碍之塔
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_tool}
""")


def ability_doc(name: str):
    return parse_card_doc(f"""
card:
  name_group: {name}
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {{action: draw, count: 1}}
""")


AURA_DOC = parse_card_doc("""
card:
  name_group: 护苗兽
effects:
  - trigger: passive_static
    actions:
      - {action: protection, args: {scope: opponent_attack_damage_to_bench}}
""")

CHECK_TRIGGER_DOC = parse_card_doc("""
card:
  name_group: 检查兽
effects:
  - trigger: trigger_on_event
    event: pokemon_check
    actions:
      - {action: draw, count: 1}
""")


def watchtower() -> CardInstance:
    return inst(399, stadium_card("监视塔"))


# ── 1. suppress_ability（火箭队的监视塔，D-029-1）─────────────────────


def test_suppress_ability_blocks_ability_manual_both_sides():
    """监视塔在场：双方【无】宝可梦 ability_manual 不枚举（对手侧同口径）；非【无】照常。"""
    colorless = pokemon("特性兽", energy_type="无", has_ability=True)
    psychic = pokemon("超特性兽", energy_type="超", has_ability=True)
    effects = {
        "监视塔": WATCHTOWER_DOC,
        "特性兽": ability_doc("特性兽"),
        "超特性兽": ability_doc("超特性兽"),
    }
    # 无监视塔：双方特性正常枚举
    plain = board_engine(
        p0_active=mon(1, colorless), p1_active=mon(2, colorless), effects=effects)
    assert ability_iids(plain, 0) == [1]
    # 监视塔在场：p0【无】特性兽不枚举
    e = board_engine(
        p0_active=mon(1, colorless), p1_active=mon(2, colorless),
        stadium=watchtower(), effects=effects)
    assert ability_iids(e, 0) == []
    # 对手侧同口径（current=1 的 p1 回合）
    e1 = board_engine(
        p0_active=mon(1, colorless), p1_active=mon(2, colorless),
        stadium=watchtower(), current=1, effects=effects)
    assert ability_iids(e1, 1) == []
    # 非【无】（超属性）不受消除影响
    e2 = board_engine(
        p0_active=mon(1, psychic), p1_active=mon(2, psychic),
        stadium=watchtower(), effects=effects)
    assert ability_iids(e2, 0) == [1]


def test_suppress_ability_lifts_when_stadium_replaced():
    """竞技场被顶掉即恢复（两竞技场替换即时生效）：监视塔 → 普通场，特性重新枚举。"""
    colorless = pokemon("特性兽", energy_type="无", has_ability=True)
    effects = {"监视塔": WATCHTOWER_DOC, "特性兽": ability_doc("特性兽")}
    e = board_engine(
        p0_active=mon(1, colorless),
        p0_hand=(inst(60, stadium_card("普通场")),),
        stadium=watchtower(), effects=effects)
    assert ability_iids(e, 0) == []
    e.apply(0, Action(kind="play_stadium", iid=60))  # 顶掉监视塔
    assert e.state.stadium.card.name == "普通场"
    assert ability_iids(e, 0) == [1]
    # 旧监视塔进其放置方弃牌区（rules-manual §5）
    assert 399 in [c.iid for c in e.state.players[0].discard]


def test_suppress_ability_blocks_bench_protection_aura():
    """谢米类被动 aura（protection scope=opponent_attack_damage_to_bench）在
    【无】持有者身上失效：有塔狙击 30 照算，无塔归零。"""
    snipe_doc = parse_card_doc("""
card:
  name_group: 狙击兽
effects:
  - trigger: on_attack
    attack: 狙击
    actions:
      - {action: damage, selector: opponent_bench, choose: 1, args: {amount: 30}}
""")
    sniper = pokemon("狙击兽", attacks=(
        AttackDef(name="狙击", cost=("无",), damage=None),))
    aura_holder = pokemon("护苗兽", energy_type="无", has_ability=True)
    target = pokemon("目标兽")
    effects = {"狙击兽": snipe_doc, "护苗兽": AURA_DOC, "监视塔": WATCHTOWER_DOC}

    def build(with_tower: bool) -> GameEngine:
        return board_engine(
            p0_active=mon(1, sniper, energies=1),
            p1_active=mon(2, pokemon("硬兽", hp=500)),
            p1_bench=(mon(80, aura_holder), mon(81, target)),
            stadium=watchtower() if with_tower else None,
            effects=effects)

    no_tower = build(False)
    no_tower.apply(0, Action(kind="attack", attack_index=0))
    no_tower.apply(0, Action(kind="choose", choices=(81,)))
    assert no_tower.state.players[1].bench[1].damage == 0  # aura 保护归零
    assert prim_results(no_tower, "damage")[0]["protected"] is True

    with_tower = build(True)
    with_tower.apply(0, Action(kind="attack", attack_index=0))
    with_tower.apply(0, Action(kind="choose", choices=(81,)))
    assert with_tower.state.players[1].bench[1].damage == 30  # 【无】持有者 aura 失效
    assert prim_results(with_tower, "damage")[0]["protected"] is False


def test_suppress_ability_blocks_pokemon_check_trigger():
    """trigger_on_event（pokemon_check 类）在【无】持有者身上不触发；非【无】照常。"""
    colorless = pokemon("检查兽", energy_type="无", has_ability=True)
    psychic = pokemon("超检查兽", energy_type="超", has_ability=True)
    psychic_doc = parse_card_doc("""
card:
  name_group: 超检查兽
effects:
  - trigger: trigger_on_event
    event: pokemon_check
    actions:
      - {action: draw, count: 1}
""")

    def build(holder: CardDef, doc, with_tower: bool) -> GameEngine:
        return board_engine(
            p0_active=mon(1, holder),
            stadium=watchtower() if with_tower else None,
            effects={"监视塔": WATCHTOWER_DOC, holder.name: doc})

    plain = build(colorless, CHECK_TRIGGER_DOC, False)
    plain.apply(0, Action(kind="end_turn"))
    assert len(plain.state.players[0].hand) == 3  # 触发：抽 1

    suppressed = build(colorless, CHECK_TRIGGER_DOC, True)
    suppressed.apply(0, Action(kind="end_turn"))
    assert len(suppressed.state.players[0].hand) == 2  # 【无】持有者不触发
    assert not [ev for ev in suppressed.events if ev.kind == "trigger_on_event"]

    unaffected = build(psychic, psychic_doc, True)
    unaffected.apply(0, Action(kind="end_turn"))
    assert len(unaffected.state.players[0].hand) == 3  # 非【无】照常触发


def test_suppress_ability_bad_args_dsl_error():
    """suppress_ability 缺 args.types / types 非属性列表 → DslError（求值点不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 监视塔
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_ability}
""")
    colorless = pokemon("特性兽", energy_type="无", has_ability=True)
    e = board_engine(
        p0_active=mon(1, colorless), stadium=watchtower(),
        effects={"监视塔": bad, "特性兽": ability_doc("特性兽")})
    with pytest.raises(DslError, match="suppress_ability"):
        e.legal_actions(0)


# ── 2. suppress_tool（阻碍之塔，D-029-2）──────────────────────────────

HP_TOOL_DOC = parse_card_doc("""
card:
  name_group: 护符
effects:
  - trigger: passive_static
    actions:
      - {action: modify_hp, args: {amount: 50}}
""")

DMG_TOOL_DOC = parse_card_doc("""
card:
  name_group: 头带
effects:
  - trigger: passive_static
    actions:
      - {action: modify_damage, args: {amount: 30}}
""")

RETREAT_TOOL_DOC = parse_card_doc("""
card:
  name_group: 滑板
effects:
  - trigger: passive_static
    actions:
      - {action: modify_retreat_cost, args: {value: all}}
""")

COST_TOOL_DOC = parse_card_doc("""
card:
  name_group: 腕带
effects:
  - trigger: passive_static
    actions:
      - {action: modify_attack_cost, args: {value: 1}}
""")

GRANT_TOOL_DOC = parse_card_doc("""
card:
  name_group: 学习器
effects:
  - trigger: passive_static
    actions:
      - {action: grant_attack, args: {attack: 授予打击}}
""")

DARK_ENERGY_DOC = parse_card_doc("""
card:
  name_group: 夜光能
effects:
  - trigger: passive_static
    actions:
      - {action: provide_energy, args: {types: [恶]}}
""")


def blocker() -> CardInstance:
    return inst(399, stadium_card("阻碍之塔"))


def test_suppress_tool_modify_hp_ko_via_check_knockouts():
    """HP 加成失效即按新有效 HP 判昏厥（走 check_knockouts）：打出阻碍之塔后
    备战受伤宝可梦（100+50 有效 HP，已受 120）昏厥进弃牌区、对手拿奖赏。"""
    holder = mon(80, pokemon("受伤兽", hp=100), damage=120,
                 tool=inst(90, tool_card("护符")))
    e = board_engine(
        p0_bench=(holder,),
        p0_hand=(inst(60, stadium_card("阻碍之塔")),),
        effects={"阻碍之塔": BLOCKER_DOC, "护符": HP_TOOL_DOC})
    assert e.state.players[0].bench  # 打出前存活（有效 HP 150 > 120）
    e.apply(0, Action(kind="play_stadium", iid=60))
    p0 = e.state.players[0]
    assert p0.bench == ()  # HP 加成失效 → 120 ≥ 100 昏厥
    assert {80, 90} <= {c.iid for c in p0.discard}  # 整叠 + 道具进弃牌区
    assert len(e.state.players[1].hand) == 1  # 对手按规则盒拿 1 张奖赏
    assert e.state.phase == "main" and e.state.current_player == 0  # 备战昏厥不换上


def test_suppress_tool_modify_damage():
    """道具 modify_damage 失效：有塔 20 无塔 50（20+30）。"""
    attacker = lambda: mon(1, pokemon("打手", hp=500), energies=1,
                           tool=inst(90, tool_card("头带")))
    effects = {"阻碍之塔": BLOCKER_DOC, "头带": DMG_TOOL_DOC}
    plain = board_engine(p0_active=attacker(), effects=effects)
    plain.apply(0, Action(kind="attack", attack_index=0))
    assert plain.state.players[1].active.damage == 50

    suppressed = board_engine(p0_active=attacker(), stadium=blocker(), effects=effects)
    suppressed.apply(0, Action(kind="attack", attack_index=0))
    assert suppressed.state.players[1].active.damage == 20


def test_suppress_tool_modify_retreat_cost():
    """道具 modify_retreat_cost 失效：有塔撤退费回卡面 2（1 能不可撤），无塔全免可撤。"""
    holder = lambda: mon(1, pokemon("逃跑兽", hp=500, retreat=2), energies=1,
                         tool=inst(90, tool_card("滑板")))
    effects = {"阻碍之塔": BLOCKER_DOC, "滑板": RETREAT_TOOL_DOC}
    plain = board_engine(
        p0_active=holder(), p0_bench=(mon(70),), effects=effects)
    assert plain._effective_retreat_cost(plain.state.players[0].active, 0) == 0
    assert [a for a in plain.legal_actions(0) if a.kind == "retreat"]

    suppressed = board_engine(
        p0_active=holder(), p0_bench=(mon(70),), stadium=blocker(), effects=effects)
    assert suppressed._effective_retreat_cost(suppressed.state.players[0].active, 0) == 2
    assert not [a for a in suppressed.legal_actions(0) if a.kind == "retreat"]


def test_suppress_tool_modify_attack_cost():
    """道具 modify_attack_cost 失效：有塔费用回 2（1 能不能攻击），无塔减 1 可攻击。"""
    boxer = pokemon("拳手", hp=500, attacks=(
        AttackDef(name="重拳", cost=("无", "无"), damage=50),))
    holder = lambda: mon(1, boxer, energies=1, tool=inst(90, tool_card("腕带")))
    effects = {"阻碍之塔": BLOCKER_DOC, "腕带": COST_TOOL_DOC}
    plain = board_engine(p0_active=holder(), effects=effects)
    assert [a for a in plain.legal_actions(0) if a.kind == "attack"]

    suppressed = board_engine(p0_active=holder(), stadium=blocker(), effects=effects)
    assert not [a for a in suppressed.legal_actions(0) if a.kind == "attack"]


def test_suppress_tool_grant_attack_enum_and_execution():
    """授予招式双落点：有塔不枚举、直接执行也被规则骨架拦截；无塔可宣言可结算。"""
    learner = tool_card("学习器", attacks=(
        AttackDef(name="授予打击", cost=("无",), damage=30),))
    holder = lambda: mon(1, pokemon("持器兽", hp=500), energies=1,
                         tool=inst(90, learner))
    effects = {"阻碍之塔": BLOCKER_DOC, "学习器": GRANT_TOOL_DOC}
    plain = board_engine(p0_active=holder(), effects=effects)
    assert [a.attack_index for a in plain.legal_actions(0) if a.kind == "attack"] == [0, 1]
    plain.apply(0, Action(kind="attack", attack_index=1))  # 授予招式结算
    assert plain.state.players[1].active.damage == 30

    suppressed = board_engine(p0_active=holder(), stadium=blocker(), effects=effects)
    assert [a.attack_index for a in suppressed.legal_actions(0)
            if a.kind == "attack"] == [0]  # 授予招式不枚举
    from battlefrontier.engine.core import IllegalActionError
    with pytest.raises(IllegalActionError):
        suppressed.apply(0, Action(kind="attack", attack_index=1))  # 执行落点拦截


def test_suppress_tool_lifts_when_stadium_replaced():
    """阻碍之塔被顶掉即恢复（道具效果与授予招式即时回来）；监视塔换上则特性消除。"""
    learner = tool_card("学习器", attacks=(
        AttackDef(name="授予打击", cost=("无",), damage=30),))
    colorless = pokemon("特性兽", energy_type="无", has_ability=True)
    holder = mon(1, colorless, energies=1, tool=inst(90, learner))
    effects = {
        "阻碍之塔": BLOCKER_DOC, "监视塔": WATCHTOWER_DOC,
        "学习器": GRANT_TOOL_DOC, "特性兽": ability_doc("特性兽"),
    }
    e = board_engine(
        p0_active=holder,
        p0_hand=(inst(60, stadium_card("监视塔")),),
        stadium=blocker(), effects=effects)
    assert [a.attack_index for a in e.legal_actions(0) if a.kind == "attack"] == [0]
    assert ability_iids(e, 0) == [1]  # 阻碍之塔不消特性
    e.apply(0, Action(kind="play_stadium", iid=60))  # 阻碍之塔 → 监视塔
    assert [a.attack_index for a in e.legal_actions(0)
            if a.kind == "attack"] == [0, 1]  # 道具恢复
    assert ability_iids(e, 0) == []  # 【无】特性被新塔消除


def test_suppress_tool_energy_passive_unaffected():
    """能量卡被动（provide_energy）不受影响：阻碍之塔在场，夜光能仍供【恶】抵费。"""
    dark_mon = pokemon("恶打手", hp=500, attacks=(
        AttackDef(name="恶击", cost=("恶",), damage=40),))
    luminous = CardDef(card_id="stub-夜光能", name="夜光能", supertype="energy",
                       is_basic_energy=False)
    holder = mon(1, dark_mon, attached=(inst(91, luminous),))
    e = board_engine(
        p0_active=holder, stadium=blocker(),
        effects={"阻碍之塔": BLOCKER_DOC, "夜光能": DARK_ENERGY_DOC})
    assert [a for a in e.legal_actions(0) if a.kind == "attack"]  # 能量提供值照常
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 40


LEARNER_DISCARD_DOC = parse_card_doc("""
card:
  name_group: 学习器
effects:
  - trigger: passive_static
    actions:
      - {action: grant_attack, args: {attack: 授予打击, discard_at_turn_end: true}}
""")


def test_suppress_tool_discard_at_turn_end():
    """D-033-2（task 033 WP2 归正）：学习器回合末自弃文本 = 宝可梦道具的效果——
    阻碍之塔在场时被消除、回合末不弃（TPCi Rules Team 2024-07-25：TM 自弃文本
    is an effect）；塔被顶掉即恢复自弃（动态求值）。"""
    learner = tool_card("学习器", attacks=(
        AttackDef(name="授予打击", cost=("无",), damage=30),))
    holder = lambda: mon(1, pokemon("持器兽", hp=500), energies=1,
                         tool=inst(90, learner))
    effects = {
        "阻碍之塔": BLOCKER_DOC, "监视塔": WATCHTOWER_DOC,
        "学习器": LEARNER_DISCARD_DOC,
    }
    # 塔在场：回合末不弃
    suppressed = board_engine(p0_active=holder(), stadium=blocker(), effects=effects)
    suppressed.apply(0, Action(kind="end_turn"))
    assert suppressed.state.players[0].active.attached_tool is not None
    # 塔被顶掉：自弃恢复
    lifted = board_engine(
        p0_active=holder(),
        p0_hand=(inst(60, stadium_card("监视塔")),),
        stadium=blocker(), effects=effects)
    lifted.apply(0, Action(kind="play_stadium", iid=60))
    lifted.apply(0, Action(kind="end_turn"))
    p0 = lifted.state.players[0]
    assert p0.active.attached_tool is None
    assert 90 in [c.iid for c in p0.discard]


# ── 3. lock_play 物品锁（含羞苞 痒痒花粉，D-029-3）────────────────────

POLLEN_DOC = parse_card_doc("""
card:
  name_group: 含羞苞
effects:
  - trigger: on_attack
    attack: 痒痒花粉
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 10}}
      - {action: lock_play, args: {category: item}}
""")

ITEM_DOC = parse_card_doc("""
card:
  name_group: 测试物品
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")

SUPPORTER_DOC = parse_card_doc("""
card:
  name_group: 测试支援者
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 2}
""")


def budew() -> CardDef:
    return pokemon("含羞苞", attacks=(
        AttackDef(name="痒痒花粉", cost=("无",), damage=None),))


def pollen_engine(**kw) -> GameEngine:
    """p0 含羞苞（1 能）攻击位；p1 手牌 = 物品/支援者/道具/能量，备战 1 只。"""
    p1_hand = kw.pop("p1_hand", (
        inst(60, item_card("测试物品")),
        inst(61, supporter_card("测试支援者")),
        inst(62, tool_card("学习器")),
        inst(63, energy()),
    ))
    p1_bench = kw.pop("p1_bench", (mon(80, pokemon("备战兽")),))
    e = board_engine(
        p0_active=mon(1, budew(), energies=1),
        p1_active=mon(2, pokemon("硬兽", hp=500), energies=1),  # 1 可供撤退
        p1_hand=p1_hand, p1_bench=p1_bench,
        effects={
            "含羞苞": POLLEN_DOC, "测试物品": ITEM_DOC, "测试支援者": SUPPORTER_DOC,
        }, **kw)
    return e


def test_lock_play_blocks_items_next_turn_only():
    """攻击后对手下个自己回合：物品不枚举；支援者/道具附着/能量附着照常；伤害照算。"""
    e = pollen_engine()
    e.apply(0, Action(kind="attack", attack_index=0))  # turn 2，p0 攻击
    assert e.state.players[1].active.damage == 10  # 伤害照算
    assert e.state.players[1].item_lock_mark == (2, 0)  # (施加时 turn, 施加方)
    assert e.state.phase == "main" and e.state.current_player == 1
    trainer_iids = play_trainer_iids(e, 1)
    assert 60 not in trainer_iids  # 物品被锁
    assert 61 in trainer_iids  # 支援者照常
    assert [a for a in e.legal_actions(1) if a.kind == "attach_tool"]  # 道具附着照常
    assert [a for a in e.legal_actions(1) if a.kind == "attach_energy"]  # 能量附着照常


def test_lock_play_expires_after_locked_turn():
    """隔一回合恢复：被锁回合结束解除，再下个自己回合物品重新可打出。"""
    e = pollen_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert 60 not in play_trainer_iids(e, 1)
    e.apply(1, Action(kind="end_turn"))  # p1 被锁回合结束 → 解除
    assert e.state.players[1].item_lock_mark is None
    e.apply(0, Action(kind="end_turn"))  # → p1 turn 3
    assert 60 in play_trainer_iids(e, 1)  # 解禁


def test_lock_play_refresh_on_consecutive_locks():
    """连续两回合被锁刷新 turn 戳：turn 3 再中痒痒花粉 → 标记更新为 (3, 0)，仍锁。"""
    e = pollen_engine()
    e.apply(0, Action(kind="attack", attack_index=0))  # turn 2 锁
    e.apply(1, Action(kind="end_turn"))
    e.apply(0, Action(kind="attack", attack_index=0))  # turn 3 再锁
    assert e.state.players[1].item_lock_mark == (3, 0)
    assert 60 not in play_trainer_iids(e, 1)


def test_lock_play_retreat_does_not_unlock():
    """锁作用于玩家侧（卡面「对手无法」）：宝可梦撤退不解锁。"""
    e = pollen_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    retreats = [a for a in e.legal_actions(1) if a.kind == "retreat"]
    assert retreats  # 硬兽 1 能撤退费 1 可撤
    e.apply(1, retreats[0])
    assert e.state.players[1].item_lock_mark == (2, 0)  # 撤退后锁仍在
    assert 60 not in play_trainer_iids(e, 1)


def test_lock_play_bad_forms_dsl_error():
    """未知 category / 带 choose / 带 selector → DslError（不猜）。"""
    bad_category = parse_card_doc("""
card:
  name_group: 含羞苞
effects:
  - trigger: on_attack
    attack: 痒痒花粉
    actions:
      - {action: lock_play, args: {category: supporter}}
""")
    e = board_engine(
        p0_active=mon(1, budew(), energies=1),
        effects={"含羞苞": bad_category})
    with pytest.raises(DslError, match="lock_play"):
        e.apply(0, Action(kind="attack", attack_index=0))

    bad_choose = parse_card_doc("""
card:
  name_group: 含羞苞
effects:
  - trigger: on_attack
    attack: 痒痒花粉
    actions:
      - {action: lock_play, choose: 1, args: {category: item}}
""")
    e2 = board_engine(
        p0_active=mon(1, budew(), energies=1),
        effects={"含羞苞": bad_choose})
    with pytest.raises(DslError, match="lock_play"):
        e2.apply(0, Action(kind="attack", attack_index=0))

    bad_selector = parse_card_doc("""
card:
  name_group: 含羞苞
effects:
  - trigger: on_attack
    attack: 痒痒花粉
    actions:
      - {action: lock_play, selector: opponent_active, args: {category: item}}
""")
    e3 = board_engine(
        p0_active=mon(1, budew(), energies=1),
        effects={"含羞苞": bad_selector})
    with pytest.raises(DslError, match="lock_play"):
        e3.apply(0, Action(kind="attack", attack_index=0))


# ── 4. damage 备战狙击（苍响 刹那斩，D-029-4）─────────────────────────

SNIPE_DOC = parse_card_doc("""
card:
  name_group: 苍响
effects:
  - trigger: on_attack
    attack: 刹那斩
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 30}}
      - {action: damage, selector: opponent_bench, choose: 1, args: {amount: 30}}
""")


def zacian() -> CardDef:
    return pokemon("苍响", energy_type="恶", attacks=(
        AttackDef(name="刹那斩", cost=("无",), damage=None),))


def snipe_engine(**kw) -> GameEngine:
    return board_engine(
        p0_active=mon(1, zacian(), energies=1),
        effects={"苍响": SNIPE_DOC, "护苗兽": AURA_DOC}, **kw)


def test_snipe_bench_main_and_snipe_both_resolve():
    """主战 30 + 选 1 只备战 30 各结算；备战落点弱抗不结算（§6 贯穿规则）。"""
    weak_target = pokemon("弱恶兽", hp=500, weakness="恶")  # 弱点=攻方属性
    e = snipe_engine(p1_bench=(mon(80, weak_target),))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 30  # 主战先结算
    assert e.state.phase == "choice"  # 狙击挂起选目标
    pc = e.state.pending_choice
    assert pc.pool == "opponent_bench" and pc.pool_iids == (80,)
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 30  # 弱点 ×2 不适用（备战贯穿规则）
    assert prim_results(e, "damage")[1]["to_bench"] is True
    assert e.state.phase == "main" and e.state.current_player == 1


def test_snipe_bench_empty_noop_main_damage_applies():
    """备战空 → 狙击节点 no-op 不挂起，主战 30 照算，回合照常结束。"""
    e = snipe_engine(p1_bench=())
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 30
    assert e.state.phase == "main" and e.state.current_player == 1  # 无挂起
    results = prim_results(e, "damage")
    assert results[1]["final"] == 0 and results[1]["reason"] == "no_targets"


def test_snipe_bench_shaymin_protection_zeroes():
    """谢米 protection（D-WP7-5）守卫同落点：受保护备战目标狙击归零，主战照算。"""
    aura_holder = pokemon("护苗兽", energy_type="草", has_ability=True)
    e = snipe_engine(p1_bench=(mon(80, aura_holder), mon(81, pokemon("目标兽"))))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(81,)))
    assert e.state.players[1].bench[1].damage == 0
    assert prim_results(e, "damage")[1]["protected"] is True
    assert e.state.players[1].active.damage == 30


def test_snipe_bench_tera_zeroes():
    """备战太晶免伤（D-027-1）守卫同落点：太晶备战目标狙击归零，主战照算。"""
    tera = pokemon("太晶兽", hp=500, is_tera=True)
    e = snipe_engine(p1_bench=(mon(80, tera),))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 0
    assert e.state.players[1].active.damage == 30


def test_snipe_bench_choose_validation():
    """opponent_bench 狙击 choose != 1 → DslError（不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 苍响
effects:
  - trigger: on_attack
    attack: 刹那斩
    actions:
      - {action: damage, selector: opponent_bench, choose: 2, args: {amount: 30}}
""")
    e = board_engine(
        p0_active=mon(1, zacian(), energies=1),
        p1_bench=(mon(80), mon(81)),
        effects={"苍响": bad})
    with pytest.raises(DslError, match="choose=1"):
        e.apply(0, Action(kind="attack", attack_index=0))


# ── 5. attach_energy own_deck distribute（长毛巨魔 庞克泵感，D-029-5）─

PUNK_DOC = parse_card_doc("""
card:
  name_group: 长毛巨魔
effects:
  - trigger: trigger_on_event
    event: own_evolve_from_hand
    actions:
      - {action: attach_energy, selector: own_deck, filters: [basic_energy, energy_恶], choose: 5, destination: attach, args: {distribute: true, target_filters: ["owner_pokemon:玛俐"]}}
""")


def grimmsnarl() -> CardDef:
    return pokemon("长毛巨魔", stage=1, evolves_from="底兽", owner="玛俐",
                   hp=500, energy_type="恶")


def dark_deck(n_dark: int = 5, n_filler: int = 3) -> tuple:
    """牌库：基本恶能量 iid 300.. +  filler（草能量/宝可梦）。"""
    darks = tuple(inst(300 + i, energy("基本恶能量", "恶")) for i in range(n_dark))
    fillers = tuple(
        inst(400 + i, energy("基本草能量", "草")) for i in range(n_filler - 1)
    ) + (inst(409, pokemon("库宝可梦")),)
    return darks + fillers


def punk_engine(*, deck=None, p0_bench=None) -> GameEngine:
    """main 阶段（turn=2）：p0 战斗场底兽（可进化），手牌长毛巨魔（iid 60）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": mon(1, pokemon("底兽", hp=500)),
        "bench": p0_bench if p0_bench is not None else (
            mon(70, pokemon("玛俐备战", owner="玛俐")),
            mon(71, pokemon("外人备战")),
        ),
        "hand": (inst(60, grimmsnarl()),),
        "deck": deck if deck is not None else dark_deck(),
    })
    e = GameEngine(RandomSource(0))
    e.state = state.model_copy(update={"players": (p0, state.players[1])})
    e.card_effects = {"长毛巨魔": PUNK_DOC}
    return e


def evolve_and_pick(e: GameEngine, iids: tuple[int, ...]) -> None:
    """从手牌进化触发庞克泵感 → 段1 选能量；返回后处于段2首轮挂起（或已完成）。"""
    e.apply(0, Action(kind="evolve", iid=60, target_iid=1))
    assert e.state.phase == "choice"  # 段1：选能量
    e.apply(0, Action(kind="choose", choices=iids))


def test_attach_distribute_concentrate_on_one():
    """集中 1 只：选 3 张恶能量全给长毛巨魔；重洗后牌库 = 原库 − 3 张。"""
    e = punk_engine()
    evolve_and_pick(e, (300, 301, 302))
    for _ in range(3):
        assert e.state.phase == "choice"
        e.apply(0, Action(kind="choose", choices=(60,)))  # 逐张都给长毛巨魔
    assert e.state.phase == "main" and e.state.current_player == 0
    p0 = e.state.players[0]
    assert len(p0.active.attached_energy) == 3
    assert all(c.card.energy_type == "恶" for c in p0.active.attached_energy)
    assert len(p0.bench[0].attached_energy) == 0
    assert sorted(c.iid for c in p0.deck) == [303, 304, 400, 401, 409]  # 重洗后集合
    result = prim_results(e, "attach_energy")[0]
    assert result["attached"] == 3 and result["shuffled"] is True


def test_attach_distribute_spread_over_multiple():
    """分散多只：2 张分别给长毛巨魔与玛俐备战；非玛俐备战始终不可选。"""
    e = punk_engine()
    evolve_and_pick(e, (300, 301))
    pc = e.state.pending_choice  # 段2 首轮：目标池仅玛俐的宝可梦
    assert pc is not None and set(pc.pool_iids) == {60, 70}  # 外人备战(71)不入池
    e.apply(0, Action(kind="choose", choices=(70,)))  # 第 1 张给玛俐备战
    e.apply(0, Action(kind="choose", choices=(60,)))  # 第 2 张给长毛巨魔
    p0 = e.state.players[0]
    assert len(p0.active.attached_energy) == 1
    assert len(p0.bench[0].attached_energy) == 1
    assert len(p0.bench[1].attached_energy) == 0


def test_attach_distribute_pick_zero_still_shuffles():
    """选 0 → no-op 仍重洗（D-WP5-1 口径）：不挂段2，牌库集合不变、shuffled 落事件。"""
    e = punk_engine()
    e.apply(0, Action(kind="evolve", iid=60, target_iid=1))
    assert e.state.phase == "choice"
    e.apply(0, Action(kind="choose", choices=()))  # 选 0 张
    assert e.state.phase == "main" and e.state.current_player == 0
    p0 = e.state.players[0]
    assert len(p0.active.attached_energy) == 0
    assert sorted(c.iid for c in p0.deck) == [300, 301, 302, 303, 304, 400, 401, 409]
    result = prim_results(e, "attach_energy")[0]
    assert result["attached"] == 0 and result["shuffled"] is True


def test_attach_distribute_deck_shortage_shrinks_pool():
    """牌库匹配能量不足 N 时选择池收缩（既有 up-to 语义）：2 张 ⇒ 池=2、可全选。"""
    e = punk_engine(deck=dark_deck(n_dark=2))
    evolve_and_pick(e, (300, 301))  # 池仅 2 张，全选
    e.apply(0, Action(kind="choose", choices=(60,)))
    e.apply(0, Action(kind="choose", choices=(60,)))
    assert len(e.state.players[0].active.attached_energy) == 2


def test_attach_distribute_ability_feasible_gate():
    """ability_feasible 双侧池门：能量池空 / 目标池空 → 不可行；双侧非空 → 可行。"""
    effect = PUNK_DOC.effects[0]
    ok = punk_engine()
    assert ability_feasible(effect, ok, 0) is True
    no_energy = punk_engine(deck=dark_deck(n_dark=0))
    assert ability_feasible(effect, no_energy, 0) is False  # 牌库无匹配能量
    no_target = punk_engine(p0_bench=(mon(71, pokemon("外人备战")),))
    # 场上无玛俐的宝可梦（底兽/外人备战均无 owner）→ 目标池空
    assert ability_feasible(effect, no_target, 0) is False


def test_attach_distribute_mutual_exclusion_dsl_error():
    """distribute 与 multi_target/energy_up_to 互斥 → DslError（三形式互斥，不猜）。"""
    bad_multi = parse_card_doc("""
card:
  name_group: 长毛巨魔
effects:
  - trigger: trigger_on_event
    event: own_evolve_from_hand
    actions:
      - {action: attach_energy, selector: own_deck, filters: [basic_energy], choose: 3, destination: attach, args: {distribute: true, multi_target: true}}
""")
    e = punk_engine()
    with pytest.raises(DslError, match="互斥"):
        run_doc(e, bad_multi, inst(60, grimmsnarl()))

    bad_up_to = parse_card_doc("""
card:
  name_group: 长毛巨魔
effects:
  - trigger: trigger_on_event
    event: own_evolve_from_hand
    actions:
      - {action: attach_energy, selector: own_deck, filters: [basic_energy], choose: 3, destination: attach, args: {distribute: true, energy_up_to: true}}
""")
    with pytest.raises(DslError, match="互斥"):
        run_doc(e, bad_up_to, inst(60, grimmsnarl()))


# ── 6. 小词（D-029-6/7/8）────────────────────────────────────────────

LANDING_DOC = parse_card_doc("""
card:
  name_group: 洛托姆
effects:
  - trigger: on_attack
    attack: 突击登陆
    condition: stadium_in_play
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 70}}
""")


def rotom() -> CardDef:
    return pokemon("洛托姆", attacks=(
        AttackDef(name="突击登陆", cost=("无",), damage=70),))


def test_stadium_in_play_attack_fails_without_stadium():
    """清单 8（D-029-6）：场上无竞技场 → 招式失败（WP1 古月鸟口径）：不结算、
    攻击机会消耗、回合结束。卡 DSL 挂成功前提词 stadium_in_play（钩子「不满足
    即失败」的正向形式，对齐古月鸟 opponent_prizes_in 正向挂载先例）。"""
    e = board_engine(
        p0_active=mon(1, rotom(), energies=1), effects={"洛托姆": LANDING_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    attack_ev = next(ev for ev in e.events if ev.kind == "attack")
    assert attack_ev.detail["failed"] is True
    assert attack_ev.detail["condition"] == "stadium_in_play"
    assert e.state.players[1].active.damage == 0  # 不结算
    assert e.state.phase == "main" and e.state.current_player == 1  # 攻击消耗、回合结束


def test_stadium_in_play_attack_succeeds_with_stadium():
    """清单 8 双向：场上有竞技场 → 条件满足，招式正常 70。"""
    e = board_engine(
        p0_active=mon(1, rotom(), energies=1),
        stadium=inst(399, stadium_card("普通场")),
        effects={"洛托姆": LANDING_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    attack_ev = next(ev for ev in e.events if ev.kind == "attack")
    assert "failed" not in attack_ev.detail
    assert e.state.players[1].active.damage == 70


def test_stadium_in_play_word_literal_semantics():
    """stadium_in_play 字面值双向：有竞技场为真、无竞技场为假（挂载词真值钉住）。"""
    from battlefrontier.dsl.chooser import condition_met

    plain = board_engine()
    assert condition_met("stadium_in_play", plain, 0) is False
    with_stadium = board_engine(stadium=inst(399, stadium_card("普通场")))
    assert condition_met("stadium_in_play", with_stadium, 0) is True


SEARCH_FAN_DOC = parse_card_doc("""
card:
  name_group: 风扇检索
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [pokemon_无, "hp_max:100"], choose: 1, destination: hand}
      - {action: shuffle_deck}
""")


def test_pokemon_type_filter_deck_search():
    """pokemon_无 检索过滤（卡维度）：超属性 / HP>100 不入选池（HP 用既有 hp_max）。"""
    deck = (
        inst(300, pokemon("无色小兽", hp=80, energy_type="无")),   # 命中
        inst(301, pokemon("无色大兽", hp=120, energy_type="无")),  # HP>100 排除
        inst(302, pokemon("超能小兽", hp=50, energy_type="超")),   # 超属性排除
    ) + tuple(inst(310 + i, energy()) for i in range(3))
    e = board_engine(
        p0_hand=(inst(60, item_card("风扇检索")),),
        p0_deck=deck, effects={"风扇检索": SEARCH_FAN_DOC})
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    assert e.state.pending_choice.pool_iids == (300,)  # 仅【无】且 HP≤100


def test_pokemon_type_filter_in_play_generalized():
    """pokemon_<属性> 场上维度泛化 + pokemon_超 回归：逐属性过滤场上宝可梦。"""
    p = PlayerState(
        active=mon(1, pokemon("超兽", energy_type="超")),
        bench=(
            mon(80, pokemon("无兽", energy_type="无")),
            mon(81, pokemon("恶兽", energy_type="恶")),
        ),
    )
    assert [m.current.iid for m in resolve_in_play_pool(p, ("pokemon_超",))] == [1]
    assert [m.current.iid for m in resolve_in_play_pool(p, ("pokemon_无",))] == [80]
    assert [m.current.iid for m in resolve_in_play_pool(p, ("pokemon_恶",))] == [81]
    # 卡维度同词（检索用）：pokemon_超 回归 + pokemon_无 新词
    assert matches(inst(1, pokemon("超卡", energy_type="超")), ("pokemon_超",))
    assert matches(inst(2, pokemon("无卡", energy_type="无")), ("pokemon_无",))
    assert not matches(inst(3, pokemon("无卡2", energy_type="无")), ("pokemon_超",))
    assert not matches(inst(4, energy("基本超能量", "超")), ("pokemon_超",))  # 能量卡不算


SCISSOR_DOC = parse_card_doc("""
card:
  name_group: 巨钳螳螂
effects:
  - trigger: on_attack
    attack: 惩罚巨钳
    actions:
      - {action: damage, selector: opponent_active, count: opponent_ability_pokemon_count, args: {base: 10, op: "+", per: 50}}
""")


def scizor() -> CardDef:
    return pokemon("巨钳螳螂", attacks=(
        AttackDef(name="惩罚巨钳", cost=("无",), damage=None),))


def scizor_engine(p1_active: InPlayPokemon, p1_bench: tuple) -> GameEngine:
    return board_engine(
        p0_active=mon(1, scizor(), energies=1),
        p1_active=p1_active, p1_bench=p1_bench,
        effects={"巨钳螳螂": SCISSOR_DOC})


def test_opponent_ability_pokemon_count():
    """惩罚巨钳：对手场上特性宝可梦 0/2/3 只 → 10+0 / 10+100 / 10+150。"""
    plain = pokemon("白板兽", hp=500)
    gifted = pokemon("特性兽", hp=500, has_ability=True)

    e0 = scizor_engine(mon(2, plain), ())
    e0.apply(0, Action(kind="attack", attack_index=0))
    assert e0.state.players[1].active.damage == 10  # 0 只

    e2 = scizor_engine(mon(2, gifted), (mon(80, gifted), mon(81, plain)))
    e2.apply(0, Action(kind="attack", attack_index=0))
    assert e2.state.players[1].active.damage == 110  # 2 只 ×50

    e3 = scizor_engine(mon(2, gifted), (mon(80, gifted), mon(81, gifted)))
    e3.apply(0, Action(kind="attack", attack_index=0))
    assert e3.state.players[1].active.damage == 160  # 3 只 ×50
