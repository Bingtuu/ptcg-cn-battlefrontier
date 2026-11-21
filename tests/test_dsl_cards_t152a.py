"""单卡 DSL 测试（task 152a）：盖诺赛克特ex——从 cards/ 真实文件装载。

盖诺赛克特ex（CSV10.5C-069 档，基础钢 ex 220，I 标 3 印刷等价类）：
「特性: 金属信号——在自己的回合可以使用1次。选择自己牌库中最多2张【钢】
属性的进化宝可梦，在给对手看过之后加入手牌。并重洗牌库。」
（ability_manual once_per_turn + search_deck filters=[pokemon_钢,
evolved_pokemon] choose=2——检索 up-to 语义 min_choose=0（吉尼亚先例）；
「在给对手看过之后」= 检索后 reveal own_hand 同过滤器（城镇百货/斗子
D-WP3-4 口径）+ shuffle_deck）
「【钢】【钢】【无】 防卫充能 150——在下一个对手的回合，这只宝可梦所受到
的招式的伤害『-30』。」（reduce_attack_damage，task 152a 引擎扩展
D-152a-1：部分减伤原语——amount=30「-30」+ timing=opponent_next_turn；
与 prevent_attack_damage 同款窗口/来源过滤，命中 = 伤害 −amount（下限 0）
而非归零；只减招式伤害，伤害指示物与招式效果不经——卡面仅「伤害」）
"""

from pathlib import Path

import pytest
from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.interpreter import ExecutionContext, run_effect
from battlefrontier.dsl.loader import DslError, load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef, InPlayPokemon

CARDS_DIR = Path(__file__).parent.parent / "cards"

GENO_DOC = load_card_doc(CARDS_DIR / "盖诺赛克特ex.yml")

# 对手招式效果 stub：伤害指示物（不减）/ 混乱（效果不防）——盾只守「伤害」
COUNTER_DOC = parse_card_doc("""
card:
  name_group: 指示兽
effects:
  - trigger: on_attack
    attack: 指示
    actions:
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 2}}
""")

CONFUSE_DOC = parse_card_doc("""
card:
  name_group: 混乱兽
effects:
  - trigger: on_attack
    attack: 混乱击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 40}}
      - {action: apply_status, selector: opponent_active, args: {status: confused}}
""")

# DSL 伤害路径对手（damage 原语经 attack_shield 减伤守卫落点）
DSL_HIT_DOC = parse_card_doc("""
card:
  name_group: 打手
effects:
  - trigger: on_attack
    attack: 打击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 40}}
""")


def geno_card() -> CardDef:
    return CardDef(
        card_id="CSV10.5C-069", name="盖诺赛克特ex", supertype="pokemon",
        hp=220, stage=0, energy_type="钢", rule_box="ex",
        attacks=(
            AttackDef(name="防卫充能", cost=("钢", "钢", "无"), damage=150),
        ),
        retreat_cost=2,
    )


def geno_mon(iid: int, energies: tuple[str, ...] = ("钢", "钢", "无")) -> InPlayPokemon:
    attached = tuple(
        inst(9000 + iid * 10 + j,
             CardDef(card_id=f"stub-能{j}", name=f"能{j}", supertype="energy",
                     energy_type=t, is_basic_energy=True))
        for j, t in enumerate(energies)
    )
    return InPlayPokemon(stack=(inst(iid, geno_card()),), attached_energy=attached)


def steel_evo(iid: int, name: str = "钢进化") -> CardDef:
    """钢属性 1 阶进化宝可梦（金属信号合法候选）。"""
    return CardDef(card_id=f"stub-{name}{iid}", name=name, supertype="pokemon",
                   hp=100, stage=1, evolves_from="幼基", energy_type="钢",
                   attacks=(AttackDef(name="打击", cost=("无",), damage=20),),
                   retreat_cost=1)


def typed_mon(iid: int, name: str, energy_type: str, *, hp: int = 300,
              damage: int = 20, cost: int = 1,
              attacks: tuple[AttackDef, ...] | None = None) -> InPlayPokemon:
    card = CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=hp, stage=0, energy_type=energy_type,
                   attacks=attacks or (AttackDef(name="打击", cost=("无",) * cost, damage=damage),),
                   retreat_cost=1)
    return in_play(iid, card, cost)


def game(*, p0_active: InPlayPokemon, p1_active: InPlayPokemon | None = None,
         p0_deck: tuple | None = None, turn: int = 2, current: int = 0,
         extra_docs: dict | None = None):
    state = main_state(p1_active_energies=1)
    p0 = state.players[0].model_copy(update={
        "active": p0_active,
        "deck": p0_deck if p0_deck is not None else state.players[0].deck,
    })
    p1 = state.players[1].model_copy(update={
        "active": p1_active or state.players[1].active,
    })
    state = state.model_copy(update={
        "players": (p0, p1), "turn": turn, "current_player": current,
    })
    e = engine_at(state)
    docs = {"盖诺赛克特ex": GENO_DOC, "打手": DSL_HIT_DOC,
            "指示兽": COUNTER_DOC, "混乱兽": CONFUSE_DOC}
    docs.update(extra_docs or {})
    e.card_effects = docs
    return e


def mixed_deck() -> tuple:
    """4 张金属信号候选边界：钢进化×2 / 钢基础 / 草进化 / 能量×5 /  filler。"""
    return (
        inst(101, steel_evo(101, "钢甲1")),
        inst(102, basic("钢基础", hp=60)),
        inst(103, CardDef(card_id="stub-草进化", name="草进化", supertype="pokemon",
                          hp=100, stage=1, evolves_from="幼草", energy_type="草")),
        inst(104, steel_evo(104, "钢甲2")),
        inst(105, basic("妙蛙种子")),
        inst(106, basic("小火龙")),
        inst(107, basic("小火龙")),
        inst(108, basic("小火龙")),
        inst(109, basic("小火龙")),
        inst(110, basic("小火龙")),
    )


# ── 金属信号 ────────────────────────────────────────────────────────────────


def test_盖诺赛克特ex_挂载等价类() -> None:
    """I 标同文本 3 印刷（db 归一化 text_raw 实测一致，2026-11-21）。"""
    assert GENO_DOC.card.card_ids == (
        "CSV10.5C-069", "CSV10.5C-164", "CSV10.5C-172")


def test_盖诺赛克特ex_金属信号_选两张钢进化入手并重洗() -> None:
    e = game(p0_active=geno_mon(1), p1_active=typed_mon(2, "靶兽", "雷"),
             p0_deck=mixed_deck())
    deck_before = list(e.state.players[0].deck)
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "choice"
    # 候选池只含钢进化（钢基础/草进化不在池）；choose 枚举 = 全部 up-to 组合（含空选）
    options = {a.choices for a in e.legal_actions(0) if a.kind == "choose"}
    assert options == {(), (101,), (104,), (101, 104)}
    e.apply(0, Action(kind="choose", choices=(101, 104)))
    p0 = e.state.players[0]
    assert {c.card.name for c in p0.hand if c.iid in (101, 104)} == {"钢甲1", "钢甲2"}
    assert len(p0.deck) == 8  # 2 张入手
    assert {c.iid for c in p0.deck}.isdisjoint({101, 104})
    # 重洗：剩余 8 张次序改变（不排序比较）
    assert [c.iid for c in p0.deck] != [c.iid for c in deck_before
                                        if c.iid not in (101, 104)]
    # 「在给对手看过之后」：reveal 事件只落钢进化
    revealed = [ev for ev in e.events if ev.kind == "reveal"]
    assert revealed[-1].detail["names"] == ["钢甲1", "钢甲2"]


def test_盖诺赛克特ex_金属信号_零张可选合法且重洗() -> None:
    """检索 up-to 语义（min_choose=0）：非空池选 0 张合法——不入手、
    重洗义务仍成立（shuffle_deck 节点照走）、限次照占。"""
    e = game(p0_active=geno_mon(1), p1_active=typed_mon(2, "靶兽", "雷"),
             p0_deck=mixed_deck())
    hand_before = tuple(e.state.players[0].hand)
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "choice"
    e.apply(0, Action(kind="choose", choices=()))
    p0 = e.state.players[0]
    assert p0.hand == hand_before  # 0 张入手
    assert len(p0.deck) == 10
    assert [c.iid for c in p0.deck] != [101, 102, 103, 104, 105,
                                        106, 107, 108, 109, 110]  # 已重洗
    # 限次照占：本回合不可再用
    assert not any(a.kind == "use_ability" for a in e.legal_actions(0))


def test_盖诺赛克特ex_金属信号_非钢非进化不在候选() -> None:
    """草进化（非钢）与钢基础（非进化）均不满足 filters AND 语义。"""
    e = game(p0_active=geno_mon(1), p1_active=typed_mon(2, "靶兽", "雷"),
             p0_deck=mixed_deck())
    e.apply(0, Action(kind="use_ability", iid=1))
    options = {a.choices for a in e.legal_actions(0) if a.kind == "choose"}
    assert options == {(), (101,), (104,), (101, 104)}  # 仅钢进化 101/104


# ── 防卫充能 ────────────────────────────────────────────────────────────────


def test_盖诺赛克特ex_防卫充能_150伤害且写部分减伤标记() -> None:
    e = game(p0_active=geno_mon(1), p1_active=typed_mon(2, "靶兽", "雷"))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 150
    shield = e.state.players[0].active.attack_shield
    assert shield is not None and len(shield) == 6 and shield[5] == 30  # 「-30」


def test_盖诺赛克特ex_防卫充能_下回合招式伤害减30() -> None:
    """白板路径（_do_attack）：150 → 120。"""
    e = game(p0_active=geno_mon(1),
             p1_active=typed_mon(2, "重击兽", "雷", damage=150))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))  # 对手下个回合窗口内
    assert e.state.players[0].active.damage == 120


def test_盖诺赛克特ex_防卫充能_减伤下限0() -> None:
    """20 − 30 → 0（不减成负）。"""
    e = game(p0_active=geno_mon(1), p1_active=typed_mon(2, "轻击兽", "雷"))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))
    assert e.state.players[0].active.damage == 0


def test_盖诺赛克特ex_防卫充能_DSL伤害路径同守() -> None:
    """damage 原语路径：对手 DSL 招式 40 → 10。"""
    p1 = typed_mon(2, "打手", "雷",
                   attacks=(AttackDef(name="打击", cost=("无",), damage=40),))
    e = game(p0_active=geno_mon(1), p1_active=p1)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))
    assert e.state.players[0].active.damage == 10


def test_盖诺赛克特ex_防卫充能_再下一回合失效() -> None:
    e = game(p0_active=geno_mon(1),
             p1_active=typed_mon(2, "重击兽", "雷", damage=100))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))  # 窗口内 −30 → 70
    assert e.state.players[0].active.damage == 70
    assert e.state.players[0].active.attack_shield is None  # 对手回合结束清除
    e.apply(0, Action(kind="end_turn"))
    e.apply(1, Action(kind="attack", attack_index=0))  # 窗口已过
    assert e.state.players[0].active.damage == 70 + 100


def test_盖诺赛克特ex_防卫充能_伤害指示物不减() -> None:
    """指示兽招式放 2 个伤害指示物（=20）：非招式伤害，不经减伤守卫。"""
    p1 = typed_mon(2, "指示兽", "雷",
                   attacks=(AttackDef(name="指示", cost=("无",), damage=None),))
    e = game(p0_active=geno_mon(1), p1_active=p1)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"  # 指示物目标选择挂起
    e.apply(1, Action(kind="choose", choices=(1,)))  # 指向盖诺赛克特ex
    assert e.state.players[0].active.damage == 20  # 不减


def test_盖诺赛克特ex_防卫充能_不防招式附加效果() -> None:
    """混乱照挂：减伤只守「伤害」，不免疫招式效果（比 protection 窄）。"""
    p1 = typed_mon(2, "混乱兽", "雷",
                   attacks=(AttackDef(name="混乱击", cost=("无",), damage=40),))
    e = game(p0_active=geno_mon(1), p1_active=p1)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))
    mon = e.state.players[0].active
    assert mon.damage == 10  # 40 − 30
    assert "confused" in (c.value for c in mon.conditions)


# ── 原语参数校验（执行期不猜）──────────────────────────────────────────────


def _run_bad_reduce(node_yaml: str) -> None:
    bad = parse_card_doc(f"""
card:
  name_group: 坏减
effects:
  - trigger: on_attack
    attack: 减击
    actions:
      - {{action: damage, selector: opponent_active, args: {{amount: 10}}}}
      - {node_yaml}
""")
    e = game(p0_active=in_play(1, basic("前台"), 1))
    ctx = ExecutionContext(e, 0, e.state.players[0].active.current,
                           "test", "on_attack")
    with pytest.raises(DslError):
        run_effect(ctx, bad.effects[0])


def test_减伤_args校验_amount必填正int() -> None:
    _run_bad_reduce("{action: reduce_attack_damage, selector: self, args: {timing: opponent_next_turn}}")
    _run_bad_reduce("{action: reduce_attack_damage, selector: self, args: {amount: 0, timing: opponent_next_turn}}")
    _run_bad_reduce("{action: reduce_attack_damage, selector: self, args: {amount: -30, timing: opponent_next_turn}}")
    _run_bad_reduce("{action: reduce_attack_damage, selector: self, args: {amount: \"30\", timing: opponent_next_turn}}")


def test_减伤_args校验_timing与selector() -> None:
    _run_bad_reduce("{action: reduce_attack_damage, selector: self, args: {amount: 30, timing: bogus}}")
    _run_bad_reduce("{action: reduce_attack_damage, selector: opponent_active, args: {amount: 30, timing: opponent_next_turn}}")
