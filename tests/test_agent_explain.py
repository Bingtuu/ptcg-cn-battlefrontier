"""task 122：agent_explain 决策理由标注（启发式自省 → 观测事件 → 回放可读）。

口径（task 042 先例）：观测事件排除 events_hash、render 正常显示、行为零变化。
首刀落地决策点 = attack（有效伤害数值键）+ promote（pokemon_score 数值键）；
retreat / ability / 能量附着为门控 tuple 键，逐分支设计留档后续（task 122 文档）。
"""

from __future__ import annotations

from helpers import deck60

from battlefrontier.agent.heuristic import HeuristicAgent
from battlefrontier.report.render import render_log
from battlefrontier.runner.play import OBSERVATION_KINDS, play_game


def _run(seed: int, explain: bool = True):
    agents = [HeuristicAgent(), HeuristicAgent()]
    for a in agents:
        a.explain_enabled = explain
    return play_game(deck60(), deck60(), seed=seed, agents=agents)


def test_agent_explain_事件入流_字段完整():
    res = _run(seed=42)
    explains = [e for e in res.events if e.kind == "agent_explain"]
    assert explains, "启发式对局应产生决策理由事件"
    ex = explains[0]
    assert ex.detail["kind"] in ("attack", "promote", "place_active")
    assert ex.detail["chosen"]
    cand = ex.detail["candidates"]
    assert 1 <= len(cand) <= 3
    assert all("label" in c and "score" in c for c in cand)


def test_agent_explain_排除events_hash_行为零变化():
    on = _run(seed=7, explain=True)
    off = _run(seed=7, explain=False)
    assert on.events_hash == off.events_hash
    assert on.winner == off.winner and on.turns == off.turns
    assert "agent_explain" in OBSERVATION_KINDS


def test_render_log_决策理由行():
    res = _run(seed=42)
    lines = render_log(res.events)
    explain_lines = [l for l in lines.splitlines() if "决策[" in l]
    assert explain_lines
    assert any("候选" in l for l in explain_lines)
