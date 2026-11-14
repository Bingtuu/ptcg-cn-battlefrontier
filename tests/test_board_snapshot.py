"""task 120：board_snapshot 回合末盘面快照事件 + 回放渲染。

事件面只增不改（task 108 先例：只动事件发射层，状态结算时点零变更）；
快照在 _on_turn_end 收尾发射（检查阶段前），同种子 events_hash 仍逐局一致。
"""

from __future__ import annotations

from helpers import finish_setup, new_game

from battlefrontier.engine.actions import Action
from battlefrontier.engine.events import GameEvent
from battlefrontier.report.render import render_log


def _game_with_turn_end():
    engine = new_game(seed=42)
    finish_setup(engine)
    engine.apply(engine.state.current_player, Action(kind="end_turn"))
    return engine


def test_board_snapshot_回合末发射_字段完整():
    engine = _game_with_turn_end()
    snaps = [e for e in engine.events if e.kind == "board_snapshot"]
    assert len(snaps) == 1
    snap = snaps[0]
    for side in ("p0", "p1"):
        s = snap.detail[side]
        assert {"active", "bench", "hand", "deck", "prizes"} <= set(s)
        assert isinstance(s["bench"], list)
    # 初始 7 手牌、6 奖赏、牌库 53（60-7 起手 + 战斗场/备战各一由 setup 放置）
    assert snap.detail["p0"]["hand"] + snap.detail["p1"]["hand"] <= 14


def test_render_log_盘面快照渲染为表():
    ev = GameEvent(
        seq=0, turn=3, phase="main", player=0, kind="board_snapshot",
        detail={
            "p0": {"active": "沙奈朵ex HP230/310 能2", "bench": ["多龙奇 HP70/70 能1"],
                   "hand": 5, "deck": 23, "prizes": 3},
            "p1": {"active": None, "bench": [], "hand": 4, "deck": 25, "prizes": 4},
        })
    text = render_log([ev])
    assert "盘面" in text and "沙奈朵ex" in text and "多龙奇" in text
    assert "手牌 5" in text and "牌库 23" in text and "奖赏 3" in text
    assert "无" in text  # p1 空战斗场
