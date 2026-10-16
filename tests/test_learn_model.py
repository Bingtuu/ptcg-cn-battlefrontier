"""task 051 · M11 WP2：模型资产 JSON 读写 + 推理接口（D-M11-3 推理解口径）。

验收口径见 `tasks/task 051.md`：特征键序强制校验（模型清单 vs FEATURE_NAMES 不符
显式报错不猜）→ 标准化 → 点积 → clamp [0,1]；资产 JSON 位级确定落盘
（sort_keys + float repr 精度）；predict 双入口（特征 dict / VisibleGameState）。
"""

import json

import pytest
from helpers import main_state

from battlefrontier.agent.features import FEATURE_NAMES, feature_vector
from battlefrontier.learn import LinearModel, load_model, predict, save_model


def _toy_model(**over) -> LinearModel:
    """手算用玩具模型：均值全 0 / 标准差全 1 / 权重全 0 + 截距 0.5。"""
    kw = {
        "feature_names": FEATURE_NAMES,
        "weights": (0.0,) * len(FEATURE_NAMES) + (0.5,),
        "mean": (0.0,) * len(FEATURE_NAMES),
        "std": (1.0,) * len(FEATURE_NAMES),
        "meta": {"warning": None},
    }
    kw.update(over)
    return LinearModel(**kw)


def _zero_feats() -> dict[str, float]:
    return {name: 0.0 for name in FEATURE_NAMES}


# ── 推理：正常路径数值正确（手算）─────────────────────────

def test_predict_截距与点积_手算对照():
    model = _toy_model()
    assert predict(model, _zero_feats()) == 0.5  # 全零特征 → 只剩截距
    # prize_diff 权重 0.1，特征值 3.0 → 0.5 + 0.3 = 0.8
    w = list(model.weights)
    w[FEATURE_NAMES.index("prize_diff")] = 0.1
    model = _toy_model(weights=tuple(w))
    feats = _zero_feats() | {"prize_diff": 3.0}
    assert predict(model, feats) == pytest.approx(0.8)


def test_predict_标准化_手算对照():
    """z-score：mean=1/std=2 维度上特征值 3 → (3-1)/2=1，×权重 0.5 + 截距 0 = 0.5。"""
    idx = FEATURE_NAMES.index("prize_diff")
    w = [0.0] * (len(FEATURE_NAMES) + 1)
    w[idx] = 0.5
    mean = [0.0] * len(FEATURE_NAMES)
    std = [1.0] * len(FEATURE_NAMES)
    mean[idx], std[idx] = 1.0, 2.0
    model = _toy_model(weights=tuple(w), mean=tuple(mean), std=tuple(std))
    feats = _zero_feats() | {"prize_diff": 3.0}
    assert predict(model, feats) == pytest.approx(0.5)


def test_predict_输出clamp到01():
    assert predict(_toy_model(weights=(0.0,) * 30 + (1.7,)), _zero_feats()) == 1.0
    assert predict(_toy_model(weights=(0.0,) * 30 + (-0.7,)), _zero_feats()) == 0.0


# ── 推理：键序强制校验（不猜）─────────────────────────────

def test_predict_键序不符_显式报错():
    model = _toy_model()
    # 键集合相同但顺序不同 → 显式报错（顺序错误会静默错配点积，不猜）
    shuffled = dict(reversed(list(_zero_feats().items())))
    with pytest.raises(ValueError, match="键序"):
        predict(model, shuffled)
    # 缺键
    missing = _zero_feats()
    del missing["prize_diff"]
    with pytest.raises(ValueError, match="键序"):
        predict(model, missing)
    # 多键
    extra = _zero_feats() | {"幽灵特征": 1.0}
    with pytest.raises(ValueError, match="键序"):
        predict(model, extra)


def test_predict_非法输入类型_显式报错():
    with pytest.raises(TypeError):
        predict(_toy_model(), [0.0] * 30)  # type: ignore[arg-type]


# ── 推理：VisibleGameState 入口 ───────────────────────────

def test_predict_view入口_与特征dict入口一致():
    view = main_state().visible_state(0)
    model = _toy_model()
    assert predict(model, view) == predict(model, feature_vector(view)) == 0.5


# ── 资产读写 ──────────────────────────────────────────────

def test_save_load_往返全等():
    model = _toy_model(meta={"lambda": 1.0, "warning": None})
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        p = Path(d) / "m.json"
        save_model(model, p)
        assert load_model(p) == model


def test_save_位级确定_两写字节全等(tmp_path):
    model = _toy_model(weights=tuple(i * 0.1 for i in range(31)))
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    save_model(model, a)
    save_model(model, b)
    assert a.read_bytes() == b.read_bytes()


def test_save_键序sorted且含必备段(tmp_path):
    p = tmp_path / "m.json"
    save_model(_toy_model(), p)
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert list(payload) == sorted(payload)  # sort_keys
    assert payload["format"] == "bf-linear-eval-v1"
    assert payload["feature_names"] == list(FEATURE_NAMES)
    assert len(payload["weights"]) == len(FEATURE_NAMES) + 1
    assert set(payload["standardize"]) == {"mean", "std"}
    assert isinstance(payload["meta"], dict)


def test_load_model_特征清单与FEATURE_NAMES不符_显式报错(tmp_path):
    p = tmp_path / "m.json"
    save_model(_toy_model(), p)
    payload = json.loads(p.read_text(encoding="utf-8"))
    names = payload["feature_names"]
    names[0], names[1] = names[1], names[0]  # 顺序篡改
    p.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True),
                 encoding="utf-8")
    with pytest.raises(ValueError, match="FEATURE_NAMES"):
        load_model(p)


def test_load_model_维度长度不符_显式报错(tmp_path):
    p = tmp_path / "m.json"
    save_model(_toy_model(), p)
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload["weights"] = payload["weights"][:-1]  # 少一维
    p.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True),
                 encoding="utf-8")
    with pytest.raises(ValueError, match="长度"):
        load_model(p)


def test_load_model_std非正_显式报错(tmp_path):
    p = tmp_path / "m.json"
    save_model(_toy_model(), p)
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload["standardize"]["std"][3] = 0.0
    p.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True),
                 encoding="utf-8")
    with pytest.raises(ValueError, match="std"):
        load_model(p)
