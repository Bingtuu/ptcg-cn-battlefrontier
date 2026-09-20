"""task 026 WP7 机制测试：宝可梦检查阶段 + 特殊状态结算（D-WP7-1/2）/
常驻伤害修正挂载面泛化（D-WP7-3）/ 攻击费用读道具（D-WP7-4）/
protection 备战伤害免疫（D-WP7-5）/ 小原语批（D-WP7-6~10）/
pokemon_check 事件 + has_ability 管道（D-WP7-11）。

设计决议（tasks/task 026.md WP7 节，2026-09-19 定稿）：
- D-WP7-1 检查阶段：每回合结束（含攻击/换上路径）插入——回合持有者方先、
  毒→灼→眠→麻固定序、随后 pokemon_check 事件触发，全部结束后统一
  check_knockouts + 奖赏（rules-manual §7.2 末注），再开下一回合。
- D-WP7-2 睡眠/麻痹不可撤退、不可用招式（枚举门控）；麻痹记录施加回合标记，
  持有者下一个自己回合结束后的检查恢复（施加当回合不恢复）。
- D-WP7-3 伤害修正四来源求和：道具（既有）+ 竞技场 + 宝可梦 aura
  （scope=own_field，同名来源去重）+ 回合级标记（turn_damage_mods）；
  condition 对攻击方持有者求值；args.target_rule_box 在求值点校验。
- D-WP7-5 protection scope=opponent_attack_damage_to_bench：伤害免疫，
  作用面 = 自己备战区，target_filters（如 no_rule_box）收敛受保护目标。
"""

from typing import ClassVar

import pytest
from helpers import basic, energy, inst, main_state, stage1

from battlefrontier.dsl import ExecutionContext, parse_card_doc, run_effect
from battlefrontier.dsl.chooser import resolve_in_play_pool
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
    owner: str | None = None, has_ability: bool = False,
    energy_type: str | None = None, weakness: str | None = None,
    resistance: str | None = None, stage: int = 0,
) -> CardDef:
    if attacks is None:
        attacks = (AttackDef(name="打击", cost=("无",) * cost, damage=damage),)
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=hp, stage=stage, attacks=attacks, retreat_cost=retreat,
        rule_box=rule_box, owner=owner, has_ability=has_ability,
        energy_type=energy_type, weakness=weakness, resistance=resistance,
    )


def mon(
    iid: int, card: CardDef | None = None, *, damage: int = 0,
    conditions: frozenset = frozenset(), energies: int = 0,
    paralyzed_mark: tuple[int, int] | None = None,
    tool: CardInstance | None = None,
) -> InPlayPokemon:
    card = card or pokemon(f"兽{iid}", hp=500)
    return InPlayPokemon(
        stack=(inst(iid, card),),
        attached_energy=tuple(inst(9000 + iid * 10 + j, energy()) for j in range(energies)),
        attached_tool=tool,
        damage=damage, conditions=conditions, paralyzed_mark=paralyzed_mark,
    )


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def supporter_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def stadium_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="竞技场")


def tool_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="宝可梦道具")


def board_engine(
    *, p0_active=None, p0_bench: tuple = (), p1_active=None, p1_bench: tuple = (),
    p0_extra_hand: tuple = (), p0_deck=None, p1_deck=None, p1_hand=None,
    stadium: CardInstance | None = None, stadium_owner: int | None = None,
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


def run_doc(e: GameEngine, doc, source: CardInstance, player: int = 0):
    """直接跑效果（绕过可行性门）：原语层 DslError/no-op 语义用。"""
    ctx = ExecutionContext(engine=e, player=player, source=source,
                           effect_id="test", trigger=doc.effects[0].trigger)
    return run_effect(ctx, doc.effects[0])


def prim_results(e: GameEngine, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


def check_events(e: GameEngine) -> list:
    return [ev for ev in e.events if ev.kind == "check_status"]


# ── 宝可梦检查阶段 + 特殊状态（清单 1-7，D-WP7-1/2）───────────────────────


def test_check_poison_counters_both_sides_and_accumulate() -> None:
    """清单1：中毒 = 检查阶段放 1 指示物；双方在场中毒宝可梦各结算；持续多回合累计。"""
    poisoned = frozenset({SpecialCondition.POISONED})
    e = board_engine(
        p0_active=mon(1, damage=0, conditions=poisoned),
        p1_active=mon(2, damage=0, conditions=poisoned),
        p1_bench=(mon(80, damage=30, conditions=poisoned),),
    )
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[0].active.damage == 10
    assert e.state.players[1].active.damage == 10
    assert e.state.players[1].bench[0].damage == 40
    # 次回合结束再放（累计）
    e.apply(1, Action(kind="end_turn"))
    assert e.state.players[0].active.damage == 20
    assert e.state.players[1].active.damage == 20
    assert e.state.players[1].bench[0].damage == 50
    # 中毒不自动恢复
    assert SpecialCondition.POISONED in e.state.players[0].active.conditions


def test_check_burn_counters_and_coin_flip() -> None:
    """清单2：灼伤 = 放 2 指示物 + 持有者掷币，正面恢复；反面保持、下轮再放。"""
    burned = frozenset({SpecialCondition.BURNED})
    # seed 0 首次掷币 = 正面：放 20 后恢复，下一轮不再放
    e = board_engine(p0_active=mon(1, damage=0, conditions=burned), seed=0)
    e.apply(0, Action(kind="end_turn"))
    p0 = e.state.players[0]
    assert p0.active.damage == 20
    assert p0.active.conditions == frozenset()  # 正面恢复
    e.apply(1, Action(kind="end_turn"))
    assert e.state.players[0].active.damage == 20  # 已恢复，不再放
    # seed 1 首次掷币 = 反面：保持，下个检查再放 20 后再掷（第二次正面恢复）
    e = board_engine(p0_active=mon(1, damage=0, conditions=burned), seed=1)
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[0].active.damage == 20
    assert SpecialCondition.BURNED in e.state.players[0].active.conditions
    e.apply(1, Action(kind="end_turn"))
    assert e.state.players[0].active.damage == 40  # 反面保持 → 再放
    assert e.state.players[0].active.conditions == frozenset()  # 第二次正面
    # 种子确定性：同种子两次运行灼伤序列一致
    def burn_trace(seed: int) -> list:
        e2 = board_engine(p0_active=mon(1, damage=0, conditions=burned), seed=seed)
        e2.apply(0, Action(kind="end_turn"))
        e2.apply(1, Action(kind="end_turn"))
        return [(ev.kind, tuple(sorted(ev.detail.items()))) for ev in e2.events]
    assert burn_trace(7) == burn_trace(7)


def test_check_sleep_coin_flip_and_action_gating() -> None:
    """清单3：睡眠掷币正面恢复反面保持；睡眠/麻痹不可撤退、不可用招式（枚举门控）。"""
    asleep = frozenset({SpecialCondition.ASLEEP})
    e = board_engine(
        p0_active=mon(1, conditions=asleep, energies=3),
        p0_bench=(mon(70),),  # 有备战 + 能量充足：仅因睡眠被门控
    )
    kinds = {a.kind for a in e.legal_actions(0)}
    assert "retreat" not in kinds and "attack" not in kinds
    # 麻痹同口径
    e = board_engine(
        p0_active=mon(1, conditions=frozenset({SpecialCondition.PARALYZED}),
                      energies=3, paralyzed_mark=(1, 1)),
        p0_bench=(mon(70),),
    )
    kinds = {a.kind for a in e.legal_actions(0)}
    assert "retreat" not in kinds and "attack" not in kinds
    # 睡眠掷币：seed 0 正面 → 恢复
    e = board_engine(p0_active=mon(1, conditions=asleep, energies=3), seed=0)
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[0].active.conditions == frozenset()
    # seed 1 反面 → 保持（不放伤害指示物）
    e = board_engine(p0_active=mon(1, conditions=asleep, energies=3), seed=1)
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[0].active.conditions == asleep
    assert e.state.players[0].active.damage == 0


def test_check_paralysis_recovers_after_holder_next_own_turn() -> None:
    """清单4：麻痹在施加当回合结束不恢复；持有者下一个自己回合结束后的检查恢复。"""
    para_doc = parse_card_doc("""
card:
  name_group: 麻痹兽
effects:
  - trigger: on_attack
    attack: 麻痹击
    actions:
      - {action: apply_status, selector: opponent_active, args: {status: paralyzed}}
""")
    attacker = pokemon("麻痹兽", attacks=(
        AttackDef(name="麻痹击", cost=("无",), damage=None),))
    e = board_engine(
        p0_active=mon(1, attacker, energies=1),
        p1_active=mon(2, energies=1), p1_bench=(mon(80),),
        effects={"麻痹兽": para_doc},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    p1 = e.state.players[1]
    assert SpecialCondition.PARALYZED in p1.active.conditions
    assert p1.active.paralyzed_mark == (2, 0)  # 施加回合标记（turn=2, p0 回合）
    # 施加当回合（p0）结束后的检查：不恢复（回合权已移交 p1，状态仍在）
    assert e.state.current_player == 1 and e.state.phase == "main"
    assert SpecialCondition.PARALYZED in e.state.players[1].active.conditions
    # 持有者（p1）本回合：麻痹期间不可用招式/撤退
    kinds = {a.kind for a in e.legal_actions(1)}
    assert "attack" not in kinds and "retreat" not in kinds
    # 持有者回合结束后的检查：恢复
    e.apply(1, Action(kind="end_turn"))
    assert e.state.players[1].active.conditions == frozenset()
    assert e.state.players[1].active.paralyzed_mark is None
    # 再下一轮回合：可正常攻击
    e.apply(0, Action(kind="end_turn"))
    assert "attack" in {a.kind for a in e.legal_actions(1)}


def test_check_paralysis_default_mark_recovers_at_own_turn_end() -> None:
    """清单4 边界：无施加标记（直接构造入场）的麻痹在持有者回合结束检查恢复。"""
    e = board_engine(
        p0_active=mon(1, conditions=frozenset({SpecialCondition.PARALYZED})),
    )
    e.apply(0, Action(kind="end_turn"))  # p0 = 持有者回合结束
    assert e.state.players[0].active.conditions == frozenset()


def test_check_unified_knockouts_prize_and_promote() -> None:
    """清单5：灼伤指示物致战斗场昏厥——全部检查处理结束后统一判昏厥 + 拿奖赏 +
    换上，换上完成后才进入下一回合。"""
    e = board_engine(
        p1_active=mon(2, pokemon("脆皮", hp=70), damage=50,
                      conditions=frozenset({SpecialCondition.BURNED})),
        p1_bench=(mon(80),),
        seed=1,  # 灼伤掷币反面不影响昏厥（先放指示物后掷币）
    )
    e.apply(0, Action(kind="end_turn"))
    # 昏厥 → p0 拿 1 奖赏 → p1 换上阶段
    assert any(ev.kind == "knockout" for ev in e.events)
    assert any(ev.kind == "take_prize" for ev in e.events)
    assert len(e.state.players[0].prizes) == 5
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    # 换上完成 → 进入 p1 回合（抽牌已发生）
    assert e.state.phase == "main" and e.state.current_player == 1
    assert e.state.players[1].active.current.iid == 80
    assert len(e.state.players[1].hand) == 1  # 回合开始抽 1


def test_check_bench_ko_no_promote() -> None:
    """清单5 边界：备战宝可梦被检查阶段指示物昏厥 → 拿奖赏、无换上，直接开下一回合。"""
    e = board_engine(
        p0_bench=(mon(70, pokemon("脆皮备战", hp=70), damage=60,
                      conditions=frozenset({SpecialCondition.POISONED})),),
    )
    e.apply(0, Action(kind="end_turn"))
    assert e.state.phase == "main" and e.state.current_player == 1
    assert e.state.players[0].bench == ()
    assert len(e.state.players[1].prizes) == 5  # p1 拿 1 奖赏


def test_check_processing_order_deterministic() -> None:
    """清单6：处理顺序 = 回合持有者方先、毒→灼→眠→麻固定序；混乱不在检查阶段结算。"""
    e = board_engine(
        p0_active=mon(1, damage=0, conditions=frozenset({
            SpecialCondition.POISONED, SpecialCondition.BURNED})),
        p0_bench=(
            mon(70, conditions=frozenset({SpecialCondition.ASLEEP})),
            mon(71, conditions=frozenset({SpecialCondition.PARALYZED}),
                paralyzed_mark=(1, 1)),
        ),
        p1_active=mon(2, damage=0, conditions=frozenset({
            SpecialCondition.POISONED, SpecialCondition.CONFUSED})),
        seed=0,  # flips: 灼伤正面恢复 / 睡眠反面保持
    )
    e.apply(0, Action(kind="end_turn"))
    seq = [(ev.player, ev.detail["status"]) for ev in check_events(e)]
    assert seq == [
        (0, "poisoned"), (0, "burned"), (0, "asleep"), (0, "paralyzed"),
        (1, "poisoned"),
    ]
    # 混乱不在检查阶段结算（无 confused 条目、混乱不恢复）
    assert SpecialCondition.CONFUSED in e.state.players[1].active.conditions
    # 灼伤正面恢复、睡眠反面保持、麻痹（持有者回合结束）恢复
    assert e.state.players[0].active.conditions == frozenset({SpecialCondition.POISONED})
    assert e.state.players[0].bench[0].conditions == frozenset({SpecialCondition.ASLEEP})
    assert e.state.players[0].bench[1].conditions == frozenset()
    # 同种子重放一致（事件流逐条一致）
    def trace() -> list:
        e2 = board_engine(
            p0_active=mon(1, damage=0, conditions=frozenset({
                SpecialCondition.POISONED, SpecialCondition.BURNED})),
            p0_bench=(
                mon(70, conditions=frozenset({SpecialCondition.ASLEEP})),
                mon(71, conditions=frozenset({SpecialCondition.PARALYZED}),
                    paralyzed_mark=(1, 1)),
            ),
            p1_active=mon(2, damage=0, conditions=frozenset({
                SpecialCondition.POISONED, SpecialCondition.CONFUSED})),
            seed=0,
        )
        e2.apply(0, Action(kind="end_turn"))
        return [(ev.kind, ev.player, tuple(sorted(ev.detail.items())))
                for ev in e2.events]
    assert trace() == trace()


def test_vocab_wp7_words_registered_and_unknown_rejected() -> None:
    """清单7：词表同步（actions/selectors/events 新词注册）；未知词 DslError 不猜。"""
    v = load_vocabularies()
    for w in ("mill", "discard_stadium", "shuffle_hand_into_deck"):
        assert w in v.actions
    assert "all_pokemon_both" in v.selectors
    assert "pokemon_check" in v.events
    # 新词可解析
    doc = parse_card_doc("""
card:
  name_group: 词表卡
effects:
  - trigger: trigger_on_event
    event: pokemon_check
    actions:
      - {action: mill, selector: opponent_deck, count: 1}
""")
    assert doc.effects[0].event == "pokemon_check"
    # 未知事件词 → DslError
    with pytest.raises(DslError, match="events"):
        parse_card_doc("""
card:
  name_group: 坏卡
effects:
  - trigger: trigger_on_event
    event: bogus_event
    actions:
      - {action: draw, count: 1}
""")


# ── 常驻伤害修正泛化（清单 8-13，D-WP7-3/4）──────────────────────────────

TOOL_MOD_DOC = parse_card_doc("""
card:
  name_group: 测试头带
effects:
  - trigger: passive_static
    actions:
      - {action: modify_damage, args: {amount: 30}}
""")

STADIUM_MOD_DOC = parse_card_doc("""
card:
  name_group: 化朗镇
effects:
  - trigger: passive_static
    condition: holder_owner:赫普
    actions:
      - {action: modify_damage, args: {amount: 30}}
""")

AURA_MOD_DOC = parse_card_doc("""
card:
  name_group: 赫普的卡比兽
effects:
  - trigger: passive_static
    condition: holder_owner:赫普
    actions:
      - {action: modify_damage, args: {amount: 30, scope: own_field}}
""")

KARATE_DOC = parse_card_doc("""
card:
  name_group: 空手道王的修炼
effects:
  - trigger: on_play
    actions:
      - {action: modify_damage, args: {amount: 40, target_rule_box: ex}}
""")


def test_damage_modifier_tool_source_regression() -> None:
    """清单8：道具来源既有口径回归（挂载面重构不回归）——无条件 +30。"""
    tool = inst(88, tool_card("测试头带"))
    e = board_engine(
        p0_active=mon(1, energies=1, tool=tool),
        effects={"测试头带": TOOL_MOD_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50  # 20 + 30


def test_damage_modifier_stadium_source() -> None:
    """清单9：竞技场来源——化朗镇在场双方「赫普的宝可梦」+30；非赫普不加；
    竞技场离场即失效；备战落点不加。"""
    stadium = inst(399, stadium_card("化朗镇"))
    fx = {"化朗镇": STADIUM_MOD_DOC}
    hop_mon = pokemon("赫普的兽", owner="赫普")
    # 赫普宝可梦 +30
    e = board_engine(p0_active=mon(1, hop_mon, energies=1),
                     stadium=stadium, stadium_owner=1, effects=fx)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50
    # 非赫普宝可梦不加
    e = board_engine(p0_active=mon(1, pokemon("普通兽"), energies=1),
                     stadium=stadium, stadium_owner=1, effects=fx)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
    # 竞技场离场（不在场）即失效
    e = board_engine(p0_active=mon(1, hop_mon, energies=1), effects=fx)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
    # 备战落点不加（DSL damage 选备战目标）
    bench_doc = parse_card_doc("""
card:
  name_group: 扫场兽
effects:
  - trigger: on_attack
    attack: 扫场
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 20}}
""")
    sweeper = pokemon("扫场兽", owner="赫普", attacks=(
        AttackDef(name="扫场", cost=("无",), damage=None),))
    e = board_engine(
        p0_active=mon(1, sweeper, energies=1),
        p1_bench=(mon(80),),
        stadium=stadium, stadium_owner=1,
        effects={**fx, "扫场兽": bench_doc},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 20  # 备战落点无修正


def test_damage_modifier_aura_dedup_same_name() -> None:
    """清单10：宝可梦 aura（scope=own_field）——卡比兽在场自己赫普宝可梦（含自身）
    +30；两只同名卡比兽去重只加一次；离场即失效；非赫普不加。"""
    snorlax = pokemon("赫普的卡比兽", owner="赫普", has_ability=True)
    fx = {"赫普的卡比兽": AURA_MOD_DOC}
    # 单只卡比兽备战：赫普攻击者 +30
    e = board_engine(
        p0_active=mon(1, pokemon("赫普的兽", owner="赫普"), energies=1),
        p0_bench=(mon(70, snorlax),), effects=fx,
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50
    # 两只同名卡比兽：去重仍只 +30
    e = board_engine(
        p0_active=mon(1, pokemon("赫普的兽", owner="赫普"), energies=1),
        p0_bench=(mon(70, snorlax), mon(71, snorlax)), effects=fx,
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50
    # 卡比兽自身攻击（含自身）也 +30
    e = board_engine(p0_active=mon(1, snorlax, energies=1), effects=fx)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50
    # 卡比兽不在场 → 不加
    e = board_engine(
        p0_active=mon(1, pokemon("赫普的兽", owner="赫普"), energies=1), effects=fx,
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
    # 非赫普攻击者：卡比兽在场也不加
    e = board_engine(
        p0_active=mon(1, pokemon("普通兽"), energies=1),
        p0_bench=(mon(70, snorlax),), effects=fx,
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20


def test_damage_modifier_turn_marker_and_clear() -> None:
    """清单11：回合级标记——空手道王打出后本回合对对手战斗场 ex +40、
    对非 ex 不加；回合结束清除（下回合不加）。"""
    fx = {"空手道王的修炼": KARATE_DOC}
    hand = (inst(60, supporter_card("空手道王的修炼")),)
    # 对 ex +40
    e = board_engine(p0_active=mon(1, energies=1),
                     p1_active=mon(2, pokemon("大王ex", rule_box="ex")),
                     p0_extra_hand=hand, effects=fx)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.players[0].turn_damage_mods == ((40, "ex"),)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 60  # 20 + 40
    # 对非 ex 不加
    e = board_engine(p0_active=mon(1, energies=1), p0_extra_hand=hand, effects=fx)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20
    # 回合结束清除：下回合不加
    e = board_engine(p0_active=mon(1, energies=1),
                     p1_active=mon(2, pokemon("大王ex", rule_box="ex")),
                     p0_extra_hand=hand, effects=fx)
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[0].turn_damage_mods == ()
    e.apply(1, Action(kind="end_turn"))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20


def test_damage_modifier_sources_stack() -> None:
    """清单11：多来源求和叠加——道具 30 + 竞技场 30 + aura 30 + 回合标记 40 = +130。"""
    tool = inst(88, tool_card("测试头带"))
    stadium = inst(399, stadium_card("化朗镇"))
    snorlax = pokemon("赫普的卡比兽", owner="赫普", has_ability=True)
    fx = {
        "测试头带": TOOL_MOD_DOC, "化朗镇": STADIUM_MOD_DOC,
        "赫普的卡比兽": AURA_MOD_DOC, "空手道王的修炼": KARATE_DOC,
    }
    e = board_engine(
        p0_active=mon(1, pokemon("赫普的兽", owner="赫普"), energies=1, tool=tool),
        p0_bench=(mon(70, snorlax),),
        p1_active=mon(2, pokemon("大王ex", rule_box="ex", hp=500)),
        p0_extra_hand=(inst(60, supporter_card("空手道王的修炼")),),
        stadium=stadium, stadium_owner=1, effects=fx,
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 150  # 20 + 30×3 + 40


def test_holder_owner_condition_and_target_rule_box() -> None:
    """清单12：holder_owner:X 条件词注册（读 CardDef.owner）；target_rule_box
    求值点校验（道具声明带 target_rule_box 时按防守方规则盒过滤）；未知条件 DslError。"""
    from battlefrontier.dsl.chooser import condition_met
    e = board_engine()
    hop = mon(1, pokemon("赫普的兽", owner="赫普"))
    other = mon(2, pokemon("普通兽"))
    assert condition_met("holder_owner:赫普", e, 0, hop) is True
    assert condition_met("holder_owner:赫普", e, 0, other) is False
    assert condition_met("holder_owner:赫普", e, 0, None) is False
    with pytest.raises(DslError, match="condition"):
        condition_met("holder_owner_x", e, 0, hop)
    # 道具声明带 target_rule_box：对 ex 生效、对非 ex 不生效
    tool_ex_doc = parse_card_doc("""
card:
  name_group: 斩ex刃
effects:
  - trigger: passive_static
    actions:
      - {action: modify_damage, args: {amount: 50, target_rule_box: ex}}
""")
    tool = inst(88, tool_card("斩ex刃"))
    e = board_engine(
        p0_active=mon(1, energies=1, tool=tool),
        p1_active=mon(2, pokemon("大王ex", rule_box="ex", hp=500)),
        effects={"斩ex刃": tool_ex_doc},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 70  # 20 + 50
    e = board_engine(p0_active=mon(1, energies=1, tool=tool),
                     effects={"斩ex刃": tool_ex_doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20  # 非 ex 不加
    # 未知 condition（竞技场声明）→ 攻击求值点 DslError 不猜
    bad_stadium = parse_card_doc("""
card:
  name_group: 坏镇
effects:
  - trigger: passive_static
    condition: bogus_condition
    actions:
      - {action: modify_damage, args: {amount: 30}}
""")
    e = board_engine(
        p0_active=mon(1, energies=1),
        stadium=inst(399, stadium_card("坏镇")), stadium_owner=0,
        effects={"坏镇": bad_stadium},
    )
    with pytest.raises(DslError, match="condition"):
        e.apply(0, Action(kind="attack", attack_index=0))
    # aura scope 未知 → DslError（不猜）
    bad_aura = parse_card_doc("""
card:
  name_group: 坏光环
effects:
  - trigger: passive_static
    actions:
      - {action: modify_damage, args: {amount: 30, scope: everywhere}}
""")
    e = board_engine(
        p0_active=mon(1, energies=1),
        p0_bench=(mon(70, pokemon("坏光环")),),
        effects={"坏光环": bad_aura},
    )
    with pytest.raises(DslError, match="scope"):
        e.apply(0, Action(kind="attack", attack_index=0))
    # on_play 回合标记参数校验：缺 amount / 带 scope → DslError
    bad_sup = parse_card_doc("""
card:
  name_group: 坏支援
effects:
  - trigger: on_play
    actions:
      - {action: modify_damage, args: {amount: 40, scope: own_field}}
""")
    e = board_engine(
        p0_extra_hand=(inst(60, supporter_card("坏支援")),),
        effects={"坏支援": bad_sup},
    )
    with pytest.raises(DslError, match="scope"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_attack_cost_tool_branch() -> None:
    """清单13：费用读道具——讲究头带持有者（赫普）招式费用 -1【无】（clamp ≥0）；
    非赫普持有者不减；道具离场即失效。"""
    band_doc = parse_card_doc("""
card:
  name_group: 赫普的讲究头带
effects:
  - trigger: passive_static
    condition: holder_owner:赫普
    actions:
      - {action: modify_attack_cost, args: {value: 1}}
""")
    fx = {"赫普的讲究头带": band_doc}
    heavy = pokemon("赫普的重兽", owner="赫普", cost=2)
    # 持有者赫普：2【无】→ 1【无】，1 能量可攻
    tool = inst(88, tool_card("赫普的讲究头带"))
    e = board_engine(p0_active=mon(1, heavy, energies=1, tool=tool), effects=fx)
    assert e._effective_attack_cost(e.state.players[0].active, 0, heavy.attacks[0]) == ("无",)
    assert "attack" in {a.kind for a in e.legal_actions(0)}
    # 非赫普持有者不减：1 能量不可攻
    plain = pokemon("普通重兽", cost=2)
    e = board_engine(p0_active=mon(1, plain, energies=1, tool=tool), effects=fx)
    assert e._effective_attack_cost(e.state.players[0].active, 0, plain.attacks[0]) == ("无", "无")
    assert "attack" not in {a.kind for a in e.legal_actions(0)}
    # 道具离场即失效
    e = board_engine(p0_active=mon(1, heavy, energies=1), effects=fx)
    assert e._effective_attack_cost(e.state.players[0].active, 0, heavy.attacks[0]) == ("无", "无")
    # clamp ≥0：1【无】费用减 1 → 0
    light = pokemon("赫普的轻兽", owner="赫普", cost=1)
    e = board_engine(p0_active=mon(1, light, energies=0, tool=tool), effects=fx)
    assert e._effective_attack_cost(e.state.players[0].active, 0, light.attacks[0]) == ()
    assert "attack" in {a.kind for a in e.legal_actions(0)}


# ── protection 备战伤害免疫（清单 14-15，D-WP7-5）─────────────────────────

SHAYMIN_DOC = parse_card_doc("""
card:
  name_group: 谢米
effects:
  - trigger: passive_static
    actions:
      - {action: protection, args: {scope: opponent_attack_damage_to_bench, target_filters: [no_rule_box]}}
""")

SWEEP_DOC = parse_card_doc("""
card:
  name_group: 扫场兽
effects:
  - trigger: on_attack
    attack: 扫场
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 50}}
""")


def sweep_engine(**kw) -> GameEngine:
    sweeper = pokemon("扫场兽", attacks=(AttackDef(name="扫场", cost=("无",), damage=None),))
    effects = {"扫场兽": SWEEP_DOC, "谢米": SHAYMIN_DOC}
    return board_engine(
        p0_active=mon(1, sweeper, energies=1),
        p1_active=mon(2, pokemon("战斗兽")),
        p1_bench=(
            mon(80, pokemon("草苗")),                    # 无规则盒 → 受保护
            mon(81, pokemon("大草ex", rule_box="ex")),   # 规则盒 → 不保护
            mon(82, pokemon("谢米", has_ability=True)),  # 保护来源
        ),
        effects=effects, **kw,
    )


def test_protection_bench_damage_scope() -> None:
    """清单14：谢米在场——对手招式对自己备战宝可梦（除规则盒）伤害归零；
    战斗场不保护；规则盒备战不保护；谢米离场即失效；非招式来源不保护。"""
    # 备战无规则盒目标：伤害归零
    e = sweep_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 0
    assert prim_results(e, "damage")[0]["protected"] is True
    # 规则盒备战目标：不保护
    e = sweep_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(81,)))
    assert e.state.players[1].bench[1].damage == 50
    # 战斗场目标：不保护（仅备战面）
    e = sweep_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[1].active.damage == 50
    # 谢米离场（不在场）即失效
    sweeper = pokemon("扫场兽", attacks=(AttackDef(name="扫场", cost=("无",), damage=None),))
    e = board_engine(
        p0_active=mon(1, sweeper, energies=1),
        p1_bench=(mon(80, pokemon("草苗")),),
        effects={"扫场兽": SWEEP_DOC, "谢米": SHAYMIN_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 50
    # 训练家卡（非招式）伤害不受此 scope 保护
    item_doc = parse_card_doc("""
card:
  name_group: 飞刀
effects:
  - trigger: on_play
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 50}}
""")
    e = board_engine(
        p0_extra_hand=(inst(60, item_card("飞刀")),),
        p1_bench=(mon(80, pokemon("草苗")), mon(82, pokemon("谢米", has_ability=True))),
        effects={"飞刀": item_doc, "谢米": SHAYMIN_DOC},
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 50


def test_protection_scope_does_not_block_counters() -> None:
    """清单14：指示物放置不是伤害、不受 opponent_attack_damage_to_bench 保护
    （与 D-WP6-7 效果免疫各管各的）。"""
    counter_doc = parse_card_doc("""
card:
  name_group: 撒菱兽
effects:
  - trigger: on_attack
    attack: 撒菱
    actions:
      - {action: place_damage_counters, selector: opponent_bench, choose: 1, args: {counters: 3}}
""")
    spiker = pokemon("撒菱兽", attacks=(AttackDef(name="撒菱", cost=("无",), damage=None),))
    e = board_engine(
        p0_active=mon(1, spiker, energies=1),
        p1_bench=(mon(80, pokemon("草苗")), mon(82, pokemon("谢米", has_ability=True))),
        effects={"撒菱兽": counter_doc, "谢米": SHAYMIN_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 30  # 指示物照常


def test_no_rule_box_in_play_filter() -> None:
    """清单15：no_rule_box 场上过滤器注册；未知场上过滤词 DslError。"""
    p = board_engine().state.players[0]
    p = p.model_copy(update={
        "bench": (
            mon(70, pokemon("草苗")),
            mon(71, pokemon("大草ex", rule_box="ex")),
        ),
    })
    pool = resolve_in_play_pool(p, ("no_rule_box",))
    assert [m.current.iid for m in pool] == [1, 70]
    with pytest.raises(DslError, match="filter"):
        resolve_in_play_pool(p, ("bogus_filter",))


# ── 小原语（清单 16-20，D-WP7-6~10）─────────────────────────────────────


def test_discard_stadium() -> None:
    """清单16：discard_stadium——公共场弃入其持有者弃牌区 + 状态清理；无竞技场 no-op。"""
    doc = parse_card_doc("""
card:
  name_group: 拆场锤
effects:
  - trigger: on_play
    actions:
      - {action: discard_stadium}
""")
    stadium = inst(399, stadium_card("老竞技场"))
    e = board_engine(
        p0_extra_hand=(inst(60, item_card("拆场锤")),),
        stadium=stadium, stadium_owner=1, effects={"拆场锤": doc},
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.stadium is None and e.state.stadium_owner is None
    assert 399 in [c.iid for c in e.state.players[1].discard]  # 入持有者弃牌区
    assert prim_results(e, "discard_stadium")[0]["discarded"] == "老竞技场"
    # 无竞技场 no-op
    e = board_engine(p0_extra_hand=(inst(60, item_card("拆场锤")),),
                     effects={"拆场锤": doc})
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert prim_results(e, "discard_stadium")[0]["discarded"] is None
    # 带 selector → DslError（不猜）
    bad = parse_card_doc("""
card:
  name_group: 坏锤
effects:
  - trigger: on_play
    actions:
      - {action: discard_stadium, selector: self}
""")
    e = board_engine(p0_extra_hand=(inst(60, item_card("坏锤")),),
                     effects={"坏锤": bad})
    with pytest.raises(DslError, match="discard_stadium"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_own_ko_by_attack_during_opponent_turn_marker() -> None:
    """清单17：古玉鱼精确标记——对手回合自己宝可梦因招式伤害昏厥 → 置位；
    效果/指示物致昏厥不置位；自己回合结束清除；宽口径标记不受影响。"""
    # 招式伤害昏厥 → 置位
    e = board_engine(
        p0_active=mon(1, energies=1),
        p1_active=mon(2, pokemon("脆皮", hp=20)),
        p1_bench=(mon(80),),
    )
    e.apply(0, Action(kind="attack", attack_index=0))  # 白板 20 → 昏厥
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    p1 = e.state.players[1]
    assert p1.own_ko_by_attack_during_opponent_turn is True   # 精确口径
    assert p1.own_ko_during_opponent_turn is True             # 宽口径不动
    # 持有者回合结束清除
    e.apply(1, Action(kind="end_turn"))
    assert e.state.players[1].own_ko_by_attack_during_opponent_turn is False
    # 指示物致昏厥 → 不置位
    counter_doc = parse_card_doc("""
card:
  name_group: 炸弹
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 2}}
""")
    e = board_engine(
        p0_extra_hand=(inst(60, item_card("炸弹")),),
        p1_active=mon(2, pokemon("脆皮", hp=20)),
        p1_bench=(mon(80),),
        effects={"炸弹": counter_doc},
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.phase == "promote"
    e.apply(1, Action(kind="promote", bench_index=0))
    p1 = e.state.players[1]
    assert p1.own_ko_by_attack_during_opponent_turn is False  # 非招式伤害不置位
    assert p1.own_ko_during_opponent_turn is True             # 宽口径置位（既有口径）


def test_own_ko_by_attack_marker_bench_snipe_ko() -> None:
    """清单17 扩（F1 复核返工）：备战区被对手招式伤害狙击昏厥 → 同样置位
    （卡面「自己的宝可梦【昏厥】」无战斗场限定）；备战指示物致昏厥仍不置位
    （place_damage_counters 不是「招式的伤害」，rules-manual §6）。"""
    snipe_doc = parse_card_doc("""
card:
  name_group: 狙击兽
effects:
  - trigger: on_attack
    attack: 狙击
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 50}}
""")
    sniper = pokemon("狙击兽", attacks=(AttackDef(name="狙击", cost=("无",), damage=None),))
    # 备战狙击伤害致昏厥 → 置位
    e = board_engine(
        p0_active=mon(1, sniper, energies=1),
        p1_bench=(mon(80, pokemon("脆皮备战", hp=30)),),
        effects={"狙击兽": snipe_doc},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench == ()  # 备战昏厥离场
    assert e.state.players[1].own_ko_by_attack_during_opponent_turn is True
    assert e.state.players[1].own_ko_during_opponent_turn is True  # 宽口径同样置位
    # 备战指示物致昏厥（招式附加效果，非「招式的伤害」）→ 不置位
    needle_doc = parse_card_doc("""
card:
  name_group: 针雨兽
effects:
  - trigger: on_attack
    attack: 针雨
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 3}}
""")
    needler = pokemon("针雨兽", attacks=(AttackDef(name="针雨", cost=("无",), damage=None),))
    e = board_engine(
        p0_active=mon(1, needler, energies=1),
        p1_bench=(mon(80, pokemon("脆皮备战", hp=30)),),
        effects={"针雨兽": needle_doc},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench == ()
    assert e.state.players[1].own_ko_by_attack_during_opponent_turn is False
    assert e.state.players[1].own_ko_during_opponent_turn is True  # 宽口径置位（既有）


def test_node_condition_if_own_ko_by_attack() -> None:
    """清单17：节点级 condition if_own_ko_by_attack_during_opponent_turn——
    未置位跳过追加伤害节点（基准照打），置位时追加。"""
    doc = parse_card_doc("""
card:
  name_group: 古玉鱼
effects:
  - trigger: on_attack
    attack: 嫉妒业火
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 50}}
      - {action: damage, selector: opponent_active, args: {amount: 90}, condition: if_own_ko_by_attack_during_opponent_turn}
""")
    fish = pokemon("古玉鱼", attacks=(AttackDef(name="嫉妒业火", cost=("无",), damage=None),))
    # 未置位：只打基准 50，追加节点 skipped
    e = board_engine(p0_active=mon(1, fish, energies=1), effects={"古玉鱼": doc})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50
    skipped = [ev for ev in e.events
               if ev.kind == "effect_primitive"
               and ev.detail.get("result", {}).get("skipped") is True]
    assert len(skipped) == 1
    # 置位（上一对手回合自己宝可梦被招式昏厥）：50 + 90
    e = board_engine(p0_active=mon(1, fish, energies=1), effects={"古玉鱼": doc})
    p0 = e.state.players[0].model_copy(update={
        "own_ko_by_attack_during_opponent_turn": True,
    })
    e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 140


ATTACH_DECK_DOC = parse_card_doc("""
card:
  name_group: 测试附能
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_deck, choose: 3, destination: attach, filters: [basic_energy, energy_火]}
""")


def fire_deck() -> tuple:
    return (
        inst(100, energy("基本火能量", "火")),
        inst(101, energy("基本火能量", "火")),
        inst(102, energy("基本火能量", "火")),
        inst(103, basic("填充兽")),
        inst(104, basic("填充兽")),
    )


def test_attach_energy_own_deck_free_distribution() -> None:
    """清单18：牌库来源附着——up-to 3（min 0）、目标自己场上宝可梦任意分配
    （可全给 1 只）、结算后重洗；选 0 仅重洗；牌库无匹配仅重洗不挂起。"""
    fx = {"测试附能": ATTACH_DECK_DOC}
    deck = fire_deck()
    # 选 2 张全给战斗场（任意分配：每张一次目标选择）
    e = board_engine(
        p0_extra_hand=(inst(60, item_card("测试附能")),),
        p0_deck=deck, effects=fx, seed=0,
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    pc = e.state.pending_choice
    assert pc.pool == "own_deck" and pc.min_choose == 0 and pc.max_choose == 3
    assert set(pc.pool_iids) == {100, 101, 102}  # 仅基本火能量进池
    e.apply(0, Action(kind="choose", choices=(100, 101)))
    assert e.state.pending_choice.pool == "own_pokemon_in_play"
    e.apply(0, Action(kind="choose", choices=(1,)))  # 第 1 张给战斗场
    e.apply(0, Action(kind="choose", choices=(1,)))  # 第 2 张仍给战斗场
    p0 = e.state.players[0]
    assert [c.iid for c in p0.active.attached_energy] == [100, 101]
    # 结算后重洗：剩余 = shuffle(原牌库) 剔除已附着（保序）
    expected = tuple(c for c in RandomSource(0).shuffle(deck) if c.iid not in (100, 101))
    assert p0.deck == expected
    assert e.state.phase == "main"  # 物品完成回主阶段
    # 选 0：仅重洗，不进目标选择
    e = board_engine(
        p0_extra_hand=(inst(60, item_card("测试附能")),),
        p0_deck=deck, effects=fx, seed=0,
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert p0.deck == RandomSource(0).shuffle(deck)
    assert p0.active.attached_energy == ()
    assert e.state.phase == "main"
    # 牌库无匹配：不挂起，仅重洗
    plain_deck = tuple(inst(110 + i, basic("填充兽")) for i in range(4))
    e = board_engine(
        p0_extra_hand=(inst(60, item_card("测试附能")),),
        p0_deck=plain_deck, effects=fx, seed=0,
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert prim_results(e, "attach_energy")[0]["attached"] == 0
    assert e.state.players[0].deck == RandomSource(0).shuffle(plain_deck)
    # multi_target 与 own_deck 组合 → DslError（语义冲突不猜）
    bad = parse_card_doc("""
card:
  name_group: 坏附能
effects:
  - trigger: on_play
    actions:
      - {action: attach_energy, selector: own_deck, choose: 2, destination: attach, args: {multi_target: true}}
""")
    e = board_engine(p0_extra_hand=(inst(60, item_card("坏附能")),),
                     effects={"坏附能": bad})
    with pytest.raises(DslError, match="own_deck"):
        e.apply(0, Action(kind="play_trainer", iid=60))


JUDGE_DOC = parse_card_doc("""
card:
  name_group: 裁判
effects:
  - trigger: on_play
    actions:
      - {action: shuffle_hand_into_deck, selector: own_hand}
      - {action: shuffle_hand_into_deck, selector: opponent_hand}
      - {action: draw, count: 4}
      - {action: draw, selector: opponent_deck, count: 4}
""")


def test_shuffle_hand_into_deck_both_and_draw() -> None:
    """清单19：裁判全流——双方手牌各回库重洗 + 各抽 4；手牌空照常抽 4；种子确定性。"""
    p0_hand_extra = (inst(61, basic("手牌兽A")), inst(62, basic("手牌兽B")))
    p1_hand = (inst(70, basic("对手手牌A")),)
    fx = {"裁判": JUDGE_DOC}
    e = board_engine(
        p0_extra_hand=(inst(60, supporter_card("裁判")),) + p0_hand_extra,
        p1_hand=p1_hand, effects=fx, seed=0,
    )
    # 打出前：p0 手牌 = 主状态 2 + 3 = 5（裁判打出后剩 4 回库），p1 手牌 1
    e.apply(0, Action(kind="play_trainer", iid=60))
    p0, p1 = e.state.players
    assert len(p0.hand) == 4 and len(p1.hand) == 4
    assert len(p0.deck) == 10 + 4 - 4  # 回库 4（裁判已离手）再抽 4
    assert len(p1.deck) == 10 + 1 - 4
    assert 61 not in [c.iid for c in p0.hand]  # 旧手牌已回库
    # 手牌空照常抽 4
    e = board_engine(
        p0_extra_hand=(inst(60, supporter_card("裁判")),),
        p1_hand=(), effects=fx, seed=0,
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert len(e.state.players[1].hand) == 4
    # 种子确定性：同种子两次运行手牌/牌库序列一致
    def run_once():
        e2 = board_engine(
            p0_extra_hand=(inst(60, supporter_card("裁判")),) + p0_hand_extra,
            p1_hand=p1_hand, effects=fx, seed=3,
        )
        e2.apply(0, Action(kind="play_trainer", iid=60))
        return (
            [c.iid for c in e2.state.players[0].hand],
            [c.iid for c in e2.state.players[0].deck],
            [c.iid for c in e2.state.players[1].hand],
        )
    assert run_once() == run_once()
    # 非法 selector → DslError
    bad = parse_card_doc("""
card:
  name_group: 坏洗牌
effects:
  - trigger: on_play
    actions:
      - {action: shuffle_hand_into_deck, selector: own_deck}
""")
    e = board_engine(p0_extra_hand=(inst(60, item_card("坏洗牌")),),
                     effects={"坏洗牌": bad})
    with pytest.raises(DslError, match="shuffle_hand_into_deck"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_place_damage_counters_own_active() -> None:
    """清单20①：own_active（惊吓炸弹反面）——自己战斗场放 N 指示物，无 choose。"""
    doc = parse_card_doc("""
card:
  name_group: 自炸弹
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: own_active, args: {counters: 2}}
""")
    e = board_engine(p0_extra_hand=(inst(60, item_card("自炸弹")),),
                     effects={"自炸弹": doc})
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.players[0].active.damage == 20
    assert prim_results(e, "place_damage_counters")[0]["placed"] == 1
    # own_active 带 choose → DslError
    bad = parse_card_doc("""
card:
  name_group: 坏炸弹
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: own_active, choose: 1, args: {counters: 1}}
""")
    e = board_engine(p0_extra_hand=(inst(60, item_card("坏炸弹")),),
                     effects={"坏炸弹": bad})
    with pytest.raises(DslError, match="own_active"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_place_damage_counters_all_pokemon_both() -> None:
    """清单20①：all_pokemon_both + filters 收敛目标池（双方全场，无 choose）。"""
    doc = parse_card_doc("""
card:
  name_group: 撒钉
effects:
  - trigger: on_play
    actions:
      - {action: place_damage_counters, selector: all_pokemon_both, filters: [basic_pokemon], args: {counters: 1}}
""")
    e = board_engine(
        p0_bench=(mon(70),),
        p1_bench=(mon(80),
                  InPlayPokemon(stack=(inst(81, basic("底兽")),
                                       inst(82, stage1("顶兽", "底兽", hp=200))))),
        p0_extra_hand=(inst(60, item_card("撒钉")),),
        effects={"撒钉": doc},
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.players[0].active.damage == 10
    assert e.state.players[0].bench[0].damage == 10
    assert e.state.players[1].active.damage == 10
    assert e.state.players[1].bench[0].damage == 10
    assert e.state.players[1].bench[1].damage == 0  # 进化体被过滤器排除
    assert prim_results(e, "place_damage_counters")[0]["placed"] == 4


def test_damage_self_fixed_no_modifiers() -> None:
    """清单20②：damage self——固定值直接放置，不吃弱点/抗性/增伤修正；
    致昏厥走正常 check_knockouts。"""
    doc = parse_card_doc("""
card:
  name_group: 爬地翅
effects:
  - trigger: on_attack
    attack: 烫伤怒涛
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 120}}
      - {action: damage, selector: self, args: {amount: 90}}
""")
    wing = pokemon("爬地翅", hp=200, energy_type="火", weakness="火",
                   resistance="火", attacks=(
                       AttackDef(name="烫伤怒涛", cost=("无",), damage=None),))
    tool = inst(88, tool_card("测试头带"))  # +30 增伤道具
    fx = {"爬地翅": doc, "测试头带": TOOL_MOD_DOC}
    e = board_engine(p0_active=mon(1, wing, energies=1, tool=tool), effects=fx)
    e.apply(0, Action(kind="attack", attack_index=0))
    # 自伤固定 90：不吃自身弱点/抗性、不吃道具增伤
    assert e.state.players[0].active.damage == 90
    # 对手战斗场 120 + 道具 30 = 150（增伤仅作用对对手战斗场落点）
    assert e.state.players[1].active.damage == 150
    self_results = [r for r in prim_results(e, "damage") if r.get("target_iid") == 1]
    assert self_results[0]["final"] == 90
    # 自伤致昏厥 → 正常昏厥结算（对手拿奖赏 + 我方换上 → 回合推进）
    frail = pokemon("脆皮翅", hp=90, attacks=(
        AttackDef(name="烫伤怒涛", cost=("无",), damage=None),))
    e = board_engine(
        p0_active=mon(1, frail, energies=1),
        p0_bench=(mon(70),),
        effects={"脆皮翅": doc, "爬地翅": doc},
    )
    e.card_effects = {"脆皮翅": doc}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "promote" and e.state.current_player == 0
    assert len(e.state.players[1].prizes) == 5  # 对手拿 1 奖赏
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 1
    # damage self 用 count 计数词 → DslError（固定值形式以外不猜）
    bad = parse_card_doc("""
card:
  name_group: 坏自伤
effects:
  - trigger: on_attack
    attack: 坏招
    actions:
      - {action: damage, selector: self, count: own_remaining_prizes, args: {per: 10, op: "×"}}
""")
    e = board_engine(p0_active=mon(1, energies=1), effects={"兽1": bad})
    src = e.state.players[0].active.current
    with pytest.raises(DslError, match="amount"):
        run_doc(e, bad, src)


def test_heal_all_pokemon_both() -> None:
    """清单20③：heal all_pokemon_both（野餐篮）——双方全场各恢复 30，
    无 choose，满血 no-op 照常。"""
    doc = parse_card_doc("""
card:
  name_group: 野餐篮
effects:
  - trigger: on_play
    actions:
      - {action: heal, selector: all_pokemon_both, args: {amount: 30}}
""")
    e = board_engine(
        p0_active=mon(1, damage=50),
        p0_bench=(mon(70, damage=30),),
        p1_active=mon(2, damage=10),
        p1_bench=(mon(80, damage=0),),
        p0_extra_hand=(inst(60, item_card("野餐篮")),),
        effects={"野餐篮": doc},
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.players[0].active.damage == 20
    assert e.state.players[0].bench[0].damage == 0
    assert e.state.players[1].active.damage == 0
    assert e.state.players[1].bench[0].damage == 0  # 满血 no-op
    result = prim_results(e, "heal")[0]
    assert result["healed"] == 70  # 30+30+10+0
    # 未知 selector 仍 DslError（回归）
    bad = parse_card_doc("""
card:
  name_group: 坏恢复
effects:
  - trigger: on_play
    actions:
      - {action: heal, selector: opponent_hand, args: {amount: 30}}
""")
    e = board_engine(p0_extra_hand=(inst(60, item_card("坏恢复")),),
                     effects={"坏恢复": bad})
    with pytest.raises(DslError, match="heal"):
        e.apply(0, Action(kind="play_trainer", iid=60))


def test_mill() -> None:
    """清单20④：mill——对手牌库顶 N 张 → 对手弃牌区；牌库不足收缩；空库 no-op。"""
    doc = parse_card_doc("""
card:
  name_group: 磨牌虫
effects:
  - trigger: on_play
    actions:
      - {action: mill, selector: opponent_deck, count: 2}
""")
    p1_deck = tuple(inst(300 + i, basic(f"库{i}")) for i in range(5))
    e = board_engine(
        p0_extra_hand=(inst(60, item_card("磨牌虫")),),
        p1_deck=p1_deck, effects={"磨牌虫": doc},
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    p1 = e.state.players[1]
    assert [c.iid for c in p1.deck] == [302, 303, 304]
    assert [c.iid for c in p1.discard] == [300, 301]  # 顶 → 弃牌区保序
    assert prim_results(e, "mill")[0]["milled"] == 2
    # 牌库不足收缩
    short = tuple(inst(300 + i, basic(f"库{i}")) for i in range(3))
    big = parse_card_doc("""
card:
  name_group: 大磨牌
effects:
  - trigger: on_play
    actions:
      - {action: mill, selector: opponent_deck, count: 10}
""")
    e = board_engine(p0_extra_hand=(inst(60, item_card("大磨牌")),),
                     p1_deck=short, effects={"大磨牌": big})
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert len(e.state.players[1].deck) == 0
    assert len(e.state.players[1].discard) == 3
    assert e.state.phase == "main"  # 牌库空不判负（判负只在回合开始抽牌）
    # 空库 no-op
    e = board_engine(p0_extra_hand=(inst(60, item_card("磨牌虫")),),
                     p1_deck=(), effects={"磨牌虫": doc})
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert prim_results(e, "mill")[0]["milled"] == 0
    # 非法 selector / count → DslError
    bad = parse_card_doc("""
card:
  name_group: 坏磨牌
effects:
  - trigger: on_play
    actions:
      - {action: mill, selector: own_deck, count: 2}
""")
    e = board_engine(p0_extra_hand=(inst(60, item_card("坏磨牌")),),
                     effects={"坏磨牌": bad})
    with pytest.raises(DslError, match="mill"):
        e.apply(0, Action(kind="play_trainer", iid=60))


# ── 雪妖女 冻结帷幕（清单 23，D-WP7-11）───────────────────────────────────

FROSLASS_DOC = parse_card_doc("""
card:
  name_group: 雪妖女
effects:
  - trigger: trigger_on_event
    event: pokemon_check
    actions:
      - {action: place_damage_counters, selector: all_pokemon_both, filters: [has_ability, not_name:雪妖女], args: {counters: 1}}
""")


def froslass(iid: int) -> InPlayPokemon:
    return mon(iid, pokemon("雪妖女", has_ability=True))


def test_froslass_pokemon_check_trigger() -> None:
    """清单23：每次宝可梦检查，双方所有拥有特性的宝可梦（除雪妖女）各放 1 指示物；
    无特性宝可梦不放；多只雪妖女各触发；雪妖女离场不触发。"""
    fx = {"雪妖女": FROSLASS_DOC}
    e = board_engine(
        p0_active=mon(1, pokemon("超能兽", has_ability=True)),
        p0_bench=(froslass(70),),
        p1_active=mon(2, pokemon("能力兽", has_ability=True)),
        p1_bench=(mon(80, pokemon("白板兽")),),
        effects=fx,
    )
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[0].active.damage == 10   # 有特性 → 放
    assert e.state.players[1].active.damage == 10
    assert e.state.players[1].bench[0].damage == 0  # 无特性 → 不放
    assert e.state.players[0].bench[0].damage == 0  # 雪妖女自身（not_name）不放
    triggers = [ev for ev in e.events
                if ev.kind == "trigger_on_event" and ev.detail.get("event") == "pokemon_check"]
    assert len(triggers) == 1
    # 双方回合结束均触发：p1 回合结束再放一轮
    e.apply(1, Action(kind="end_turn"))
    assert e.state.players[0].active.damage == 20
    # 多只雪妖女各触发各结算（无同名锁）
    e = board_engine(
        p0_active=mon(1, pokemon("超能兽", has_ability=True)),
        p0_bench=(froslass(70),),
        p1_bench=(froslass(80),),
        effects=fx,
    )
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[0].active.damage == 20  # 两只雪妖女各放 1
    triggers = [ev for ev in e.events
                if ev.kind == "trigger_on_event" and ev.detail.get("event") == "pokemon_check"]
    assert len(triggers) == 2
    assert e.state.players[1].bench[0].damage == 0  # 对手雪妖女也不被放
    # 雪妖女离场（不在场）不触发
    e = board_engine(p0_active=mon(1, pokemon("超能兽", has_ability=True)), effects=fx)
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[0].active.damage == 0


def test_has_ability_pipeline_and_filters() -> None:
    """清单23：CardDef.has_ability ← db abilities 非空（WP1 管道路径）；
    has_ability / not_name:X 场上过滤器注册。"""
    from battlefrontier.data.cards import carddef_from_db

    class FakeCard:
        card_id = "FAKE-300"
        name_full = "桩兽"
        card_type = "pokemon"
        hp = 100
        stage = "基础"
        types = ("超",)
        weakness = None
        resistance = None
        retreat_cost = 0
        attacks = ()
        rule_box_type = None
        prize_cards = 1
        trainer_subtype = None
        is_ace_spec = False
        provides = None
        evolves_from_text = None
        evolution_chain_id = None
        is_tera = False
        owner = None
        effect_tags = None
        abilities: ClassVar = [{"name": "冻结帷幕", "text": "..."}]

    card, _ = carddef_from_db(FakeCard())
    assert card.has_ability is True

    class FakeNoAbility(FakeCard):
        abilities = None

    card, _ = carddef_from_db(FakeNoAbility())
    assert card.has_ability is False

    class FakeEmptyAbility(FakeCard):
        abilities: ClassVar = []

    card, _ = carddef_from_db(FakeEmptyAbility())
    assert card.has_ability is False

    # 场上过滤器注册
    p = board_engine().state.players[0].model_copy(update={
        "bench": (mon(70, pokemon("特性兽", has_ability=True)),
                  mon(71, pokemon("雪妖女", has_ability=True))),
    })
    pool = resolve_in_play_pool(p, ("has_ability",))
    assert [m.current.iid for m in pool] == [70, 71]  # 战斗场白板（默认无特性）排除
    pool = resolve_in_play_pool(p, ("not_name:雪妖女",))
    assert 71 not in [m.current.iid for m in pool]


# ── 规格/质量复核返工（2026-09-19：M1 清理幂等 / M2 检查×挂起 / m9 守卫边界）────


def test_attack_ko_promote_path_turn_end_cleanup() -> None:
    """复核 M1 回归：攻击致昏厥→换上路径不经 _on_turn_end——检查阶段入口统一
    补调，retreat_lock / extra_prize_tera_ko / own_ko_during_opponent_turn /
    discard_at_turn_end 道具自弃四项不陈旧泄漏。"""
    learner_doc = parse_card_doc("""
card:
  name_group: 学习器桩
effects:
  - trigger: passive_static
    actions:
      - {action: grant_attack, args: {attack: 桩招, discard_at_turn_end: true}}
""")
    tool = inst(88, tool_card("学习器桩"))
    e = board_engine(
        p0_active=mon(1, energies=1, tool=tool).model_copy(
            update={"retreat_lock": True}),
        p1_active=mon(2, pokemon("脆皮", hp=20)),
        p1_bench=(mon(80),),
        effects={"学习器桩": learner_doc},
    )
    p0 = e.state.players[0].model_copy(update={
        "extra_prize_tera_ko": True,
        "own_ko_during_opponent_turn": True,
    })
    e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    e.apply(0, Action(kind="attack", attack_index=0))  # 白板 20 → KO → p1 换上
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    # 检查入口补调 _on_turn_end(0)：四项全清 + 道具自弃进弃牌区
    p0 = e.state.players[0]
    assert p0.active.retreat_lock is False
    assert p0.extra_prize_tera_ko is False
    assert p0.own_ko_during_opponent_turn is False
    assert p0.active.attached_tool is None
    assert 88 in [c.iid for c in p0.discard]
    assert e.state.phase == "main" and e.state.current_player == 1


CHECK_KNIFE_DOC = parse_card_doc("""
card:
  name_group: 检查飞刀兽
effects:
  - trigger: trigger_on_event
    event: pokemon_check
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 30}}
""")


def test_check_trigger_suspend_and_resume() -> None:
    """复核 M2：检查阶段触发效果挂起选择——翻 choice 阶段（检查进行中标记保持、
    回合权未推进），choose 恢复后经 _run_or_suspend 检查拦截回到检查推进：
    排水 → 统一昏厥结算 → 开下一回合。"""
    e = board_engine(
        p0_bench=(mon(70, pokemon("检查飞刀兽", has_ability=True)),),
        effects={"检查飞刀兽": CHECK_KNIFE_DOC},
    )
    e.apply(0, Action(kind="end_turn"))
    # 触发效果挂起：choice 阶段、检查标记保持、尚未开下一回合
    assert e.state.phase == "choice" and e.state.current_player == 0
    assert e.state.pokemon_check_next == 1
    pc = e.state.pending_choice
    assert pc is not None and pc.pool == "opponent_pokemon_any"
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[1].active.damage == 30
    # 恢复后检查收尾：开下一回合（p1 抽 1）、检查标记清零
    assert e.state.phase == "main" and e.state.current_player == 1
    assert e.state.pokemon_check_next is None
    assert len(e.state.players[1].hand) == 1


def test_damage_scope_protection_does_not_block_check_counters() -> None:
    """复核 m9①：谢米 scope=opponent_attack_damage_to_bench 是招式伤害免疫——
    冻结帷幕的指示物放置（非伤害、非招式落点）不被挡。"""
    e = board_engine(
        p0_bench=(froslass(70),),
        p1_bench=(mon(80, pokemon("谢米", has_ability=True)),),
        effects={"雪妖女": FROSLASS_DOC, "谢米": SHAYMIN_DOC},
    )
    e.apply(0, Action(kind="end_turn"))
    # 谢米有特性且非雪妖女 → 冻结帷幕目标；伤害免疫不挡指示物
    assert e.state.players[1].bench[0].damage == 10


FLAME_VEIL_DOC = parse_card_doc("""
card:
  name_group: 火恐龙
effects:
  - trigger: passive_static
    actions:
      - {action: protection, args: {scope: opponent_attack_effects}}
""")


def test_attack_effects_protection_does_not_block_pokemon_check() -> None:
    """复核 m9②：闪焰之幕（scope=opponent_attack_effects）只管对手招式效果——
    pokemon_check 触发的效果不是招式效果，照常落点。"""
    e = board_engine(
        p0_bench=(froslass(70),),
        p1_bench=(mon(80, pokemon("火恐龙", has_ability=True)),),
        effects={"雪妖女": FROSLASS_DOC, "火恐龙": FLAME_VEIL_DOC},
    )
    e.apply(0, Action(kind="end_turn"))
    assert e.state.players[1].bench[0].damage == 10
