"""task 070 WP0 机制测试：逆转能量 chooser 组合词
own_prizes_more_and_holder_evolved_no_rule_box。

逆转能量（CSV2C-128）text_raw：「只要这张卡牌，被附着于宝可梦身上，就被视作
1个【无】能量。如果自己的剩余奖赏卡张数，比对手的剩余奖赏卡张数多的话，则
这张卡牌，只要被附着于进化宝可梦身上（除「拥有规则的宝可梦」外），就被视作
3个所有属性的能量。」

组合词 = 奖赏比较（own_prizes_more_than_opponent）∧ 持有者为进化（stage≥1）
∧ 无规则盒（rule_box is None）；组合词先例 self_is_active_and_first_own_turn
（chooser.py _CONDITIONS）。
"""

from helpers import energy, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.chooser import condition_met
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    CardInstance,
    InPlayPokemon,
)

COND = "own_prizes_more_and_holder_evolved_no_rule_box"


def pokemon(
    name: str, *, stage: int = 0, rule_box: str | None = None,
    attacks: tuple | None = None,
) -> CardDef:
    if attacks is None:
        attacks = (AttackDef(name="打击", cost=("无",), damage=20),)
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=500, stage=stage, attacks=attacks, rule_box=rule_box,
    )


def special_energy(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="energy",
                   is_basic_energy=False)


def mon(iid: int, card: CardDef, attached: tuple[CardInstance, ...] = ()) -> InPlayPokemon:
    return InPlayPokemon(stack=(inst(iid, card),), attached_energy=attached)


def board_engine(
    *, p0_active: InPlayPokemon, p0_prizes: int = 6, p1_prizes: int = 6,
    effects: dict | None = None,
) -> GameEngine:
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": p0_active,
        "prizes": tuple(inst(200 + i, pokemon(f"赏{i}")) for i in range(p0_prizes)),
    })
    p1 = state.players[1].model_copy(update={
        "prizes": tuple(inst(400 + i, pokemon(f"敌赏{i}")) for i in range(p1_prizes)),
    })
    e = GameEngine(RandomSource(0))
    e.state = state.model_copy(update={"players": (p0, p1)})
    e.card_effects = effects or {}
    return e


# ── 组合词直测（condition_met）────────────────────────────────────────


def test_condition_prizes_more_and_evolved_no_rule_box() -> None:
    """奖赏 6v5（多）+ 1阶无规则盒持有者 → 通过。"""
    holder = mon(1, pokemon("奇鲁莉安", stage=1))
    e = board_engine(p0_active=holder, p0_prizes=6, p1_prizes=5)
    assert condition_met(COND, e, 0, holder)


def test_condition_prizes_not_more() -> None:
    """奖赏相等 / 更少 → 不通过（其余条件满足也不救）。"""
    holder = mon(1, pokemon("奇鲁莉安", stage=1))
    e = board_engine(p0_active=holder, p0_prizes=5, p1_prizes=5)
    assert not condition_met(COND, e, 0, holder)
    e = board_engine(p0_active=holder, p0_prizes=4, p1_prizes=5)
    assert not condition_met(COND, e, 0, holder)


def test_condition_holder_basic_rejected() -> None:
    """基础宝可梦（stage 0）持有者 → 不通过。"""
    holder = mon(1, pokemon("拉鲁拉丝", stage=0))
    e = board_engine(p0_active=holder, p0_prizes=6, p1_prizes=5)
    assert not condition_met(COND, e, 0, holder)


def test_condition_holder_rule_box_rejected() -> None:
    """进化但带规则盒（ex）持有者 → 不通过（「除拥有规则的宝可梦外」）。"""
    holder = mon(1, pokemon("沙奈朵ex", stage=2, rule_box="ex"))
    e = board_engine(p0_active=holder, p0_prizes=6, p1_prizes=5)
    assert not condition_met(COND, e, 0, holder)


def test_condition_mon_none_rejected() -> None:
    """无持有者（mon=None）→ 不通过。"""
    e = board_engine(p0_active=mon(1, pokemon("奇鲁莉安", stage=1)),
                     p0_prizes=6, p1_prizes=5)
    assert not condition_met(COND, e, 0, None)


# ── provide_energy 分层集成（条件块覆盖无条件块）──────────────────────

REVERSAL_DOC = parse_card_doc(f"""
card:
  name_group: 逆转能量
effects:
  - trigger: passive_static
    condition: {COND}
    actions:
      - {{action: provide_energy, args: {{types: all, count: 3}}}}
  - trigger: passive_static
    actions:
      - {{action: provide_energy, args: {{types: [无]}}}}
""")


def fire3_attacker(name: str, *, stage: int = 1, rule_box: str | None = None) -> CardDef:
    return pokemon(name, stage=stage, rule_box=rule_box,
                   attacks=(AttackDef(name="三火击", cost=("火", "火", "火"), damage=30),))


def attack_kinds(e: GameEngine, player: int = 0) -> list[int]:
    return [a.attack_index for a in e.legal_actions(player) if a.kind == "attack"]


def test_reversal_energy_provides_3_rainbow_when_condition_met() -> None:
    """条件通过（6v5 + 1阶无规则盒）：1 张逆转能量供 3 彩虹 → 【火】【火】【火】可攻。"""
    holder = mon(1, fire3_attacker("火兽"), attached=(inst(90, special_energy("逆转能量")),))
    e = board_engine(p0_active=holder, p0_prizes=6, p1_prizes=5,
                     effects={"逆转能量": REVERSAL_DOC})
    assert 0 in attack_kinds(e)


def test_reversal_energy_falls_back_to_1_colorless() -> None:
    """条件不通过（奖赏相等）：回退 1 个【无】——3 有色需求不可攻，1 无色需求可攻。"""
    holder = mon(1, fire3_attacker("火兽"), attached=(inst(90, special_energy("逆转能量")),))
    e = board_engine(p0_active=holder, effects={"逆转能量": REVERSAL_DOC})
    assert attack_kinds(e) == []
    plain = mon(1, pokemon("无兽"), attached=(inst(90, special_energy("逆转能量")),))
    e = board_engine(p0_active=plain, effects={"逆转能量": REVERSAL_DOC})
    assert 0 in attack_kinds(e)


def test_reversal_energy_rule_box_holder_falls_back() -> None:
    """规则盒持有者（ex）：条件不通过 → 回退 1 个【无】。"""
    holder = mon(1, fire3_attacker("火兽ex", rule_box="ex"),
                 attached=(inst(90, special_energy("逆转能量")),))
    e = board_engine(p0_active=holder, p0_prizes=6, p1_prizes=5,
                     effects={"逆转能量": REVERSAL_DOC})
    assert attack_kinds(e) == []


def test_basic_energy_unaffected_by_combo_word() -> None:
    """回归：基本能量无 DSL 文档 → 既有口径（energy_type 抵费）不经过组合词。"""
    holder = mon(1, fire3_attacker("火兽"),
                 attached=tuple(inst(90 + j, energy("基本火能量", "火")) for j in range(3)))
    e = board_engine(p0_active=holder, effects={"逆转能量": REVERSAL_DOC})
    assert 0 in attack_kinds(e)
