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
from battlefrontier.agent.policy_features import (
    POLICY_STATE_NAMES,
    policy_action_names,
)
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


# ── task 062 WP2b：v2 特征训练接入 ───────────────────────────

STUB_VOCAB = tuple(sorted({c.name for c in deck60()}))
V2_ACTION_NAMES = policy_action_names(STUB_VOCAB)
V2_INPUT_DIM = len(POLICY_STATE_NAMES) + len(V2_ACTION_NAMES)


@pytest.fixture(scope="module")
def samples_v2(snapshot_dir):
    from battlefrontier.learn.policy_data import load_policy_samples

    return load_policy_samples(snapshot_dir, card_vocab=STUB_VOCAB)


class TestTrainPolicyV2:
    def test_v2训练meta词表与形状(self, samples_v2, tmp_path) -> None:
        model = train_policy(samples_v2, epochs=2, hidden=8, code_version="test-v2",
                             state_names=POLICY_STATE_NAMES,
                             action_names=V2_ACTION_NAMES,
                             card_vocab=STUB_VOCAB)
        assert model.meta["feature_version"] == "v2"
        assert model.card_vocab == STUB_VOCAB
        assert model.hidden == 8
        assert len(model.weights["w1"]) == 8
        assert all(len(r) == V2_INPUT_DIM for r in model.weights["w1"])
        assert len(model.weights["w2"]) == 1 and len(model.weights["w2"][0]) == 8
        assert 0.0 <= model.meta["train_argmax_accuracy"] <= 1.0
        # v2 资产可落盘回读（format 分派走 policy_model 既有校验）
        out = tmp_path / "policy-v2.json"
        save_policy_model(model, out)
        loaded = load_policy_model(out)
        assert loaded == model
        assert loaded.card_vocab == STUB_VOCAB

    def test_v1缺省路径feature_version(self, samples) -> None:
        """不传 state/action/card_vocab → v1 口径逐位不变，meta feature_version=v1。"""
        model = train_policy(samples, epochs=1, hidden=4)
        assert model.meta["feature_version"] == "v1"
        assert model.card_vocab is None
        assert all(len(r) == INPUT_DIM for r in model.weights["w1"])

    @pytest.mark.parametrize("kwargs", [
        {"card_vocab": STUB_VOCAB},
        {"state_names": POLICY_STATE_NAMES},
        {"action_names": V2_ACTION_NAMES},
        {"state_names": POLICY_STATE_NAMES, "action_names": V2_ACTION_NAMES},
        {"state_names": POLICY_STATE_NAMES, "card_vocab": STUB_VOCAB},
        {"action_names": V2_ACTION_NAMES, "card_vocab": STUB_VOCAB},
    ])
    def test_参数混搭显式报错(self, samples, kwargs) -> None:
        """state_names/action_names/card_vocab 三者要么全 None（v1）要么全提供（v2）。"""
        with pytest.raises(ValueError, match="混搭"):
            train_policy(samples, epochs=1, hidden=4, **kwargs)

    def test_v2_state_names不符显式报错(self, samples_v2) -> None:
        """v2 分支 state_names 须与 POLICY_STATE_NAMES 逐一相等（不猜）。"""
        with pytest.raises(ValueError, match="state_names"):
            train_policy(samples_v2, epochs=1, hidden=4,
                         state_names=tuple(reversed(POLICY_STATE_NAMES)),
                         action_names=V2_ACTION_NAMES, card_vocab=STUB_VOCAB)

    def test_v2_action_names不符显式报错(self, samples_v2) -> None:
        """v2 分支 action_names 须与 policy_action_names(card_vocab) 逐一相等。"""
        with pytest.raises(ValueError, match="action_names"):
            train_policy(samples_v2, epochs=1, hidden=4,
                         state_names=POLICY_STATE_NAMES,
                         action_names=tuple(reversed(V2_ACTION_NAMES)),
                         card_vocab=STUB_VOCAB)

    def test_样本缺特征键显式报错(self) -> None:
        """样本 dict 缺键 → ValueError 带缺失键名与样本上下文（不猜）。"""
        from battlefrontier.learn.policy_data import PolicySample
        from battlefrontier.learn.train_policy import _flatten_samples

        bad = PolicySample(pair_index=3, seed=456,
                           state={"turn_norm": 0.5},
                           actions=(dict.fromkeys(V2_ACTION_NAMES, 0.0),),
                           teacher_index=0)
        with pytest.raises(ValueError, match="缺特征键"):
            _flatten_samples([bad], POLICY_STATE_NAMES, V2_ACTION_NAMES)


# ── 向量化等价性（task 058 性能修正）────────────────────────────


def _reference_terms(net, rows):
    """旧逐样本算法的独立参考实现：每样本 cat(state, action) 前向 + cross_entropy。"""
    import torch

    terms = []
    for s in rows:
        st = torch.tensor([s.state[n] for n in FEATURE_NAMES],
                          dtype=torch.float32)
        acts = torch.tensor([[a[n] for n in ACTION_FEATURE_NAMES]
                             for a in s.actions], dtype=torch.float32)
        x = torch.cat([st.unsqueeze(0).expand(acts.shape[0], -1), acts], dim=1)
        logits = net(x).squeeze(-1)
        terms.append(torch.nn.functional.cross_entropy(
            logits.unsqueeze(0), torch.tensor([s.teacher_index])))
    return terms


class TestVectorizedEquivalence:
    """向量化 loss/argmax 与旧逐样本算法数值一致（同初始化同数据，atol 1e-5）。"""

    def _net_and_flat(self, samples):
        import torch

        from battlefrontier.learn.train_policy import (
            _flatten_samples,
            _split_by_game,
        )

        train_rows, _ = _split_by_game(samples, DEFAULT_SPLIT_SEED)
        torch.manual_seed(DEFAULT_SPLIT_SEED)
        net = torch.nn.Sequential(
            torch.nn.Linear(INPUT_DIM, 8),
            torch.nn.ReLU(),
            torch.nn.Linear(8, 1),
        )
        x, teacher_global, sample_ids = _flatten_samples(train_rows)
        assert x.shape == (sample_ids.numel(), INPUT_DIM)
        assert teacher_global.numel() == len(train_rows)
        return net, train_rows, x, teacher_global, sample_ids

    def test_向量化loss与逐样本数值一致(self, samples) -> None:
        import torch

        from battlefrontier.learn.train_policy import _vectorized_loss

        net, rows, x, teacher_global, sample_ids = self._net_and_flat(samples)
        vec = _vectorized_loss(net, x, teacher_global, sample_ids)
        ref = torch.stack(_reference_terms(net, rows)).mean()
        assert vec.shape == ()
        assert abs(float(vec.detach()) - float(ref.detach())) <= 1e-5
        # 梯度同样一致（累加序差异容忍）
        g_vec = torch.autograd.grad(vec, list(net.parameters()))
        g_ref = torch.autograd.grad(ref, list(net.parameters()))
        for gv, gr in zip(g_vec, g_ref, strict=True):
            assert torch.allclose(gv, gr, atol=1e-5, rtol=1e-4)

    def test_向量化argmax准确率与逐样本一致(self, samples) -> None:
        import torch

        from battlefrontier.learn.train_policy import _argmax_accuracy

        net, rows, x, teacher_global, sample_ids = self._net_and_flat(samples)
        acc = _argmax_accuracy(net, x, teacher_global, sample_ids)
        with torch.no_grad():
            correct = 0
            for s in rows:
                st = torch.tensor([s.state[n] for n in FEATURE_NAMES],
                                  dtype=torch.float32)
                acts = torch.tensor([[a[n] for n in ACTION_FEATURE_NAMES]
                                     for a in s.actions], dtype=torch.float32)
                xi = torch.cat([st.unsqueeze(0).expand(acts.shape[0], -1), acts],
                               dim=1)
                logits = net(xi).squeeze(-1)
                correct += int(int(logits.argmax().item()) == s.teacher_index)
        assert acc == correct / len(rows)


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
