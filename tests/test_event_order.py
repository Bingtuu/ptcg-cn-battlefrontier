"""task 108：事件序观感债修复——招式效果窗口内昏厥/拿奖事件滞后冲刷。

问题（task 063/064 单列观感债）：招式带 on_attack DSL 效果且造成昏厥时，旧序为
attack → effect_start → knockout → take_prize → effect_primitive ×n → effect_end ——
同一招式的文本效果事件排在昏厥/拿奖之后，回放阅读顺序违背因果。

新序（本文件锁定）：招式效果链内产生的 knockout / take_prize / prize_bonus /
game_over 事件入缓冲，attack completion 收尾（effect_end 之后）统一冲刷：
attack → effect_start → [damage / effect_primitive …] → effect_end → knockout →
take_prize → …。状态结算时点一律不变（task 026 WP2 / D-WP2-1 / task 064 定案），
只动事件发射顺序；窗口外（无 DSL 招式 / 混乱自伤 / 训练家·特性·场馆效果）零变化。
"""

from helpers import engine_at, inst
from test_attack import battle, energies, mon

from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, InPlayPokemon

# 伤害 + 伤害后追加原语（clear_status）：既覆盖「造成昏厥的招式自身带效果」主场景，
# 其 effect_primitive 事件又必须在 knockout 之前（因果序）。
SMITE_DOC = parse_card_doc("""
card:
  name_group: 重击兽
effects:
  - trigger: on_attack
    attack: 破甲重击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 200}}
      - {action: clear_status, selector: self}
""")

# 伤害 + choose 挂起原语：覆盖「窗口内先昏厥、后挂起、再恢复」的跨挂起冲刷。
SUSPEND_DOC = parse_card_doc("""
card:
  name_group: 重击兽
effects:
  - trigger: on_attack
    attack: 破甲重击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 200}}
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 10}}
""")


def striker(doc, *, bench: bool):
    """p0 战斗场 = 重击兽（1 无能量），p1 战斗场 hp200；bench=True 时 p1 有备战（不判负）。"""
    card = mon("重击兽", attacks=(AttackDef(name="破甲重击", cost=("无",), damage=200),),
               hp=120)
    p1_bench = (InPlayPokemon(stack=(inst(3, mon("厚皮兽", hp=90)),)),) if bench else ()
    e = engine_at(battle(
        InPlayPokemon(stack=(inst(1, card),), attached_energy=energies("无")),
        InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=200)),)),
        p1_bench=p1_bench,
    ))
    e.card_effects = {card.name: doc}
    return e


def kinds(e):
    return [ev.kind for ev in e.events]


def test_ko_events_flushed_after_attack_effect_end() -> None:
    """招式效果窗口内昏厥：knockout/take_prize 滞后到 effect_end 之后（因果序）。"""
    e = striker(SMITE_DOC, bench=True)
    e.apply(0, Action(kind="attack", attack_index=0))
    ks = kinds(e)
    i_start = ks.index("effect_start")
    i_end = ks.index("effect_end")
    i_ko = ks.index("knockout")
    i_prize = ks.index("take_prize")
    # 招式的追加效果原语在昏厥之前
    assert i_start < i_end < i_ko < i_prize
    # 昏厥块在效果链收尾处：knockout 之前是 effect_end
    assert ks[i_ko - 1] == "effect_end"
    # 状态 settlement 时点不变：奖赏已被拿走（事件滞后 ≠ 结算滞后）
    assert len(e.state.players[0].prizes) == 5
    # 事件多重集不变：每个 kind 各出现一次（缓冲不丢不重）
    assert ks.count("knockout") == 1 and ks.count("take_prize") == 1


def test_ko_events_flushed_before_game_over() -> None:
    """窗口内拿完奖终局：game_over 事件排在缓冲的 knockout/take_prize 之后。"""
    e = striker(SMITE_DOC, bench=False)
    # 只留 1 张奖赏：拿完即胜（胜利条件①）发生在效果窗口内
    p0 = e.state.players[0]
    e.state = e.state.model_copy(update={
        "players": (p0, e.state.players[1].model_copy(update={
            "prizes": e.state.players[1].prizes[:1],
        })),
    })
    e.apply(0, Action(kind="attack", attack_index=0))
    ks = kinds(e)
    assert e.state.phase == "game_over"
    assert ks.index("knockout") < ks.index("take_prize") < ks.index("game_over")
    # game_over 前紧邻的是 take_prize（因果链完整）
    assert ks[ks.index("game_over") - 1] == "take_prize"


def test_ko_events_buffered_across_suspend_resume() -> None:
    """窗口内先昏厥后挂起：恢复前 knockout 不在事件流（缓冲中），恢复后一次性冲刷。"""
    e = striker(SUSPEND_DOC, bench=True)
    e.apply(0, Action(kind="attack", attack_index=0))
    # 挂起态：昏厥状态已 settlement，但 knockout 事件尚未入流
    assert e.state.phase == "choice"
    assert e.state.players[1].active is None
    assert "knockout" not in kinds(e)
    # 恢复效果链 → completion 收尾冲刷
    choose = next(a for a in e.legal_actions(0) if a.kind == "choose")
    e.apply(0, choose)
    ks = kinds(e)
    assert ks.index("effect_end") < ks.index("knockout") < ks.index("take_prize")
    assert ks.count("knockout") == 1


def test_plain_attack_ko_order_unchanged() -> None:
    """窗口外（无 DSL 绑定招式）昏厥：knockout 紧跟 attack 事件，旧序不变。"""
    e = striker(None, bench=True)
    e.apply(0, Action(kind="attack", attack_index=0))
    ks = kinds(e)
    i_atk = ks.index("attack")
    i_ko = ks.index("knockout")
    # 旧序：attack → …（无 effect_start/effect_end）→ knockout
    assert i_atk < i_ko
    assert "effect_start" not in ks and "effect_end" not in ks
    assert ks.index("take_prize") > i_ko


# ── 排水内层帧回归（task 108 开发期 replay 抽查实证漏洞）────────────────────

from helpers import basic, energy, in_play  # noqa: E402  (放尾部避免与顶部 helpers 导入冲突观感)
from test_primitives_wp6 import CACTUS_DOC, attack_engine, cactus  # noqa: E402

COUNTER_DOC = parse_card_doc("""
card:
  name_group: 攻击兽
effects:
  - trigger: on_attack
    attack: 打击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 100}}
      - {action: clear_status, selector: self}
""")


def test_drain_inner_frame_ko_events_not_lost() -> None:
    """窗口内「昏厥 → 排水反伤再昏厥」：排水内层帧的昏厥事件一块不丢。

    replay 抽查（gard-zoro 种子 300003）曾抓到：排水内层（反伤 completion 帧）
    在 attack 完成段冲刷点之后才产生昏厥事件，初版实现无补冲关口 → 整块丢失。
    现由包装层 finally 深度 0 + 未挂起关口补冲。次序：仙人掌昏厥（完成段冲刷）
    → 反伤触发事件 → 攻击兽昏厥（深度 0 补冲）。
    """
    card = mon("攻击兽", attacks=(AttackDef(name="打击", cost=("无",), damage=100),),
               hp=60)
    e = attack_engine(
        COUNTER_DOC, card,
        p0_energies=(inst(9001, energy()),),
        p0_bench=(InPlayPokemon(stack=(inst(90, basic("己方备战")),)),),
        p1_active=in_play(2, cactus(hp=50)),
        p1_bench=(in_play(80, basic("对手备战")),),
        extra_effects={"沙铃仙人掌": CACTUS_DOC},
    )
    e.apply(0, Action(kind="attack", attack_index=0))
    ks = kinds(e)
    ko_idx = [i for i, k in enumerate(ks) if k == "knockout"]
    assert len(ko_idx) == 2  # 仙人掌 + 攻击兽，一块不丢
    i_trig = ks.index("trigger_on_event")
    assert ko_idx[0] < i_trig < ko_idx[1]
    assert e.state.players[0].active is None
    assert e.state.phase == "promote"
