"""M11 学得评估器模型资产（task 051 WP2，D-M11-3）：JSON 读写 + 推理接口。

资产 = 单 JSON（进版本控制，D3-4）：weights（末位截距）/ feature 键序清单 /
标准化 mean/std / meta（数据种子区间 / 局数 / 配对数 / 代码版本 / 卡池 /
split_seed / λ / 训练+验证 MSE / 常数基线 MSE / 告警字段）。落盘位级确定：
json.dumps（sort_keys，float 走 repr 最短往返精度）。

推理：特征键序强制校验（模型清单 vs FEATURE_NAMES 不符显式报错——不猜）→
z-score 标准化 → 点积（含截距）→ clamp [0,1]。predict 双入口：特征 dict
（键序须与模型清单逐一相等）或 VisibleGameState（内部走 feature_vector）。

task 155 WP4：资产 format 分派——``bf-linear-eval-v1`` 走上面 v1 校验路径
逐字不动；``bf-linear-eval-v3`` 清单以资产为准（不再对 FEATURE_NAMES），
meta 必含 card_vocab / zones，``predict(VisibleGameState)`` 自动走
``feature_vector_v3(view, vocab, zones)``（分派依据 = 模型是否携带
card_vocab，v1 资产恒为 None）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.agent.eval_features import EVAL_V3_ZONES, feature_vector_v3
from battlefrontier.agent.features import FEATURE_NAMES, feature_vector
from battlefrontier.engine.state import VisibleGameState

__all__ = ["MODEL_FORMAT", "MODEL_FORMAT_V3", "LinearModel", "load_model",
           "predict", "save_model"]

MODEL_FORMAT = "bf-linear-eval-v1"
# task 155 WP3：v3 训练产物 format（装载/预测分派在 WP4 才接——load_model 现状
# 只认 v1，本常量当前仅供 save_model 写盘与 meta 锚点）。
MODEL_FORMAT_V3 = "bf-linear-eval-v3"


@dataclass(frozen=True)
class LinearModel:
    """线性评估器资产：weights 末位为截距；mean/std 与 feature_names 同序。

    task 155 WP4：v3 资产（bf-linear-eval-v3）另携 card_vocab / zones
    （装载时从 meta 还原；None = v1 语义，向后兼容默认值）。
    """

    feature_names: tuple[str, ...]
    weights: tuple[float, ...]   # len = len(feature_names) + 1，末位截距
    mean: tuple[float, ...]
    std: tuple[float, ...]
    meta: dict
    card_vocab: tuple[str, ...] | None = None   # v3：卡身份分区词表
    zones: tuple[str, ...] | None = None        # v3：分区名单（缺省 EVAL_V3_ZONES）


def save_model(model: LinearModel, path: str | Path, *,
               model_format: str = MODEL_FORMAT) -> None:
    """模型资产落盘（UTF-8 / ensure_ascii=False / indent=2 / sort_keys，位级确定）。

    task 155 WP3：``model_format`` 可覆盖 format 字段（v3 产物写
    ``MODEL_FORMAT_V3``——装载分派在 WP4）；缺省 = v1 旧行为逐位不变。
    """
    payload = {
        "format": model_format,
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
    """载入模型资产；结构 / 特征清单 / 维度长度不符显式报错（不猜）。

    task 155 WP4：按 ``payload["format"]`` 分派——v1 校验路径逐字不动；
    v3 清单以资产为准（绕开 FEATURE_NAMES 闸），meta 必含 card_vocab /
    zones 且类型 / 区名合法。
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format") == MODEL_FORMAT_V3:
        return _load_model_v3(payload)
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


def _load_model_v3(payload: dict) -> LinearModel:
    """task 155 WP4：v3 资产（bf-linear-eval-v3）装载校验——特征清单以
    资产内钉死清单为准（不再对 FEATURE_NAMES）；meta 必含 card_vocab /
    zones（不猜）。"""
    names = tuple(payload["feature_names"])
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
    card_vocab = meta.get("card_vocab")
    if (not isinstance(card_vocab, tuple | list)
            or not all(isinstance(n, str) for n in card_vocab)):
        raise ValueError("v3 资产 meta 缺 card_vocab 或非 tuple/list of str"
                         "（装载须自带词表，不猜）")
    zones = meta.get("zones")
    if (not isinstance(zones, tuple | list)
            or not all(isinstance(z, str) for z in zones)):
        raise ValueError("v3 资产 meta 缺 zones 或非 tuple/list of str（不猜）")
    unknown = [z for z in zones if z not in EVAL_V3_ZONES]
    if unknown:
        raise ValueError(f"v3 资产 meta zones 含未知区名 {unknown!r}"
                         f"（合法区 = {list(EVAL_V3_ZONES)!r}，不猜）")
    return LinearModel(feature_names=names, weights=weights, mean=mean, std=std,
                       meta=meta, card_vocab=tuple(card_vocab),
                       zones=tuple(zones))


def predict(model: LinearModel, x: Mapping[str, float] | VisibleGameState) -> float:
    """V(局面) → [0,1] 行动方胜率估计：标准化 → 点积（含截距）→ clamp。

    特征 dict 入口：键序须与模型清单逐一相等（顺序错误会静默错配点积——显式
    报错不猜）；VisibleGameState 入口：v1 走 feature_vector，v3（模型携
    card_vocab）走 feature_vector_v3（词表 / 分区以资产 meta 为准）。
    """
    if isinstance(x, VisibleGameState):
        if model.card_vocab is not None:
            feats = feature_vector_v3(
                x, card_vocab=model.card_vocab,
                zones=model.zones if model.zones is not None else EVAL_V3_ZONES)
        else:
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
