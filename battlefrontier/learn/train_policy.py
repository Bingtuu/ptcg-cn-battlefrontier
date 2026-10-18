"""M12 蒸馏策略训练器（task 058 WP2，D-M12-3/4）：torch MLP 打分机 + 教师硬标签 NLL。

- **模型**（D-M12-3）：score(state ⊕ action) = W2·relu(W1·x + b1) + b2，输入
  56 维（状态 30 = FEATURE_NAMES + 行动 26 = ACTION_FEATURE_NAMES），单层隐藏
  64 + ReLU，输出标量 logit；逐决策点合法行动掩码 softmax + 教师下标 NLL
  （试点硬标签；软标签缺口见 task 057 遗留）。
- **训练**：全批量 Adam（小数据量级不做 mini-batch 洗牌），向量化实现——样本
  预处理一次拍平成大张量 X [Σn_i, 56]（state 行按合法行动数重复拼行动特征）
  + teacher 全局下标 + 行→样本 id，每 epoch 一次前向后分段 logsumexp
  （数值稳定两段法：detach 分段 max + exp-sum-log，与逐样本
  cross_entropy(logits, teacher) = −logit[teacher] + logsumexp(logits) 数学
  等价，掩码天然满足——只有合法行动进 logits）；按局 (pair_index, seed)
  80/20 划分（同局样本不跨集，train.py 先例）；缺省超参全钉死写 meta
  （epochs 100 / lr 1e-3 / hidden 64 / split_seed 20261018）。
- **训练非复算面**（task 056 D3-4）：torch 随机源（初始化/cudnn/BLAS）不锁，
  torch.manual_seed(split_seed) 仅尽力锚定初始化；资产落盘即锁定，推理
  确定性不受损。meta 落 torch_version 锚定训练环境。
- **本文件是唯一允许 import torch 的模块**（task 056 防回流基准）；holdout
  argmax 准确率（掩码 argmax == 教师下标 的比例）落 meta。
"""

from __future__ import annotations

import random

import torch

from battlefrontier.agent.action_features import ACTION_FEATURE_NAMES
from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.learn.policy_data import PolicySample
from battlefrontier.learn.policy_model import PolicyModel

__all__ = [
    "DEFAULT_EPOCHS",
    "DEFAULT_HIDDEN",
    "DEFAULT_LR",
    "DEFAULT_SPLIT_SEED",
    "TRAIN_RATIO",
    "train_policy",
]

# 缺省超参（D-M12-3，全钉死写 meta；CLI 缺省同此）
DEFAULT_EPOCHS = 100
DEFAULT_LR = 1e-3
DEFAULT_HIDDEN = 64
DEFAULT_SPLIT_SEED = 20261018
TRAIN_RATIO = 0.8

# 自适应线程数粒度：每 _ROWS_PER_THREAD 拍平行配 1 线程（见 train_policy 注释）
_ROWS_PER_THREAD = 50_000

_INPUT_DIM = len(FEATURE_NAMES) + len(ACTION_FEATURE_NAMES)


def _split_by_game(samples: list[PolicySample], split_seed: int,
                   ) -> tuple[list[PolicySample], list[PolicySample]]:
    """按局 (pair_index, seed) 80/20 划分；同局样本不跨集（train.py 先例）。"""
    game_ids = sorted({(s.pair_index, s.seed) for s in samples})
    if len(game_ids) < 2:
        raise ValueError(f"局数不足（{len(game_ids)} < 2）无法划分训练/验证集")
    shuffled = list(game_ids)
    random.Random(split_seed).shuffle(shuffled)
    n_train = max(1, min(len(game_ids) - 1, int(len(game_ids) * TRAIN_RATIO)))
    train_ids = set(shuffled[:n_train])
    train = [s for s in samples if (s.pair_index, s.seed) in train_ids]
    val = [s for s in samples if (s.pair_index, s.seed) not in train_ids]
    return train, val


def _flatten_samples(samples: list[PolicySample]):
    """样本列 → 拍平大张量 (X [Σn_i, 56], teacher 全局下标, 行→样本 id)。

    一次性预处理（训练外成本）：state 行按合法行动数重复拼行动特征；
    teacher 全局下标 = 样本段起点 + teacher_index（段内下标）。
    """
    flat, teacher_global, ids = [], [], []
    for i, s in enumerate(samples):
        st = [s.state[name] for name in FEATURE_NAMES]
        start = len(flat)
        for a in s.actions:
            flat.append(st + [a[name] for name in ACTION_FEATURE_NAMES])
        ids.extend([i] * (len(flat) - start))
        teacher_global.append(start + s.teacher_index)
    x = torch.tensor(flat, dtype=torch.float32)
    return (x,
            torch.tensor(teacher_global, dtype=torch.long),
            torch.tensor(ids, dtype=torch.long))


def _segment_logsumexp(logits, sample_ids, n_samples):
    """分段 logsumexp（数值稳定：detach 分段 max + exp-sum-log，梯度等价）。"""
    seg_max = torch.full((n_samples,), float("-inf"), dtype=logits.dtype)
    seg_max.scatter_reduce_(0, sample_ids, logits.detach(), "amax")
    shifted = torch.exp(logits - seg_max[sample_ids])
    seg_sum = torch.zeros(n_samples, dtype=logits.dtype)
    seg_sum.index_add_(0, sample_ids, shifted)
    return seg_max + torch.log(seg_sum)


def _vectorized_loss(net, x, teacher_global, sample_ids):
    """全批量一次前向 + 分段 logsumexp − 教师 logit，按样本均值 NLL。

    与逐样本 cross_entropy(logits, teacher) 数学等价：
    CE = −logit[teacher] + logsumexp(logits)。
    """
    logits = net(x).squeeze(-1)
    lse = _segment_logsumexp(logits, sample_ids, teacher_global.numel())
    return (lse - logits[teacher_global]).mean()


def _argmax_accuracy(net, x, teacher_global, sample_ids) -> float:
    """掩码 argmax 准确率：分段首个最大 logit 下标 == 教师下标 的样本比例。"""
    n_samples = teacher_global.numel()
    with torch.no_grad():
        logits = net(x).squeeze(-1)
        seg_max = torch.full((n_samples,), float("-inf"), dtype=logits.dtype)
        seg_max.scatter_reduce_(0, sample_ids, logits, "amax")
        n_rows = logits.numel()
        pos = torch.arange(n_rows)
        # 分段内首个最大值（并列取先，与逐样本 argmax 一致）：非最大行置 n_rows
        first = torch.where(logits == seg_max[sample_ids], pos,
                            torch.full_like(pos, n_rows))
        seg_first = torch.full((n_samples,), n_rows, dtype=torch.long)
        seg_first.scatter_reduce_(0, sample_ids, first, "amin")
        correct = int((seg_first == teacher_global).sum().item())
    return correct / n_samples


def train_policy(samples: list[PolicySample], *, epochs: int = DEFAULT_EPOCHS,
                 lr: float = DEFAULT_LR, hidden: int = DEFAULT_HIDDEN,
                 split_seed: int = DEFAULT_SPLIT_SEED,
                 code_version: str = "",
                 pool: str | None = None) -> PolicyModel:
    """样本列 → 训练完成的 PolicyModel（meta 全量落账，含 holdout argmax 准确率）。

    全批量 Adam：每 epoch 全训练集一次前向/反向。训练非复算面（D3-4）：
    torch.manual_seed(split_seed) 锚定初始化，其余随机源不锁。
    """
    if not samples:
        raise ValueError("样本为空（不猜）")
    if epochs < 1:
        raise ValueError(f"epochs 须 ≥ 1：{epochs}（不猜）")
    if hidden < 1:
        raise ValueError(f"hidden 须 ≥ 1：{hidden}（不猜）")
    train_rows, val_rows = _split_by_game(samples, split_seed)
    torch.manual_seed(split_seed)
    net = torch.nn.Sequential(
        torch.nn.Linear(_INPUT_DIM, hidden),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden, 1),
    )
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    x_train, teacher_train, ids_train = _flatten_samples(train_rows)

    # torch 算内并行线程数按拍平行数自适应：小数据多线程是纯同步开销（实测
    # 1.4 万行 16 线程 193ms vs 1 线程 29ms/epoch），试点规模（~3M 行）则
    # 多线程占优（16 线程 2.3s vs 1 线程 6.5s/epoch）；训练后恢复原设置。
    prev_threads = torch.get_num_threads()
    torch.set_num_threads(
        max(1, min(prev_threads, x_train.shape[0] // _ROWS_PER_THREAD)))
    try:
        train_loss = 0.0
        for _epoch in range(epochs):
            opt.zero_grad()
            loss = _vectorized_loss(net, x_train, teacher_train, ids_train)
            loss.backward()
            opt.step()
            train_loss = float(loss.item())

        train_acc = _argmax_accuracy(net, x_train, teacher_train, ids_train)
        val_acc = None
        if val_rows:
            x_val, teacher_val, ids_val = _flatten_samples(val_rows)
            val_acc = _argmax_accuracy(net, x_val, teacher_val, ids_val)
    finally:
        torch.set_num_threads(prev_threads)

    game_ids = {(s.pair_index, s.seed) for s in samples}
    meta = {
        "code_version": code_version,
        "epochs": epochs,
        "games": len(game_ids),
        "hidden": hidden,
        "lr": lr,
        "pairs": len({s.pair_index for s in samples}),
        "pool": pool,
        "rows": len(samples),
        "seed_max": max(s for _, s in game_ids),
        "seed_min": min(s for _, s in game_ids),
        "split_seed": split_seed,
        "torch_version": torch.__version__,
        "train_argmax_accuracy": train_acc,
        "train_games": len({(s.pair_index, s.seed) for s in train_rows}),
        "train_loss": train_loss,
        "train_rows": len(train_rows),
        "val_argmax_accuracy": val_acc,
        "val_games": len({(s.pair_index, s.seed) for s in val_rows}),
        "val_rows": len(val_rows),
        "warning": None if val_acc is not None
        else "holdout 为空（验证集无样本），val_argmax_accuracy=None——如实落账",
    }
    with torch.no_grad():
        w1, b1 = net[0].weight, net[0].bias
        w2, b2 = net[2].weight, net[2].bias
        weights = {
            "w1": tuple(tuple(float(v) for v in row) for row in w1.tolist()),
            "b1": tuple(float(v) for v in b1.tolist()),
            "w2": tuple(tuple(float(v) for v in row) for row in w2.tolist()),
            "b2": tuple(float(v) for v in b2.tolist()),
        }
    return PolicyModel(hidden=hidden, weights=weights, meta=meta)
