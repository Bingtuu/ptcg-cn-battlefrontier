"""task 032 WP1（A1，D-032-1）：chooser 选择方向的 cost/actions 段穿透。

解释器挂起时把扁平步骤 phase 标注上 NeedChoice.step_phase → chooser.build_pending
透传 → PendingChoice.step_phase（默认 "actions"）；Agent 经 view.pending_choice
读取——cost 段（代价支付，如大地容器弃 1 手牌）取最低评分，actions 段（收益
选择，如检索拿牌）维持最高评分。tie-break 均保持 choices 升序确定性。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, inst, main_state

from battlefrontier.agent.heuristic import HeuristicAgent
from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.state import CardDef, PendingChoice

CARDS_DIR = Path(__file__).parent.parent / "cards"

EARTH_VESSEL_DOC = load_card_doc(CARDS_DIR / "大地容器.yml")


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品")


def decide(engine: GameEngine) -> Action:
    return HeuristicAgent().observe(
        engine.state.visible_state(0), engine.legal_actions(0)
    )


# ── PendingChoice.step_phase 字段 ────────────────────────────────────────

def test_pending_choice_step_phase_default_and_serialization() -> None:
    """默认值 "actions"；model_dump/model_validate 往返与 model_copy 保持。"""
    pc = PendingChoice(
        player=0, source=inst(60, item("测试物品")), effect_index=0, cursor=0,
        pool="own_hand", min_choose=1, max_choose=1, pool_iids=(10, 11),
    )
    assert pc.step_phase == "actions"
    assert PendingChoice.model_validate(pc.model_dump(mode="json")) == pc
    cost_pc = pc.model_copy(update={"step_phase": "cost"})
    assert cost_pc.step_phase == "cost"
    assert PendingChoice.model_validate(cost_pc.model_dump(mode="json")) == cost_pc


# ── 真实卡效果内挂起标注（大地容器：cost 弃 1 手牌 → 检索基本能量）─────────

def earth_vessel_engine() -> GameEngine:
    """main 阶段、p0 手牌含大地容器（iid 60）、牌库含基本能量的引擎。"""
    state = main_state(p0_extra_hand=(inst(60, item("大地容器")),))
    p0 = state.players[0].model_copy(update={
        "deck": tuple(inst(100 + i, energy()) for i in range(5))
        + tuple(inst(110 + i, basic("垫牌")) for i in range(5)),
    })
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"大地容器": EARTH_VESSEL_DOC}
    return engine


def test_earth_vessel_cost_suspend_tagged_cost() -> None:
    """cost 段弃牌挂起：pending.step_phase == "cost"。"""
    e = earth_vessel_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    assert e.state.pending_choice.step_phase == "cost"


def test_earth_vessel_search_suspend_tagged_actions() -> None:
    """cost 支付后检索段挂起：pending.step_phase == "actions"。"""
    e = earth_vessel_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose"))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    assert e.state.pending_choice.step_phase == "actions"


# ── 启发式方向：cost 取最低评分 / actions 维持最高评分 ───────────────────

def choice_engine(*, step_phase: str | None) -> GameEngine:
    """phase=choice 局面：池 = 手牌中的高分宝可梦（iid 50）+ 低分能量（iid 51）。

    step_phase=None 表示无挂起（防御路径：pending_choice 为 None）。
    """
    state = main_state()
    pc = None
    if step_phase is not None:
        pc = PendingChoice(
            player=0, source=inst(60, item("测试物品")), effect_index=0, cursor=0,
            pool="own_hand", min_choose=1, max_choose=1, pool_iids=(50, 51),
            step_phase=step_phase,
        )
    engine = engine_at(state.model_copy(update={"phase": "choice", "pending_choice": pc}))
    return engine


def test_heuristic_cost_phase_picks_lowest_score() -> None:
    """cost 段：弃牌代价选最低评分（能量 51），不再扔高分宝可梦。"""
    e = choice_engine(step_phase="cost")
    assert decide(e) == Action(kind="choose", choices=(51,))


def test_heuristic_actions_phase_picks_highest_score() -> None:
    """actions 段（回归）：收益选择维持最高评分（宝可梦 50）。"""
    e = choice_engine(step_phase="actions")
    assert decide(e) == Action(kind="choose", choices=(50,))


def test_heuristic_choose_without_pending_keeps_highest_score() -> None:
    """防御路径：pending_choice 为 None 的 choose 维持最高评分。"""
    e = choice_engine(step_phase=None)
    view = e.state.visible_state(0)
    assert view.pending_choice is None
    acts = [Action(kind="choose", choices=(50,)), Action(kind="choose", choices=(51,))]
    assert HeuristicAgent()._pick_choose(view, acts) == Action(kind="choose", choices=(50,))


def test_heuristic_cost_phase_visible_only_to_chooser() -> None:
    """step_phase 仅向挂起选择方揭示（同 pending_pool 门控口径）。"""
    e = earth_vessel_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.visible_state(0).pending_choice is not None
    assert e.state.visible_state(1).pending_choice is None


def test_earth_vessel_full_flow_picks_energy_as_cost() -> None:
    """e2e：启发式打大地容器——cost 弃能量（最低分，不扔宝可梦）；检索段取满 2 张。"""
    e = earth_vessel_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert decide(e) == Action(kind="choose", choices=(51,))  # cost：弃能量不扔宝可梦
    e.apply(0, Action(kind="choose", choices=(51,)))
    assert e.state.phase == "choice"
    act = decide(e)  # 检索段：up-to 2 取满（能量各 1 分，tie-break choices 升序）
    assert act == Action(kind="choose", choices=(100, 101))
    e.apply(0, act)
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert [c.iid for c in p0.hand] == [50, 100, 101]
    assert [c.iid for c in p0.discard] == [51, 60]  # cost 弃能量 + 本体收尾
