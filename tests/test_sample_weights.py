"""task 066 WP1：per-kind 样本权重 + end_turn 双投票降噪 join 测试（D-066-1/2/3）。

- kind 权重表钉死：play_stadium ×3.0 / use_ability ×2.0 / 其余 ×1.0。
- end_turn 双投票：ceiling 行（agreement rows，index = 快照文件行号，真实数据
  已实证）join 回快照行；agree=false 的 end_turn 点 w=0.25，agree=true 及其余
  kind 按 D-066-1。缺票 / ceiling 文件缺失 / kind 不匹配 / index 重复 均显式
  报错（不猜不跳过）。
- 权重序与 load_policy_samples 样本序对齐：sorted glob pair-*.jsonl × 文件内
  行序（两函数同一份枚举口径）。
"""

from __future__ import annotations

import json

import pytest

from battlefrontier.learn.sample_weights import (
    DEFAULT_CEILING_DIR,
    END_TURN_UNSTABLE_WEIGHT,
    END_TURN_UNSTABLE_WEIGHT_V2,
    KIND_WEIGHTS_V1,
    KIND_WEIGHTS_V2,
    LOSS_NORMALIZATION,
    WEIGHT_SCHEME_KIND_V1,
    WEIGHT_SCHEME_KIND_V2,
    WEIGHT_SCHEME_NONE,
    compute_sample_weights,
)

HEADER = {"record": "header", "format": "bf-m11-snapshot-v1", "pair_index": 0}


def _row(kind: str, phase: str = "main", seed: int = 1) -> dict:
    return {"record": "snapshot", "action_kind": kind, "phase": phase,
            "seed": seed, "turn": 1, "player": 0, "n_legal": 3}


def _write_snapshot(dirpath, name: str, rows: list[dict]) -> None:
    lines = [json.dumps(HEADER, ensure_ascii=False)]
    lines += [json.dumps(r, ensure_ascii=False) for r in rows]
    (dirpath / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ceiling_row(index: int, teacher_kind: str, agree: bool,
                 student_kind: str = "attack") -> dict:
    return {"index": index, "seed": 1, "turn": 1, "player": 0,
            "teacher_kind": teacher_kind, "student_kind": student_kind,
            "agree": agree}


def _write_ceiling(dirpath, name: str, rows: list[dict]) -> None:
    (dirpath / name).write_text(
        json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture()
def ceiling_dir(tmp_path):
    d = tmp_path / "ceiling"
    d.mkdir()
    return d


class TestConstants:
    def test_kind权重表钉死(self) -> None:
        assert KIND_WEIGHTS_V1 == {"play_stadium": 3.0, "use_ability": 2.0}

    def test_kind权重表v2钉死(self) -> None:
        # D-066-5 A2 降剂量（2026-10-21 用户拍板）
        assert KIND_WEIGHTS_V2 == {"play_stadium": 1.5, "use_ability": 1.25}
        assert END_TURN_UNSTABLE_WEIGHT_V2 == 0.5


class TestSchemeV2:
    def test_v2方案映射与meta(self, data_dir, ceiling_dir) -> None:
        _write_snapshot(data_dir, "pair-0-x.jsonl", [
            _row("play_stadium"), _row("use_ability"), _row("end_turn"),
            _row("attack")])
        _write_ceiling(ceiling_dir, "pair-0-x.json", [
            _ceiling_row(2, "end_turn", agree=False)])
        weights, meta = compute_sample_weights(
            data_dir, scheme=WEIGHT_SCHEME_KIND_V2, ceiling_dir=ceiling_dir)
        assert weights == [1.5, 1.25, 0.5, 1.0]
        assert meta["name"] == "kind-weights-v2"
        assert meta["kind_weights"] == {"play_stadium": 1.5, "use_ability": 1.25}
        assert meta["end_turn_unstable_weight"] == 0.5
        assert END_TURN_UNSTABLE_WEIGHT == 0.25
        assert WEIGHT_SCHEME_NONE == "none"
        assert WEIGHT_SCHEME_KIND_V1 == "kind-weights-v1"
        assert LOSS_NORMALIZATION == "sum(w*nll)/sum(w)"
        assert DEFAULT_CEILING_DIR == "results/m12-anchor1-ceiling"


class TestKindWeightsV1:
    def test_kind映射与end_turn双投票(self, data_dir, ceiling_dir) -> None:
        rows = [
            _row("attack"),          # 0 → 1.0
            _row("play_stadium"),    # 1 → 3.0
            _row("use_ability"),     # 2 → 2.0
            _row("end_turn"),        # 3 → agree → 1.0
            _row("end_turn"),        # 4 → 不一致 → 0.25
            _row("attach_energy"),   # 5 → 1.0
        ]
        _write_snapshot(data_dir, "pair-0-甲x乙.jsonl", rows)
        _write_ceiling(ceiling_dir, "pair-0-甲x乙.json", [
            _ceiling_row(0, "attack", True),
            _ceiling_row(1, "play_stadium", False),
            _ceiling_row(3, "end_turn", True),
            _ceiling_row(4, "end_turn", False, student_kind="play_trainer"),
        ])
        weights, meta = compute_sample_weights(
            data_dir, scheme=WEIGHT_SCHEME_KIND_V1, ceiling_dir=ceiling_dir)
        assert weights == [1.0, 3.0, 2.0, 1.0, 0.25, 1.0]
        assert meta["name"] == "kind-weights-v1"
        assert meta["kind_weights"] == {"play_stadium": 3.0, "use_ability": 2.0}
        assert meta["end_turn_unstable_weight"] == 0.25
        assert meta["loss_normalization"] == "sum(w*nll)/sum(w)"
        assert meta["ceiling_dir"] == str(ceiling_dir)
        assert meta["ceiling_files"] == 1
        assert meta["end_turn_points"] == 2
        assert meta["end_turn_unstable_points"] == 1

    def test_多文件顺序与样本序对齐(self, data_dir, ceiling_dir) -> None:
        """sorted glob 文件序 × 文件内行序（load_policy_samples 同口径）。"""
        _write_snapshot(data_dir, "pair-1-丙x丁.jsonl",
                        [_row("play_stadium"), _row("end_turn")])
        _write_snapshot(data_dir, "pair-0-甲x乙.jsonl",
                        [_row("use_ability"), _row("attack")])
        _write_ceiling(ceiling_dir, "pair-0-甲x乙.json", [])
        _write_ceiling(ceiling_dir, "pair-1-丙x丁.json",
                       [_ceiling_row(1, "end_turn", False)])
        weights, meta = compute_sample_weights(
            data_dir, scheme=WEIGHT_SCHEME_KIND_V1, ceiling_dir=ceiling_dir)
        # pair-0 文件字典序在前
        assert weights == [2.0, 1.0, 3.0, 0.25]
        assert meta["ceiling_files"] == 2

    def test_none方案全1且无meta(self, data_dir) -> None:
        _write_snapshot(data_dir, "pair-0-甲x乙.jsonl",
                        [_row("play_stadium"), _row("end_turn")])
        weights, meta = compute_sample_weights(data_dir, scheme=WEIGHT_SCHEME_NONE)
        assert weights == [1.0, 1.0]
        assert meta is None

    def test_未知方案显式报错(self, data_dir) -> None:
        _write_snapshot(data_dir, "pair-0-甲x乙.jsonl", [_row("attack")])
        with pytest.raises(ValueError, match="未知.*weight.*方案|未知方案"):
            compute_sample_weights(data_dir, scheme="bogus")


class TestJoinErrors:
    """缺票 / 文件缺失 / kind 不匹配 / index 重复 → 显式报错（不猜不跳过）。"""

    def _snapshot(self, data_dir) -> None:
        _write_snapshot(data_dir, "pair-0-甲x乙.jsonl",
                        [_row("attack"), _row("end_turn")])

    def test_ceiling文件缺失显式报错(self, data_dir, ceiling_dir) -> None:
        self._snapshot(data_dir)
        with pytest.raises(ValueError, match="ceiling 文件缺失"):
            compute_sample_weights(
                data_dir, scheme=WEIGHT_SCHEME_KIND_V1, ceiling_dir=ceiling_dir)

    def test_缺票显式报错(self, data_dir, ceiling_dir) -> None:
        self._snapshot(data_dir)
        _write_ceiling(ceiling_dir, "pair-0-甲x乙.json",
                       [_ceiling_row(0, "attack", True)])  # index 1 缺票
        with pytest.raises(ValueError, match="缺票"):
            compute_sample_weights(
                data_dir, scheme=WEIGHT_SCHEME_KIND_V1, ceiling_dir=ceiling_dir)

    def test_kind不匹配显式报错(self, data_dir, ceiling_dir) -> None:
        self._snapshot(data_dir)
        _write_ceiling(ceiling_dir, "pair-0-甲x乙.json",
                       [_ceiling_row(1, "attack", True)])  # 快照行 1 = end_turn
        with pytest.raises(ValueError, match="kind 不匹配"):
            compute_sample_weights(
                data_dir, scheme=WEIGHT_SCHEME_KIND_V1, ceiling_dir=ceiling_dir)

    def test_重复index显式报错(self, data_dir, ceiling_dir) -> None:
        self._snapshot(data_dir)
        _write_ceiling(ceiling_dir, "pair-0-甲x乙.json", [
            _ceiling_row(1, "end_turn", True),
            _ceiling_row(1, "end_turn", False),
        ])
        with pytest.raises(ValueError, match="重复"):
            compute_sample_weights(
                data_dir, scheme=WEIGHT_SCHEME_KIND_V1, ceiling_dir=ceiling_dir)

    def test_无快照文件显式报错(self, data_dir, ceiling_dir) -> None:
        with pytest.raises(ValueError, match=r"pair-\*\.jsonl"):
            compute_sample_weights(
                data_dir, scheme=WEIGHT_SCHEME_KIND_V1, ceiling_dir=ceiling_dir)
