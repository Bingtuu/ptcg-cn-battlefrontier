"""随机 Agent：均匀随机选择合法行动（引擎验证与 baseline 用，非正式策略）。"""

from __future__ import annotations

from battlefrontier.engine.actions import Action
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import VisibleGameState


class RandomAgent:
    def __init__(self, rng: RandomSource) -> None:
        self._rng = rng

    def observe(self, view: VisibleGameState, legal_actions: list[Action]) -> Action:
        return legal_actions[self._rng.randbelow(len(legal_actions))]
