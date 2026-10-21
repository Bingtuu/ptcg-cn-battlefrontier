"""task 062 WP2a：策略模型资产 bf-distilled-policy-v2（format 分派 + card_vocab）。

- v2：card_vocab 非 None → format=bf-distilled-policy-v2，特征清单 =
  POLICY_STATE_NAMES / policy_action_names(card_vocab)，payload 增 card_vocab。
- v1 旧资产（models/policy-m12-v1.json）保持可装载，card_vocab 为 None
  （M12 锚 1 复算锚，D-062-4）。
- 未知 format / 缺 card_vocab / 词表与清单联动不符 / 权重形状不符 → 显式报错
  （不猜）；v1/v2 落盘均位级确定。
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from battlefrontier.agent.policy_features import (
    POLICY_STATE_NAMES,
    policy_action_names,
)
from battlefrontier.learn.policy_model import (
    POLICY_FORMAT,
    POLICY_FORMAT_V2,
    PolicyModel,
    load_policy_model,
    save_policy_model,
)

VOCAB = ("博士的研究", "基本超能量", "沙奈朵ex")  # 字典序钉死（WP2b 装载校验口径）
V2_IN_DIM = len(POLICY_STATE_NAMES) + len(policy_action_names(VOCAB))


def _toy_v2_model(hidden: int = 3) -> PolicyModel:
    return PolicyModel(
        hidden=hidden,
        weights={
            "w1": tuple(tuple(0.01 * (i + j) for j in range(V2_IN_DIM))
                        for i in range(hidden)),
            "b1": tuple(0.0 for _ in range(hidden)),
            "w2": (tuple(0.1 for _ in range(hidden)),),
            "b2": (0.5,),
        },
        meta={"feature_version": "v2"},
        card_vocab=VOCAB,
    )


def _save_mutated_v2(path, mutate) -> None:
    """落盘 v2 玩具模型 → JSON 变异 → 写回（装载失败用例用）。"""
    save_policy_model(_toy_v2_model(), path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class TestPolicyModelV2:
    def test_format常量钉死(self) -> None:
        assert POLICY_FORMAT == "bf-distilled-policy-v1"
        assert POLICY_FORMAT_V2 == "bf-distilled-policy-v2"

    def test_v2往返与位级确定(self, tmp_path) -> None:
        path = tmp_path / "m-v2.json"
        model = _toy_v2_model()
        save_policy_model(model, path)
        first = path.read_bytes()
        save_policy_model(model, path)
        assert path.read_bytes() == first
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["format"] == POLICY_FORMAT_V2
        assert payload["card_vocab"] == list(VOCAB)
        assert tuple(payload["state_feature_names"]) == POLICY_STATE_NAMES
        assert tuple(payload["action_feature_names"]) == policy_action_names(VOCAB)
        loaded = load_policy_model(path)
        assert loaded == model
        assert loaded.card_vocab == VOCAB

    def test_v1资产保持可装载(self) -> None:
        """已入库资产 models/policy-m12-v1.json（M12 锚 1 复算锚）走 v1 路径。"""
        model = load_policy_model("models/policy-m12-v1.json")
        assert model.card_vocab is None
        assert model.hidden > 0

    def test_v1在库资产逐字节锚(self, tmp_path) -> None:
        """真实在库资产 load → save → 字节全等（v1 落盘路径零漂移锚，WP2a 复核遗留）。"""
        src = Path("models/policy-m12-v1.json")
        model = load_policy_model(src)
        out = tmp_path / "roundtrip.json"
        save_policy_model(model, out)
        assert out.read_bytes() == src.read_bytes()

    def test_空card_vocab落盘显式报错(self, tmp_path) -> None:
        """card_vocab == () → save 显式报错（save 不能产出 load 拒绝的文件）。"""
        model = replace(_toy_v2_model(), card_vocab=())
        with pytest.raises(ValueError, match="card_vocab"):
            save_policy_model(model, tmp_path / "m.json")

    def test_v2词表未按字典序显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"

        def unsorted(p):
            vocab = ["沙奈朵ex", "博士的研究", "基本超能量"]  # 非字典序（博<基<沙）
            p["card_vocab"] = vocab
            p["action_feature_names"] = list(policy_action_names(tuple(vocab)))

        _save_mutated_v2(path, unsorted)
        with pytest.raises(ValueError, match="字典序"):
            load_policy_model(path)

    def test_v2词表重复显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"

        def duped(p):
            vocab = ["博士的研究", "博士的研究", "基本超能量", "沙奈朵ex"]
            p["card_vocab"] = vocab
            p["action_feature_names"] = list(policy_action_names(tuple(vocab)))

        _save_mutated_v2(path, duped)
        with pytest.raises(ValueError, match="去重"):
            load_policy_model(path)

    def test_v1落盘位级确定(self, tmp_path) -> None:
        from battlefrontier.agent.action_features import ACTION_FEATURE_NAMES
        from battlefrontier.agent.features import FEATURE_NAMES

        in_dim = len(FEATURE_NAMES) + len(ACTION_FEATURE_NAMES)
        model = PolicyModel(
            hidden=2,
            weights={
                "w1": tuple(tuple(0.01 * (i + j) for j in range(in_dim))
                            for i in range(2)),
                "b1": (0.0, 0.0),
                "w2": ((0.1, 0.1),),
                "b2": (0.5,),
            },
            meta={"source": "toy-v1"})
        assert model.card_vocab is None
        path = tmp_path / "m-v1.json"
        save_policy_model(model, path)
        first = path.read_bytes()
        save_policy_model(model, path)
        assert path.read_bytes() == first
        assert json.loads(path.read_text(encoding="utf-8"))["format"] == POLICY_FORMAT
        assert "card_vocab" not in json.loads(path.read_text(encoding="utf-8"))
        assert load_policy_model(path) == model

    def test_v2缺card_vocab显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"
        _save_mutated_v2(path, lambda p: p.pop("card_vocab"))
        with pytest.raises(ValueError, match="card_vocab"):
            load_policy_model(path)

    def test_v2空card_vocab显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"
        _save_mutated_v2(path, lambda p: p.__setitem__("card_vocab", []))
        with pytest.raises(ValueError, match="card_vocab"):
            load_policy_model(path)

    def test_v2词表与行动清单不符显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"
        # 字典序合法但与 action_feature_names 联动不符的词表
        _save_mutated_v2(path, lambda p: p.__setitem__(
            "card_vocab", ["博士的研究", "基本超能量", "梦幻ex"]))
        with pytest.raises(ValueError, match="action_feature_names"):
            load_policy_model(path)

    def test_v2状态清单不符显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"
        _save_mutated_v2(path, lambda p: p.__setitem__(
            "state_feature_names", list(reversed(p["state_feature_names"]))))
        with pytest.raises(ValueError, match="POLICY_STATE_NAMES"):
            load_policy_model(path)

    def test_未知format显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"
        _save_mutated_v2(path, lambda p: p.__setitem__("format", "bf-policy-v3"))
        with pytest.raises(ValueError, match="format"):
            load_policy_model(path)

    def test_v2权重形状不符显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"

        def break_w1(p):
            p["weights"]["w1"] = [row[:-1] for row in p["weights"]["w1"]]

        _save_mutated_v2(path, break_w1)
        with pytest.raises(ValueError, match="形状"):
            load_policy_model(path)

    def test_v2_meta缺失显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"
        _save_mutated_v2(path, lambda p: p.pop("meta"))
        with pytest.raises(TypeError, match="meta"):
            load_policy_model(path)
