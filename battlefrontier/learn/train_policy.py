"""M12 蒸馏策略训练器（task 058 WP2，D-M12-3/4）：torch MLP 打分机 + 教师硬标签 NLL。

- **模型**（D-M12-3）：score(state ⊕ action) = W2·relu(W1·x + b1) + b2，输入
  56 维（状态 30 = FEATURE_NAMES + 行动 26 = ACTION_FEATURE_NAMES），单层隐藏
  64 + ReLU，输出标量 logit；逐决策点合法行动掩码 softmax + 教师下标 NLL
  （试点硬标签；软标签缺口见 task 057 遗留）。
- **训练**：全批量 Adam（小数据量级不做 mini-batch 洗牌）；按局 (pair_index,
  seed) 80/20 划分（同局样本不跨集，train.py 先例）；缺省超参全钉死写 meta
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


def _sample_tensors(samples: list[PolicySample]):
    """样本列 → (状态向量列, 行动矩阵列, 教师下标列)（纯 Python 列表，调用侧转张量）。"""
    states, actions, teachers = [], [], []
    for s in samples:
        states.append([s.state[name] for name in FEATURE_NAMES])
        actions.append([[a[name] for name in ACTION_FEATURE_NAMES]
                        for a in s.actions])
        teachers.append(s.teacher_index)
    return states, actions, teachers


def _score_batch(net, states, actions) -> list:
    """逐样本打分：state 广播拼每条合法行动 → logit 向量列（变长，不 pad）。"""
    out = []
    for st, acts in zip(states, actions, strict=True):
        n = acts.shape[0]
        x = torch.cat([st.unsqueeze(0).expand(n, -1), acts], dim=1)
        out.append(net(x).squeeze(-1))
    return out


def _argmax_accuracy(net, states, actions, teachers) -> float:
    """掩码 argmax 准确率：logit 最大下标 == 教师下标 的样本比例。"""
    correct = 0
    for logits, t in zip(_score_batch(net, states, actions), teachers, strict=True):
        correct += int(int(logits.argmax().item()) == t)
    return correct / len(teachers)


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
    t_states, t_actions, t_teacher = _sample_tensors(train_rows)
    t_states = [torch.tensor(st, dtype=torch.float32) for st in t_states]
    t_actions = [torch.tensor(acts, dtype=torch.float32) for acts in t_actions]

    train_loss = 0.0
    for _epoch in range(epochs):
        opt.zero_grad()
        loss = torch.zeros(())
        for logits, t in zip(_score_batch(net, t_states, t_actions), t_teacher,
                             strict=True):
            loss = loss + torch.nn.functional.cross_entropy(
                logits.unsqueeze(0), torch.tensor([t]))
        loss = loss / len(t_teacher)
        loss.backward()
        opt.step()
        train_loss = float(loss.item())

    with torch.no_grad():
        train_acc = _argmax_accuracy(net, t_states, t_actions, t_teacher)
        val_acc = None
        if val_rows:
            v_states, v_actions, v_teacher = _sample_tensors(val_rows)
            v_states = [torch.tensor(st, dtype=torch.float32) for st in v_states]
            v_actions = [torch.tensor(acts, dtype=torch.float32)
                         for acts in v_actions]
            val_acc = _argmax_accuracy(net, v_states, v_actions, v_teacher)

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
