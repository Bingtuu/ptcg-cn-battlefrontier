"""M11 学得评估器模型资产（task 051 WP2，D-M11-3）：JSON 读写 + 推理接口。

资产 = 单 JSON（进版本控制，D3-4）：weights（末位截距）/ feature 键序清单 /
标准化 mean/std / meta（数据种子区间 / 局数 / 配对数 / 代码版本 / 卡池 /
split_seed / λ / 训练+验证 MSE / 常数基线 MSE / 告警字段）。落盘位级确定：
json.dumps（sort_keys，float 走 repr 最短往返精度）。

推理：特征键序强制校验（模型清单 vs FEATURE_NAMES 不符显式报错——不猜）→
z-score 标准化 → 点积（含截距）→ clamp [0,1]。predict 双入口：特征 dict
（键序须与模型清单逐一相等）或 VisibleGameState（内部走 feature_vector）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.agent.features import FEATURE_NAMES, feature_vector
from battlefrontier.engine.state import VisibleGameState

__all__ = ["MODEL_FORMAT", "LinearModel", "load_model", "predict", "save_model"]

MODEL_FORMAT = "bf-linear-eval-v1"


@dataclass(frozen=True)
class LinearModel:
    """线性评估器资产：weights 末位为截距；mean/std 与 feature_names 同序。"""

    feature_names: tuple[str, ...]
    weights: tuple[float, ...]   # len = len(feature_names) + 1，末位截距
    mean: tuple[float, ...]
    std: tuple[float, ...]
    meta: dict


def save_model(model: LinearModel, path: str | Path) -> None:
    """模型资产落盘（UTF-8 / ensure_ascii=False / indent=2 / sort_keys，位级确定）。"""
    payload = {
        "format": MODEL_FORMAT,
        "feature_names": list(model.feature_names),
        "weights": list(model.weights),
        "standardize": {"mean": list(model.mean), "std": list(model.std)},
        "meta": model.meta,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")


def load_model(path: str | Path) -> LinearModel:
    """载入模型资产；结构 / 特征清单 / 维度长度不符显式报错（不猜）。"""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format") != MODEL_FORMAT:
        raise ValueError(f"模型 format 不符：{payload.get('format')!r}（期望 {MODEL_FORMAT}）")
    names = tuple(payload["feature_names"])
    if names != FEATURE_NAMES:
        raise ValueError(
            "模型特征清单与 FEATURE_NAMES 不符（训练/推理非同一份清单——不猜）："
            f"模型 {list(names)!r} vs 代码 {list(FEATURE_NAMES)!r}")
    weights = tuple(float(w) for w in payload["weights"])
    mean = tuple(float(v) for v in payload["standardize"]["mean"])
    std = tuple(float(v) for v in payload["standardize"]["std"])
    d = len(names)
    if len(weights) != d + 1 or len(mean) != d or len(std) != d:
        raise ValueError(
            f"模型维度长度不符：weights {len(weights)} / mean {len(mean)} / "
            f"std {len(std)}（特征 {d} 维，weights 应为 {d + 1}）")
    if any(s <= 0.0 for s in std):
        raise ValueError("模型标准化 std 含非正值（不猜）")
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise TypeError("模型 meta 缺失或非 dict（不猜）")
    return LinearModel(feature_names=names, weights=weights, mean=mean, std=std,
                       meta=meta)


def predict(model: LinearModel, x: Mapping[str, float] | VisibleGameState) -> float:
    """V(局面) → [0,1] 行动方胜率估计：标准化 → 点积（含截距）→ clamp。

    特征 dict 入口：键序须与模型清单逐一相等（顺序错误会静默错配点积——显式
    报错不猜）；VisibleGameState 入口内部走 feature_vector（键序钉死）。
    """
    if isinstance(x, VisibleGameState):
        feats = feature_vector(x)
    elif isinstance(x, Mapping):
        feats = x
    else:
        raise TypeError(f"predict 输入须为特征 dict 或 VisibleGameState：{type(x).__name__}")
    if tuple(feats) != model.feature_names:
        raise ValueError(
            "特征键序与模型清单不符（不猜）："
            f"输入 {list(feats)!r} vs 模型 {list(model.feature_names)!r}")
    total = model.weights[-1]
    for i, name in enumerate(model.feature_names):
        total += ((feats[name] - model.mean[i]) / model.std[i]) * model.weights[i]
    return min(1.0, max(0.0, total))
