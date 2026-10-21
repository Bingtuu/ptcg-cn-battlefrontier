"""M12 WP3 蒸馏策略 Agent（task 059，D-M12-5）：numpy 前向打分 + 合法行动掩码 argmax。

- **构造收 PolicyModel 实例**（资产装载在调用侧：experiment._build_one /
  agreement.replay_student 经 learn.policy_model.load_policy_model 强校验，
  不猜纪律）；构造时权重转 numpy 数组并复核形状（防御纵深）。
- **特征版本分派**（task 062 WP2c，D-062-4）：按 `meta.feature_version`
  （缺省 "v1"）——v1 = 状态 30 维（agent.features.feature_vector，键序
  FEATURE_NAMES）⊕ 行动 26 维（agent.action_features.action_features，键序
  ACTION_FEATURE_NAMES），路径逐位不变；v2 = 状态 36 维
  （agent.policy_features.policy_state_features，键序 POLICY_STATE_NAMES）
  ⊕ 行动 26+词表维（policy_action_features，键序
  policy_action_names(card_vocab)，卡身份 one-hot），要求 model.card_vocab
  非 None（None → ValueError，不猜）。
- **observe**：state 特征 ⊕ 每条合法行动特征 → 前向
  score = W2·relu(W1·x + b1) + b2（与 learn/train_policy.py 训练侧同一打分式）
  → 掩码 argmax 返回选中行动。
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
from battlefrontier.agent.policy_features import (
    POLICY_STATE_NAMES,
    policy_action_features,
    policy_action_names,
    policy_state_features,
)
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import VisibleGameState
from battlefrontier.learn.policy_model import PolicyModel

__all__ = ["DistilledAgent"]


class DistilledAgent:
    """蒸馏策略打分机 Agent（PRD §7.1 统一接口；bf-distilled-policy-v1/v2 资产）。"""

    def __init__(self, model: PolicyModel) -> None:
        self._model = model
        version = model.meta.get("feature_version", "v1")
        if version == "v2":
            if model.card_vocab is None:
                raise ValueError(
                    "feature_version=v2 但 card_vocab 为 None（不猜）")
            self._vocab: tuple[str, ...] | None = model.card_vocab
            self._action_names: tuple[str, ...] = policy_action_names(model.card_vocab)
            in_dim = len(POLICY_STATE_NAMES) + len(self._action_names)
        elif version == "v1":
            self._vocab = None
            self._action_names = ACTION_FEATURE_NAMES
            in_dim = len(FEATURE_NAMES) + len(ACTION_FEATURE_NAMES)
        else:
            raise ValueError(f"未知 feature_version：{version!r}（不猜）")
        w = model.weights
        w1 = np.asarray(w["w1"], dtype=np.float64)  # [hidden][in]
        b1 = np.asarray(w["b1"], dtype=np.float64)  # [hidden]
        w2 = np.asarray(w["w2"], dtype=np.float64)  # [1][hidden]
        b2 = np.asarray(w["b2"], dtype=np.float64)  # [1]
        if (w1.shape != (model.hidden, in_dim) or b1.shape != (model.hidden,)
                or w2.shape != (1, model.hidden) or b2.shape != (1,)):
            raise ValueError(
                f"模型权重形状不符（不猜）：w1 {w1.shape} / b1 {b1.shape} / "
                f"w2 {w2.shape} / b2 {b2.shape}（期望 w1 ({model.hidden}, "
                f"{in_dim}) / b1 ({model.hidden},) / w2 (1, {model.hidden}) / "
                f"b2 (1,)）")
        self._w1, self._b1, self._w2, self._b2 = w1, b1, w2, b2

    def observe(self, view: VisibleGameState, legal_actions: list[Action]) -> Action:
        if not legal_actions:
            raise ValueError("无合法行动可选")
        if len(legal_actions) == 1:
            # 唯一选择不算分（确定性早退，MCTSAgent 同例）
            return legal_actions[0]
        if self._vocab is None:
            # v1 路径（逐位不变）
            state = feature_vector(view)
            state_row = [state[name] for name in FEATURE_NAMES]
            x = np.asarray(
                [state_row + [action_features(a, view)[name]
                              for name in ACTION_FEATURE_NAMES]
                 for a in legal_actions],
                dtype=np.float64)
        else:
            # v2 路径（task 062 WP2c）：36 维状态 + 26+词表维行动（卡身份 one-hot）
            state_v2 = policy_state_features(view)
            state_row_v2 = [state_v2[name] for name in POLICY_STATE_NAMES]
            # 每条行动特征只算一次（纯函数，键序钉死；曾按 name 内层重复调用
            # 138×n 次，matrix 慢 ~10 倍——性能护栏测试钉死调用数）
            rows = []
            for a in legal_actions:
                feats = policy_action_features(a, view, self._vocab)
                rows.append(state_row_v2
                            + [feats[name] for name in self._action_names])
            x = np.asarray(rows, dtype=np.float64)
        hidden = np.maximum(x @ self._w1.T + self._b1, 0.0)  # relu
        scores = (hidden @ self._w2.T + self._b2).reshape(-1)
        # 掩码 argmax：候选 = legal_actions；ties 取首索引（argmax 平手返回首个
        # 最大值，确定性）
        return legal_actions[int(np.argmax(scores))]
