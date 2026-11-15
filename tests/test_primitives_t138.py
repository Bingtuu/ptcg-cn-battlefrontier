"""原语扩展测试（task 138）：on_attack 招式使用门 usage_gate / 计数词
bench_count_own / 时效减伤 prevent_attack_damage（D-138-1/2/3）——只加不改
（既有测试零改动证明，见全量 pytest）。

- 太乐巴戈斯ex 同盟打击「这个招式，在后攻玩家的最初回合无法使用」：
  Effect 级 usage_gate 开放词 second_player_first_turn（枚举点门控 + 执行双保险；
  区别于古月鸟 condition「招式失败」语义——禁用时根本不可宣言）。
- 太乐巴戈斯ex 同盟打击「造成自己备战宝可梦数量×30伤害」：计数词 bench_count_own。
- 太乐巴戈斯ex 皇冠蛋白石「在下一个对手的回合，这只宝可梦不会受到【基础】
  宝可梦（除【无】宝可梦外）的招式的伤害」：prevent_attack_damage 原语
  （timing=opponent_next_turn 时效 + attacker_stage/except_attacker_type 来源
  过滤；生效窗口 = 「下一个对手的回合」，对手回合结束清除——对齐
  D-069-1 own_turn_end 时点纪律；接入点 = 招式伤害三路径：_do_attack 白板 /
  DSL damage 原语 / copy_attack 白板复制，对齐 _survival_cap 三落点纪律）。
"""

import pytest
from helpers import basic, engine_at, in_play, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.interpreter import ExecutionContext, run_effect
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action, IllegalActionError
from battlefrontier.engine.state import AttackDef, CardDef, InPlayPokemon

# ── D-138-1：usage_gate 招式使用门 ─────────────────────────────────────────

GATEDOC = parse_card_doc("""
card:
  name_group: 门兽
effects:
  - trigger: on_attack
    attack: 门招
    usage_gate: second_player_first_turn
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 10}}
""")

# ── D-138-2：bench_count_own ────────────────────────────────────────────────

BENCHDOC = parse_card_doc("""
card:
  name_group: 群兽
effects:
  - trigger: on_attack
    attack: 群击
    actions:
      - {action: damage, selector: opponent_active, count: bench_count_own, args: {op: "×", per: 30}}
""")

# ── D-138-3：prevent_attack_damage 时效减伤 ────────────────────────────────

SHIELDDOC = parse_card_doc("""
card:
  name_group: 盾兽
effects:
  - trigger: on_attack
    attack: 盾击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 50}}
      - {action: prevent_attack_damage, selector: self, args: {timing: opponent_next_turn, attacker_stage: basic, except_attacker_type: 无}}
""")

# 打击走 DSL 路径的对手（测 _damage 原语守卫落点）
DSL_HIT_DOC = parse_card_doc("""
card:
  name_group: 打手
effects:
  - trigger: on_attack
    attack: 打击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 40}}
""")

# 备战狙击（测「这只宝可梦」不限战斗场）
BENCH_HIT_DOC = parse_card_doc("""
card:
  name_group: 狙击手
effects:
  - trigger: on_attack
    attack: 狙击
    actions:
      - {action: damage, selector: opponent_bench, choose: 1, args: {amount: 40}}
""")

# 白板复制（测 copy_attack whiteboard 路径守卫落点）
COPYDOC = parse_card_doc("""
card:
  name_group: 复制兽
effects:
  - trigger: on_attack
    attack: 复制
    actions:
      - {action: copy_attack, selector: opponent_active_attack, choose: 1}
""")


def gate_mon() -> CardDef:
    return CardDef(card_id="stub-门兽", name="门兽", supertype="pokemon",
                   hp=100, stage=0,
                   attacks=(AttackDef(name="门招", cost=("无",), damage=10),),
                   retreat_cost=1)


def shield_card() -> CardDef:
    return CardDef(card_id="stub-盾兽", name="盾兽", supertype="pokemon",
                   hp=200, stage=0, energy_type="无",
                   attacks=(AttackDef(name="盾击", cost=("无",), damage=50),),
                   retreat_cost=1)


def shield_mon(iid: int = 1) -> InPlayPokemon:
    return in_play(iid, shield_card(), 1)


def typed_mon(iid: int, name: str, energy_type: str, *,
              damage: int = 20, cost: int = 1,
              attacks: tuple[AttackDef, ...] | None = None) -> InPlayPokemon:
    card = CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=100, stage=0, energy_type=energy_type,
                   attacks=attacks or (AttackDef(name="打击", cost=("无",) * cost, damage=damage),),
                   retreat_cost=1)
    return in_play(iid, card, cost)


def game(*, p0_active: InPlayPokemon | None = None,
         p1_active: InPlayPokemon | None = None,
         p0_bench: tuple[InPlayPokemon, ...] = (),
         turn: int = 2, current: int = 0):
    state = main_state(p1_active_energies=1)
    p0 = state.players[0].model_copy(update={
        "active": p0_active or state.players[0].active,
        "bench": p0_bench,
    })
    p1 = state.players[1].model_copy(update={
        "active": p1_active or state.players[1].active,
    })
    state = state.model_copy(update={
        "players": (p0, p1), "turn": turn, "current_player": current,
    })
    e = engine_at(state)
    e.card_effects = {
        "门兽": GATEDOC, "群兽": BENCHDOC, "盾兽": SHIELDDOC,
        "打击兽": DSL_HIT_DOC, "狙击手": BENCH_HIT_DOC, "复制兽": COPYDOC,
    }
    return e


# ── D-138-1 红测 ───────────────────────────────────────────────────────────


def test_usage_gate_后攻最初回合不枚举() -> None:
    e = game(p1_active=in_play(2, gate_mon(), 1), turn=1, current=1)
    assert all(a.kind != "attack" for a in e.legal_actions(1))


def test_usage_gate_后攻第二回合起枚举() -> None:
    e = game(p1_active=in_play(2, gate_mon(), 1), turn=3, current=1)
    assert any(a.kind == "attack" for a in e.legal_actions(1))


def test_usage_gate_词求值四象限() -> None:
    """turn==1 且行动方 != first_player = 后攻玩家最初回合（turn 计数仅在
    先攻方回合开始递增，故 turn==1 覆盖双方各自最初回合；先攻最初回合
    另有全局首回合禁攻，门求值本身对 first_player 为假）。"""
    e = game(p1_active=in_play(2, gate_mon(), 1), turn=1, current=1)
    assert e._usage_gate_banned(1, "second_player_first_turn") is True
    assert e._usage_gate_banned(0, "second_player_first_turn") is False
    e.state = e.state.model_copy(update={"turn": 2})
    assert e._usage_gate_banned(1, "second_player_first_turn") is False
    with pytest.raises(DslError):
        e._usage_gate_banned(1, "bogus_gate")


def test_usage_gate_直接驱动报非法() -> None:
    e = game(p1_active=in_play(2, gate_mon(), 1), turn=1, current=1)
    with pytest.raises(IllegalActionError):
        e.apply(1, Action(kind="attack", attack_index=0))


def test_usage_gate_非on_attack触发_装载报错() -> None:
    with pytest.raises(DslError):
        parse_card_doc("""
card:
  name_group: 坏门
effects:
  - trigger: on_play
    usage_gate: second_player_first_turn
    actions:
      - {action: draw, selector: own_deck, count: 1}
""")


def test_usage_gate_词表外词_装载报错() -> None:
    with pytest.raises(DslError):
        parse_card_doc("""
card:
  name_group: 坏门
effects:
  - trigger: on_attack
    attack: 门招
    usage_gate: bogus_gate
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 10}}
""")


# ── D-138-2 红测 ───────────────────────────────────────────────────────────


def swarm_mon() -> InPlayPokemon:
    card = CardDef(card_id="stub-群兽", name="群兽", supertype="pokemon",
                   hp=100, stage=0,
                   attacks=(AttackDef(name="群击", cost=("无",), damage=30),),
                   retreat_cost=1)
    return in_play(1, card, 1)


def test_bench_count_own_按己方备战数量取值() -> None:
    bench = (typed_mon(60, "备1", "雷"), typed_mon(61, "备2", "雷"),
             typed_mon(62, "备3", "雷"))
    e = game(p0_active=swarm_mon(), p1_active=typed_mon(2, "靶兽", "雷"),
             p0_bench=bench)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 90  # 3 × 30（靶 100HP 不昏厥）


def test_bench_count_own_零备战为0伤害() -> None:
    e = game(p0_active=swarm_mon())
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 0


def test_bench_count_own_装载走counters词表() -> None:
    with pytest.raises(DslError):
        parse_card_doc("""
card:
  name_group: 错词兽
effects:
  - trigger: on_attack
    attack: 群击
    actions:
      - {action: damage, selector: opponent_active, count: bench_count_ownn, args: {op: "×", per: 30}}
""")


# ── D-138-3 红测 ───────────────────────────────────────────────────────────


def _shield_game(**kw):
    return game(p0_active=shield_mon(), **kw)


def test_盾_基础非无攻击伤害归零() -> None:
    e = _shield_game(p1_active=typed_mon(2, "雷兽", "雷"))
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50
    assert e.state.players[0].active.attack_shield is not None
    e.apply(1, Action(kind="attack", attack_index=0))  # 对手回合：基础雷 → 0
    assert e.state.players[0].active.damage == 0


def test_盾_无属性攻击照常伤害() -> None:
    e = _shield_game(p1_active=typed_mon(2, "无兽", "无"))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))  # 无属性不被来源排除
    assert e.state.players[0].active.damage == 20


def test_盾_一阶进化攻击照常伤害() -> None:
    s1 = CardDef(card_id="stub-进化兽", name="进化兽", supertype="pokemon",
                 hp=120, stage=1, evolves_from="幼兽", energy_type="雷",
                 attacks=(AttackDef(name="打击", cost=("无", "无"), damage=40),),
                 retreat_cost=2)
    e = _shield_game(p1_active=in_play(2, s1, 2))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))  # 1 阶 ≠ 基础 → 照伤
    assert e.state.players[0].active.damage == 40


def test_盾_DSL路径伤害原语守卫() -> None:
    p1 = typed_mon(2, "打击兽", "雷",
                   attacks=(AttackDef(name="打击", cost=("无",), damage=40),))
    e = _shield_game(p1_active=p1)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))  # DSL damage 落点同守
    assert e.state.players[0].active.damage == 0


def test_盾_备战落点同样免疫() -> None:
    # 盾在 p0 备战（卡面「这只宝可梦」不限战斗场）
    shielded = shield_mon(70).model_copy(update={
        "attack_shield": (2, 0, 2, 0, ("无",))})
    p1 = typed_mon(2, "狙击手", "雷",
                   attacks=(AttackDef(name="狙击", cost=("无",), damage=40),))
    e = game(p0_active=in_play(1, basic("前台"), 1),
             p1_active=p1, p0_bench=(shielded,), current=1)
    e.apply(1, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"
    e.apply(1, Action(kind="choose", choices=(70,)))
    assert e.state.players[0].bench[0].damage == 0


def test_盾_白板复制路径守卫() -> None:
    # p0 战斗场 = 携带预设盾标记的白板雷兽；p1 复制其招式结算
    host = typed_mon(1, "雷兽", "雷").model_copy(update={
        "attack_shield": (2, 0, 2, 0, ("无",))})
    p1 = typed_mon(2, "复制兽", "雷",
                   attacks=(AttackDef(name="复制", cost=("无",), damage=None),))
    e = game(p0_active=host, p1_active=p1, current=1)
    e.apply(1, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="choose", choices=(0,)))  # 复制「打击」白板结算
    assert e.state.players[0].active.damage == 0


def test_盾_对手回合结束清除() -> None:
    e = _shield_game(p1_active=typed_mon(2, "雷兽", "雷"))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))
    # 对手（p1）回合已结束 → 盾清除；p0 回合开始
    assert e.state.current_player == 0
    assert e.state.players[0].active.attack_shield is None


def test_盾_失效后对手攻击照常() -> None:
    e = _shield_game(p1_active=typed_mon(2, "雷兽", "雷"))
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(1, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="end_turn"))
    e.apply(1, Action(kind="attack", attack_index=0))
    assert e.state.players[0].active.damage == 20  # 盾已过期，雷兽 20 照算


def test_盾_后攻施加_生效窗口下一个先攻回合() -> None:
    # p1（后攻）盾兽在 turn==1 施加 → expiry_turn=2；p0 的 turn==2 回合内
    # 生效（p0 攻击方 = 基础雷兽，非无属性 → 被免疫）
    e = game(p0_active=typed_mon(1, "雷兽", "雷"), p1_active=shield_mon(2),
             turn=1, current=1)
    e.apply(1, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.attack_shield == (1, 1, 2, 0, ("无",))
    e.apply(0, Action(kind="attack", attack_index=0))  # p0 基础雷被免疫
    assert e.state.players[1].active.damage == 0


def test_盾_args校验_执行期不猜() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏盾
effects:
  - trigger: on_attack
    attack: 盾击
    actions:
      - {action: prevent_attack_damage, selector: self, args: {timing: bogus, attacker_stage: basic}}
""")
    e = game(p0_active=shield_mon())
    ctx = ExecutionContext(e, 0, e.state.players[0].active.current,
                           "test", "on_attack")
    with pytest.raises(DslError):
        run_effect(ctx, bad.effects[0])


def test_盾_args校验_selector必须self() -> None:
    bad = parse_card_doc("""
card:
  name_group: 坏盾
effects:
  - trigger: on_attack
    attack: 盾击
    actions:
      - {action: prevent_attack_damage, selector: opponent_active, args: {timing: opponent_next_turn}}
""")
    e = game(p0_active=shield_mon())
    ctx = ExecutionContext(e, 0, e.state.players[0].active.current,
                           "test", "on_attack")
    with pytest.raises(DslError):
        run_effect(ctx, bad.effects[0])
