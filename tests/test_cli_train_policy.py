"""task 062 WP2d：CLI train-policy --pool 触发 v2 特征训练 验收测试。

- 提供 --pool：build_card_vocab 构建卡身份词表（卡池 YAML + db）→ v2 特征
  样本 → v2 训练 → 资产 format bf-distilled-policy-v2（meta
  feature_version="v2"、card_vocab 钉入、w1 行宽 = len(POLICY_STATE_NAMES)
  + len(policy_action_names(vocab))）；打印追加词表大小。测试侧 monkeypatch
  build_card_vocab 为 stub 小词表（不依赖真实卡池/db，口径随测试词表）。
- 不提供 --pool：v1 旧行为逐位不变（test_policy_train.py 既有 CLI 用例原样绿；
  此处显式断言资产 format v1 / meta feature_version="v1" / card_vocab None）。
"""

from __future__ import annotations

import json

import pytest
from helpers import deck60

from battlefrontier.agent import policy_features
from battlefrontier.agent.policy_features import (
    POLICY_STATE_NAMES,
    policy_action_names,
)
from battlefrontier.cli import main as cli_main
from battlefrontier.learn.policy_model import (
    POLICY_FORMAT,
    POLICY_FORMAT_V2,
    load_policy_model,
)
from battlefrontier.runner.snapshot import run_collect_snapshots
from battlefrontier.tune.fitness import PairAssignment, PreparedPair

STUB_VOCAB = tuple(sorted({c.name for c in deck60()}))
V2_ACTION_NAMES = policy_action_names(STUB_VOCAB)
V2_INPUT_DIM = len(POLICY_STATE_NAMES) + len(V2_ACTION_NAMES)


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"测试A{index}",
                                  archetype_b=f"测试B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


@pytest.fixture(scope="module")
def snapshot_dir(tmp_path_factory):
    """stub 配对教师（1×2 MCTS）2 局快照目录（v1/v2 两条 CLI 路径共用）。"""
    out = tmp_path_factory.mktemp("cli-train-policy")
    (s,) = run_collect_snapshots([_stub_pair(0)], games_per_pair=2,
                                 seed_start=460000, out_dir=out, workers=1,
                                 teacher={"worlds": 1, "iterations": 2,
                                          "rollout_turn_cap": 50})
    assert s.rows > 0
    return out


class TestTrainPolicyPoolV2:
    def test_pool提供产出v2资产(self, snapshot_dir, tmp_path,
                                monkeypatch, capsys) -> None:
        recorded: dict[str, tuple] = {}

        def fake_build_card_vocab(pool_path, db_path):
            recorded["args"] = (pool_path, db_path)
            return STUB_VOCAB

        monkeypatch.setattr(policy_features, "build_card_vocab",
                            fake_build_card_vocab)
        out = tmp_path / "policy-v2.json"
        rc = cli_main(["train-policy", "--data", str(snapshot_dir),
                       "--pool", "config/fake-pool.yml",
                       "--out", str(out), "--epochs", "1", "--hidden", "8"])
        assert rc == 0
        # 词表构建入口拿到 --pool 路径（db 路径走本机配置解析）
        assert recorded["args"][0] == "config/fake-pool.yml"
        model = load_policy_model(out)
        assert model.meta["feature_version"] == "v2"
        assert model.card_vocab == STUB_VOCAB
        assert model.meta["pool"] == "config/fake-pool.yml"
        # 输入维度口径随测试词表：36 状态 + 26 行动 + len(词表) 卡身份
        assert len(POLICY_STATE_NAMES) == 36
        assert len(V2_ACTION_NAMES) == 26 + len(STUB_VOCAB)
        assert all(len(r) == V2_INPUT_DIM for r in model.weights["w1"])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["format"] == POLICY_FORMAT_V2
        # 打印追加词表大小
        assert f"词表 {len(STUB_VOCAB)} 张" in capsys.readouterr().out

    def test_词表构建失败退出码1(self, snapshot_dir, tmp_path,
                                 monkeypatch) -> None:
        def boom(pool_path, db_path):
            raise ValueError("词表构建失败 stub")

        monkeypatch.setattr(policy_features, "build_card_vocab", boom)
        rc = cli_main(["train-policy", "--data", str(snapshot_dir),
                       "--pool", "config/fake-pool.yml",
                       "--out", str(tmp_path / "m.json"), "--epochs", "1"])
        assert rc == 1

    def test_不提供pool保持v1(self, snapshot_dir, tmp_path) -> None:
        out = tmp_path / "policy-v1.json"
        rc = cli_main(["train-policy", "--data", str(snapshot_dir),
                       "--out", str(out), "--epochs", "1", "--hidden", "8"])
        assert rc == 0
        model = load_policy_model(out)
        assert model.card_vocab is None
        assert model.meta["feature_version"] == "v1"
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["format"] == POLICY_FORMAT
