"""单卡 DSL 测试（task 134）：咕咕-不眠 / 能量转移-H6——从 cards/ 真实文件装载。

咕咕 CSV9.5C-141（不眠类）：「这只宝可梦不会陷入【睡眠】状态」=
status_immunity 声明式（args.status=asleep）——引擎 apply_status 落点守卫
（任何来源的睡眠施加均不适用，与 protection 的「对手招式限定」不同）。
能量转移 CSVH6C-031：H6 异文本等价类拆分档（text_raw 多两个「的」），
效果语义与主类一致（两段式 move_energy）。
"""

from pathlib import Path

from helpers import basic, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.dsl.loader import load_card_dir, load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import AttackDef, CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

GU_DOC = load_card_doc(CARDS_DIR / "咕咕-不眠.yml")
H6_DOC = load_card_doc(CARDS_DIR / "能量转移-H6.yml")

SLEEP_ATTACK_DOC = parse_card_doc("""
card:
  name_group: 催眠兽
effects:
  - trigger: on_attack
    attack: 催眠
    actions:
      - {action: apply_status, selector: opponent_active, args: {status: asleep}}
""")

SLEEP_ITEM_DOC = parse_card_doc("""
card:
  name_group: 睡眠物品
effects:
  - trigger: on_play
    actions:
      - {action: apply_status, selector: opponent_active, args: {status: asleep}}
""")


def attacker_card() -> CardDef:
    return CardDef(card_id="stub-催眠兽", name="催眠兽", supertype="pokemon",
                   hp=70, stage=0,
                   attacks=(AttackDef(name="催眠", cost=("无",), damage=0),),
                   retreat_cost=1)


def item_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def attack_engine(p1_active, extra_effects: dict) -> GameEngine:
    """main 阶段：p0 战斗场催眠兽（iid 1，附着 1 能），p1 战斗场可调。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, attacker_card(), 1),
    })
    p1 = state.players[1].model_copy(update={"active": p1_active})
    e = GameEngine(RandomSource(0))
    e.state = state.model_copy(update={"players": (p0, p1)})
    e.card_effects = {"催眠兽": SLEEP_ATTACK_DOC, **extra_effects}
    return e


def prim_results(e, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action]


# ── 定义库装配 ──────────────────────────────────────────────────────────

def test_library_mounts_both_classes() -> None:
    docs = load_card_dir(CARDS_DIR)
    assert "CSV9.5C-141" in docs          # 咕咕 不眠类
    assert "CSVH6C-031" in docs           # 能量转移 H6 异文本类
    assert len(docs.by_name("咕咕")) == 3      # 寂静之翼 / 三刺击 / 不眠
    assert len(docs.by_name("能量转移")) == 2  # 主类 / H6 类
    node = GU_DOC.effects[0].actions[0]
    assert node.action == "status_immunity" and node.args["status"] == "asleep"


# ── 不眠：status_immunity 落点守卫 ─────────────────────────────────────

def test_sleep_attack_blocked_by_bumian() -> None:
    """对手招式施加睡眠：不眠声明拦截（applied=None/status_immunity）。"""
    gugu = CardDef(card_id="stub-咕咕", name="咕咕", supertype="pokemon",
                   hp=60, stage=0,
                   attacks=(AttackDef(name="撞击", cost=("无", "无"), damage=20),),
                   retreat_cost=1)
    e = attack_engine(in_play(2, gugu), {"咕咕": GU_DOC})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.conditions == frozenset()
    assert prim_results(e, "apply_status") == [
        {"applied": None, "reason": "status_immunity"}]


def test_sleep_attack_applies_without_bumian() -> None:
    """对照：无声明目标正常陷入睡眠（落点结果 applied；检查后掷币恢复不归本守卫）。"""
    e = attack_engine(in_play(2, basic("硬兽", hp=500)), {})
    e.apply(0, Action(kind="attack", attack_index=0))
    assert prim_results(e, "apply_status") == [{"applied": "asleep", "target": "硬兽"}]


def test_sleep_item_blocked_by_bumian() -> None:
    """训练家卡效果施加睡眠同样不适用（不眠不限定来源，区别于 protection）。"""
    state = main_state(p0_extra_hand=(inst(60, item_card("睡眠物品")),))
    gugu = CardDef(card_id="stub-咕咕", name="咕咕", supertype="pokemon",
                   hp=60, stage=0,
                   attacks=(AttackDef(name="撞击", cost=("无", "无"), damage=20),),
                   retreat_cost=1)
    p1 = state.players[1].model_copy(update={"active": in_play(2, gugu)})
    e = GameEngine(RandomSource(0))
    e.state = state.model_copy(update={"players": (state.players[0], p1)})
    e.card_effects = {"睡眠物品": SLEEP_ITEM_DOC, "咕咕": GU_DOC}
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.players[1].active.conditions == frozenset()
    assert prim_results(e, "apply_status") == [
        {"applied": None, "reason": "status_immunity"}]


# ── 能量转移-H6：两段式 move_energy（语义同主类）──────────────────────

def test_h6_move_energy_full_flow() -> None:
    active = in_play(1, basic("妙蛙种子"), energies=2)   # 附着 9010/9011
    bench = (in_play(5, basic("小火龙"), energies=1),)   # 附着 9050
    state = main_state(p0_extra_hand=(inst(60, item_card("能量转移")),))
    p0 = state.players[0].model_copy(update={"active": active, "bench": bench})
    e = GameEngine(RandomSource(0))
    e.state = state.model_copy(update={"players": (p0, state.players[1])})
    e.card_effects = {"能量转移": H6_DOC}
    e.apply(0, Action(kind="play_trainer", iid=60))
    choices = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert choices == [(9010,), (9011,), (9050,)]  # 池 = 全场已附着基本能量
    e.apply(0, Action(kind="choose", choices=(9010,)))
    choices = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert choices == [(5,)]  # 目标排除来源（iid 1）
    e.apply(0, Action(kind="choose", choices=(5,)))
    p0s = e.state.players[0]
    assert [c.iid for c in p0s.active.attached_energy] == [9011]
    assert [c.iid for c in p0s.bench[0].attached_energy] == [9050, 9010]
    assert 60 in [c.iid for c in p0s.discard]
