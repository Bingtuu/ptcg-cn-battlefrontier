"""M13：split 报告扩展与旧报告兼容。"""

from battlefrontier.report.calibration import (
    CalibrationCell,
    CalibrationReport,
    format_calibration,
)
from battlefrontier.report.deviation_pack import deviation_payload


def _report(*, split: bool) -> CalibrationReport:
    cell = CalibrationCell(
        archetype="甲", opponent="乙", en_archetype="A", en_opponent="B",
        sim_decided=10, sim_wins=6, sim_draws=0, sim_failed=0,
        sim_wr=0.6, sim_ci=(0.3, 0.8), real_n=100, real_wr=0.5,
        real_low_confidence=False, delta=0.1,
    )
    meta = {
        "experiment": "m13", "seed_min": 1, "seed_max": 10,
        "code_version": "cv", "data_version": "dv", "real": {}, "warnings": [],
    }
    if split:
        meta["validation_split"] = "time-70-30"
        meta["validation_limitation"] = "从 M13 起冻结的前瞻验证，并非绝对未见 holdout"
    return CalibrationReport(
        group_name="m13", cells=(cell,), weighted_mean_abs_delta=0.1,
        ci_coverage=1.0, meta=meta,
    )


def test_split_report_exposes_extended_summary():
    rep = _report(split=True)
    text = format_calibration(rep)
    assert "未加权平均 |Δ| 10.0%" in text
    assert "|Δ|≥25% 格 0/1" in text
    assert "行级 甲" in text
    assert "限制：从 M13 起冻结的前瞻验证，并非绝对未见 holdout" in text
    payload = deviation_payload(rep)
    assert payload["summary"]["unweighted_mean_abs_delta"] == 0.1
    assert payload["summary"]["rows"][0]["archetype"] == "甲"


def test_legacy_report_does_not_expose_extended_summary():
    rep = _report(split=False)
    text = format_calibration(rep)
    assert "未加权平均" not in text
    assert "行级" not in text
    assert "summary" not in deviation_payload(rep)
