"""task 064：check_knockouts wipe 检查跨扫描补检（promote 空场判平修复）。

规则出处：rules-manual §8 胜利条件②（对手战斗宝可梦昏厥且备战区无可换上 → 胜）；
判定时点 = 昏厥结算点立即判（与条件①拿完奖赏同点位；附录 A ko_self 同口径先例
与 2026-08-30 bounce 判负决议；task 064 决议 ✅ 已核 2026-10-21）。换上仍推迟到效果完成后
（D-WP2-1）——判负时点与换上时点分离。

背景（task 063 诊断）：战斗场与备战在同一效果链的不同扫描被分别清空时，旧实现
wipe 检查只嵌在「本扫描内战斗场昏厥」分支 → 漏检 → 残留 promote_queue → 翻
promote 阶段备战空 → legal_actions 空 → runner 判平（m9 247 局 / v2 90 局，
no_legal_actions 类别 100% 归因；实例 m9 game 5306 seed 105305）。
"""

from helpers import basic, engine_at, inst
from test_attack import battle, energies, mon

from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef, InPlayPokemon

# 5306 形态：战斗场伤害 + 备战铺伤同链（幻影潜袭结构）
SWEEP_DOC = parse_card_doc("""
card:
  name_group: 扫荡兽
effects:
  - trigger: on_attack
    attack: 幻影横扫
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 100}}
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 6}}
""")


def sweeper() -> CardDef:
    return mon("扫荡兽", attacks=(AttackDef(name="幻影横扫", cost=("无",), damage=100),))


def _sweep_engine() -> "object":
    """p0 扫荡兽（1 能）vs p1 战斗场 100HP + 备战 60HP（100 昏厥 + 6 指示物昏厥）。"""
    state = battle(
        InPlayPokemon(stack=(inst(1, sweeper()),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=100)),)),
        p1_bench=(InPlayPokemon(stack=(inst(3, basic("波波", hp=60)),)),),
    )
    e = engine_at(state)
    e.card_effects = {"扫荡兽": SWEEP_DOC}
    return e


# ── 组 1：战斗场先昏 + 同链备战清空（跨扫描 wipe，5306 形态）─────────────────

def test_cross_scan_wipe_is_loss_not_promote_deadlock():
    """同一招式效果链内战斗场先昏厥（备战尚存 → 入队推迟换上）、随后备战被指示物
    清空：wipe 检查跨扫描补检 → §8 胜利条件②判负（不再落入 promote 空备战死锁
    → runner 判平）。"""
    e = _sweep_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    # damage 节点 KO 战斗场：备战尚在 → 入队不翻阶段（D-WP2-1），指示物节点选择挂起
    assert e.state.phase == "choice"
    assert e.state.promote_queue == (1,)
    e.apply(0, Action(kind="choose", choices=(3,)))  # 6 指示物清空备战（60 昏厥）
    # 扫描结束全场空检：p1 战斗场（前扫描昏厥）+ 备战（本扫描昏厥）均无宝可梦 → 判负
    assert e.state.phase == "game_over"
    assert e.state.winner == 0 and not e.state.is_draw
    over = next(ev for ev in e.events if ev.kind == "game_over")
    assert over.detail["reason"] == "no_pokemon"


# ── 组 2：双方同时清空（跨扫描双方 wipe → 平局）─────────────────────────────

DOUBLE_SWEEP_DOC = parse_card_doc("""
card:
  name_group: 自爆扫荡兽
effects:
  - trigger: on_attack
    attack: 同归
    actions:
      - {action: place_damage_counters, selector: own_active, args: {counters: 10}}
      - {action: place_damage_counters, selector: all_pokemon_both, args: {counters: 10}}
""")


def test_cross_scan_double_wipe_is_draw():
    """效果链节点 1 自伤昏厥自己战斗场（备战尚存 → 入队），节点 2 全场铺伤同时
    清空自己备战与对手战斗场（对手备战空）：跨扫描双方场上均无宝可梦 → 平局
    （§8 同时胜利口径）。"""
    attacker = mon("自爆扫荡兽", hp=100,
                   attacks=(AttackDef(name="同归", cost=("无",), damage=None),))
    state = battle(
        InPlayPokemon(stack=(inst(1, attacker),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=100)),)),
    )
    p0 = state.players[0].model_copy(update={
        "bench": (InPlayPokemon(stack=(inst(3, basic("小拉达")),)),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"自爆扫荡兽": DOUBLE_SWEEP_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "game_over"
    assert e.state.is_draw and e.state.winner is None
    over = next(ev for ev in e.events if ev.kind == "game_over")
    assert over.detail["reason"] == "no_pokemon"


# ── 组 3：效果中途判负时点（后续节点不执行）──────────────────────────────────

SWEEP_THEN_DRAW_DOC = parse_card_doc("""
card:
  name_group: 扫荡兽
effects:
  - trigger: on_attack
    attack: 幻影横扫
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 100}}
      - {action: place_damage_counters, selector: opponent_pokemon_any, choose: 1, args: {counters: 6}}
      - {action: draw, count: 2}
""")


def test_cross_scan_wipe_game_over_mid_effect_skips_remaining_nodes():
    """判负时点 = 昏厥结算点（效果中途）立即判：wiping 链后的 draw 节点不执行
    （对拍 test_run_effect_breaks_on_game_over 的 prizes 判负形态）。"""
    e = _sweep_engine()
    e.card_effects = {"扫荡兽": SWEEP_THEN_DRAW_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(3,)))
    assert e.state.phase == "game_over" and e.state.winner == 0
    prims = [ev.detail["action"] for ev in e.events if ev.kind == "effect_primitive"]
    assert prims == ["damage", "place_damage_counters"]  # draw 节点未执行


# ── 回归不变式：战斗场昏厥但备战尚存 → 照旧入队换上（不判负）─────────────────

def test_active_ko_with_bench_still_promotes():
    """跨扫描补检不误伤正常路径：战斗场昏厥、备战未被清空 → 入队换上不判负。"""
    state = battle(
        InPlayPokemon(stack=(inst(1, sweeper()),), attached_energy=energies("超")),
        InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=100)),)),
        p1_bench=(InPlayPokemon(stack=(inst(3, basic("波波", hp=70)),)),),
    )
    e = engine_at(state)
    e.card_effects = {"扫荡兽": SWEEP_DOC}
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(3,)))  # 60 ≤ 70 不昏厥
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase != "game_over"
