"""task 012：on_attack 招式效果框架 + 计数表达式/变量伤害 + clear_status。

规则出处：rules-manual §6（伤害计算：基准 → 弱点 ×2 → 抗性 -30；备战区目标不计算
弱点抗性——贯穿规则，非卡面特例）；§8（攻击致昏厥走 check_knockouts 换上流程）。
语义约定（PRD §5.1 task 012 补充）：Effect.attack 绑定的招式，伤害与效果全部由
DSL 结算（AttackDef.damage 仅作装载/展示数据，不重复结算）。
"""

import pytest
from helpers import basic, energy, engine_at, inst
from test_attack import battle, energies, mon

from battlefrontier.dsl import load_card_dir, parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    InPlayPokemon,
    SpecialCondition,
)

KIRLIA_DOC = parse_card_doc("""
card:
  name_group: 奇鲁莉安
effects:
  - trigger: on_attack
    attack: 精神强念
    actions:
      - {action: damage, selector: opponent_active, count: attached_energy_on_opponent_active, args: {base: 60, per: 20, op: "+"}}
""")

CLEFAIRY_DOC = parse_card_doc("""
card:
  name_group: 莉莉艾的皮皮ex
effects:
  - trigger: on_attack
    attack: 满月回旋曲
    actions:
      - {action: damage, selector: opponent_active, count: bench_count_both, args: {base: 20, per: 20, op: "+"}}
""")

DRIFLOON_DOC = parse_card_doc("""
card:
  name_group: 飘飘球
effects:
  - trigger: on_attack
    attack: 气球炸弹
    actions:
      - {action: damage, selector: opponent_active, count: damage_counters_on_self, args: {per: 30, op: "×"}}
""")

FEZANDIPITI_DOC = parse_card_doc("""
card:
  name_group: 吉雉鸡ex
effects:
  - trigger: on_attack
    attack: 残忍箭矢
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 100}}
""")

SCREAM_TAIL_DOC = parse_card_doc("""
card:
  name_group: 吼叫尾
effects:
  - trigger: on_attack
    attack: 凶暴吼叫
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, count: damage_counters_on_target, args: {per: 20, op: "×"}}
""")

GARDEVOIR_ATK_DOC = parse_card_doc("""
card:
  name_group: 沙奈朵ex
effects:
  - trigger: on_attack
    attack: 奇迹之力
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 190}}
      - {action: clear_status, selector: self}
""")


def attacker(name: str, attack: AttackDef, *, hp: int = 120, energy_type: str = "超") -> CardDef:
    return mon(name, attacks=(attack,), hp=hp, energy_type=energy_type)


def atk_engine(card: CardDef, attached: tuple[str, ...], doc, *,
               p0_damage: int = 0, p1_active: CardDef | None = None,
               p1_energies: tuple[str, ...] = (), p1_bench: tuple[InPlayPokemon, ...] = (),
               p0_conditions=frozenset()):
    """p0 战斗场 = card（attached 能量 + 可选伤害/状态），p1 战斗场 hp200 + 可选附着/备战。"""
    defender = p1_active or mon("厚皮兽", hp=200)
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, card),), attached_energy=energies(*attached),
                      damage=p0_damage, conditions=p0_conditions),
        InPlayPokemon(stack=(inst(2, defender),), attached_energy=energies(*p1_energies)),
        p1_bench=p1_bench,
    ))
    if doc is not None:
        e.card_effects = {card.name: doc}
    return e


# ── 枚举：on_attack 绑定使纯效果招式可枚举 ───────────────────────────────

def test_effect_attack_with_doc_enumerated() -> None:
    """damage=None 招式：有 on_attack 绑定 → 枚举；无绑定 → 不枚举（白板纪律不变）。"""
    card = attacker("吉雉鸡ex", AttackDef(name="残忍箭矢", cost=("无", "无", "无"), damage=None))
    e = atk_engine(card, ("超", "超", "超"), FEZANDIPITI_DOC)
    assert [a for a in e.legal_actions(0) if a.kind == "attack"] == [Action(kind="attack", attack_index=0)]
    e = atk_engine(card, ("超", "超", "超"), None)
    assert not [a for a in e.legal_actions(0) if a.kind == "attack"]


# ── 变量伤害（计数表达式）────────────────────────────────────────────────

def test_psyshock_plus_per_attached_energy() -> None:
    """精神强念：60 + 对手战斗场附着能量 ×20（3 张 → 120）。"""
    card = attacker("奇鲁莉安", AttackDef(name="精神强念", cost=("超", "超", "无"),
                                          damage=60, damage_modifier="+"))
    e = atk_engine(card, ("超", "超", "无"), KIRLIA_DOC, p1_energies=("超", "超", "超"))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 120
    assert e.state.current_player == 1  # DSL 攻击后回合正常结束


def test_variable_damage_weakness_resistance_on_active() -> None:
    """变量伤害对战斗场目标照常结算弱点 ×2 / 抗性 -30（rules-manual §6）。"""
    card = attacker("奇鲁莉安", AttackDef(name="精神强念", cost=("超", "超", "无"),
                                          damage=60, damage_modifier="+"))
    weak = atk_engine(card, ("超", "超", "无"), KIRLIA_DOC,
                      p1_active=mon("胆小兽", hp=400, weakness="超"), p1_energies=("超",))
    weak.apply(0, Action(kind="attack", attack_index=0))
    assert weak.state.players[1].active.damage == 160  # (60+20)×2
    res = atk_engine(card, ("超", "超", "无"), KIRLIA_DOC,
                     p1_active=mon("坚硬兽", hp=200, resistance="超"), p1_energies=("超",))
    res.apply(0, Action(kind="attack", attack_index=0))
    assert res.state.players[1].active.damage == 50  # 60+20-30


def test_full_moon_bench_count_both() -> None:
    """满月回旋曲：20 + 双方备战宝可梦数量 ×20（p0 备战 1 + p1 备战 2 → 80）。"""
    card = attacker("莉莉艾的皮皮ex", AttackDef(name="满月回旋曲", cost=("超", "无"),
                                                damage=20, damage_modifier="+"))
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, card),), attached_energy=energies("超", "超")),
        InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=200)),)),
        p1_bench=(InPlayPokemon(stack=(inst(3, basic("小火龙")),)),
                  InPlayPokemon(stack=(inst(4, basic("小火龙")),))),
    ))
    # p0 加 1 只备战
    p0 = e.state.players[0].model_copy(update={
        "bench": (InPlayPokemon(stack=(inst(5, basic("妙蛙种子")),)),),
    })
    e.state = e.state.model_copy(update={"players": (p0, e.state.players[1])})
    e.card_effects = {"莉莉艾的皮皮ex": CLEFAIRY_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 80


def test_balloon_bomb_self_counters() -> None:
    """气球炸弹：自身伤害指示物 ×30（4 个 = 40 伤害 → 120）；0 个 → 0 伤仍结束回合。"""
    card = attacker("飘飘球", AttackDef(name="气球炸弹", cost=("超", "超"),
                                        damage=30, damage_modifier="×"))
    e = atk_engine(card, ("超", "超"), DRIFLOON_DOC, p0_damage=40)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 120
    e = atk_engine(card, ("超", "超"), DRIFLOON_DOC)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0
    assert e.state.current_player == 1


# ── 任意目标（chooser）+ 备战不计算弱抗 ──────────────────────────────────

def test_cruel_arrow_bench_target_no_weakres() -> None:
    """残忍箭矢：选对手任意 1 只造成 100；备战目标不计算弱点抗性（×2 不适用）。"""
    card = attacker("吉雉鸡ex", AttackDef(name="残忍箭矢", cost=("无", "无", "无"), damage=None))
    bench = (InPlayPokemon(stack=(inst(3, mon("胆小兽", hp=200, weakness="超")),)),)
    e = atk_engine(card, ("超", "超", "超"), FEZANDIPITI_DOC, p1_bench=bench)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"
    choices = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert choices == [(2,), (3,)]  # 对手战斗场 + 备战全枚举
    e.apply(0, Action(kind="choose", choices=(3,)))
    p1 = e.state.players[1]
    assert e.state.phase == "main" and e.state.current_player == 1  # 选完即结算并结束回合
    assert p1.bench[0].damage == 100  # 弱点不翻倍
    assert p1.active.damage == 0


def test_scream_tail_target_counters() -> None:
    """凶暴吼叫：所选目标身上指示物 ×20（备战 6 个 → 120，落备战目标）。"""
    card = attacker("吼叫尾", AttackDef(name="凶暴吼叫", cost=("超", "无"), damage=None))
    bench = (InPlayPokemon(stack=(inst(3, mon("厚皮兽", hp=300)),), damage=60),)
    e = atk_engine(card, ("超", "超"), SCREAM_TAIL_DOC, p1_bench=bench)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(3,)))
    assert e.state.players[1].bench[0].damage == 180  # 60 + 120


# ── 奇迹之力：DSL 全权结算（不重复白板伤害）+ clear_status ───────────────

def test_miracle_force_damage_once_and_clear_status() -> None:
    """AttackDef.damage=190 与 DSL amount=190 并存：只结算一次 190（委托语义）；
    自身混乱/灼伤全部恢复。"""
    card = attacker("沙奈朵ex", AttackDef(name="奇迹之力", cost=("超", "超", "无"), damage=190), hp=310)
    e = atk_engine(card, ("超", "超", "无"), GARDEVOIR_ATK_DOC,
                   p0_conditions=frozenset({SpecialCondition.CONFUSED, SpecialCondition.BURNED}))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 190  # 非 380
    assert e.state.players[0].active.conditions == frozenset()
    prims = [ev for ev in e.events if ev.kind == "effect_primitive"]
    assert [p.detail["action"] for p in prims] == ["damage", "clear_status"]


def test_dsl_attack_knockout_goes_promote() -> None:
    """DSL 攻击致战斗场昏厥：进换上流程，不被回合推进覆盖（completion=attack）。"""
    card = attacker("吉雉鸡ex", AttackDef(name="残忍箭矢", cost=("无", "无", "无"), damage=None))
    e = atk_engine(card, ("超", "超", "超"), FEZANDIPITI_DOC,
                   p1_active=mon("脆皮兽", hp=100),
                   p1_bench=(InPlayPokemon(stack=(inst(3, basic("小火龙")),)),))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(2,)))  # 打战斗场
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 1


# ── 失败路径（不猜）──────────────────────────────────────────────────────

def test_unknown_counter_dsl_error() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏招式
effects:
  - trigger: on_attack
    attack: 坏招
    actions:
      - {action: damage, selector: opponent_active, count: all, args: {per: 20, op: "×"}}
""")
    card = attacker("坏招式", AttackDef(name="坏招", cost=("无",), damage=None))
    e = atk_engine(card, ("超",), bad)
    with pytest.raises(DslError, match="计数表达式"):
        e.apply(0, Action(kind="attack", attack_index=0))


# ── 定义库与对局级确定性 ────────────────────────────────────────────────

def test_card_library_attack_docs() -> None:
    docs = load_card_dir("cards")
    for name in ("吉雉鸡ex", "吼叫尾", "奇鲁莉安", "莉莉艾的皮皮ex", "飘飘球"):
        assert name in docs
    k = docs["奇鲁莉安"].effects[0]
    assert k.trigger == "on_attack" and k.attack == "精神强念"
    assert k.actions[0].args == {"base": 60, "per": 20, "op": "+"}
    g = docs["沙奈朵ex"]
    assert {e.trigger for e in g.effects} == {"ability_manual", "on_attack"}


def test_play_game_with_attack_effects_deterministic() -> None:
    """含效果招式的整局对局：同种子事件流 hash 一致。"""
    from battlefrontier.runner.play import play_game

    kirlia = attacker("奇鲁莉安", AttackDef(name="精神强念", cost=("超", "超", "无"),
                                           damage=60, damage_modifier="+"))
    drifloon = attacker("飘飘球", AttackDef(name="气球炸弹", cost=("超", "超"),
                                            damage=30, damage_modifier="×"))
    deck = ([kirlia] * 4 + [drifloon] * 4 + [basic("小火龙")] * 16
            + [energy("基本超能量", "超")] * 20 + [energy()] * 16)
    effects = load_card_dir("cards")
    r1 = play_game(deck, deck, seed=9, card_effects=effects)
    r2 = play_game(deck, deck, seed=9, card_effects=effects)
    assert r1.events_hash == r2.events_hash
