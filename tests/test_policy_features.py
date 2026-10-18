"""task 058 · M12 WP2：行动特征化 + 快照→样本转换验收测试（D-M12-1/2）。

- 行动 kind 词表 16 类钉死（core.py 15 种 + chooser「choose」——任务书「15 类」
  系漏计 choose，D-M12-1）；特征键序 = kind one-hot 16 + 数值标量 6 +
  目标关系标志 4（Action 结构化字段无 damage/amount/count，D-M12-2）。
- 快照→样本转换（learn/policy_data.py）：重建 GameState → 行动方 visible view
  特征（信息纪律：与 feature_vector(visible_state) 逐一相等）→ 合法行动逐条
  特征化 → 教师 chosen 在合法列内的下标；教师行动不合法显式报错（不猜）。
"""

from __future__ import annotations

import pytest
from helpers import basic, deck60, in_play, main_state

from battlefrontier.agent.action_features import (
    ACTION_FEATURE_NAMES,
    ACTION_KINDS,
    action_features,
)
from battlefrontier.agent.features import FEATURE_NAMES, feature_vector
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.learn.policy_data import (
    PolicySample,
    load_policy_samples,
    row_to_sample,
)
from battlefrontier.runner.snapshot import (
    SnapshotFile,
    load_snapshot_file,
    run_collect_snapshots,
    snapshot_state,
    teacher_action,
)
from battlefrontier.tune.fitness import PairAssignment, PreparedPair

EXPECTED_KINDS = (
    "attach_energy", "attach_tool", "attack", "choose", "confirm_setup",
    "end_turn", "evolve", "place_active", "place_bench", "play_stadium",
    "play_trainer", "promote", "retreat", "shrink_bench", "use_ability",
    "use_stadium",
)

EXPECTED_ACTION_FEATURES = tuple(f"kind_{k}" for k in EXPECTED_KINDS) + (
    "attack_index",
    "has_iid",
    "has_target_iid",
    "has_bench_index",
    "bench_index",
    "n_choices",
    "target_is_own_active",
    "target_is_own_bench",
    "target_is_opp_active",
    "target_is_opp_bench",
)


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"测试A{index}",
                                  archetype_b=f"测试B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


@pytest.fixture(scope="module")
def snapshot_file(tmp_path_factory) -> SnapshotFile:
    """stub 配对教师（1×2 MCTS）小预算快照（test_agreement 同口径）。"""
    out = tmp_path_factory.mktemp("policy-snapshots")
    (s,) = run_collect_snapshots([_stub_pair(0)], games_per_pair=2,
                                 seed_start=440000, out_dir=out, workers=1,
                                 teacher={"worlds": 1, "iterations": 2,
                                          "rollout_turn_cap": 50})
    assert s.rows > 0
    return load_snapshot_file(out / s.filename)


# ── 行动特征（纯函数）────────────────────────────────────────


class TestActionFeatures:
    def test_kind词表钉死(self) -> None:
        assert ACTION_KINDS == EXPECTED_KINDS

    def test_特征键序钉死(self) -> None:
        assert ACTION_FEATURE_NAMES == EXPECTED_ACTION_FEATURES
        assert len(ACTION_FEATURE_NAMES) == 26
        assert len(set(ACTION_FEATURE_NAMES)) == len(ACTION_FEATURE_NAMES)

    def test_kind_onehot逐类命中(self) -> None:
        view = main_state().visible_state(0)
        for kind in ACTION_KINDS:
            feats = action_features(Action(kind=kind), view)
            assert tuple(feats) == ACTION_FEATURE_NAMES
            assert feats[f"kind_{kind}"] == 1.0
            assert sum(feats[f"kind_{k}"] for k in ACTION_KINDS) == 1.0

    def test_未知kind显式报错(self) -> None:
        with pytest.raises(ValueError, match="未知"):
            action_features(Action(kind="hack"), main_state().visible_state(0))

    def test_数值标量(self) -> None:
        view = main_state().visible_state(0)
        feats = action_features(
            Action(kind="choose", attack_index=1, iid=9, target_iid=2,
                   bench_index=3, choices=(5, 6)), view)
        assert feats["attack_index"] == 1.0
        assert feats["has_iid"] == 1.0
        assert feats["has_target_iid"] == 1.0
        assert feats["has_bench_index"] == 1.0
        assert feats["bench_index"] == 3.0
        assert feats["n_choices"] == 2.0
        empty = action_features(Action(kind="end_turn"), view)
        assert empty["attack_index"] == 0.0
        assert empty["has_iid"] == 0.0
        assert empty["has_target_iid"] == 0.0
        assert empty["has_bench_index"] == 0.0
        assert empty["bench_index"] == 0.0
        assert empty["n_choices"] == 0.0

    def test_目标关系标志(self) -> None:
        """target_iid 经行动方 visible view 解析（信息纪律：只看可见区域）。"""
        state = main_state(p1_bench=(in_play(3, basic("小火龙")),))
        p0 = state.players[0].model_copy(
            update={"bench": (in_play(7, basic("小火龙")),)})
        state = state.model_copy(update={"players": (p0, state.players[1])})
        view = state.visible_state(0)
        # main_state：己方 active iid=1 / 对方 active iid=2 / 对方 bench iid=3 /
        # 己方 bench iid=7
        cases = {1: "target_is_own_active", 7: "target_is_own_bench",
                 2: "target_is_opp_active", 3: "target_is_opp_bench"}
        flags = ("target_is_own_active", "target_is_own_bench",
                 "target_is_opp_active", "target_is_opp_bench")
        for iid, hit in cases.items():
            feats = action_features(Action(kind="attach_tool", iid=50, target_iid=iid),
                                    view)
            for f in flags:
                assert feats[f] == (1.0 if f == hit else 0.0), (iid, f)
        # 无 target / target 不在可见在场区（如手牌 iid）→ 全 0
        for action in (Action(kind="play_trainer", iid=50),
                       Action(kind="attach_tool", iid=50, target_iid=999)):
            feats = action_features(action, view)
            assert all(feats[f] == 0.0 for f in flags)


# ── 快照→样本转换 ────────────────────────────────────────────


class TestRowToSample:
    def test_样本结构与信息纪律(self, snapshot_file) -> None:
        """样本 state 特征与 feature_vector(visible_state) 逐一相等（只用行动方
        可见视图）；行动特征与合法行动逐条对拍；教师下标命中教师行动。"""
        row = next(r for r in snapshot_file.rows if r["phase"] == "main")
        sample = row_to_sample(row, pair_index=0,
                               card_effects=snapshot_file.card_effects())
        assert isinstance(sample, PolicySample)
        state = snapshot_state(row)
        view = state.visible_state(row["player"])
        assert sample.state == feature_vector(view)
        assert tuple(sample.state) == FEATURE_NAMES
        engine = GameEngine(RandomSource(row["seed"]),
                            card_effects=snapshot_file.card_effects())
        engine.state = state
        legal = engine.legal_actions(row["player"])
        assert len(sample.actions) == len(legal) == row["n_legal"]
        for feats, action in zip(sample.actions, legal, strict=True):
            assert feats == action_features(action, view)
            assert tuple(feats) == ACTION_FEATURE_NAMES
        assert legal[sample.teacher_index] == teacher_action(row)
        assert (sample.pair_index, sample.seed) == (0, row["seed"])

    def test_教师行动不在合法列显式报错(self, snapshot_file) -> None:
        row = dict(snapshot_file.rows[0])
        row["action"] = {"kind": "attack", "attack_index": 99}
        row["action_kind"] = "attack"
        with pytest.raises(ValueError, match="不在合法行动列"):
            row_to_sample(row, pair_index=0,
                          card_effects=snapshot_file.card_effects())

    def test_全阶段行可转换(self, snapshot_file) -> None:
        """冒烟全量行（含 choice/setup/promote 阶段）逐行转换不炸。"""
        card_effects = snapshot_file.card_effects()
        for row in snapshot_file.rows:
            sample = row_to_sample(row, pair_index=0, card_effects=card_effects)
            assert 0 <= sample.teacher_index < len(sample.actions)


class TestLoadPolicySamples:
    def test_目录载入(self, snapshot_file, tmp_path) -> None:
        import json

        path = tmp_path / "pair-0-测试Ax测试B.jsonl"
        lines = [{"record": "header", **snapshot_file.header}] + \
            [{**r, "record": "snapshot"} for r in snapshot_file.rows]
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in lines)
            + "\n", encoding="utf-8")
        samples = load_policy_samples(tmp_path)
        assert len(samples) == len(snapshot_file.rows)
        assert all(s.pair_index == 0 for s in samples)
        assert len({s.seed for s in samples}) == 2

    def test_空目录显式报错(self, tmp_path) -> None:
        with pytest.raises(ValueError, match=r"pair-\*\.jsonl"):
            load_policy_samples(tmp_path)
