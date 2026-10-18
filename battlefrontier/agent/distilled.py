"""M12 WP3 蒸馏策略 Agent（task 059，D-M12-5）：numpy 前向打分 + 合法行动掩码 argmax。

- **构造收 PolicyModel 实例**（资产装载在调用侧：experiment._build_one /
  agreement.replay_student 经 learn.policy_model.load_policy_model 强校验，
  不猜纪律）；构造时权重转 numpy 数组并复核形状（防御纵深）。
- **observe**：state 30 维特征（agent.features.feature_vector，键序
  FEATURE_NAMES）⊕ 每条合法行动 26 维特征（agent.action_features.action_features，
  键序 ACTION_FEATURE_NAMES）→ 前向 score = W2·relu(W1·x + b1) + b2
  （与 learn/train_policy.py 训练侧同一打分式）→ 掩码 argmax 返回选中行动。
- **掩码口径**：打分只覆盖传入的 legal_actions（引擎枚举序）——非法行动永不
  进入候选，天然满足「AI 永不非法操作」（PRD §7.1）。
- **天然确定性**：全程无随机源；ties 取首索引（numpy argmax 平手返回首个最大
  值，合法行动列表序 = 引擎枚举序，确定性）。唯一合法行动早退不算分
  （MCTSAgent 同例）。
- **分层纪律**：推理前向只准 numpy（task 056，D3-3 核销：runtime 零 torch
  import）；无需 bind_engine / determinize——observe 只吃可见视图，天然守
  信息纪律（agreement 重放直接复用，task 060 锚 1 离线评估基建）。
"""

from __future__ import annotations

import numpy as np

from battlefrontier.agent.action_features import (
    ACTION_FEATURE_NAMES,
    action_features,
)
from battlefrontier.agent.features import FEATURE_NAMES, feature_vector
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import VisibleGameState
from battlefrontier.learn.policy_model import PolicyModel

__all__ = ["DistilledAgent"]

_IN_DIM = len(FEATURE_NAMES) + len(ACTION_FEATURE_NAMES)  # 56 = 状态 30 + 行动 26


class DistilledAgent:
    """蒸馏策略打分机 Agent（PRD §7.1 统一接口；bf-distilled-policy-v1 资产）。"""

    def __init__(self, model: PolicyModel) -> None:
        self._model = model
        w = model.weights
        w1 = np.asarray(w["w1"], dtype=np.float64)  # [hidden][in]
        b1 = np.asarray(w["b1"], dtype=np.float64)  # [hidden]
        w2 = np.asarray(w["w2"], dtype=np.float64)  # [1][hidden]
        b2 = np.asarray(w["b2"], dtype=np.float64)  # [1]
        if (w1.shape != (model.hidden, _IN_DIM) or b1.shape != (model.hidden,)
                or w2.shape != (1, model.hidden) or b2.shape != (1,)):
            raise ValueError(
                f"模型权重形状不符（不猜）：w1 {w1.shape} / b1 {b1.shape} / "
                f"w2 {w2.shape} / b2 {b2.shape}（期望 w1 ({model.hidden}, "
                f"{_IN_DIM}) / b1 ({model.hidden},) / w2 (1, {model.hidden}) / "
                f"b2 (1,)）")
        self._w1, self._b1, self._w2, self._b2 = w1, b1, w2, b2

    def observe(self, view: VisibleGameState, legal_actions: list[Action]) -> Action:
        if not legal_actions:
            raise ValueError("无合法行动可选")
        if len(legal_actions) == 1:
            # 唯一选择不算分（确定性早退，MCTSAgent 同例）
            return legal_actions[0]
        state = feature_vector(view)
        state_row = [state[name] for name in FEATURE_NAMES]
        x = np.asarray(
            [state_row + [action_features(a, view)[name]
                          for name in ACTION_FEATURE_NAMES]
             for a in legal_actions],
            dtype=np.float64)
        hidden = np.maximum(x @ self._w1.T + self._b1, 0.0)  # relu
        scores = (hidden @ self._w2.T + self._b2).reshape(-1)
        # 掩码 argmax：候选 = legal_actions；ties 取首索引（argmax 平手返回首个
        # 最大值，确定性）
        return legal_actions[int(np.argmax(scores))]
