"""task 052 WP3：决策一致率 harness 验收测试（D-M11-5）。

分母口径 v1（main 阶段 attack/play_trainer/end_turn 三类；非 main 与其余 main
行动类进附录计数）/ 种子协议（配置指纹 + 快照序号派生，钉死进报告）/
确定性（同快照同配置两跑逐一致）/ CLI 冒烟（agreement 小预算合成 +
collect-snapshots 真实池跳过式冒烟）。
"""

import json
from pathlib import Path

import pytest
import yaml
from helpers import deck60

from battlefrontier.cli import main as cli_main
from battlefrontier.runner.agreement import (
    DENOMINATOR_KINDS,
    agreement_report,
    classify_row,
    config_fingerprint,
    run_agreement,
    student_seed,
)
from battlefrontier.runner.snapshot import (
    SnapshotFile,
    load_snapshot_file,
    run_collect_snapshots,
)
from battlefrontier.tune.fitness import PairAssignment, PreparedPair

_STUDENT = {"worlds": 1, "iterations": 2, "rollout_turn_cap": 50}


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"测试A{index}",
                                  archetype_b=f"测试B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


@pytest.fixture(scope="module")
def snapshot_file(tmp_path_factory) -> SnapshotFile:
    """stub 配对教师（1×2 MCTS）小预算快照（全模块共享一份，重放只读）。"""
    out = tmp_path_factory.mktemp("snapshots")
    (s,) = run_collect_snapshots([_stub_pair(0)], games_per_pair=2,
                                 seed_start=420000, out_dir=out, workers=1,
                                 teacher={"worlds": 1, "iterations": 2,
                                          "rollout_turn_cap": 50})
    assert s.rows > 0
    return load_snapshot_file(out / s.filename)


# ── 分母口径（classify_row 纯函数）────────────────────────────


class TestClassify:
    def test_三类计入分母(self) -> None:
        for kind in ("attack", "play_trainer", "end_turn"):
            assert classify_row({"phase": "main", "action_kind": kind}) == "denominator"

    def test_非main阶段剔除(self) -> None:
        for phase in ("choice", "promote", "setup_active", "setup_bench"):
            assert classify_row({"phase": phase, "action_kind": "choose"}
                                ).startswith("excluded")
            assert classify_row({"phase": phase, "action_kind": "attack"}
                                ) == "excluded:non_main"

    def test_其余main行动类剔除(self) -> None:
        for kind in ("retreat", "evolve", "use_ability", "attach_energy",
                     "place_bench", "attach_tool", "play_stadium", "use_stadium"):
            assert classify_row({"phase": "main", "action_kind": kind}
                                ) == "excluded:other_main"
        assert DENOMINATOR_KINDS == {"attack", "play_trainer", "end_turn"}


# ── 种子协议 ────────────────────────────────────────────────


class TestSeedProtocol:
    def test_指纹与种子确定性(self) -> None:
        fp = config_fingerprint(_STUDENT)
        assert fp == config_fingerprint(dict(reversed(list(_STUDENT.items()))))
        assert fp != config_fingerprint({**_STUDENT, "iterations": 3})
        assert student_seed(fp, 0) == student_seed(fp, 0)
        assert student_seed(fp, 0) != student_seed(fp, 1)
        assert 0 <= student_seed(fp, 0) < 2**64


# ── 一致率统计与确定性 ───────────────────────────────────────


class TestAgreement:
    def test_分母与附录计数(self, snapshot_file) -> None:
        """分母 = main 三类行数；附录覆盖其余；分母+附录 == 快照总数。"""
        report = run_agreement(snapshot_file, _STUDENT)
        rows = snapshot_file.rows
        expected_denom = sum(1 for r in rows if classify_row(r) == "denominator")
        assert report["snapshots_total"] == len(rows)
        assert report["denominator"] == expected_denom
        ap = report["appendix"]
        assert ap["excluded_non_main"] == sum(
            1 for r in rows if classify_row(r) == "excluded:non_main")
        assert ap["excluded_other_main"] == sum(
            1 for r in rows if classify_row(r) == "excluded:other_main")
        assert ap["teacher_action_not_legal"] == 0
        assert (report["denominator"] + ap["excluded_non_main"]
                + ap["excluded_other_main"]) == len(rows)
        assert 0.0 <= report["agreement_rate"] <= 1.0
        assert report["agree"] == sum(1 for d in report["rows"] if d["agree"])
        # 教师快照含三类行动（覆盖断言：白板镜像 main 阶段 attack/end_turn 常见）
        assert report["denominator"] > 0

    def test_种子钉死进报告(self, snapshot_file) -> None:
        report = run_agreement(snapshot_file, _STUDENT)
        fp = report["config_fingerprint"]
        assert fp == config_fingerprint(_STUDENT)
        assert report["config"] == _STUDENT
        for d in report["rows"]:
            assert d["student_seed"] == student_seed(fp, d["index"])

    def test_确定性_两跑逐一致(self, snapshot_file) -> None:
        """同快照文件 + 同受测配置两跑：报告逐字段全等。"""
        a = run_agreement(snapshot_file, _STUDENT)
        b = run_agreement(snapshot_file, _STUDENT)
        assert a == b

    def test_合成剔除行_附录计数(self, snapshot_file) -> None:
        """合成 choose / retreat 快照行：不进分母、附录计数 +1 各。"""
        base = dict(snapshot_file.rows[0])
        choose_row = {**base, "phase": "choice", "action_kind": "choose"}
        retreat_row = {**base, "phase": "main", "action_kind": "retreat"}
        snap = SnapshotFile(header=snapshot_file.header,
                            rows=[choose_row, retreat_row])
        report = run_agreement(snap, _STUDENT)
        assert report["denominator"] == 0
        assert report["agreement_rate"] is None
        assert report["appendix"]["excluded_non_main"] == 1
        assert report["appendix"]["excluded_other_main"] == 1

    def test_截断配置重放_冒烟(self, snapshot_file, tmp_path) -> None:
        """受测配置带 eval_cutoff_turns + 玩具评估器：重放正常、报告结构完整。"""
        from battlefrontier.agent.features import FEATURE_NAMES
        from battlefrontier.learn.model import LinearModel, save_model

        n = len(FEATURE_NAMES)
        save_model(LinearModel(
            feature_names=FEATURE_NAMES,
            weights=tuple([0.0] * n + [0.6]),
            mean=tuple(0.0 for _ in range(n)),
            std=tuple(1.0 for _ in range(n)),
            meta={"source": "toy"}), tmp_path / "toy.json")
        student = {**_STUDENT, "eval_cutoff_turns": 5,
                   "evaluator_path": str(tmp_path / "toy.json")}
        report = run_agreement(snapshot_file, student)
        assert report["denominator"] > 0
        assert report["config"]["eval_cutoff_turns"] == 5

    def test_报告渲染(self, snapshot_file) -> None:
        text = agreement_report(run_agreement(snapshot_file, _STUDENT))
        assert "一致率" in text and "附录" in text


# ── CLI ─────────────────────────────────────────────────────


class TestCli:
    def test_agreement_cli_冒烟(self, snapshot_file, tmp_path) -> None:
        snap_path = tmp_path / "snap.jsonl"
        rows = [{"record": "header", **snapshot_file.header}] + \
            [{**r, "record": "snapshot"} for r in snapshot_file.rows]
        snap_path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
            + "\n", encoding="utf-8")
        out = tmp_path / "report.json"
        rc = cli_main(["agreement", str(snap_path), "--worlds", "1",
                       "--iterations", "2", "--output", str(out)])
        assert rc == 0
        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["denominator"] > 0
        # CLI 受测配置 = _STUDENT + 默认 eval_cutoff_turns=0
        assert report["config_fingerprint"] == config_fingerprint(
            {**_STUDENT, "eval_cutoff_turns": 0})

    def test_agreement_cli_K大于0无评估器_报错(self, snapshot_file, tmp_path) -> None:
        snap_path = tmp_path / "snap.jsonl"
        snap_path.write_text(
            json.dumps({"record": "header", **snapshot_file.header},
                       ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8")
        rc = cli_main(["agreement", str(snap_path), "--worlds", "1",
                       "--iterations", "2", "--eval-cutoff-turns", "5"])
        assert rc == 1

    _DB_PATH = Path("C:/Vibe Project/Pokearena/data/ptcg-cn.db")

    @pytest.mark.skipif(not _DB_PATH.exists(), reason="本机无 ptcg-cn.db")
    def test_collect_snapshots_cli_真实池冒烟(self, tmp_path) -> None:
        """target-pool.v1 前两个 archetype（1 配对）× 1 局 1×1 教师：header +
        快照行落盘，可载入评估。"""
        full = yaml.safe_load(
            Path("config/target-pool.v1.yml").read_text(encoding="utf-8"))
        mini = dict(full, decks=full["decks"][:2])
        pool_path = tmp_path / "pool.yml"
        pool_path.write_text(yaml.safe_dump(mini, allow_unicode=True),
                             encoding="utf-8")
        out = tmp_path / "m11-eval"
        rc = cli_main(["collect-snapshots", "--pool", str(pool_path),
                       "--games-per-pair", "1", "--seed-start", "430000",
                       "--out", str(out), "--workers", "1",
                       "--worlds", "1", "--iterations", "1",
                       "--db", str(self._DB_PATH)])
        assert rc == 0
        files = list(out.glob("pair-*.jsonl"))
        assert len(files) == 1
        snap = load_snapshot_file(files[0])
        assert snap.header["format"] == "bf-m11-snapshot-v1"
        report = run_agreement(snap, {"worlds": 1, "iterations": 1,
                                      "rollout_turn_cap": 50})
        assert report["snapshots_total"] >= 0  # 单局可能零搜索点，结构完整即可
