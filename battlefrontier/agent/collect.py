"""M11 数据采集钩子（task 050 WP1，D-M11-1）：跑局时显式采集决策点特征。

事件流为增量 delta、不含 setup 手牌构成，离线重建决策点局面做不到——故在
`play_game` 驱动循环挂可选 collector（默认 None = 行为零变化，events_hash
回归纪律）。每个 main 阶段决策点记录（特征向量, action 结构, turn, player），
局末 `finish` 按行动方视角打结局标签（胜 1 / 平 0.5 / 负 0）。

纪律：不消费任何随机源（纯被动记录）；失败局（异常）由调用方剔除——collector
本身不吞异常。
"""

from __future__ import annotations

from dataclasses import asdict

from battlefrontier.agent.features import feature_vector
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import VisibleGameState

__all__ = ["FeatureCollector"]


class FeatureCollector:
    """单局特征采集器：缓冲该局 main 阶段决策点，局末打标签产出数据行。

    行结构：turn / player / features（FEATURE_NAMES 键序）/ action（Action
    逐字段 dict——Action 是 dataclass，用 dataclasses.asdict 序列化）/ label。
    pair_index / seed 由产线驱动侧补（collector 只懂单局）。
    """

    def __init__(self) -> None:
        self._records: list[dict] = []

    def on_decision(self, view: VisibleGameState, player: int, action: Action) -> None:
        """驱动循环在 agent.observe 返回行动后调用；仅 main 阶段决策点入缓冲。"""
        if view.phase != "main":
            return
        self._records.append({
            "turn": view.turn,
            "player": player,
            "features": feature_vector(view),
            "action": asdict(action),
        })

    def finish(self, winner: int | None, is_draw: bool) -> list[dict]:
        """局末打标签并返回该局全部行（行动方视角：胜 1 / 平 0.5 / 负 0）。

        winner=None 且非平局 = 异常结局，显式报错（不猜）。
        """
        if not is_draw and winner not in (0, 1):
            raise ValueError(f"结局异常（不猜）：winner={winner} 且非平局")
        rows = []
        for rec in self._records:
            label = 0.5 if is_draw else (1.0 if winner == rec["player"] else 0.0)
            rows.append({**rec, "label": label})
        return rows
