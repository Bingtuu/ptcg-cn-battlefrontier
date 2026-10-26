"""task 066 WP1：加权 NLL 数值对拍 / 缺省逐位全等 / meta 往返 / double-run / CLI。

- 加权 masked softmax NLL：loss = sum(w×nll)/sum(w)，nll_i = 分段 logsumexp −
  教师 logit（掩码天然满足）。小手算例对拍 loss 数值；w 全 1 与无权路径逐位
  全等（loss 值 == 且梯度 torch.equal）。
- 缺省（--weight-scheme none / train_policy 不传新参数）与现状逐位全等：meta
  不出现 weight_scheme 键（资产字节面零变化）；CLI 缺省 vs 显式 none 字节全等。
- meta weight_scheme 段写入/读回；旧资产（无段 v1/v2）装载不受影响。
- double-run：同数据同方案训练两遍，资产 sha256 逐字节全等（D3-4 不破）。
"""

from __future__ import annotations

import hashlib
import json
import math

import pytest
import torch
from helpers import deck60

from battlefrontier.agent.action_features import ACTION_FEATURE_NAMES
from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.cli import main as cli_main
from battlefrontier.learn.policy_data import PolicySample
from battlefrontier.learn.policy_model import (
    PolicyModel,
    load_policy_model,
    save_policy_model,
)
from battlefrontier.learn.train_policy import (
    _flatten_samples,
    _vectorized_loss,
    train_policy,
)
from battlefrontier.runner.snapshot import (
    load_snapshot_file,
    run_collect_snapshots,
)
from battlefrontier.tune.fitness import PairAssignment, PreparedPair

INPUT_DIM = len(FEATURE_NAMES) + len(ACTION_FEATURE_NAMES)


def _toy_samples(n_games: int = 4) -> list[PolicySample]:
    """合成样本（v1 键序，n_games 局各 3 点；按局 80/20 划分需 ≥2 局）。"""
    out = []
    for g in range(n_games):
        for r in range(3):
            out.append(PolicySample(
                pair_index=g % 2, seed=1000 + g,
                state={n: 0.01 * (g + r + i)
                       for i, n in enumerate(FEATURE_NAMES)},
                actions=tuple(
                    {n: 0.02 * (g + r + a + i)
                     for i, n in enumerate(ACTION_FEATURE_NAMES)}
                    for a in range(2)),
                teacher_index=(g + r) % 2))
    return out


SCHEME_META = {
    "name": "kind-weights-v1",
    "kind_weights": {"play_stadium": 3.0, "use_ability": 2.0},
    "end_turn_unstable_weight": 0.25,
    "loss_normalization": "sum(w*nll)/sum(w)",
    "ceiling_dir": "results/m12-anchor1-ceiling",
    "ceiling_files": 36,
    "end_turn_points": 100,
    "end_turn_unstable_points": 66,
}


# ── 加权 NLL 数值对拍 ────────────────────────────────────────


def _hand_net():
    """hidden=1 手算网：logit = relu(a + 2b)（in = (a, b)）。"""
    net = torch.nn.Sequential(
        torch.nn.Linear(2, 1), torch.nn.ReLU(), torch.nn.Linear(1, 1))
    with torch.no_grad():
        net[0].weight[:] = torch.tensor([[1.0, 2.0]])
        net[0].bias[:] = torch.tensor([0.0])
        net[2].weight[:] = torch.tensor([[1.0]])
        net[2].bias[:] = torch.tensor([0.0])
    return net


def _hand_samples() -> list[PolicySample]:
    """样本 0：logits [2, 3] 教师 1；样本 1：logits [0, 0] 教师 0（relu 截负）。"""
    return [
        PolicySample(pair_index=0, seed=1, state={"a": 1.0},
                     actions=({"b": 0.5}, {"b": 1.0}), teacher_index=1),
        PolicySample(pair_index=1, seed=2, state={"a": 0.0},
                     actions=({"b": -2.0}, {"b": 0.0}), teacher_index=0),
    ]


def _hand_nll() -> tuple[float, float]:
    nll0 = math.log(math.exp(2.0) + math.exp(3.0)) - 3.0
    nll1 = math.log(2.0) - 0.0
    return nll0, nll1


class TestWeightedNLL:
    def test_加权loss手算对拍(self) -> None:
        net = _hand_net()
        samples = _hand_samples()
        x, teacher_global, ids = _flatten_samples(samples, ("a",), ("b",))
        nll0, nll1 = _hand_nll()
        w = torch.tensor([2.0, 0.5], dtype=torch.float32)
        loss = _vectorized_loss(net, x, teacher_global, ids, weights=w)
        expected = (2.0 * nll0 + 0.5 * nll1) / 2.5
        assert float(loss.detach()) == pytest.approx(expected, abs=1e-6)

    def test_全1权重与无权路径逐位全等(self) -> None:
        net = _hand_net()
        samples = _hand_samples()
        x, teacher_global, ids = _flatten_samples(samples, ("a",), ("b",))
        ones = torch.ones(2, dtype=torch.float32)
        loss_w = _vectorized_loss(net, x, teacher_global, ids, weights=ones)
        loss_0 = _vectorized_loss(net, x, teacher_global, ids)
        assert float(loss_w.detach()) == float(loss_0.detach())
        g_w = torch.autograd.grad(loss_w, list(net.parameters()),
                                  retain_graph=True)
        g_0 = torch.autograd.grad(loss_0, list(net.parameters()))
        for gw, g0 in zip(g_w, g_0, strict=True):
            assert torch.equal(gw, g0)

    def test_权重进入梯度(self) -> None:
        """加权样本的梯度贡献按 w 缩放：w=[2,0.5] ≠ 无权梯度。"""
        net = _hand_net()
        samples = _hand_samples()
        x, teacher_global, ids = _flatten_samples(samples, ("a",), ("b",))
        w = torch.tensor([2.0, 0.5], dtype=torch.float32)
        loss_w = _vectorized_loss(net, x, teacher_global, ids, weights=w)
        loss_0 = _vectorized_loss(net, x, teacher_global, ids)
        g_w = torch.autograd.grad(loss_w, list(net.parameters()),
                                  retain_graph=True)
        g_0 = torch.autograd.grad(loss_0, list(net.parameters()))
        assert any(not torch.allclose(gw, g0)
                   for gw, g0 in zip(g_w, g_0, strict=True))


# ── train_policy 加权接入 ────────────────────────────────────


class TestTrainPolicyWeighted:
    def test_加权训练meta与资产往返(self, tmp_path) -> None:
        samples = _toy_samples()
        weights = [2.0 if i % 3 == 0 else 1.0 for i in range(len(samples))]
        model = train_policy(samples, epochs=2, hidden=8,
                             code_version="test-w",
                             sample_weights=weights,
                             weight_scheme=SCHEME_META)
        assert model.meta["weight_scheme"] == SCHEME_META
        assert model.meta["train_loss"] > 0.0
        out = tmp_path / "policy-w.json"
        save_policy_model(model, out)
        loaded = load_policy_model(out)
        assert loaded == model
        assert loaded.meta["weight_scheme"]["name"] == "kind-weights-v1"

    def test_缺省路径meta无weight_scheme键(self) -> None:
        """不传新参数 = 现状逐位全等：meta 不出现 weight_scheme 键。"""
        model = train_policy(_toy_samples(), epochs=1, hidden=4,
                             code_version="test-plain")
        assert "weight_scheme" not in model.meta

    def test_权重长度不符显式报错(self) -> None:
        samples = _toy_samples()
        with pytest.raises(ValueError, match="长度"):
            train_policy(samples, epochs=1, hidden=4,
                         sample_weights=[1.0], weight_scheme=SCHEME_META)

    def test_非正权重显式报错(self) -> None:
        samples = _toy_samples()
        bad = [1.0] * len(samples)
        bad[2] = 0.0
        with pytest.raises(ValueError, match="权重"):
            train_policy(samples, epochs=1, hidden=4, sample_weights=bad,
                         weight_scheme=SCHEME_META)

    def test_weight_scheme无权重显式报错(self) -> None:
        with pytest.raises(ValueError, match="weight_scheme"):
            train_policy(_toy_samples(), epochs=1, hidden=4,
                         weight_scheme=SCHEME_META)

    def test_double_run_sha256逐字节全等(self, tmp_path) -> None:
        """同数据同方案训练两遍，资产 sha256 逐字节全等（D3-4 非复算面不破）。"""
        samples = _toy_samples()
        weights = [3.0 if i % 4 == 0 else 0.25 if i % 4 == 1 else 1.0
                   for i in range(len(samples))]
        digests = []
        for run in range(2):
            model = train_policy(samples, epochs=3, hidden=8,
                                 code_version="test-dd",
                                 sample_weights=weights,
                                 weight_scheme=SCHEME_META)
            out = tmp_path / f"run{run}.json"
            save_policy_model(model, out)
            digests.append(hashlib.sha256(out.read_bytes()).hexdigest())
        assert digests[0] == digests[1]

    def test_double_run无权路径sha256全等(self, tmp_path) -> None:
        digests = []
        for run in range(2):
            model = train_policy(_toy_samples(), epochs=3, hidden=8,
                                 code_version="test-dd0")
            out = tmp_path / f"plain{run}.json"
            save_policy_model(model, out)
            digests.append(hashlib.sha256(out.read_bytes()).hexdigest())
        assert digests[0] == digests[1]


# ── meta 段校验与旧资产兼容 ──────────────────────────────────


class TestWeightSchemeMeta:
    def _toy_model(self) -> PolicyModel:
        return PolicyModel(
            hidden=2,
            weights={
                "w1": tuple(tuple(0.01 * (i + j) for j in range(INPUT_DIM))
                            for i in range(2)),
                "b1": (0.0, 0.0),
                "w2": ((0.1, 0.1),),
                "b2": (0.5,),
            },
            meta={"source": "toy"})

    def test_weight_scheme段写入读回(self, tmp_path) -> None:
        model = self._toy_model()
        model.meta["weight_scheme"] = SCHEME_META
        out = tmp_path / "m.json"
        save_policy_model(model, out)
        loaded = load_policy_model(out)
        assert loaded.meta["weight_scheme"] == SCHEME_META

    def test_weight_scheme段非dict显式报错(self, tmp_path) -> None:
        model = self._toy_model()
        model.meta["weight_scheme"] = "bogus"
        out = tmp_path / "m.json"
        save_policy_model(model, out)
        with pytest.raises(ValueError, match="weight_scheme"):
            load_policy_model(out)

    def test_旧资产无段可装载(self) -> None:
        """入库旧资产（无 weight_scheme 段的 v1/v2）装载不受影响。"""
        from pathlib import Path

        for name in ("policy-m12-v1.json", "policy-m12-v2.json"):
            path = Path("models") / name
            if not path.exists():
                pytest.skip(f"本机无 {path}")
            model = load_policy_model(path)
            assert "weight_scheme" not in model.meta


# ── CLI 端到端（stub 快照 + 合成 ceiling）────────────────────


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"测试A{index}",
                                  archetype_b=f"测试B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


@pytest.fixture(scope="module")
def snapshot_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("policy-weights")
    (s,) = run_collect_snapshots([_stub_pair(0)], games_per_pair=2,
                                 seed_start=460000, out_dir=out, workers=1,
                                 teacher={"worlds": 1, "iterations": 25,
                                          "rollout_turn_cap": 50})
    assert s.rows > 0
    return out


@pytest.fixture(scope="module")
def ceiling_dir(snapshot_dir, tmp_path_factory):
    """从 stub 快照合成第二投票：end_turn 行全部 agree=false（异种子选 attack）。"""
    out = tmp_path_factory.mktemp("ceiling")
    n_unstable = 0
    for f in sorted(snapshot_dir.glob("pair-*.jsonl")):
        snap = load_snapshot_file(f)
        rows = [{"index": i, "seed": r["seed"], "turn": r["turn"],
                 "player": r["player"], "teacher_kind": "end_turn",
                 "student_kind": "attack", "agree": False}
                for i, r in enumerate(snap.rows)
                if r["action_kind"] == "end_turn"]
        n_unstable += len(rows)
        (out / (f.stem + ".json")).write_text(
            json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")
    assert n_unstable > 0  # stub 快照必有 end_turn 决策点，否则测试形同虚设
    return out


class TestTrainPolicyCliWeights:
    def test_kind_weights_v1端到端(self, snapshot_dir, ceiling_dir,
                                   tmp_path) -> None:
        out = tmp_path / "policy-w.json"
        rc = cli_main(["train-policy", "--data", str(snapshot_dir),
                       "--out", str(out), "--epochs", "1", "--hidden", "8",
                       "--weight-scheme", "kind-weights-v1",
                       "--ceiling-dir", str(ceiling_dir)])
        assert rc == 0
        model = load_policy_model(out)
        ws = model.meta["weight_scheme"]
        assert ws["name"] == "kind-weights-v1"
        assert ws["kind_weights"] == {"play_stadium": 3.0, "use_ability": 2.0}
        assert ws["end_turn_unstable_weight"] == 0.25
        assert ws["end_turn_points"] > 0
        assert ws["end_turn_unstable_points"] == ws["end_turn_points"]

    def test_缺省与显式none逐字节全等(self, snapshot_dir, tmp_path) -> None:
        """--weight-scheme 缺省 vs 显式 none：资产 sha256 逐字节全等。"""
        digests = []
        for run, extra in enumerate([[], ["--weight-scheme", "none"]]):
            out = tmp_path / f"cli{run}.json"
            rc = cli_main(["train-policy", "--data", str(snapshot_dir),
                           "--out", str(out), "--epochs", "1", "--hidden", "8",
                           "--code-version", "test-cli"] + extra)
            assert rc == 0
            digests.append(hashlib.sha256(out.read_bytes()).hexdigest())
        assert digests[0] == digests[1]

    def test_ceiling文件缺失退出码1(self, snapshot_dir, tmp_path) -> None:
        empty = tmp_path / "no-ceiling"
        empty.mkdir()
        rc = cli_main(["train-policy", "--data", str(snapshot_dir),
                       "--out", str(tmp_path / "m.json"),
                       "--epochs", "1",
                       "--weight-scheme", "kind-weights-v1",
                       "--ceiling-dir", str(empty)])
        assert rc == 1

    def test_非法方案argparse拒绝(self, snapshot_dir, tmp_path) -> None:
        with pytest.raises(SystemExit):
            cli_main(["train-policy", "--data", str(snapshot_dir),
                      "--out", str(tmp_path / "m.json"),
                      "--weight-scheme", "bogus"])
