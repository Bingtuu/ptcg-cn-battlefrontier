"""M11 学得评估器（task 051 WP2，设计：docs/superpowers/specs/2026-10-16-m11-learned-evaluator-design.md）。

train（岭回归闭式解训练器 + 按局划分 + λ 选定）/ train_v3（task 155 WP3：
v3 位置行数据的分块两遍流式岭回归，λ 六档——复用 train 的划分/抽样/警戒
口径）/ model（模型资产 JSON 读写 +
predict 推理接口，WP3 MCTS 截断接入用）。

M12（task 058 WP2）：policy_model（bf-distilled-policy-v1 策略资产读写，torch-free）
/ policy_data（快照→样本转换）/ train_policy（torch 训练器，唯一允许 import
torch 的模块——不进本 __init__，CLI 惰性导入）。
"""

from battlefrontier.learn.model import (
    MODEL_FORMAT,
    MODEL_FORMAT_V3,
    LinearModel,
    load_model,
    predict,
    save_model,
)
from battlefrontier.learn.policy_model import (
    POLICY_FORMAT,
    PolicyModel,
    load_policy_model,
    save_policy_model,
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
from battlefrontier.learn.train_v3 import (
    CHUNK_ROWS,
    LAMBDAS_V3,
    train_model_v3,
)

__all__ = [
    "CHUNK_ROWS",
    "DEFAULT_SPLIT_SEED",
    "DEFAULT_SUBSAMPLE_SEED",
    "LAMBDAS",
    "LAMBDAS_V3",
    "MODEL_FORMAT",
    "MODEL_FORMAT_V3",
    "POLICY_FORMAT",
    "TRAIN_RATIO",
    "LinearModel",
    "PolicyModel",
    "load_dataset",
    "load_model",
    "load_policy_model",
    "predict",
    "save_model",
    "save_policy_model",
    "split_by_game",
    "subsample_rows",
    "train_model",
    "train_model_v3",
]
