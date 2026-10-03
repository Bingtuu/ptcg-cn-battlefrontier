"""task 033 WP1（D-033-1）：damage opponent_active 空战斗场 no-op。

触发场景（M6 12 局 / M8b 18 局失败同一形态，spy 复现 seed 100052）：古玉鱼
嫉妒业火首 damage 节点昏厥对手战斗场（promote_queue 排队、换上推迟到效果
完成，D-WP2-1）→ 同效果后续 damage opponent_active 读空战斗场。
口径：追加伤害作用于已昏厥的原目标（不存在）→ 节点空结算；WP4 宣言裁决
（落点空不阻却、无法执行部分 no-op）+ D-029-4 备战空 no-op 同型先例。
"""

from helpers import basic, engine_at, in_play, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

TWO_HIT_DOC = parse_card_doc("""
card:
  name_group: 双段手
effects:
  - trigger: on_attack
    attack: 双段击
    actions:
      - {action: damage, selector: opponent_active, args: {amount: 9999}}
      - {action: damage, selector: opponent_active, args: {amount: 10}}
""")


def double_hitter() -> CardDef:
    return CardDef(
        card_id="stub-双段手", name="双段手", supertype="pokemon", hp=120, stage=0,
        attacks=(AttackDef(name="双段击", cost=("无",), damage=10),),
    )


def ko_then_empty_engine():
    """p0 双段手（1 能量已附）vs p1 战斗场脆皮（HP 50）+ 备战 1 只。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, double_hitter(), 1),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("脆皮", hp=50), 0),
        "bench": (in_play(3, basic("备胎"), 0),),
    })
    engine = engine_at(state.model_copy(update={"players": (p0, p1)}))
    engine.card_effects = {"双段手": TWO_HIT_DOC}
    return engine


def test_second_damage_node_noop_on_empty_active() -> None:
    """首节点昏厥 → 次节点 damage opponent_active 空战斗场 no-op 不抛错；
    事件流落 reason=no_targets；换上走队列（效果完成后）。"""
    e = ko_then_empty_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    prims = [
        ev for ev in e.events
        if ev.kind == "effect_primitive" and ev.detail.get("action") == "damage"
    ]
    assert len(prims) == 2
    first, second = (p.detail["result"] for p in prims)
    assert first["final"] == 9999
    assert second["final"] == 0 and second["reason"] == "no_targets"
    assert second["target"] is None
    # 换上队列：效果完成后 p1 选备战换上（phase=promote 类）
    assert e.state.players[1].active is None
    promote_acts = [a for a in e.legal_actions(1) if a.kind == "promote"]
    assert promote_acts
    e.apply(1, promote_acts[0])
    assert e.state.players[1].active is not None
    assert e.state.phase == "main" and e.state.current_player == 1  # 回合权正常移交


def test_empty_active_noop_does_not_knockout_check() -> None:
    """no-op 节点不触发昏厥结算（备胎不因 10 伤害节点受伤）。"""
    e = ko_then_empty_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].bench[0].damage == 0
