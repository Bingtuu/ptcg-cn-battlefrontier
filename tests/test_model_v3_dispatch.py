"""task 155 WP4：资产 format bf-linear-eval-v3 装载/预测分派验收测试。

预注册判据冻结于 tasks/task 155.md：``load_model`` 按 ``payload["format"]``
分派——v1（``MODEL_FORMAT``）走现有校验路径**逐字不动**（``names !=
FEATURE_NAMES`` 的装载闸只对 v1 format 生效，eval-linear-v1/v2 保持可
装载）；v3（``MODEL_FORMAT_V3``）清单以资产为准，meta 必含 card_vocab /
zones，``predict(VisibleGameState)`` 自动走 ``feature_vector_v3(view,
vocab, zones)``。冻结 gate 脚本 ``.kimi-code/t150_eval_gate.py`` 的调用面
（``load_model`` + ``predict(model, view)``）对 v3 资产不得改一行。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import main_state

from battlefrontier.agent.eval_features import (
    EVAL_V3_ZONES,
    eval_v3_names,
    feature_vector_v3,
)
from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.learn.model import (
    MODEL_FORMAT,
    MODEL_FORMAT_V3,
    LinearModel,
    load_model,
    predict,
    save_model,
)

# 小型词表：main_state 局面可见卡名全覆盖（手牌 小火龙/基本能量、
# 己方盘面 妙蛙种子/基本能量、对手盘面 小火龙/基本能量）。
VOCAB = ("基本能量", "小火龙", "妙蛙种子")

ROOT = Path(__file__).resolve().parent.parent


def _v3_model(card_vocab: tuple[str, ...] = VOCAB,
              zones: tuple[str, ...] = EVAL_V3_ZONES,
              meta: dict | None = None) -> LinearModel:
    """v3 玩具资产：均值全 0 / 标准差全 1 / 权重全 0 + 截距 0.5。"""
    names = eval_v3_names(card_vocab)
    d = len(names)
    full_meta = {"card_vocab": list(card_vocab), "feature_set": "v3",
                 "warning": None, "zones": list(zones)}
    if meta:
        full_meta.update(meta)
    return LinearModel(feature_names=names, weights=(0.0,) * d + (0.5,),
                       mean=(0.0,) * d, std=(1.0,) * d, meta=full_meta,
                       card_vocab=card_vocab, zones=zones)


def _save_v3(model: LinearModel, path: Path) -> None:
    save_model(model, path, model_format=MODEL_FORMAT_V3)


# ── v3 资产 round-trip：清单以资产为准 ──────────────────────


def test_v3_roundtrip_清单以资产为准且可预测(tmp_path):
    model = _v3_model()
    p = tmp_path / "v3.json"
    _save_v3(model, p)
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["format"] == MODEL_FORMAT_V3
    # v3 清单（36 + 4×3 = 48 维）≠ FEATURE_NAMES——装载不得走 v1 的
    # FEATURE_NAMES 闸，以资产内清单为准
    assert tuple(payload["feature_names"]) != FEATURE_NAMES
    loaded = load_model(p)
    assert loaded == model
    assert loaded.feature_names == eval_v3_names(VOCAB)
    assert loaded.card_vocab == VOCAB
    assert loaded.zones == EVAL_V3_ZONES
    # 特征 dict 入口（键序 = 清单序）→ 输出 ∈ [0,1]
    view = main_state().visible_state(0)
    out = predict(loaded, feature_vector_v3(view, VOCAB))
    assert 0.0 <= out <= 1.0


# ── v3 装载校验：meta card_vocab / zones 强制（不猜）─────────


def test_v3_meta缺card_vocab_显式报错(tmp_path):
    model = _v3_model()
    model.meta.pop("card_vocab")
    p = tmp_path / "v3.json"
    _save_v3(model, p)
    with pytest.raises(ValueError, match="card_vocab"):
        load_model(p)


def test_v3_meta缺zones_显式报错(tmp_path):
    model = _v3_model()
    model.meta.pop("zones")
    p = tmp_path / "v3.json"
    _save_v3(model, p)
    with pytest.raises(ValueError, match="zones"):
        load_model(p)


@pytest.mark.parametrize("bad_vocab", ["妙蛙种子", [1, 2, 3], [("a",), "b"], 42])
def test_v3_card_vocab非字符串列表_显式报错(tmp_path, bad_vocab):
    model = _v3_model(meta={"card_vocab": bad_vocab})
    # meta 与携带字段不一致时以 meta（资产）为准——构造一致再落盘
    model = LinearModel(feature_names=model.feature_names, weights=model.weights,
                        mean=model.mean, std=model.std, meta=model.meta,
                        card_vocab=VOCAB, zones=EVAL_V3_ZONES)
    p = tmp_path / "v3.json"
    _save_v3(model, p)
    with pytest.raises(ValueError, match="card_vocab"):
        load_model(p)


@pytest.mark.parametrize("bad_zones", [["镜中世界"], ("own_hand", 42),
                                       "own_hand"])
def test_v3_zones未知区名_显式报错(tmp_path, bad_zones):
    model = _v3_model(meta={"zones": bad_zones})
    model = LinearModel(feature_names=model.feature_names, weights=model.weights,
                        mean=model.mean, std=model.std, meta=model.meta,
                        card_vocab=VOCAB, zones=EVAL_V3_ZONES)
    p = tmp_path / "v3.json"
    _save_v3(model, p)
    with pytest.raises(ValueError, match="zones"):
        load_model(p)


# ── predict：VisibleGameState 入口对 v3 走 feature_vector_v3 ──


def test_v3_predict_view入口_自动走v3特征层():
    """v3 资产 predict(view) = predict(特征 dict)（dict 经 feature_vector_v3），
    且 cid_ 权重真实参与点积（证明没走 v1 的 feature_vector）。"""
    names = eval_v3_names(VOCAB)
    weights = list((0.0,) * len(names) + (0.5,))
    weights[names.index("cid_own_hand_小火龙")] = 0.25
    model = LinearModel(feature_names=names, weights=tuple(weights),
                        mean=(0.0,) * len(names), std=(1.0,) * len(names),
                        meta={"card_vocab": list(VOCAB), "zones": list(EVAL_V3_ZONES)},
                        card_vocab=VOCAB, zones=EVAL_V3_ZONES)
    view = main_state().visible_state(0)  # 己方手牌恰 1 张小火龙
    out = predict(model, view)
    assert out == pytest.approx(0.75)  # 截距 0.5 + 计数 1 × 权重 0.25
    assert out == predict(model, feature_vector_v3(view, VOCAB, EVAL_V3_ZONES))
    assert 0.0 <= out <= 1.0


def test_v3_predict_dict入口键序校验沿用(tmp_path):
    model = _v3_model()
    p = tmp_path / "v3.json"
    _save_v3(model, p)
    loaded = load_model(p)
    view = main_state().visible_state(0)
    shuffled = dict(reversed(list(feature_vector_v3(view, VOCAB).items())))
    with pytest.raises(ValueError, match="键序"):
        predict(loaded, shuffled)


def test_v3_资产喂gate调用面_load加predict_view可运行(tmp_path):
    """冻结 gate 脚本 .kimi-code/t150_eval_gate.py 的调用面 = load_model +
    predict(model, visible_state)——伪造 v3 资产原样可跑。"""
    p = tmp_path / "eval-linear-v3.json"
    _save_v3(_v3_model(), p)
    model = load_model(p)
    assert model.meta["feature_set"] == "v3"
    out = predict(model, main_state().visible_state(0))
    assert isinstance(out, float) and 0.0 <= out <= 1.0


# ── v1 回归锚：v1 路径逐字不动 ──────────────────────────────


def test_v1实际资产仍可装载且为v1语义():
    """models/eval-linear-v1.json（入库锚定资产）装载走 v1 路径：
    FEATURE_NAMES 闸照常生效，card_vocab/zones 缺省 None。"""
    model = load_model(ROOT / "models" / "eval-linear-v1.json")
    assert model.feature_names == FEATURE_NAMES
    assert model.card_vocab is None
    assert model.zones is None
    # v1 语义：predict(view) 走 feature_vector（30 维），输出 ∈ [0,1]
    out = predict(model, main_state().visible_state(0))
    assert 0.0 <= out <= 1.0


def test_v1清单被篡改仍走FEATURE_NAMES闸(tmp_path):
    """v1 format 的装载闸不因 v3 分派存在而改变（回归锚）。"""
    from battlefrontier.agent.features import feature_vector

    names = list(FEATURE_NAMES)
    names[0], names[1] = names[1], names[0]
    model = LinearModel(feature_names=tuple(names),
                        weights=(0.0,) * (len(names) + 1),
                        mean=(0.0,) * len(names), std=(1.0,) * len(names),
                        meta={"warning": None})
    p = tmp_path / "v1.json"
    save_model(model, p)  # 缺省 model_format = v1
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["format"] == MODEL_FORMAT
    with pytest.raises(ValueError, match="FEATURE_NAMES"):
        load_model(p)
    # 旁证：feature_vector（v1 入口）在本测试覆盖 import
    view = main_state().visible_state(0)
    assert tuple(feature_vector(view)) == FEATURE_NAMES
