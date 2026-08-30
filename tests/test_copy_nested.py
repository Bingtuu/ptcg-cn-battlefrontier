"""task 020：copy_attack 嵌套 chooser（二级挂起帧）。

场景：梦幻ex 基因侵入复制「自身含运行时选择的 DSL 招式」（如吉雉鸡ex 残忍箭矢
选任意对手宝可梦）——外层挂起选招式 → 内层挂起选目标 → 内层完成后外层收尾。
嵌套层级 >1（套娃复制）维持显式 DslError（不猜）。
"""

import hashlib
import json

import pytest
from helpers import basic, engine_at, in_play, main_state

from battlefrontier.agent.heuristic import HeuristicAgent
from battlefrontier.dsl import load_card_dir, parse_card_doc
from battlefrontier.dsl.loader import DslError
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

MEW_DOC = parse_card_doc("""
card:
  name_group: 梦幻ex
effects:
  - trigger: on_attack
    attack: 基因侵入
    actions:
      - {action: copy_attack, selector: opponent_active_attack, choose: 1}
""")

# 外层 copy 节点后还有后续节点（验证内层完成后外层续跑）
MEW_DRAW_DOC = parse_card_doc("""
card:
  name_group: 梦幻ex
effects:
  - trigger: on_attack
    attack: 基因侵入
    actions:
      - {action: copy_attack, selector: opponent_active_attack, choose: 1}
      - {action: draw, count: 1}
""")

# 内层含运行时选择（等价残忍箭矢结构：选任意对手宝可梦造成定量伤害）
SNIPER_DOC = parse_card_doc("""
card:
  name_group: 狙手兽
effects:
  - trigger: on_attack
    attack: 狙击
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 100}}
""")

# 内层同层两个选择节点
DOUBLE_DOC = parse_card_doc("""
card:
  name_group: 双选兽
effects:
  - trigger: on_attack
    attack: 双选
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 50}}
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 30}}
""")

# 套娃构造：被复制招式自身是 copy_attack（嵌套层级 >1）
DOLL_A_DOC = parse_card_doc("""
card:
  name_group: 套娃A
effects:
  - trigger: on_attack
    attack: 镜像A
    actions:
      - {action: copy_attack, selector: opponent_active_attack, choose: 1}
""")
DOLL_B_DOC = parse_card_doc("""
card:
  name_group: 套娃B
effects:
  - trigger: on_attack
    attack: 镜像B
    actions:
      - {action: copy_attack, selector: opponent_active_attack, choose: 1}
""")


def mew() -> CardDef:
    return CardDef(card_id="stub-梦幻ex", name="梦幻ex", supertype="pokemon",
                   hp=180, stage=0, rule_box="ex", energy_type="超",
                   attacks=(AttackDef(name="基因侵入", cost=("无",), damage=None),),
                   retreat_cost=0)


def doll(name: str, attack: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="pokemon",
                   hp=180, stage=0, energy_type="超",
                   attacks=(AttackDef(name=attack, cost=("无",), damage=None),),
                   retreat_cost=0)


def _engine(opp_card: CardDef, opp_doc, mew_doc=MEW_DOC, mew_card: CardDef | None = None,
            extra_docs: dict | None = None):
    state = main_state(p0_active_energies=1)
    p0 = state.players[0].model_copy(update={"active": in_play(1, mew_card or mew(), 1)})
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, opp_card),
        "bench": (in_play(3, basic("备战靶", hp=70)),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {("梦幻ex" if mew_card is None else mew_card.name): mew_doc,
                      opp_card.name: opp_doc, **(extra_docs or {})}
    return e


def _apply_script(e, script):
    for act in script:
        e.apply(e.state.current_player, act)


# ── 嵌套挂起主流程 ───────────────────────────────────────

def test_copy_attack_with_inner_choice():
    e = _engine(CardDef(card_id="stub-狙手兽", name="狙手兽", supertype="pokemon",
                        hp=200, stage=0,
                        attacks=(AttackDef(name="狙击", cost=("无",), damage=None),)),
                SNIPER_DOC)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"  # 外层挂起：选招式
    e.apply(0, Action(kind="choose", choices=(0,)))
    assert e.state.phase == "choice"  # 内层挂起：选目标
    pc = e.state.pending_choice
    assert pc.pool == "opponent_pokemon_any" and sorted(pc.pool_iids) == [2, 3]
    e.apply(0, Action(kind="choose", choices=(2,)))  # 打对手战斗场（狙手兽 hp200 存活）
    assert e.state.phase == "main" and e.state.current_player == 1  # 攻击后回合推进
    assert e.state.players[1].active.damage == 100
    assert e.state.players[1].bench[0].damage == 0
    assert any(ev.kind == "copy_attack" for ev in e.events)


def test_real_cards_gene_hack_copies_cruel_arrow():
    """真实卡回归：梦幻ex 基因侵入 → 吉雉鸡ex 残忍箭矢（task 019 CLI 触发的原缺口）。"""
    docs = load_card_dir("cards")
    jiji = CardDef(card_id="stub-吉雉鸡ex", name="吉雉鸡ex", supertype="pokemon",
                   hp=210, stage=0, rule_box="ex",
                   attacks=(AttackDef(name="残忍箭矢", cost=("无",), damage=None),))
    e = _engine(jiji, docs["吉雉鸡ex"], mew_doc=docs["梦幻ex"])
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(0,)))   # 选 残忍箭矢
    assert e.state.phase == "choice"
    e.apply(0, Action(kind="choose", choices=(2,)))   # 打战斗场
    assert e.state.players[1].active.damage == 100
    assert e.state.current_player == 1


def test_inner_effect_two_choice_nodes():
    """内层同层两次挂起：两笔伤害依序落在各自所选目标。"""
    e = _engine(CardDef(card_id="stub-双选兽", name="双选兽", supertype="pokemon",
                        hp=200, stage=0,
                        attacks=(AttackDef(name="双选", cost=("无",), damage=None),)),
                DOUBLE_DOC)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(0,)))   # 选招式 双选
    e.apply(0, Action(kind="choose", choices=(2,)))   # 第一笔 50 → 战斗场
    assert e.state.phase == "choice"                  # 内层第二次挂起
    e.apply(0, Action(kind="choose", choices=(3,)))   # 第二笔 30 → 备战靶
    assert e.state.players[1].active.damage == 50
    assert e.state.players[1].bench[0].damage == 30
    assert e.state.current_player == 1


def test_outer_continues_after_copy_node():
    """内层完成后外层 copy 节点收尾（不重复执行内层），后续节点照常执行。"""
    e = _engine(CardDef(card_id="stub-狙手兽", name="狙手兽", supertype="pokemon",
                        hp=200, stage=0,
                        attacks=(AttackDef(name="狙击", cost=("无",), damage=None),)),
                SNIPER_DOC, mew_doc=MEW_DRAW_DOC)
    hand_before = len(e.state.players[0].hand)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(0,)))
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert len(e.state.players[0].hand) == hand_before + 1  # draw 1 执行
    assert e.state.players[1].active.damage == 100          # 内层只跑了一次
    assert e.state.current_player == 1
    assert sum(1 for ev in e.events if ev.kind == "copy_attack") == 1  # 事件不重复


def test_nested_depth_over_one_raises():
    """套娃复制（嵌套层级 >1）：显式 DslError，不猜不静默。"""
    e = _engine(doll("套娃B", "镜像B"), DOLL_B_DOC,
                mew_card=doll("套娃A", "镜像A"), mew_doc=DOLL_A_DOC)
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(0,)))   # 复制 镜像B
    assert e.state.phase == "choice"                  # 内层挂起：选我方招式（同层允许）
    with pytest.raises(DslError, match="嵌套"):
        e.apply(0, Action(kind="choose", choices=(0,)))  # 镜像B 再复制 镜像A → 层级 3


# ── 确定性与 Agent 驱动 ──────────────────────────────────

def _run_scripted():
    e = _engine(CardDef(card_id="stub-狙手兽", name="狙手兽", supertype="pokemon",
                        hp=200, stage=0,
                        attacks=(AttackDef(name="狙击", cost=("无",), damage=None),)),
                SNIPER_DOC)
    _apply_script(e, [Action(kind="attack", attack_index=0),
                      Action(kind="choose", choices=(0,)),
                      Action(kind="choose", choices=(3,))])
    payload = json.dumps([ev.model_dump(mode="json") for ev in e.events],
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest(), e


def test_nested_copy_deterministic_replay():
    hash_a, _ = _run_scripted()
    hash_b, _ = _run_scripted()
    assert hash_a == hash_b


def test_heuristic_agent_drives_nested_copy():
    """HeuristicAgent 全程驱动嵌套复制（chooser 对手池评分可见）不卡死。"""
    e = _engine(CardDef(card_id="stub-狙手兽", name="狙手兽", supertype="pokemon",
                        hp=200, stage=0,
                        attacks=(AttackDef(name="狙击", cost=("无",), damage=None),)),
                SNIPER_DOC)
    agent = HeuristicAgent()
    while not (e.state.phase == "main" and e.state.current_player == 1):
        player = e.state.current_player
        acts = e.legal_actions(player)
        assert acts
        e.apply(player, agent.observe(e.state.visible_state(player), acts))
    total_damage = e.state.players[1].active.damage + e.state.players[1].bench[0].damage
    assert total_damage == 100
