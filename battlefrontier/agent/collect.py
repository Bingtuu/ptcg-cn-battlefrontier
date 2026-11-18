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

from battlefrontier.agent.eval_features import eval_v3_names, feature_vector_v3
from battlefrontier.agent.features import feature_vector
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import VisibleGameState

__all__ = ["FeatureCollector"]


class FeatureCollector:
    """单局特征采集器：缓冲该局 main 阶段决策点，局末打标签产出数据行。

    行结构：turn / player / features / action（Action 逐字段 dict——Action
    是 dataclass，用 dataclasses.asdict 序列化）/ label。
    pair_index / seed 由产线驱动侧补（collector 只懂单局）。

    task 155 WP2：``feature_set="v3"`` 时 features 为位置对齐 float list
    （名序 = ``eval_v3_names(card_vocab)``，header 由产线侧钉进文件——
    560 维 dict 键名重复落盘 ≈ 50GB+，位置格式压到 ~1/4）；缺省 "v1" =
    现状逐位不动（FEATURE_NAMES 键序 dict，card_vocab 传入也忽略）。
    """

    def __init__(self, feature_set: str = "v1",
                 card_vocab: tuple[str, ...] | None = None) -> None:
        if feature_set not in ("v1", "v3"):
            raise ValueError(f"未知 feature_set={feature_set!r}（只支持 v1/v3，不猜）")
        if feature_set == "v3" and card_vocab is None:
            raise ValueError("feature_set='v3' 必须提供 card_vocab（不猜）")
        self._feature_set = feature_set
        self._card_vocab = card_vocab
        self._v3_names = (eval_v3_names(card_vocab)
                          if feature_set == "v3" else None)
        self._records: list[dict] = []

    def on_decision(self, view: VisibleGameState, player: int, action: Action) -> None:
        """驱动循环在 agent.observe 返回行动后调用；仅 main 阶段决策点入缓冲。"""
        if view.phase != "main":
            return
        if self._feature_set == "v3":
            assert self._card_vocab is not None and self._v3_names is not None
            feats = feature_vector_v3(view, self._card_vocab)
            features: dict[str, float] | list[float] = \
                [feats[n] for n in self._v3_names]
        else:
            features = feature_vector(view)
        self._records.append({
            "turn": view.turn,
            "player": player,
            "features": features,
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
