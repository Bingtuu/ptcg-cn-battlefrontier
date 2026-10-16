"""M11 学得评估器（task 051 WP2，设计：docs/superpowers/specs/2026-10-16-m11-learned-evaluator-design.md）。

train（岭回归闭式解训练器 + 按局划分 + λ 选定）/ model（模型资产 JSON 读写 +
predict 推理接口，WP3 MCTS 截断接入用）。
"""

from battlefrontier.learn.model import (
    MODEL_FORMAT,
    LinearModel,
    load_model,
    predict,
    save_model,
)
from battlefrontier.learn.train import (
    DEFAULT_SPLIT_SEED,
    DEFAULT_SUBSAMPLE_SEED,
    LAMBDAS,
    TRAIN_RATIO,
    load_dataset,
    split_by_game,
    subsample_rows,
    train_model,
)

__all__ = [
    "DEFAULT_SPLIT_SEED",
    "DEFAULT_SUBSAMPLE_SEED",
    "LAMBDAS",
    "MODEL_FORMAT",
    "TRAIN_RATIO",
    "LinearModel",
    "load_dataset",
    "load_model",
    "predict",
    "save_model",
    "split_by_game",
    "subsample_rows",
    "train_model",
]
