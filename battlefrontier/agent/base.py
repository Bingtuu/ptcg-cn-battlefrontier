"""Agent 协议（PRD §7.1）：启发式 / MCTS / RL 共用的统一接口。

Agent 只见过滤后的可见视图（对手手牌内容不可见），从引擎枚举的
合法行动列表中选择其一返回——AI 永不非法操作。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import VisibleGameState


@runtime_checkable
class Agent(Protocol):
    def observe(self, view: VisibleGameState, legal_actions: list[Action]) -> Action:
        """根据可见局面与合法行动列表，返回选择的行动。"""
        ...
