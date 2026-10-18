"""task 058 · M12 WP2：策略模型资产 + torch 训练管线 + CLI 验收测试（D-M12-3/4）。

- 资产 bf-distilled-policy-v1：format id / 特征词表键序 / 权重形状强校验，
  装载失败显式报错（不猜）；落盘位级确定（同模型两写字节全等）。
- 训练（learn/train_policy.py，torch dev-only）：MLP 打分机（state⊕action →
  标量 logit）合法行动掩码 softmax + 教师硬标签 NLL；按局 80/20 划分；
  holdout argmax 准确率落 meta；训练非复算面（D3-4），缺省超参全钉死写 meta。
- CLI train-policy 端到端小样本：冒烟快照目录 → 资产 JSON 可装载回读。
"""

from __future__ import annotations

import json

import pytest
from helpers import deck60

from battlefrontier.agent.action_features import ACTION_FEATURE_NAMES
from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.cli import main as cli_main
from battlefrontier.learn.policy_model import (
    POLICY_FORMAT,
    PolicyModel,
    load_policy_model,
    save_policy_model,
)
from battlefrontier.learn.train_policy import (
    DEFAULT_EPOCHS,
    DEFAULT_HIDDEN,
    DEFAULT_LR,
    DEFAULT_SPLIT_SEED,
    train_policy,
)
from battlefrontier.runner.snapshot import run_collect_snapshots
from battlefrontier.tune.fitness import PairAssignment, PreparedPair

INPUT_DIM = len(FEATURE_NAMES) + len(ACTION_FEATURE_NAMES)


def _toy_model(hidden: int = 4) -> PolicyModel:
    return PolicyModel(
        hidden=hidden,
        weights={
            "w1": tuple(tuple(0.01 * (i + j) for j in range(INPUT_DIM))
                        for i in range(hidden)),
            "b1": tuple(0.0 for _ in range(hidden)),
            "w2": (tuple(0.1 for _ in range(hidden)),),
            "b2": (0.5,),
        },
        meta={"source": "toy"})


def _mutated(path, mutate) -> None:
    """落盘玩具模型 → JSON 变异 → 写回（装载失败用例用）。"""
    save_policy_model(_toy_model(), path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"测试A{index}",
                                  archetype_b=f"测试B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


@pytest.fixture(scope="module")
def snapshot_dir(tmp_path_factory):
    """stub 配对教师（1×2 MCTS）2 局快照目录（供载入/训练/CLI 共用）。"""
    out = tmp_path_factory.mktemp("policy-train")
    (s,) = run_collect_snapshots([_stub_pair(0)], games_per_pair=2,
                                 seed_start=450000, out_dir=out, workers=1,
                                 teacher={"worlds": 1, "iterations": 2,
                                          "rollout_turn_cap": 50})
    assert s.rows > 0
    return out


@pytest.fixture(scope="module")
def samples(snapshot_dir):
    from battlefrontier.learn.policy_data import load_policy_samples

    return load_policy_samples(snapshot_dir)


# ── 模型资产 ─────────────────────────────────────────────────


class TestPolicyModelAsset:
    def test_format钉死(self) -> None:
        assert POLICY_FORMAT == "bf-distilled-policy-v1"

    def test_往返与位级确定(self, tmp_path) -> None:
        path = tmp_path / "m.json"
        model = _toy_model()
        save_policy_model(model, path)
        first = path.read_bytes()
        save_policy_model(model, path)
        assert path.read_bytes() == first
        assert load_policy_model(path) == model

    def test_format不符显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"
        _mutated(path, lambda p: p.__setitem__("format", "bf-linear-eval-v1"))
        with pytest.raises(ValueError, match="format"):
            load_policy_model(path)

    def test_词表键序不符显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"
        _mutated(path, lambda p: p.__setitem__(
            "state_feature_names", list(reversed(p["state_feature_names"]))))
        with pytest.raises(ValueError, match="FEATURE_NAMES"):
            load_policy_model(path)
        _mutated(path, lambda p: p.__setitem__(
            "action_feature_names", list(reversed(p["action_feature_names"]))))
        with pytest.raises(ValueError, match="ACTION_FEATURE_NAMES"):
            load_policy_model(path)

    def test_权重形状不符显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"

        def break_w1(p):
            p["weights"]["w1"] = p["weights"]["w1"] + p["weights"]["w1"]

        _mutated(path, break_w1)
        with pytest.raises(ValueError, match="形状"):
            load_policy_model(path)

    def test_meta缺失显式报错(self, tmp_path) -> None:
        path = tmp_path / "m.json"
        _mutated(path, lambda p: p.pop("meta"))
        with pytest.raises(TypeError, match="meta"):
            load_policy_model(path)


# ── 训练管线 ─────────────────────────────────────────────────


class TestTrainPolicy:
    def test_小样本训练与meta(self, samples, tmp_path) -> None:
        model = train_policy(samples, epochs=2, hidden=8, code_version="test-sha")
        m = model.meta
        assert model.hidden == 8
        assert len(model.weights["w1"]) == 8
        assert len(model.weights["w1"][0]) == INPUT_DIM
        assert len(model.weights["b1"]) == 8
        assert len(model.weights["w2"]) == 1 and len(model.weights["w2"][0]) == 8
        assert len(model.weights["b2"]) == 1
        # 缺省钉死与超参回显
        assert m["epochs"] == 2 and m["hidden"] == 8
        assert m["lr"] == DEFAULT_LR
        assert m["split_seed"] == DEFAULT_SPLIT_SEED
        assert m["code_version"] == "test-sha"
        assert m["rows"] == len(samples)
        assert m["games"] == 2 and m["train_games"] + m["val_games"] == 2
        assert 0.0 <= m["train_argmax_accuracy"] <= 1.0
        assert m["val_argmax_accuracy"] is None \
            or 0.0 <= m["val_argmax_accuracy"] <= 1.0
        assert m["train_loss"] > 0.0
        assert "torch_version" in m
        # 资产可落盘回读
        out = tmp_path / "policy.json"
        save_policy_model(model, out)
        assert load_policy_model(out) == model

    def test_单局划分显式报错(self, samples) -> None:
        one_game = [s for s in samples if s.seed == samples[0].seed]
        with pytest.raises(ValueError, match="局数不足"):
            train_policy(one_game, epochs=1, hidden=4)

    def test_缺省值钉死(self) -> None:
        assert DEFAULT_EPOCHS == 100
        assert DEFAULT_LR == 1e-3
        assert DEFAULT_HIDDEN == 64
        assert DEFAULT_SPLIT_SEED == 20261018


# ── CLI ─────────────────────────────────────────────────────


class TestTrainPolicyCli:
    def test_端到端小样本(self, snapshot_dir, tmp_path) -> None:
        out = tmp_path / "policy.json"
        rc = cli_main(["train-policy", "--data", str(snapshot_dir),
                       "--out", str(out), "--epochs", "1", "--hidden", "8"])
        assert rc == 0
        model = load_policy_model(out)
        assert model.meta["epochs"] == 1 and model.meta["hidden"] == 8
        assert model.meta["rows"] > 0
        assert model.meta["val_argmax_accuracy"] is None \
            or 0.0 <= model.meta["val_argmax_accuracy"] <= 1.0

    def test_空目录退出码1(self, tmp_path) -> None:
        data = tmp_path / "empty"
        data.mkdir()
        rc = cli_main(["train-policy", "--data", str(data),
                       "--out", str(tmp_path / "m.json"), "--epochs", "1"])
        assert rc == 1


def test_冒烟数据转换与训练(tmp_path) -> None:
    """真实冒烟快照（results/m12-teacher-smoke，984 点/5 局）：载入 → 1 epoch
    训练 → 资产落盘可回读（任务书验收 3 的测试侧镜像）。"""
    from pathlib import Path

    from battlefrontier.learn.policy_data import load_policy_samples

    smoke = Path("results/m12-teacher-smoke")
    if not smoke.exists():
        pytest.skip("本机无冒烟数据")
    smoke_samples = load_policy_samples(smoke)
    assert len(smoke_samples) == 984
    model = train_policy(smoke_samples, epochs=1, hidden=16, code_version="smoke")
    out = tmp_path / "smoke-policy.json"
    save_policy_model(model, out)
    loaded = load_policy_model(out)
    assert loaded.meta["games"] == 5
    assert loaded.meta["val_argmax_accuracy"] is not None
