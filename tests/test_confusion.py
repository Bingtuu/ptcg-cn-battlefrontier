"""task 013：混乱状态（D1 决议）+ apply_status 原语 + 愿增猿「精神幻觉」。

D1 决议（rules-reference 附录 A，2026-08-28 核定）：混乱只对战斗区宝可梦生效；
陷入混乱的宝可梦决定使用招式时掷 1 次硬币——正面招式正常发动（混乱不解除），
反面招式完全失败（不发动任何效果）+ 自身放 3 个伤害指示物。
"""

import pytest
from helpers import basic, energy, inst
from test_attack import battle, energies, mon

from battlefrontier.dsl import load_card_dir, parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import AttackDef, InPlayPokemon, SpecialCondition

MUNKIDORI_DOC = parse_card_doc("""
card:
  name_group: 愿增猿
effects:
  - trigger: on_attack
    attack: 精神幻觉
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 60}}
      - {action: apply_status, selector: opponent_active, args: {status: confused}}
""")


def confused_engine(state, *, heads: bool) -> GameEngine:
    """构造首枚掷币结果为 heads 的引擎（snapshot/restore 预窥，不消耗序列）。"""
    for seed in range(1000):
        e = GameEngine(RandomSource(seed))
        snap = e.rng.snapshot()
        result = e.rng.flip_coin()
        e.rng.restore(snap)
        if result == heads:
            e.state = state
            return e
    raise AssertionError("1000 个种子内未找到目标掷币结果")


def puncher(name: str = "打手", hp: int = 120) -> object:
    return mon(name, attacks=(AttackDef(name="撞击", cost=("无",), damage=50),), hp=hp,
               energy_type="超")


def confused_battle(*, atk_hp: int = 120, p1_bench=(), p0_bench=()):
    """p0 战斗场混乱的打手（1 能量），p1 战斗场厚皮兽 hp200。"""
    atk = InPlayPokemon(
        stack=(inst(1, puncher(hp=atk_hp)),),
        attached_energy=energies("超"),
        conditions=frozenset({SpecialCondition.CONFUSED}),
    )
    state = battle(atk, InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=200)),)),
                   p1_bench=p1_bench)
    if p0_bench:
        p0 = state.players[0].model_copy(update={"bench": p0_bench})
        state = state.model_copy(update={"players": (p0, state.players[1])})
    return state


# ── apply_status：精神幻觉 e2e ───────────────────────────────────────────

def test_mirage_applies_confusion() -> None:
    """精神幻觉：60 伤害 + 对手战斗宝可梦陷入混乱。"""
    card = mon("愿增猿", attacks=(AttackDef(name="精神幻觉", cost=("超", "无"), damage=60),),
               hp=110, energy_type="恶")
    e = engine_at_confused_free(card)
    e.apply(0, Action(kind="attack", attack_index=0))
    d = e.state.players[1].active
    assert d.damage == 60
    assert d.conditions == frozenset({SpecialCondition.CONFUSED})
    assert [p.detail["action"] for p in e.events if p.kind == "effect_primitive"] == [
        "damage", "apply_status",
    ]


def engine_at_confused_free(card):
    from helpers import engine_at

    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, card),), attached_energy=energies("超", "超")),
        InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=200)),)),
    ))
    e.card_effects = {"愿增猿": MUNKIDORI_DOC}
    return e


def test_unknown_status_dsl_error() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏状态
effects:
  - trigger: on_attack
    attack: 坏招
    actions:
      - {action: apply_status, selector: opponent_active, args: {status: 睡着了}}
""")
    card = mon("坏状态", attacks=(AttackDef(name="坏招", cost=("无",), damage=None),),
               energy_type="超")
    e = engine_at_confused_free(card)
    e.card_effects = {"坏状态": bad}
    with pytest.raises(DslError, match="未知特殊状态"):
        e.apply(0, Action(kind="attack", attack_index=0))


# ── 混乱攻击掷币（D1）────────────────────────────────────────────────────

def test_confused_heads_attack_proceeds_stays_confused() -> None:
    """正面：招式正常结算，混乱不解除。"""
    e = confused_engine(confused_battle(), heads=True)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50
    assert SpecialCondition.CONFUSED in e.state.players[0].active.conditions  # 不解除
    assert e.state.current_player == 1
    check = next(ev for ev in e.events if ev.kind == "confusion_check")
    assert check.detail["result"] == "heads"


def test_confused_tails_attack_fails_self_damage() -> None:
    """反面：招式完全失败（白板伤害不结算），自身 +30（3 指示物），回合结束。"""
    e = confused_engine(confused_battle(), heads=False)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0
    assert e.state.players[0].active.damage == 30
    assert SpecialCondition.CONFUSED in e.state.players[0].active.conditions
    assert e.state.current_player == 1  # 回合正常给对手
    assert not [ev for ev in e.events if ev.kind == "effect_primitive"]


def test_confused_tails_dsl_attack_no_effect() -> None:
    """反面 + DSL 招式：效果一个不执行（无伤害、不施加状态）。"""
    card = mon("愿增猿", attacks=(AttackDef(name="精神幻觉", cost=("超", "无"), damage=60),),
               hp=110, energy_type="恶")
    state = battle(
        InPlayPokemon(stack=(inst(1, card),), attached_energy=energies("超", "超"),
                      conditions=frozenset({SpecialCondition.CONFUSED})),
        InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=200)),)),
    )
    e = confused_engine(state, heads=False)
    e.card_effects = {"愿增猿": MUNKIDORI_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    d = e.state.players[1].active
    assert d.damage == 0 and d.conditions == frozenset()
    assert e.state.players[0].active.damage == 30


def test_confused_tails_self_ko_promote_then_opponent_turn() -> None:
    """反面自我昏厥：攻击方换上后回合权给对手（攻击已消耗），对手拿奖赏。"""
    bench = (InPlayPokemon(stack=(inst(5, basic("小火龙")),)),)
    e = confused_engine(confused_battle(atk_hp=30, p0_bench=bench), heads=False)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "promote" and e.state.current_player == 0  # 攻击方换上
    assert len(e.state.players[1].prizes) == 5  # 对手拿 1 张
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.current_player == 1 and e.state.phase == "main"  # 回合权给对手
    assert e.state.turn == 2  # 对手同一 turn 数（turn 只在 first_player 回合开始 +1）


def test_retreat_clears_confusion() -> None:
    """撤退清除混乱（既有 conditions 清除机制回归锁定）。"""
    bench = (InPlayPokemon(stack=(inst(5, basic("小火龙")),)),)
    e = confused_engine(confused_battle(p0_bench=bench), heads=True)
    e.apply(0, Action(kind="retreat", bench_index=0))
    assert e.state.players[0].active.current.iid == 5
    old = e.state.players[0].bench[0]
    assert old.conditions == frozenset()


# ── 定义库与对局级确定性 ────────────────────────────────────────────────

def test_card_library_munkidori() -> None:
    docs = load_card_dir("cards")
    assert "愿增猿" in docs
    eff = next(e for e in docs["愿增猿"].effects if e.trigger == "on_attack")
    assert eff.attack == "精神幻觉"
    assert [a.action for a in eff.actions] == ["damage", "apply_status"]


def test_play_game_with_confusion_deterministic() -> None:
    """含混乱招式的整局对局：同种子事件流 hash 一致（掷币走统一随机源）。"""
    from battlefrontier.runner.play import play_game

    munk = mon("愿增猿", attacks=(AttackDef(name="精神幻觉", cost=("超", "无"), damage=60),),
               hp=110, energy_type="恶")
    deck = ([munk] * 4 + [basic("小火龙")] * 20
            + [energy("基本超能量", "超")] * 20 + [energy()] * 16)
    effects = load_card_dir("cards")
    r1 = play_game(deck, deck, seed=13, card_effects=effects)
    r2 = play_game(deck, deck, seed=13, card_effects=effects)
    assert r1.events_hash == r2.events_hash
