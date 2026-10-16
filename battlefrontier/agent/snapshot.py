"""M11 决策一致率快照采集钩子（task 052 WP3，D-M11-5）：跑局时落决策点局面快照。

与 FeatureCollector（task 050，D-M11-1）同为 play_game 可选钩子（默认 None =
行为零变化，events_hash 回归纪律）；差异：本钩子记录的是**完整序列化
GameState + 教师结构化 Action**（含隐藏信息——本地产物不回流 Agent 决策），
供离线一致率评估在同一局面重放受测配置比对 argmax。

只落教师实际搜索的决策点：驱动循环在 observe 返回后回传 consideration
（MCTS 根统计；唯一合法行动早退路径不产生，mcts.py 口径）——consideration
为 None 的决策点不记录。教师 heuristic / random 无搜索，天然零记录。

纪律：不消费任何随机源（model_dump 纯读）；失败局由调用方剔除——collector
本身不吞异常。
"""

from __future__ import annotations

from dataclasses import asdict

from battlefrontier.agent.mcts import Consideration
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine

__all__ = ["SnapshotCollector"]


class SnapshotCollector:
    """单局快照采集器：缓冲该局教师实际搜索的决策点快照（含全部阶段）。

    行结构：turn / phase / player / action_kind / n_legal / action（Action
    逐字段 dict）/ state（GameState model_dump JSON）。seed / pair 信息由
    产线驱动侧补（collector 只懂单局）。分母口径过滤（main 阶段三类行动）
    在离线评估侧进行（D-M11-5），采集侧全量保留供附录观察。
    """

    def __init__(self) -> None:
        self._rows: list[dict] = []

    @property
    def rows(self) -> list[dict]:
        return list(self._rows)

    def on_decision(
        self, *, engine: GameEngine, player: int, action: Action,
        consideration: Consideration | None, n_legal: int,
    ) -> None:
        """驱动循环在 agent.observe 返回后、apply 前调用（engine.state = 决策点局面）。

        consideration 非 None = 教师（MCTS）在该点实际搜索（>1 合法行动）——
        只落这类决策点；唯一合法行动早退不产生 consideration，天然剔除。
        """
        if consideration is None:
            return
        state = engine.state
        self._rows.append({
            "turn": state.turn,
            "phase": state.phase,
            "player": player,
            "action_kind": action.kind,
            "n_legal": n_legal,
            "action": asdict(action),
            "state": state.model_dump(mode="json"),
        })
