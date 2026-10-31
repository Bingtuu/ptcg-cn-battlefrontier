"""M13：校准扩展汇总与运行 manifest。"""

from __future__ import annotations

import hashlib
import json

import pytest

from battlefrontier.report.calibration import CalibrationCell, CalibrationReport
from battlefrontier.report.validation import (
    calibration_summary,
    write_validation_manifest,
)


def _cell(**kw) -> CalibrationCell:
    base = {
        "archetype": "甲", "opponent": "乙", "en_archetype": "A", "en_opponent": "B",
        "sim_decided": 10, "sim_wins": 6, "sim_draws": 0, "sim_failed": 0,
        "sim_wr": 0.6, "sim_ci": (0.3, 0.8),
        "real_n": 100, "real_wr": 0.5, "real_low_confidence": False, "delta": 0.1,
    }
    base.update(kw)
    return CalibrationCell(**base)


def _report(cells) -> CalibrationReport:
    return CalibrationReport(
        group_name="m13", cells=tuple(cells), weighted_mean_abs_delta=None,
        ci_coverage=None, meta={"code_version": "cv", "data_version": "dv", "real": {}},
    )


def test_summary_computes_unweighted_high_residual_and_rows():
    rep = _report([
        _cell(),
        _cell(
            archetype="乙", opponent="甲", en_archetype="B", en_opponent="A",
            sim_wr=0.4, real_n=300, real_wr=0.75, delta=-0.35,
        ),
        _cell(real_n=None, real_wr=None, real_low_confidence=None, delta=None),
    ])
    summary = calibration_summary(rep)
    assert summary["weighted_mean_abs_delta"] == pytest.approx(0.2875)
    assert summary["unweighted_mean_abs_delta"] == pytest.approx(0.225)
    assert summary["high_residual_cells"] == 1
    assert summary["max_cell"] == {"archetype": "乙", "opponent": "甲", "delta": -0.35}
    assert [row["archetype"] for row in summary["rows"]] == ["乙", "甲"]
    assert summary["rows"][0]["weighted_mean_abs_delta"] == pytest.approx(0.35)
    assert summary["rows"][0]["max_cell"]["opponent"] == "甲"


def test_summary_handles_no_valid_real_cells():
    summary = calibration_summary(_report([
        _cell(real_n=None, real_wr=None, real_low_confidence=None, delta=None),
    ]))
    assert summary["weighted_mean_abs_delta"] is None
    assert summary["unweighted_mean_abs_delta"] is None
    assert summary["high_residual_cells"] == 0
    assert summary["max_cell"] is None
    assert summary["rows"] == []


def test_manifest_records_protocol_reports_and_artifact_hashes(tmp_path):
    artifact = tmp_path / "results.db"
    artifact.write_bytes(b"locked-results")
    rep = _report([_cell()])
    path = write_validation_manifest(
        tmp_path / "out", protocol={"method": "time-70-30"},
        reports={"full": rep}, artifacts={"results": artifact},
        report_paths={"full": {"json": tmp_path / "full" / "deviation.json"}},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["protocol"] == {"method": "time-70-30"}
    assert payload["reports"]["full"]["summary"]["unweighted_mean_abs_delta"] == 0.1
    assert payload["artifacts"]["results"]["sha256"] == hashlib.sha256(b"locked-results").hexdigest()
    assert payload["report_paths"]["full"]["json"].replace("\\", "/").endswith("full/deviation.json")
