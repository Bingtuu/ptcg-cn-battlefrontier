"""task 072：偏差包 Markdown/HTML 与 CSV/JSON 数字同源。"""

import csv
import json

from battlefrontier.report.calibration import (
    CalibrationCell,
    CalibrationReport,
    format_calibration,
)
from battlefrontier.report.deviation_pack import write_deviation_pack


def _cell(**kw) -> CalibrationCell:
    base = {
        "archetype": "甲", "opponent": "乙", "en_archetype": "A", "en_opponent": "B",
        "sim_decided": 10, "sim_wins": 6, "sim_draws": 1, "sim_failed": 0,
        "sim_wr": 0.6, "sim_ci": (0.3, 0.8),
        "real_n": 100, "real_wr": 0.5, "real_low_confidence": False, "delta": 0.1,
    }
    base.update(kw)
    return CalibrationCell(**base)


def _report() -> CalibrationReport:
    cells = (
        _cell(),
        _cell(archetype="丙", opponent="丁", en_archetype="C", en_opponent="D",
              real_n=None, real_wr=None, real_low_confidence=None, delta=None),
    )
    return CalibrationReport(
        group_name="v2-calibration",
        cells=cells,
        weighted_mean_abs_delta=0.1,
        ci_coverage=1.0,
        meta={"experiment": "v2-calibration", "seed_min": 1, "seed_max": 2,
              "code_version": "abc", "data_version": "dv", "real": {},
              "warnings": []},
    )


def test_pack_four_files_share_calibration_numbers(tmp_path) -> None:
    rep = _report()
    paths = write_deviation_pack(tmp_path, rep)
    assert set(paths) == {"md", "html", "csv", "json"}
    markdown = paths["md"].read_text(encoding="utf-8")
    text = format_calibration(rep)
    assert text in markdown
    html = paths["html"].read_text(encoding="utf-8")
    assert "甲 vs 乙" in html
    assert "format_calibration" in html
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["weighted_mean_abs_delta"] == rep.weighted_mean_abs_delta
    assert payload["cells"][0]["delta"] == rep.cells[0].delta
    assert payload["cells"][1]["delta"] is None
    assert payload["cells"][0]["sim_wr"] == rep.cells[0].sim_wr
    with paths["csv"].open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert abs(float(rows[0]["sim_wr"]) - rep.cells[0].sim_wr) < 1e-9
    assert abs(float(rows[0]["delta"]) - rep.cells[0].delta) < 1e-9
    assert rows[1]["delta"] == ""
    assert rows[1]["real_n"] == ""
