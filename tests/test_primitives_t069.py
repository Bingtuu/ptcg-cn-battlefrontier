"""task 069 引擎扩展批·机制测试：WP1 虹色因子（modify_evolution 声明驱动
进化加宽）/ WP2 顽强之心（prevent_ko 满 HP 免昏厥截顶）/ WP3 璀璨结晶
（modify_attack_cost args.types=all + holder_is_tera）/ WP5 ACE 锁
（lock_play 可挂 passive_static + category=ace_spec + holder_has_tool
+ _ace_spec_play_locked 守卫 + 手牌使出五门类过滤）/ WP4 力之沙漏
（own_turn_end 事件 + 道具来源寻源 + attach_energy own_discard
target_pool=self）/ WP6 原语小扩（discard own_attached_energy choose=N /
计数词 attached_energy_on_opponent_all / heal own_bench 全体）。

设计决议（tasks/task 069.md，2026-10-21 定稿）：
- D-069-2 ACE 锁覆盖面 = 广义五门类（物品/支援者/竞技场打出 + 道具附着 +
  能量附着）；求值点实时扫对手场——来源离场/特性消除立即解锁。
- WP1：进化合法性从纯名字链扩为 DSL 声明可加宽（modify_evolution args
  {match_evolves_from, rule_box}，挂在声明持有者的卡文档 passive_static）；
  登场当回合/已进化当回合门（entered_play_this_turn / evolved_this_turn）
  自然生效；_do_evolve 零改复用；_ability_suppressed 守卫（特性来源）。
- WP2：满 HP 受招式伤害且伤害 ≥ 有效 HP 时截顶至 有效HP − remaining_hp
  （「满 HP」= target.damage == 0；截顶作用于弱点/抗性结算后的 final）；
  三处伤害施加点统一接入（_do_attack 白板 / DSL damage 原语 on_attack 门控 /
  copy_attack 白板复制）；指示物与效果伤害不经守卫；自伤（_damage_self）
  不截顶（非「受到招式的伤害」，对齐自伤不经保护守卫先例）；
  _ability_suppressed 守卫（特性来源）。
- WP3：types:all 减免语义从「只减【无】」（D-WP5-4）扩为「减任意 1 个符号」；
  确定性取法钉死：优先【无】符号，无则按 cost 序列首个有色符号
  （_units_cover_cost 只验满足性，取法只影响 agent 可视费用）；存量 DSL
  未写 types 键行为零变化。
"""

import pytest
from helpers import inst, main_state

from battlefrontier.dsl import ExecutionContext, parse_card_doc, run_effect
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    InPlayPokemon,
)

# ── 夹具（对齐 tests/test_primitives_t29.py 风格）──────────────────────


def pokemon(
    name: str, *, hp: int = 500, attacks: tuple | None = None, damage: int = 20,
    cost: int = 1, stage: int = 0, energy_type: str | None = None,
    has_ability: bool = False, is_tera: bool = False, rule_box: str | None = None,
    evolves_from: str | None = None, retreat: int = 1,
) -> CardDef:
    if attacks is None:
        attacks = (AttackDef(name="打击", cost=("无",) * cost, damage=damage),)
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=stage, attacks=attacks, energy_type=energy_type,
        has_ability=has_ability, is_tera=is_tera, rule_box=rule_box,
        evolves_from=evolves_from, retreat_cost=retreat,
    )


def tool_card(name: str, *, is_ace_spec: bool = False) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具", is_ace_spec=is_ace_spec)


def stadium_card(name: str, *, is_ace_spec: bool = False) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="竞技场", is_ace_spec=is_ace_spec)


def item_card(name: str, *, is_ace_spec: bool = False) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品", is_ace_spec=is_ace_spec)


def supporter_card(name: str, *, is_ace_spec: bool = False) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者", is_ace_spec=is_ace_spec)


def energy_card(name: str, energy_type: str | None = None, *, is_ace_spec: bool = False) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy",
                   energy_type=energy_type, is_basic_energy=True,
                   is_ace_spec=is_ace_spec)


def mon(
    iid: int, card: CardDef | None = None, *, damage: int = 0,
    attached: tuple[CardInstance, ...] = (),
    tool: CardInstance | None = None,
) -> InPlayPokemon:
    card = card or pokemon(f"兽{iid}")
    return InPlayPokemon(
        stack=(inst(iid, card),), attached_energy=attached,
        damage=damage, attached_tool=tool,
    )


def board_engine(
    *, p0_active=None, p0_bench: tuple = (), p1_active=None, p1_bench: tuple = (),
    p0_hand=None, p1_hand=None, stadium: CardInstance | None = None,
    stadium_owner: int = 0, turn: int = 2, current: int = 0, seed: int = 0,
    effects: dict | None = None,
) -> GameEngine:
    """main 阶段（默认 turn=2, current=0）：可调双方场上/手牌与公共竞技场。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": p0_active if p0_active is not None else mon(1),
        "bench": p0_bench,
    })
    if p0_hand is not None:
        p0 = p0.model_copy(update={"hand": p0_hand})
    p1 = state.players[1].model_copy(update={
        "active": p1_active if p1_active is not None else mon(2, pokemon("硬兽", hp=500)),
        "bench": p1_bench,
    })
    if p1_hand is not None:
        p1 = p1.model_copy(update={"hand": p1_hand})
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
    """直接跑效果（绕过枚举门）：原语层 DslError 语义用。"""
    ctx = ExecutionContext(engine=e, player=player, source=source,
                           effect_id="test", trigger=doc.effects[0].trigger)
    return run_effect(ctx, doc.effects[0])


def iids_of(e: GameEngine, player: int, kind: str) -> list[int]:
    return [a.iid for a in e.legal_actions(player) if a.kind == kind]


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


# ══════════════════════════════════════════════════════════════════════
# WP1 虹色因子（伊布ex）：modify_evolution 声明驱动进化加宽
# ══════════════════════════════════════════════════════════════════════

EEVEE_EX_DOC = parse_card_doc("""
card:
  name_group: 伊布ex
effects:
  - trigger: passive_static
    actions:
      - {action: modify_evolution, args: {match_evolves_from: 伊布, rule_box: ex}}
""")

EEVEE_EX = pokemon("伊布ex", energy_type="无", rule_box="ex")
FLAREON_EX = pokemon("火伊布ex", stage=1, evolves_from="伊布",
                     energy_type="火", rule_box="ex")
VAPOREON_EX = pokemon("水伊布ex", stage=1, evolves_from="伊布",
                      energy_type="水", rule_box="ex")
FLAREON_PLAIN = pokemon("火伊布", stage=1, evolves_from="伊布", energy_type="火")
EEVEE_BASIC = pokemon("伊布", energy_type="无")


def test_modify_evolution_enumerates_and_executes():
    """伊布ex 在场 + 手牌火伊布ex（rule_box=ex 且 evolves_from=伊布）→ 枚出且可执行。"""
    e = board_engine(
        p0_active=mon(1, EEVEE_EX), p0_hand=(inst(50, FLAREON_EX),),
        effects={"伊布ex": EEVEE_EX_DOC},
    )
    act = Action(kind="evolve", iid=50, target_iid=1)
    assert act in e.legal_actions(0)
    e.apply(0, act)
    p0 = e.state.players[0]
    assert p0.active.current.card.name == "火伊布ex"
    assert 50 in p0.evolved_this_turn
    assert all(c.iid != 50 for c in p0.hand)


def test_modify_evolution_rule_box_and_chain_must_match():
    """rule_box 不匹配（无规则盒火伊布）/ evolves_from 不匹配 → 不经声明分支枚出。"""
    other_ex = pokemon("雷丘ex", stage=1, evolves_from="皮卡丘",
                       energy_type="雷", rule_box="ex")
    e = board_engine(
        p0_active=mon(1, EEVEE_EX),
        p0_hand=(inst(50, FLAREON_PLAIN), inst(51, other_ex)),
        effects={"伊布ex": EEVEE_EX_DOC},
    )
    assert not [a for a in e.legal_actions(0) if a.kind == "evolve"]


def test_modify_evolution_entered_play_this_turn_blocked():
    """声明持有者登场当回合（entered_play_this_turn）不可进化——既有门自然生效。"""
    e = board_engine(
        p0_active=mon(1, EEVEE_EX), p0_hand=(inst(50, FLAREON_EX),),
        effects={"伊布ex": EEVEE_EX_DOC},
    )
    p0 = e.state.players[0].model_copy(update={"entered_play_this_turn": {1}})
    e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    assert not [a for a in e.legal_actions(0) if a.kind == "evolve"]


def test_modify_evolution_evolved_this_turn_blocked():
    """声明持有者当回合已进化过（evolved_this_turn）不可再进化。"""
    e = board_engine(
        p0_active=mon(1, EEVEE_EX), p0_hand=(inst(50, FLAREON_EX),),
        effects={"伊布ex": EEVEE_EX_DOC},
    )
    p0 = e.state.players[0].model_copy(update={"evolved_this_turn": {1}})
    e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    assert not [a for a in e.legal_actions(0) if a.kind == "evolve"]


def test_modify_evolution_second_evolve_other_holder_ok():
    """每只每回合限 1 次：进化过一只后，另一只声明持有者可正常进化。"""
    e = board_engine(
        p0_active=mon(1, EEVEE_EX), p0_bench=(mon(2, EEVEE_EX),),
        p0_hand=(inst(50, FLAREON_EX), inst(51, VAPOREON_EX)),
        effects={"伊布ex": EEVEE_EX_DOC},
    )
    e.apply(0, Action(kind="evolve", iid=50, target_iid=1))
    evolves = [(a.iid, a.target_iid) for a in e.legal_actions(0) if a.kind == "evolve"]
    assert (51, 2) in evolves
    assert (51, 1) not in evolves  # 已进化目标栈顶 ∈ evolved_this_turn


def test_modify_evolution_ability_suppressed():
    """监视塔 suppress_ability（伊布ex 为【无】）→ 声明失效，不枚出。"""
    e = board_engine(
        p0_active=mon(1, EEVEE_EX), p0_hand=(inst(50, FLAREON_EX),),
        stadium=inst(399, stadium_card("监视塔")),
        effects={"伊布ex": EEVEE_EX_DOC, "监视塔": WATCHTOWER_DOC},
    )
    assert not [a for a in e.legal_actions(0) if a.kind == "evolve"]


def test_modify_evolution_bad_args_dsl_error():
    """缺 match_evolves_from / rule_box → DslError（求值点不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 伊布ex
effects:
  - trigger: passive_static
    actions:
      - {action: modify_evolution, args: {match_evolves_from: 伊布}}
""")
    e = board_engine(
        p0_active=mon(1, EEVEE_EX), p0_hand=(inst(50, FLAREON_EX),),
        effects={"伊布ex": bad},
    )
    with pytest.raises(DslError, match="modify_evolution"):
        e.legal_actions(0)


def test_evolve_name_chain_regression():
    """回归：纯名字链进化不受影响（无 DSL 文档的常规 evolves_from==卡名 路径）。"""
    e = board_engine(
        p0_active=mon(1, EEVEE_BASIC), p0_hand=(inst(50, FLAREON_EX),),
        effects={},
    )
    assert Action(kind="evolve", iid=50, target_iid=1) in e.legal_actions(0)


# ══════════════════════════════════════════════════════════════════════
# WP3 璀璨结晶（ACE SPEC 道具）：modify_attack_cost types:all + holder_is_tera
# ══════════════════════════════════════════════════════════════════════

CRYSTAL_DOC = parse_card_doc("""
card:
  name_group: 璀璨结晶
effects:
  - trigger: passive_static
    condition: holder_is_tera
    actions:
      - {action: modify_attack_cost, args: {value: 1, types: all}}
""")

TRI_ATTACK = AttackDef(name="三重击", cost=("火", "水", "雷"), damage=100)
FIRE_COLORLESS_ATTACK = AttackDef(name="火无击", cost=("火", "无"), damage=50)


def tera_attacker(attack: AttackDef, *, is_tera: bool = True) -> CardDef:
    return pokemon("太晶兽", attacks=(attack,), is_tera=is_tera, energy_type="火")


def crystal_engine(
    attack: AttackDef, energies: tuple, *, is_tera: bool = True,
    stadium: CardInstance | None = None, extra_effects: dict | None = None,
) -> GameEngine:
    effects = {"璀璨结晶": CRYSTAL_DOC, **(extra_effects or {})}
    return board_engine(
        p0_active=mon(1, tera_attacker(attack, is_tera=is_tera),
                      attached=energies,
                      tool=inst(90, tool_card("璀璨结晶"))),
        stadium=stadium,
        effects=effects,
    )


def attack_enumerated(e: GameEngine) -> bool:
    return any(a.kind == "attack" and a.attack_index == 0 for a in e.legal_actions(0))


def test_types_all_colored_reduction_enables_attack():
    """【火】【水】【雷】费太晶持有者带璀璨结晶：减任意 1 符号，附着水+雷即可攻击
    （确定性取法：无【无】符号 → 减 cost 序列首个有色符号【火】，有效费用 = 水雷）。"""
    energies = (inst(9101, energy_card("水能量", "水")),
                inst(9102, energy_card("雷能量", "雷")))
    e = crystal_engine(TRI_ATTACK, energies)
    assert attack_enumerated(e)


def test_types_all_reduction_pin_first_colored():
    """取法钉死回归：减的是首个有色符号【火】——附着火+水（缺雷）不满足（水，雷）。"""
    energies = (inst(9101, energy_card("火能量", "火")),
                inst(9102, energy_card("水能量", "水")))
    e = crystal_engine(TRI_ATTACK, energies)
    assert not attack_enumerated(e)


def test_types_all_prefers_colorless_symbol():
    """费用含【无】时优先减【无】：【火】【无】→ 有效费用【火】，单火能量即可攻击。"""
    e = crystal_engine(FIRE_COLORLESS_ATTACK, (inst(9101, energy_card("火能量", "火")),))
    assert attack_enumerated(e)
    # 无工具对照：原费【火】【无】需 2 张能量
    plain = board_engine(
        p0_active=mon(1, tera_attacker(FIRE_COLORLESS_ATTACK),
                      attached=(inst(9101, energy_card("火能量", "火")),)),
        effects={"璀璨结晶": CRYSTAL_DOC},
    )
    assert not attack_enumerated(plain)


def test_types_all_non_tera_holder_no_reduction():
    """holder_is_tera 条件：非太晶持有者不减（3 费招 2 能量不可攻击）。"""
    energies = (inst(9101, energy_card("水能量", "水")),
                inst(9102, energy_card("雷能量", "雷")))
    e = crystal_engine(TRI_ATTACK, energies, is_tera=False)
    assert not attack_enumerated(e)


def test_types_all_tool_suppressed_restores_cost():
    """阻碍之塔 suppress_tool → 道具声明失效，恢复原价（2 能量不可攻击）。"""
    energies = (inst(9101, energy_card("水能量", "水")),
                inst(9102, energy_card("雷能量", "雷")))
    e = crystal_engine(
        TRI_ATTACK, energies,
        stadium=inst(399, stadium_card("阻碍之塔")),
        extra_effects={"阻碍之塔": BLOCKER_DOC},
    )
    assert not attack_enumerated(e)


def test_types_all_bad_types_value_dsl_error():
    """types 仅支持 all（未知值 = DslError 不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 坏结晶
effects:
  - trigger: passive_static
    actions:
      - {action: modify_attack_cost, args: {value: 1, types: 火}}
""")
    e = board_engine(
        p0_active=mon(1, tera_attacker(TRI_ATTACK),
                      attached=(inst(9101, energy_card("水能量", "水")),
                                inst(9102, energy_card("雷能量", "雷"))),
                      tool=inst(90, tool_card("坏结晶"))),
        effects={"坏结晶": bad},
    )
    with pytest.raises(DslError, match="modify_attack_cost"):
        e.legal_actions(0)


# ══════════════════════════════════════════════════════════════════════
# WP5 ACE 锁（盖诺赛克特）：lock_play passive_static + category=ace_spec
# ══════════════════════════════════════════════════════════════════════

GENESECT_DOC = parse_card_doc("""
card:
  name_group: 盖诺赛克特
effects:
  - trigger: passive_static
    condition: holder_has_tool
    actions:
      - {action: lock_play, args: {category: ace_spec}}
""")

GENESECT = pokemon("盖诺赛克特", energy_type="无", has_ability=True)

ITEM_DOC = parse_card_doc("""
card:
  name_group: 秘密箱
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")

NORMAL_ITEM_DOC = parse_card_doc("""
card:
  name_group: 普通物品
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")

SUPPORTER_DOC = parse_card_doc("""
card:
  name_group: 王牌支援者
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 2}
""")

ACE_ITEM = item_card("秘密箱", is_ace_spec=True)
NORMAL_ITEM = item_card("普通物品")
ACE_SUPPORTER = supporter_card("王牌支援者", is_ace_spec=True)
ACE_STADIUM = stadium_card("王牌竞技场", is_ace_spec=True)
ACE_TOOL = tool_card("王牌道具", is_ace_spec=True)
ACE_ENERGY = energy_card("王牌能量", "火", is_ace_spec=True)

ACE_HAND = (
    inst(50, ACE_ITEM), inst(51, NORMAL_ITEM), inst(52, ACE_SUPPORTER),
    inst(53, ACE_STADIUM), inst(54, ACE_TOOL), inst(55, ACE_ENERGY),
)

ACE_EFFECTS = {
    "秘密箱": ITEM_DOC, "普通物品": NORMAL_ITEM_DOC,
    "王牌支援者": SUPPORTER_DOC, "盖诺赛克特": GENESECT_DOC,
}


def genesect_bench(*, with_tool: bool = True) -> InPlayPokemon:
    tool = inst(91, tool_card("望远镜")) if with_tool else None
    return mon(20, GENESECT, tool=tool)


def ace_lock_engine(**kwargs) -> GameEngine:
    kwargs.setdefault("p0_hand", ACE_HAND)
    kwargs.setdefault("effects", dict(ACE_EFFECTS))
    return board_engine(**kwargs)


def assert_all_ace_locked(e: GameEngine) -> None:
    """五门类 ACE 全部不枚举（D-069-2），非 ACE 物品照常。"""
    assert 50 not in iids_of(e, 0, "play_trainer")
    assert 52 not in iids_of(e, 0, "play_trainer")
    assert 53 not in iids_of(e, 0, "play_stadium")
    assert 54 not in iids_of(e, 0, "attach_tool")
    assert 55 not in iids_of(e, 0, "attach_energy")


def assert_all_ace_free(e: GameEngine) -> None:
    assert 50 in iids_of(e, 0, "play_trainer")
    assert 51 in iids_of(e, 0, "play_trainer")  # 非 ACE 物品不受锁影响
    assert 52 in iids_of(e, 0, "play_trainer")
    assert 53 in iids_of(e, 0, "play_stadium")
    assert 54 in iids_of(e, 0, "attach_tool")
    assert 55 in iids_of(e, 0, "attach_energy")


def test_ace_lock_blocks_all_five_categories():
    """盖诺赛克特+道具在对手场 → 我方 ACE 物品/支援者/竞技场/道具附着/能量附着全锁。"""
    e = ace_lock_engine(p1_bench=(genesect_bench(),))
    assert_all_ace_locked(e)
    assert 51 in iids_of(e, 0, "play_trainer")  # 非 ACE 物品不受影响


def test_ace_lock_requires_holder_tool():
    """holder_has_tool 条件：盖诺赛克特身上无道具 → 不锁。"""
    e = ace_lock_engine(p1_bench=(genesect_bench(with_tool=False),))
    assert_all_ace_free(e)


def test_ace_lock_side_correctness():
    """侧别：盖诺赛克特在自己场上不锁自己的 ACE（锁作用于对手）。"""
    e = ace_lock_engine(p0_bench=(genesect_bench(),))
    assert_all_ace_free(e)


def test_ace_lock_ability_suppressed_unlocks():
    """监视塔 suppress_ability（盖诺赛克特为【无】）→ 特性来源声明失效，解锁。"""
    effects = {**ACE_EFFECTS, "监视塔": WATCHTOWER_DOC}
    e = ace_lock_engine(
        p1_bench=(genesect_bench(),),
        stadium=inst(399, stadium_card("监视塔")),
        effects=effects,
    )
    assert_all_ace_free(e)


def test_ace_lock_source_leaves_play_unlocks():
    """求值点实时扫场：盖诺赛克特离场立即解锁。"""
    e = ace_lock_engine(p1_bench=(genesect_bench(),))
    assert 50 not in iids_of(e, 0, "play_trainer")
    p1 = e.state.players[1].model_copy(update={"bench": ()})
    e.state = e.state.model_copy(update={"players": (e.state.players[0], p1)})
    assert_all_ace_free(e)


def test_ace_lock_condition_false_then_true_dynamic():
    """condition 动态求值：道具被移除（直接改状态）即解锁。"""
    e = ace_lock_engine(p1_bench=(genesect_bench(),))
    assert_all_ace_locked(e)
    holder = e.state.players[1].bench[0].model_copy(update={"attached_tool": None})
    p1 = e.state.players[1].model_copy(update={"bench": (holder,)})
    e.state = e.state.model_copy(update={"players": (e.state.players[0], p1)})
    assert_all_ace_free(e)


def test_lock_play_passive_static_item_category_dsl_error():
    """passive_static 挂载的 lock_play 仅支持 category=ace_spec
    （item 锁走 on_attack 解释执行，D-029-3；误挂 = DslError 不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 坏锁兽
effects:
  - trigger: passive_static
    actions:
      - {action: lock_play, args: {category: item}}
""")
    e = board_engine(
        p0_hand=(inst(50, ACE_ITEM),),
        p1_bench=(mon(20, pokemon("坏锁兽", has_ability=True)),),
        effects={"坏锁兽": bad, "秘密箱": ITEM_DOC},
    )
    with pytest.raises(DslError, match="lock_play"):
        e.legal_actions(0)


def test_lock_play_on_play_ace_spec_category_dsl_error():
    """解释执行路径（on_play/on_attack）的 lock_play 仅支持 category=item
    （ace_spec 仅 passive_static 声明挂载；不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 坏锁卡
effects:
  - trigger: on_play
    actions:
      - {action: lock_play, args: {category: ace_spec}}
""")
    e = board_engine()
    with pytest.raises(DslError, match="lock_play"):
        run_doc(e, bad, inst(60, item_card("坏锁卡")))


# ══════════════════════════════════════════════════════════════════════
# WP2 顽强之心（皮卡丘ex）：prevent_ko 满 HP 免昏厥截顶
# ══════════════════════════════════════════════════════════════════════

PIKACHU_DOC = parse_card_doc("""
card:
  name_group: 皮卡丘ex
effects:
  - trigger: passive_static
    actions:
      - {action: prevent_ko, args: {remaining_hp: 10, when: full_hp}}
""")

PIKACHU_EX = pokemon("皮卡丘ex", hp=100, energy_type="雷",
                     has_ability=True, rule_box="ex")

WATCHTOWER_LIGHTNING_DOC = parse_card_doc("""
card:
  name_group: 监视塔
effects:
  - trigger: passive_static
    actions:
      - {action: suppress_ability, args: {types: [雷]}}
""")

# 攻方 DSL 绑定招式的伤害（on_attack damage 原语）与铺伤（place_damage_counters）
SLAM_DOC = parse_card_doc("""
card:
  name_group: 攻兽
effects:
  - trigger: on_attack
    attack: 重击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 200}}
""")

SCATTER_DOC = parse_card_doc("""
card:
  name_group: 铺伤兽
effects:
  - trigger: on_attack
    attack: 撒菱
    actions:
      - {action: place_damage_counters, selector: all_pokemon_both,
         args: {counters: 10}}
""")

HAMMER_DOC = parse_card_doc("""
card:
  name_group: 重锤
effects:
  - trigger: on_play
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 200}}
""")

COPY_DOC = parse_card_doc("""
card:
  name_group: 梦幻
effects:
  - trigger: on_attack
    attack: 复制
    actions:
      - {action: copy_attack, selector: opponent_active_attack, choose: 1}
""")


def heavy_attacker(damage: int, *, energy_type: str = "无", name: str = "攻兽") -> CardDef:
    """零费固定伤害白板攻击兽（cost=() 免附能量）。"""
    return pokemon(name, attacks=(AttackDef(name="重击", cost=(), damage=damage),),
                   energy_type=energy_type)


def pikachu_engine(
    *, attacker: CardDef | None = None, pikachu_card: CardDef = PIKACHU_EX,
    pikachu_damage: int = 0, effects: dict | None = None, **kwargs,
) -> GameEngine:
    return board_engine(
        p0_active=mon(1, attacker or heavy_attacker(120)),
        p1_active=mon(2, pikachu_card, damage=pikachu_damage),
        effects={"皮卡丘ex": PIKACHU_DOC, **(effects or {})},
        **kwargs,
    )


def ko_events(e: GameEngine) -> list:
    return [ev for ev in e.events if ev.kind == "knockout"]


def test_prevent_ko_full_hp_lethal_whiteboard_capped():
    """满 HP 白板致死（120 ≥ 100）→ 截顶至 100−10=90，不昏厥，对局继续。"""
    e = pikachu_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 90
    assert not ko_events(e)
    assert e.state.phase == "main" and e.state.current_player == 1


def test_prevent_ko_full_hp_nonlethal_passthrough():
    """满 HP 非致死（60 < 100）→ 不截顶，全额承受。"""
    e = pikachu_engine(attacker=heavy_attacker(60))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 60
    assert not ko_events(e)


def test_prevent_ko_damaged_target_normal_ko():
    """已受伤（damage=20，非满 HP）+ 致死 → 不截顶，正常昏厥（ex 拿 2 奖赏）。"""
    e = pikachu_engine(pikachu_damage=20)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert ko_events(e)
    assert len([ev for ev in e.events if ev.kind == "take_prize"]) == 2
    # 无备战可换上 → 对手判负（rules-manual §8 胜利条件②）
    assert e.state.phase == "game_over" and e.state.winner == 0


def test_prevent_ko_damage_counters_bypass():
    """指示物致死不经守卫：满 HP 被铺 10 个指示物（100）→ 照常昏厥。"""
    e = pikachu_engine(
        attacker=pokemon("铺伤兽", attacks=(AttackDef(name="撒菱", cost=(),
                                                    damage=None),)),
        effects={"铺伤兽": SCATTER_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert any(ev.detail.get("name") == "皮卡丘ex" for ev in ko_events(e))
    assert e.state.phase == "game_over" and e.state.winner == 0


def test_prevent_ko_ability_suppressed_bypass():
    """监视塔 suppress_ability（皮卡丘ex 为【雷】）→ 特性失效，白板致死照常昏厥。"""
    e = pikachu_engine(
        stadium=inst(399, stadium_card("监视塔")),
        effects={"监视塔": WATCHTOWER_LIGHTNING_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert any(ev.detail.get("name") == "皮卡丘ex" for ev in ko_events(e))
    assert e.state.phase == "game_over" and e.state.winner == 0


def test_prevent_ko_weakness_doubled_still_capped():
    """弱点 ×2 结算后仍致死（斗 60 ×2 = 120 ≥ 100）→ 同样截顶至 90。"""
    weak_pika = PIKACHU_EX.model_copy(update={"weakness": "斗"})
    e = pikachu_engine(attacker=heavy_attacker(60, energy_type="斗"),
                       pikachu_card=weak_pika)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 90
    assert not ko_events(e)


def test_prevent_ko_dsl_damage_primitive_capped():
    """DSL damage 原语（on_attack，200）→ 截顶至 90。"""
    e = pikachu_engine(
        attacker=pokemon("攻兽", attacks=(AttackDef(name="重击", cost=(),
                                                  damage=None),)),
        effects={"攻兽": SLAM_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 90
    assert not ko_events(e)
    assert e.state.phase == "main" and e.state.current_player == 1


def test_prevent_ko_trainer_effect_damage_bypass():
    """效果伤害不经守卫：on_play 训练家 damage 200 → 满 HP 照常昏厥。"""
    e = pikachu_engine(
        p0_hand=(inst(50, item_card("重锤")),),
        effects={"重锤": HAMMER_DOC},
    )
    e.apply(0, Action(kind="play_trainer", iid=50))
    assert any(ev.detail.get("name") == "皮卡丘ex" for ev in ko_events(e))
    assert e.state.phase == "game_over" and e.state.winner == 0


def test_prevent_ko_copy_attack_whiteboard_capped():
    """copy_attack 白板复制：梦幻复制皮卡丘自己的白板高伤招（200）打回满 HP
    皮卡丘 → 截顶至 90。"""
    strong_pika = PIKACHU_EX.model_copy(update={
        "attacks": (AttackDef(name="十万伏特", cost=(), damage=200),),
    })
    mew = pokemon("梦幻", attacks=(AttackDef(name="复制", cost=(), damage=None),))
    e = board_engine(
        p0_active=mon(1, mew), p1_active=mon(2, strong_pika),
        effects={"皮卡丘ex": PIKACHU_DOC, "梦幻": COPY_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"
    e.apply(0, Action(kind="choose", choices=(0,)))
    assert e.state.players[1].active.damage == 90
    assert not ko_events(e)


def test_prevent_ko_missing_remaining_hp_dsl_error():
    """缺 remaining_hp → DslError（求值点不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 皮卡丘ex
effects:
  - trigger: passive_static
    actions:
      - {action: prevent_ko, args: {when: full_hp}}
""")
    e = pikachu_engine(effects={"皮卡丘ex": bad})
    with pytest.raises(DslError, match="prevent_ko"):
        e.apply(0, Action(kind="attack", attack_index=0))


def test_prevent_ko_unknown_when_dsl_error():
    """when 仅支持 full_hp（未知值 = DslError 不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 皮卡丘ex
effects:
  - trigger: passive_static
    actions:
      - {action: prevent_ko, args: {remaining_hp: 10, when: always}}
""")
    e = pikachu_engine(effects={"皮卡丘ex": bad})
    with pytest.raises(DslError, match="prevent_ko"):
        e.apply(0, Action(kind="attack", attack_index=0))


# ══════════════════════════════════════════════════════════════════════
# WP4 力之沙漏：own_turn_end 事件（D-069-1 时点口径：检查阶段内、状态结算
# 之后）+ 道具来源寻源（_drain_event_triggers 扩 attached_tool +
# _tool_suppressed 守卫）+ attach_energy own_discard 扩 target_pool=self
# （段 2 免选，目标 = 来源道具持有者；「则可选择」= energy_up_to=true）
# ══════════════════════════════════════════════════════════════════════

HOURGLASS_DOC = parse_card_doc("""
card:
  name_group: 力之沙漏
effects:
  - trigger: trigger_on_event
    event: own_turn_end
    condition: self_is_active
    actions:
      - {action: attach_energy, selector: own_discard, filters: [basic_energy],
         choose: 1, destination: attach,
         args: {target_pool: self, energy_up_to: true}}
""")

FROSLASS_DOC = parse_card_doc("""
card:
  name_group: 雪妖女
effects:
  - trigger: trigger_on_event
    event: pokemon_check
    actions:
      - {action: place_damage_counters, selector: all_pokemon_both, args: {counters: 1}}
""")


def hourglass_engine(
    *, bench_tool: bool = False, discard: tuple = (),
    stadium: CardInstance | None = None, extra_effects: dict | None = None,
) -> GameEngine:
    """p0 回合 main 阶段：力之沙漏（iid=90）挂在 p0 战斗场（或备战 iid=3）。"""
    tool = inst(90, tool_card("力之沙漏"))
    holder = mon(3 if bench_tool else 1, tool=tool)
    e = board_engine(
        p0_active=mon(1) if bench_tool else holder,
        p0_bench=(holder,) if bench_tool else (),
        stadium=stadium,
        effects={"力之沙漏": HOURGLASS_DOC, **(extra_effects or {})},
    )
    if discard:
        p0 = e.state.players[0].model_copy(update={"discard": discard})
        e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    return e


def own_turn_end_events(e: GameEngine) -> list:
    return [
        ev for ev in e.events
        if ev.kind == "trigger_on_event" and ev.detail.get("event") == "own_turn_end"
    ]


def test_own_turn_end_attach_basic_energy_to_active_holder():
    """end_turn → 检查阶段触发力之沙漏 → 挂起选弃牌区基本能量 → 附到战斗场持有者，
    挂起恢复后检查收尾、正常开下一回合。"""
    e = hourglass_engine(discard=(inst(60, energy_card("基本火能量", "火")),))
    e.apply(0, Action(kind="end_turn"))
    assert e.state.phase == "choice" and e.state.current_player == 0
    pc = e.state.pending_choice
    assert pc.pool == "own_discard" and tuple(pc.pool_iids) == (60,)
    e.apply(0, Action(kind="choose", choices=(60,)))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [60]
    assert p0.discard == ()
    assert e.state.phase == "main" and e.state.current_player == 1
    assert len(e.state.players[1].hand) == 1  # 对手回合开始抽牌


def test_own_turn_end_energy_up_to_choose_zero_forfeit():
    """「则可选择」= energy_up_to（min_choose=0）：选 0 张放弃，能量留弃牌区。"""
    e = hourglass_engine(discard=(inst(60, energy_card("基本火能量", "火")),))
    e.apply(0, Action(kind="end_turn"))
    assert e.state.phase == "choice"
    assert Action(kind="choose", choices=()) in e.legal_actions(0)
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert p0.active.attached_energy == ()
    assert [c.iid for c in p0.discard] == [60]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_own_turn_end_bench_holder_condition_blocks():
    """持有者在备战区（condition self_is_active 不满足）→ 不触发。"""
    e = hourglass_engine(
        bench_tool=True, discard=(inst(60, energy_card("基本火能量", "火")),),
    )
    e.apply(0, Action(kind="end_turn"))
    assert not own_turn_end_events(e)
    assert e.state.players[0].bench[0].attached_energy == ()
    assert e.state.phase == "main" and e.state.current_player == 1


def test_own_turn_end_empty_discard_pool_no_suspend():
    """弃牌区无基本能量 → 触发照常分发，能量池空 → 不挂起、空结算。"""
    e = hourglass_engine()
    e.apply(0, Action(kind="end_turn"))
    assert own_turn_end_events(e)
    assert e.state.players[0].active.attached_energy == ()
    assert e.state.phase == "main" and e.state.current_player == 1


def test_own_turn_end_tool_left_play_not_triggered():
    """道具回合中已离场（检查阶段入队扫描时无 attached_tool）→ 不触发。"""
    e = hourglass_engine(discard=(inst(60, energy_card("基本火能量", "火")),))
    holder = e.state.players[0].active.model_copy(update={"attached_tool": None})
    p0 = e.state.players[0].model_copy(update={"active": holder})
    e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    e.apply(0, Action(kind="end_turn"))
    assert not own_turn_end_events(e)
    assert e.state.phase == "main" and e.state.current_player == 1


def test_own_turn_end_tool_suppressed_by_blocker_not_fired():
    """阻碍之塔 suppress_tool 在场 → 排水点守卫拦截，道具效果不分发。"""
    e = hourglass_engine(
        discard=(inst(60, energy_card("基本火能量", "火")),),
        stadium=inst(399, stadium_card("阻碍之塔")),
        extra_effects={"阻碍之塔": BLOCKER_DOC},
    )
    e.apply(0, Action(kind="end_turn"))
    assert not own_turn_end_events(e)
    assert e.state.players[0].active.attached_energy == ()
    assert e.state.phase == "main" and e.state.current_player == 1


def test_own_turn_end_fifo_before_pokemon_check():
    """与 pokemon_check 触发同帧 FIFO：own_turn_end 先入队先分发——力之沙漏
    挂起选择时雪妖女尚未触发；恢复后雪妖女才结算。"""
    e = hourglass_engine(
        discard=(inst(60, energy_card("基本火能量", "火")),),
        extra_effects={"雪妖女": FROSLASS_DOC},
    )
    froslass = mon(3, pokemon("雪妖女", has_ability=True))
    p0 = e.state.players[0].model_copy(update={"bench": (froslass,)})
    e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    e.apply(0, Action(kind="end_turn"))
    assert e.state.phase == "choice"
    fired = [
        ev.detail.get("event") for ev in e.events if ev.kind == "trigger_on_event"
    ]
    assert fired == ["own_turn_end"]
    e.apply(0, Action(kind="choose", choices=(60,)))
    fired = [
        ev.detail.get("event") for ev in e.events if ev.kind == "trigger_on_event"
    ]
    assert fired == ["own_turn_end", "pokemon_check"]
    assert e.state.players[1].active.damage == 10  # 雪妖女效果已结算
    assert e.state.phase == "main" and e.state.current_player == 1


def test_attach_energy_target_pool_unknown_dsl_error():
    """target_pool 未知值 = DslError（不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 坏沙漏
effects:
  - trigger: trigger_on_event
    event: own_turn_end
    actions:
      - {action: attach_energy, selector: own_discard, choose: 1, destination: attach,
         args: {target_pool: bogus}}
""")
    e = board_engine()
    with pytest.raises(DslError, match="target_pool"):
        run_doc(e, bad, inst(60, tool_card("坏沙漏")))


def test_attach_energy_self_target_filters_dsl_error():
    """target_pool=self 目标固定为来源持有者——target_filters 组合 = DslError（不猜）。"""
    bad = parse_card_doc("""
card:
  name_group: 坏沙漏
effects:
  - trigger: trigger_on_event
    event: own_turn_end
    actions:
      - {action: attach_energy, selector: own_discard, choose: 1, destination: attach,
         args: {target_pool: self, target_filters: [basic_energy]}}
""")
    e = board_engine()
    with pytest.raises(DslError, match="target_filters"):
        run_doc(e, bad, inst(60, tool_card("坏沙漏")))


# ══════════════════════════════════════════════════════════════════════
# WP6 原语小扩 ×3：discard own_attached_energy choose=N（皮卡丘ex 黄晶伏特
# 弃自身 3 能量）/ 计数词 attached_energy_on_opponent_all（叶伊布ex
# 绿叶风暴 ×60）/ heal own_bench 全体（叶伊布ex 苔纹玛瑙 各回 100）
# ══════════════════════════════════════════════════════════════════════

JOLT_DOC = parse_card_doc("""
card:
  name_group: 黄晶兽
effects:
  - trigger: on_attack
    attack: 黄晶伏特
    actions:
      - {action: discard, selector: own_attached_energy, choose: 3}
      - {action: damage, selector: opponent_active, args: {amount: 220}}
""")


def jolt_engine(energies: tuple) -> GameEngine:
    attacker = pokemon(
        "黄晶兽", attacks=(AttackDef(name="黄晶伏特", cost=(), damage=None),),
        rule_box="ex",
    )
    return board_engine(
        p0_active=mon(1, attacker, attached=energies),
        effects={"黄晶兽": JOLT_DOC},
    )


def test_discard_own_attached_energy_choose3():
    """choose=3：弃来源宝可梦自身 3 张附着能量（池收窄为来源，exclude 他者），
    后序伤害节点照算。"""
    energies = tuple(inst(9100 + i, energy_card(f"雷能量{i}", "雷")) for i in range(3))
    e = jolt_engine(energies)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice" and e.state.current_player == 0
    pc = e.state.pending_choice
    assert pc.pool == "own_attached_energy"
    assert pc.min_choose == 3 and pc.max_choose == 3
    assert tuple(sorted(pc.pool_iids)) == (9100, 9101, 9102)
    e.apply(0, Action(kind="choose", choices=(9100, 9101, 9102)))
    p0 = e.state.players[0]
    assert p0.active.attached_energy == ()
    assert sorted(c.iid for c in p0.discard) == [9100, 9101, 9102]
    assert e.state.players[1].active.damage == 220
    assert e.state.phase == "main" and e.state.current_player == 1


def test_discard_own_attached_energy_choose3_insufficient_pool_noop():
    """池不足 3 张 → 弃置 no-op 不挂起（对齐 choose=1 池空 no-op 口径），伤害照算。"""
    energies = tuple(inst(9100 + i, energy_card(f"雷能量{i}", "雷")) for i in range(2))
    e = jolt_engine(energies)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[0].active.attached_energy == energies
    assert e.state.players[0].discard == ()
    assert e.state.players[1].active.damage == 220
    assert e.state.phase == "main" and e.state.current_player == 1


def test_discard_own_attached_energy_choose0_dsl_error():
    """choose 须为正 int（choose=0 = DslError 不猜）。

    schema 层 choose 有 ge=1 约束（装载期已拦），此处经 model_copy 绕过校验
    直达原语守卫（求值点不猜的双保险）。
    """
    doc = parse_card_doc("""
card:
  name_group: 坏兽
effects:
  - trigger: on_attack
    attack: 坏招
    actions:
      - {action: discard, selector: own_attached_energy, choose: 1}
""")
    node = doc.effects[0].actions[0].model_copy(update={"choose": 0})
    effect = doc.effects[0].model_copy(update={"actions": (node,)})
    bad = doc.model_copy(update={"effects": (effect,)})
    e = board_engine()
    with pytest.raises(DslError, match="discard"):
        run_doc(e, bad, e.state.players[0].active.current)


LEAF_STORM_DOC = parse_card_doc("""
card:
  name_group: 叶伊布ex
effects:
  - trigger: on_attack
    attack: 绿叶风暴
    actions:
      - {action: damage, selector: opponent_active,
         count: attached_energy_on_opponent_all, args: {per: 60, op: "×"}}
""")


def leafstorm_engine(p1_active_energy: int, p1_bench_energy: int) -> GameEngine:
    attacker = pokemon(
        "叶伊布ex", attacks=(AttackDef(name="绿叶风暴", cost=(), damage=None),),
        rule_box="ex",
    )
    p1_active = mon(2, pokemon("硬兽", hp=500), attached=tuple(
        inst(9200 + i, energy_card(f"草能量{i}", "草")) for i in range(p1_active_energy)
    ))
    p1_bench = (mon(3, pokemon("备兽"), attached=tuple(
        inst(9210 + i, energy_card(f"草能量b{i}", "草"))
        for i in range(p1_bench_energy)
    )),)
    return board_engine(
        p0_active=mon(1, attacker),
        p1_active=p1_active, p1_bench=p1_bench,
        effects={"叶伊布ex": LEAF_STORM_DOC},
    )


def test_counter_attached_energy_on_opponent_all():
    """对手全场（战斗 2 + 备战 1 = 3 张）附着能量 ×60 = 180。"""
    e = leafstorm_engine(2, 1)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 180


def test_counter_attached_energy_on_opponent_all_zero():
    """对手全场无附着能量 → 0 伤害（招式照常宣言、回合消耗）。"""
    e = leafstorm_engine(0, 0)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0
    assert e.state.phase == "main" and e.state.current_player == 1


AGATE_DOC = parse_card_doc("""
card:
  name_group: 叶伊布ex
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: heal, selector: own_bench, args: {amount: 100}}
""")


def agate_engine(bench: tuple) -> GameEngine:
    return board_engine(
        p0_active=mon(1, pokemon("叶伊布ex", has_ability=True, rule_box="ex"),
                      damage=100),
        p0_bench=bench,
        effects={"叶伊布ex": AGATE_DOC},
    )


def test_heal_own_bench_all():
    """自己备战全体各回 100：100→0 / 50→0（不过回复）；战斗场持有者不受影响。"""
    e = agate_engine((mon(3, pokemon("甲"), damage=100),
                      mon(4, pokemon("乙"), damage=50)))
    act = Action(kind="use_ability", iid=1)
    assert act in e.legal_actions(0)
    e.apply(0, act)
    p0 = e.state.players[0]
    assert [m.damage for m in p0.bench] == [0, 0]
    assert p0.active.damage == 100
    assert e.state.phase == "main" and e.state.current_player == 0


def test_heal_own_bench_empty_bench_not_enumerated():
    """备战空 = 无落点 → 特性不枚举（ability_feasible 门）。"""
    e = agate_engine(())
    assert not [a for a in e.legal_actions(0) if a.kind == "use_ability"]


def test_heal_own_bench_full_hp_noop():
    """备战满血 → 恢复 0 空结算（floor 0 不过回复），特性照常消耗次数。"""
    e = agate_engine((mon(3, pokemon("甲")),))
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.players[0].bench[0].damage == 0
    assert 1 in e.state.players[0].abilities_used_this_turn
