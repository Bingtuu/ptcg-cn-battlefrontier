"""M12 蒸馏策略模型资产（task 058 WP2，D-M12-4）：bf-distilled-policy-v1/v2 JSON 读写。

资产 = 单 JSON（进版本控制，D3-4）：format id / hidden / 权重嵌套列表
（w1 [hidden][in] / b1 [hidden] / w2 [1][hidden] / b2 [1]）/ 双特征词表
（键序钉死）/ meta（种子 / 局数 / 配对 / 代码版本 / 训练超参 / 训练+holdout 指标）。
落盘位级确定：json.dumps（ensure_ascii=False / indent=2 / sort_keys，model.py 先例）。

format 分派（task 062 WP2a，D-062-4）：
- v1：in = 状态 30 维 + 行动 26 维；词表 = FEATURE_NAMES / ACTION_FEATURE_NAMES；
  PolicyModel.card_vocab 为 None。既有入库资产（models/policy-m12-v1.json，
  M12 锚 1 复算锚）保持可装载，v1 落盘路径逐字节不变。
- v2：card_vocab 非 None；词表 = POLICY_STATE_NAMES（36）/
  policy_action_names(card_vocab)（26 + 词表大小）；payload 增 card_vocab。

装载强校验（不猜）：format id / 词表键序与代码常量逐一相等（v2 含 card_vocab
与 action_feature_names 联动一致）/ 权重形状与 hidden、词表维度一致 / meta 为
dict——任一不符显式报错。推理前向（numpy）属 WP3，本模块只管资产读写。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.agent.action_features import ACTION_FEATURE_NAMES
from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.agent.policy_features import (
    POLICY_STATE_NAMES,
    policy_action_names,
)

__all__ = [
    "POLICY_FORMAT",
    "POLICY_FORMAT_V2",
    "PolicyModel",
    "load_policy_model",
    "save_policy_model",
]

POLICY_FORMAT = "bf-distilled-policy-v1"
POLICY_FORMAT_V2 = "bf-distilled-policy-v2"


@dataclass(frozen=True)
class PolicyModel:
    """策略打分机资产：score(state ⊕ action) = W2·relu(W1·x + b1) + b2。

    card_vocab：v2 资产的卡身份词表（D-062-2）；v1 资产 = None。
    """

    hidden: int
    weights: dict[str, tuple]  # w1 [hidden][in] / b1 [hidden] / w2 [1][hidden] / b2 [1]
    meta: dict
    card_vocab: tuple[str, ...] | None = None


def save_policy_model(model: PolicyModel, path: str | Path) -> None:
    """模型资产落盘（UTF-8 / ensure_ascii=False / indent=2 / sort_keys，位级确定）。

    card_vocab 为 None → v1 旧路径原样（既有资产逐字节兼容）；非 None → v2，
    特征清单按 policy_features 推导，payload 增 card_vocab。
    """
    if model.card_vocab is None:
        payload = {
            "format": POLICY_FORMAT,
            "state_feature_names": list(FEATURE_NAMES),
            "action_feature_names": list(ACTION_FEATURE_NAMES),
        }
    else:
        payload = {
            "format": POLICY_FORMAT_V2,
            "state_feature_names": list(POLICY_STATE_NAMES),
            "action_feature_names": list(policy_action_names(model.card_vocab)),
            "card_vocab": list(model.card_vocab),
        }
    payload.update({
        "hidden": model.hidden,
        "weights": {
            "w1": [list(r) for r in model.weights["w1"]],
            "b1": list(model.weights["b1"]),
            "w2": [list(r) for r in model.weights["w2"]],
            "b2": list(model.weights["b2"]),
        },
        "meta": model.meta,
    })
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")


def load_policy_model(path: str | Path) -> PolicyModel:
    """载入模型资产；按 format 分派 v1/v2 校验，任一不符显式报错（不猜）。"""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    fmt = payload.get("format")
    if fmt == POLICY_FORMAT:
        return _load_v1(payload)
    if fmt == POLICY_FORMAT_V2:
        return _load_v2(payload)
    raise ValueError(
        f"模型 format 不符：{fmt!r}（期望 {POLICY_FORMAT} 或 {POLICY_FORMAT_V2}）")


def _check_weights(payload: dict, in_dim: int) -> tuple[int, dict[str, tuple]]:
    """权重解析 + 形状校验（v1/v2 共用）；形状不符显式报错。"""
    hidden = int(payload["hidden"])
    raw = payload["weights"]
    weights = {
        "w1": tuple(tuple(float(v) for v in row) for row in raw["w1"]),
        "b1": tuple(float(v) for v in raw["b1"]),
        "w2": tuple(tuple(float(v) for v in row) for row in raw["w2"]),
        "b2": tuple(float(v) for v in raw["b2"]),
    }
    ok = (
        len(weights["w1"]) == hidden
        and all(len(row) == in_dim for row in weights["w1"])
        and len(weights["b1"]) == hidden
        and len(weights["w2"]) == 1 and len(weights["w2"][0]) == hidden
        and len(weights["b2"]) == 1
    )
    if not ok:
        raise ValueError(
            f"模型权重形状不符（不猜）：w1 {len(weights['w1'])}×"
            f"{len(weights['w1'][0]) if weights['w1'] else 0} / b1 {len(weights['b1'])}"
            f" / w2 {len(weights['w2'])}×"
            f"{len(weights['w2'][0]) if weights['w2'] else 0} / b2 {len(weights['b2'])}"
            f"（期望 w1 {hidden}×{in_dim} / b1 {hidden} / w2 1×{hidden} / b2 1）")
    return hidden, weights


def _check_meta(payload: dict) -> dict:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise TypeError("模型 meta 缺失或非 dict（不猜）")
    return meta


def _load_v1(payload: dict) -> PolicyModel:
    if tuple(payload["state_feature_names"]) != FEATURE_NAMES:
        raise ValueError(
            "模型状态特征清单与 FEATURE_NAMES 不符（训练/推理非同一份清单——不猜）")
    if tuple(payload["action_feature_names"]) != ACTION_FEATURE_NAMES:
        raise ValueError(
            "模型行动特征清单与 ACTION_FEATURE_NAMES 不符（训练/推理非同一份清单——不猜）")
    in_dim = len(FEATURE_NAMES) + len(ACTION_FEATURE_NAMES)
    hidden, weights = _check_weights(payload, in_dim)
    return PolicyModel(hidden=hidden, weights=weights, meta=_check_meta(payload))


def _load_v2(payload: dict) -> PolicyModel:
    raw_vocab = payload.get("card_vocab")
    if not isinstance(raw_vocab, list) or not raw_vocab \
            or not all(isinstance(n, str) for n in raw_vocab):
        raise ValueError(
            f"模型 card_vocab 缺失/为空/非字符串清单（不猜）：{raw_vocab!r}")
    card_vocab = tuple(raw_vocab)
    if tuple(payload["state_feature_names"]) != POLICY_STATE_NAMES:
        raise ValueError(
            "模型状态特征清单与 POLICY_STATE_NAMES 不符（训练/推理非同一份清单——不猜）")
    if tuple(payload["action_feature_names"]) != policy_action_names(card_vocab):
        raise ValueError(
            "模型行动特征清单与 card_vocab 联动不符（期望 action_feature_names"
            " == policy_action_names(card_vocab)——不猜）")
    in_dim = len(POLICY_STATE_NAMES) + len(policy_action_names(card_vocab))
    hidden, weights = _check_weights(payload, in_dim)
    return PolicyModel(hidden=hidden, weights=weights, meta=_check_meta(payload),
                       card_vocab=card_vocab)
