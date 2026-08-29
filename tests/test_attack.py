"""task 008：招式成本匹配 / 弱点抗性 / 规则盒奖赏 / 任意时机昏厥检查。

规则出处：rules-manual §6（能量需求按属性+数量，无色任意属性可抵；伤害计算顺序：
基准 ≤0 终止 → 弱点 ×2 → 抗性 -30）、§1.4/§8（规则盒宝可梦昏厥奖赏张数：
ex/V/VSTAR=2，VMAX=3；昏厥整叠进弃牌堆）、§8（备战区昏厥同样结算奖赏，
无需换上；备战伤害不计算弱点抗性）。
"""

from helpers import basic, energy, engine_at, inst

from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import PRIZE_BY_RULE_BOX
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    GameState,
    InPlayPokemon,
    PlayerState,
)


def mon(
    name: str,
    *,
    attacks: tuple[AttackDef, ...] = (),
    hp: int = 70,
    energy_type: str | None = None,
    weakness: str | None = None,
    resistance: str | None = None,
    rule_box: str | None = None,
) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon", hp=hp, stage=0,
        energy_type=energy_type, attacks=attacks, weakness=weakness,
        resistance=resistance, rule_box=rule_box,
    )


def energies(*types: str) -> tuple[CardInstance, ...]:
    return tuple(inst(5000 + i, energy(energy_type=t)) for i, t in enumerate(types))


def battle(
    p0_active: InPlayPokemon,
    p1_active: InPlayPokemon,
    p1_bench: tuple[InPlayPokemon, ...] = (),
) -> GameState:
    p0 = PlayerState(
        deck=tuple(inst(100 + i, basic("妙蛙种子")) for i in range(10)),
        prizes=tuple(inst(200 + i, basic("妙蛙种子")) for i in range(6)),
        active=p0_active,
    )
    p1 = PlayerState(
        deck=tuple(inst(300 + i, basic("小火龙")) for i in range(10)),
        prizes=tuple(inst(400 + i, basic("小火龙")) for i in range(6)),
        active=p1_active,
        bench=p1_bench,
    )
    return GameState(players=(p0, p1), turn=2, current_player=0, phase="main", first_player=0)


# ── 能量成本匹配（rules-manual §6：指定属性 + 无色任意抵）──────────────────

def test_typed_cost_matching() -> None:
    atk = AttackDef(name="精神强念", cost=("超", "无"), damage=30)
    cases = [
        (("超", "超"), True),   # 2 超：指定属性 + 无色都满足
        (("超", "恶"), True),   # 1 超 1 恶：无色由恶抵
        (("恶", "恶"), False),  # 无超属性能量
        (("超",), False),       # 数量不足
    ]
    for types, expected in cases:
        e = engine_at(battle(
            InPlayPokemon(stack=(inst(1, mon("沙奈朵", attacks=(atk,))),), attached_energy=energies(*types)),
            InPlayPokemon(stack=(inst(2, basic("小火龙")),)),
        ))
        attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
        assert (len(attacks) == 1) == expected, f"attached={types}"


def test_multi_attack_enumeration() -> None:
    card = mon("双招兽", attacks=(
        AttackDef(name="撞击", cost=("无",), damage=20),
        AttackDef(name="重磅冲击", cost=("超", "超"), damage=80),
    ))
    # 1 个超能量：只够招式 0
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, card),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, basic("小火龙")),)),
    ))
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert [a.attack_index for a in attacks] == [0]
    # 2 个超能量：两招都可，attack_index 区分
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, card),), attached_energy=energies("超", "超")),
        InPlayPokemon(stack=(inst(2, basic("小火龙")),)),
    ))
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    assert [a.attack_index for a in attacks] == [0, 1]
    # 用招式 1 攻击：按招式 1 结算伤害（防守方 HP 200 保证不昏厥）
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, card),), attached_energy=energies("超", "超")),
        InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=200)),)),
    ))
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 80


def test_effect_attack_not_enumerated() -> None:
    """damage=None 的效果招式白板期不枚举（效果随 DSL on_attack 落地，task 009+）。"""
    card = mon("辅助兽", attacks=(AttackDef(name="奇异之光", cost=("无",), damage=None),))
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, card),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, basic("小火龙")),)),
    ))
    assert "attack" not in {a.kind for a in e.legal_actions(0)}


# ── 弱点 / 抗性（rules-manual §6：基准 → 弱点 ×2 → 抗性 -30）────────────────

def test_weakness_doubles_damage() -> None:
    attacker = mon("超能兽", energy_type="超",
                   attacks=(AttackDef(name="念力", cost=("无",), damage=30),))
    defender = mon("胆小兽", weakness="超")
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, attacker),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, defender),)),
    ))
    e.apply(0, Action(kind="attack"))
    assert e.state.players[1].active.damage == 60  # 30 ×2


def test_resistance_reduces_damage() -> None:
    attacker = mon("超能兽", energy_type="超",
                   attacks=(AttackDef(name="念力", cost=("无",), damage=40),))
    defender = mon("坚硬兽", resistance="超")
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, attacker),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, defender),)),
    ))
    e.apply(0, Action(kind="attack"))
    assert e.state.players[1].active.damage == 10  # 40 -30


def test_resistance_to_zero_no_damage() -> None:
    """抗性后 ≤0：不造成伤害（rules-manual §6 下限）。"""
    attacker = mon("超能兽", energy_type="超",
                   attacks=(AttackDef(name="念力", cost=("无",), damage=30),))
    defender = mon("坚硬兽", resistance="超")
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, attacker),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, defender),)),
    ))
    e.apply(0, Action(kind="attack"))
    assert e.state.players[1].active.damage == 0
    assert e.state.current_player == 1  # 招式仍结束回合


# ── 规则盒奖赏（rules-manual §1.4/§8）────────────────────────────────────

def test_rule_box_prize_mapping() -> None:
    assert PRIZE_BY_RULE_BOX == {"ex": 2, "V": 2, "VSTAR": 2, "VMAX": 3}


def test_ex_knockout_takes_two_prizes() -> None:
    attacker = mon("打手", attacks=(AttackDef(name="撞击", cost=("无",), damage=100),))
    defender = mon("沙奈朵ex", hp=80, rule_box="ex")
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, attacker),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, defender),)),
    ))
    e.apply(0, Action(kind="attack"))
    p0 = e.state.players[0]
    assert len(p0.prizes) == 4 and len(p0.hand) == 2  # 拿 2 张
    prize_events = [ev for ev in e.events if ev.kind == "take_prize"]
    assert len(prize_events) == 2  # 每张一条事件（回放保真）


def test_ex_knockout_last_prizes_wins() -> None:
    """只剩 2 张奖赏时击倒 ex：拿完即胜（rules-manual §8 胜利条件①）。"""
    attacker = mon("打手", attacks=(AttackDef(name="撞击", cost=("无",), damage=100),))
    defender = mon("沙奈朵ex", hp=80, rule_box="ex")
    state = battle(
        InPlayPokemon(stack=(inst(1, attacker),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, defender),)),
        p1_bench=(InPlayPokemon(stack=(inst(3, basic("小火龙")),)),),
    )
    p0 = state.players[0].model_copy(update={"prizes": state.players[0].prizes[:2]})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.apply(0, Action(kind="attack"))
    assert e.state.phase == "game_over" and e.state.winner == 0


# ── 任意时机昏厥检查（rules-manual §8；铺伤/状态伤害的前置框架）──────────────

def test_bench_knockout_no_promote() -> None:
    """备战区伤害 ≥ HP 同样昏厥：整叠进弃牌堆、对手拿奖赏，无需换上。"""
    hurt = InPlayPokemon(stack=(inst(3, basic("飘飘球", hp=60)),), damage=60)
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, basic("妙蛙种子")),)),
        InPlayPokemon(stack=(inst(2, basic("小火龙")),)),
        p1_bench=(hurt,),
    ))
    e.check_knockouts()
    p0, p1 = e.state.players
    assert len(p1.bench) == 0 and len(p1.discard) == 1
    assert len(p0.prizes) == 5  # 对手拿 1 张
    assert e.state.phase == "main"  # 无需换上，流程不变
    assert any(ev.kind == "knockout" for ev in e.events)


def test_check_knockouts_active_entry() -> None:
    """任意时机入口：战斗场伤害 ≥ HP 经 check_knockouts 走昏厥 + 换上流程。"""
    hurt = InPlayPokemon(stack=(inst(2, basic("小火龙", hp=70)),), damage=70)
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, basic("妙蛙种子")),)),
        hurt,
        p1_bench=(InPlayPokemon(stack=(inst(3, basic("小火龙")),)),),
    ))
    e.check_knockouts()
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.players[1].active is not None
    assert e.state.phase == "main" and e.state.current_player == 1
