"""task 026 WP3：own_evolve_from_hand 事件分发（_do_evolve 挂点，猫头夜鹰机制）。

分发点 = _do_evolve（主阶段从手牌进化行动）入口；复用 WP2 触发分发公共函数
（condition 门控 / 同卡同事件多个 → DslError / completion="ability" 本体不弃置）。

用户裁决（2026-09-07，取代 D-WP3-2 待核口径）：触发条件「将这张卡牌从手牌使出
并进行进化时」的判定关键 = 进化卡本身从手牌使出——
- 主阶段从手牌进化（_do_evolve）→ 触发（直发，不入队）
- 神奇糖果跳阶（evolve skip_stage，_apply_evolution zone="hand"）→ 触发
  （原语内入队 pending_event_triggers，效果完成后由 _run_or_suspend 完成路径排水）
- 招式学习器「进化」（from_deck，zone="deck"，进化卡不经过手牌）→ 不触发
setup 无进化行动天然不触发。排水时来源已不在场上 → 跳过不发动（离场即失效）。
"""

import pytest
from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

OWL_DOC = parse_card_doc("""
card:
  name_group: 猫头夜鹰
effects:
  - trigger: trigger_on_event
    event: own_evolve_from_hand
    condition: own_tera_in_play
    actions:
      - {action: search_deck, selector: own_deck, filters: [trainer], choose: 2, destination: hand}
      - {action: reveal, selector: own_hand, filters: [trainer]}
      - {action: shuffle_deck}
""")

OWL_DOUBLE_DOC = parse_card_doc("""
card:
  name_group: 猫头夜鹰
effects:
  - trigger: trigger_on_event
    event: own_evolve_from_hand
    actions:
      - {action: draw, count: 1}
  - trigger: trigger_on_event
    event: own_evolve_from_hand
    actions:
      - {action: draw, count: 2}
""")

CANDY_DOC = parse_card_doc("""
card:
  name_group: 神奇糖果
effects:
  - trigger: on_play
    actions:
      - {action: evolve, selector: own_hand, choose: 1, filters: [stage2_pokemon], args: {mode: skip_stage}}
""")

LEARNER_DOC = parse_card_doc("""
card:
  name_group: 招式学习器 进化
effects:
  - trigger: passive_static
    actions:
      - {action: grant_attack, args: {attack: 进化, discard_at_turn_end: true}}
  - trigger: on_attack
    attack: 进化
    actions:
      - {action: evolve, selector: own_bench, choose: 2, args: {mode: from_deck}}
      - {action: shuffle_deck}
""")

DRAW_DOC = parse_card_doc("""
card:
  name_group: 测试抽牌
effects:
  - trigger: on_play
    actions:
      - {action: draw, count: 1}
""")


def hoothoot(chain: str | None = None) -> CardDef:
    return CardDef(card_id="stub-咕咕", name="咕咕", supertype="pokemon",
                   hp=70, stage=0, evolution_chain=chain)


def noctowl(name: str = "猫头夜鹰", chain: str | None = None,
            stage: int = 1, evolves_from: str = "咕咕") -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon", hp=100,
        stage=stage, evolves_from=evolves_from, evolution_chain=chain,
        attacks=(AttackDef(name="高速之翼", cost=("无", "无"), damage=60),),
    )


def tera_mon(name: str = "太晶兽") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=120, stage=0, is_tera=True)


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def learner_tool() -> CardDef:
    return CardDef(card_id="stub-招式学习器 进化", name="招式学习器 进化",
                   supertype="trainer", trainer_subtype="宝可梦道具",
                   attacks=(AttackDef(name="进化", cost=("无",), damage=None),))


def candy_engine(*, active_card, deck):
    """main 阶段（turn=2）：p0 备战区同链基础（iid 70），手牌含神奇糖果（iid 60）+
    合成 stage2 猫头夜鹰 stub（iid 61；真实卡为 1 阶，此处仅为挂文档的机制合成）。"""
    owl_s2 = noctowl(name="猫头夜鹰", chain="X", stage=2, evolves_from="中鸟")
    state = main_state(p0_extra_hand=(inst(60, item_card("神奇糖果")), inst(61, owl_s2)))
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active_card),
        "bench": (in_play(70, hoothoot(chain="X")),),
        "deck": deck,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"神奇糖果": CANDY_DOC, "猫头夜鹰": OWL_DOC}
    return e


def evolve_engine(*, doc=OWL_DOC, active_card=None, extra_hand: tuple = (), deck=None):
    """main 阶段（turn=2）：p0 备战区有咕咕（iid 70），手牌含进化卡（iid 60）。"""
    state = main_state(p0_extra_hand=(inst(60, noctowl()),) + extra_hand)
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, active_card if active_card is not None else tera_mon()),
        "bench": (in_play(70, hoothoot()),),
    })
    if deck is not None:
        p0 = p0.model_copy(update={"deck": deck})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"猫头夜鹰": doc}
    return e


def trainer_deck():
    return (inst(110, item_card("测试物品甲")), inst(111, item_card("测试物品乙"))) + tuple(
        inst(100 + i, basic("妙蛙种子")) for i in range(8)
    )


def test_evolve_from_hand_triggers_with_condition_met():
    """主阶段从手牌进化 + own_tera_in_play 满足 → 触发：检索训练家 → reveal → 洗牌，
    可挂起（chooser），完成后回主阶段；进化卡本体压栈顶（不弃置）。"""
    e = evolve_engine(deck=trainer_deck())
    e.apply(0, Action(kind="evolve", iid=60, target_iid=70))
    assert e.state.phase == "choice"  # 检索挂起
    kinds = [ev.kind for ev in e.events]
    assert kinds.index("evolve") < kinds.index("trigger_on_event")
    trig = next(ev for ev in e.events if ev.kind == "trigger_on_event")
    assert trig.detail["event"] == "own_evolve_from_hand"
    assert trig.detail["iid"] == 60 and trig.detail["name"] == "猫头夜鹰"
    pc = e.state.pending_choice
    assert pc is not None and pc.pool_iids == (110, 111)  # 仅训练家进池
    e.apply(0, Action(kind="choose", choices=(110, 111)))
    reveal = next(ev for ev in e.events if ev.kind == "reveal")
    assert reveal.detail["iids"] == [110, 111]
    assert reveal.detail["names"] == ["测试物品甲", "测试物品乙"]
    assert e.state.phase == "main" and e.state.current_player == 0
    p0 = e.state.players[0]
    assert p0.bench[0].current.iid == 60  # 猫头夜鹰压咕咕栈顶
    assert {110, 111} <= {c.iid for c in p0.hand}
    assert 60 not in [c.iid for c in p0.discard]  # 本体不弃置


def test_evolve_condition_not_met_no_fire():
    """condition own_tera_in_play 不满足（场上无太晶）→ 进化照常、特性不发动。"""
    e = evolve_engine(active_card=basic("妙蛙种子"), deck=trainer_deck())
    e.apply(0, Action(kind="evolve", iid=60, target_iid=70))
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
    assert not [ev for ev in e.events if ev.kind == "reveal"]
    assert e.state.players[0].bench[0].current.iid == 60  # 进化本身生效
    assert [c.iid for c in e.state.players[0].hand] == [50, 51]


def test_multiple_same_event_effects_dsl_error():
    """一张卡多个 own_evolve_from_hand 效果 → DslError（不猜，需要时再扩展顺序分发）。"""
    e = evolve_engine(doc=OWL_DOUBLE_DOC)
    with pytest.raises(DslError, match="trigger_on_event"):
        e.apply(0, Action(kind="evolve", iid=60, target_iid=70))


def test_dsl_evolve_skip_stage_from_hand_triggers():
    """用户裁决（2026-09-07）：神奇糖果跳阶（zone="hand"）进化卡从手牌使出 → 触发。

    机制测试用合成 stage2 stub 挂猫头夜鹰文档（真实猫头夜鹰为 1 阶，其神奇糖果
    路径不存在；触发语义 = 「进化卡从手牌使出」，与阶段数无关）。触发经
    pending_event_triggers 入队、效果完成后排水：检索挂起 → choose 恢复 →
    回我方主阶段；神奇糖果本体已进弃牌区。
    """
    e = candy_engine(active_card=tera_mon(), deck=trainer_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(61,)))  # 段1：手牌 stage2
    e.apply(0, Action(kind="choose", choices=(70,)))  # 段2：同链基础目标
    # 糖果效果完成后排水 → 触发寻找宝石：检索训练家挂起
    assert e.state.phase == "choice"
    kinds = [ev.kind for ev in e.events]
    assert kinds.index("evolve") < kinds.index("trigger_on_event")
    trig = next(ev for ev in e.events if ev.kind == "trigger_on_event")
    assert trig.detail["event"] == "own_evolve_from_hand"
    assert trig.detail["iid"] == 61 and trig.detail["name"] == "猫头夜鹰"
    e.apply(0, Action(kind="choose", choices=(110, 111)))
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.current_player == 0
    assert p0.bench[0].current.iid == 61  # 进化已生效
    assert 60 in [c.iid for c in p0.discard]  # 糖果本体进弃牌区
    assert 61 not in [c.iid for c in p0.discard]  # 特性卡本体不弃置
    assert {110, 111} <= {c.iid for c in p0.hand}
    assert e.state.pending_event_triggers == ()  # 队列已排空


def test_candy_skip_stage_condition_not_met_no_fire():
    """裁决口径：入队但 condition（own_tera_in_play）不满足 → 排水时门控不发动。"""
    e = candy_engine(active_card=basic("妙蛙种子"), deck=trainer_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(61,)))
    e.apply(0, Action(kind="choose", choices=(70,)))
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
    assert not [ev for ev in e.events if ev.kind == "reveal"]
    assert e.state.players[0].bench[0].current.iid == 61  # 进化本身生效
    assert [c.iid for c in e.state.players[0].hand] == [50, 51]  # 检索未执行
    assert e.state.pending_event_triggers == ()


def test_learner_from_deck_does_not_trigger():
    """裁决回归锁定：招式学习器「进化」（from_deck，进化卡不经过手牌）→ 不触发。"""
    owl = noctowl()  # 1 阶 evolves_from 咕咕（牌库中，iid 300）
    holder = in_play(1, basic("妙蛙种子"), 1).model_copy(update={
        "attached_tool": inst(90, learner_tool()),
    })
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": holder,
        "bench": (in_play(70, hoothoot()),),
        "deck": (inst(300, owl),) + state.players[0].deck,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"招式学习器 进化": LEARNER_DOC, "猫头夜鹰": OWL_DOC}
    attacks = [a for a in e.legal_actions(0) if a.kind == "attack"]
    e.apply(0, next(a for a in attacks if a.attack_index == 1))  # 授予招式「进化」
    e.apply(0, Action(kind="choose", choices=(70,)))   # 段1：备战区目标
    e.apply(0, Action(kind="choose", choices=(300,)))  # 段2：牌库中的进化形态
    assert any(ev.kind == "evolve" and ev.detail["iid"] == 300 for ev in e.events)
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
    assert e.state.pending_event_triggers == ()
    assert e.state.players[0].bench[0].current.iid == 300  # 进化本身生效
    # 攻击结算完回合推进给对手
    assert e.state.phase == "main" and e.state.current_player == 1


def test_stale_event_trigger_entry_skipped():
    """排水时来源已不在场上 → 跳过不发动、不炸，队列清空，流程照常收尾（离场即失效）。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("测试抽牌")),))
    state = state.model_copy(update={
        "pending_event_triggers": ((0, 999, "own_evolve_from_hand"),),  # 999 不在场上
    })
    e = engine_at(state)
    e.card_effects = {"测试抽牌": DRAW_DOC}
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
    assert e.state.pending_event_triggers == ()
    assert [c.iid for c in e.state.players[0].hand] == [50, 51, 100]  # draw 1 正常执行


def test_setup_phase_has_no_evolve_action():
    """setup 阶段无进化行动（天然不触发，清单14 前半）：布阵阶段合法行动仅放置/确认。"""
    state = main_state(p0_extra_hand=(inst(60, noctowl()),))
    state = state.model_copy(update={"phase": "setup_bench"})
    e = engine_at(state)
    e.card_effects = {"猫头夜鹰": OWL_DOC}
    kinds = {a.kind for a in e.legal_actions(0)}
    assert "evolve" not in kinds
