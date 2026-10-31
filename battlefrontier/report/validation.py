"""M13：开发/验证校准扩展汇总与运行 manifest。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from battlefrontier.report.calibration import CalibrationCell, CalibrationReport


def _mean_abs(cells: list[CalibrationCell], *, weighted: bool) -> float | None:
    if not cells:
        return None
    if weighted:
        return sum(abs(c.delta) * c.real_n for c in cells) / sum(c.real_n for c in cells)
    return sum(abs(c.delta) for c in cells) / len(cells)


def _max_cell(cells: list[CalibrationCell]) -> dict | None:
    if not cells:
        return None
    cell = max(cells, key=lambda c: abs(c.delta))
    return {
        "archetype": cell.archetype,
        "opponent": cell.opponent,
        "delta": cell.delta,
    }


def calibration_summary(rep: CalibrationReport) -> dict:
    """汇总有效真实格；缺真实数据格不进入任何均值或行级指标。"""
    valid = [c for c in rep.cells if c.delta is not None]
    rows = []
    for archetype in sorted({c.archetype for c in valid}):
        cells = [c for c in valid if c.archetype == archetype]
        rows.append({
            "archetype": archetype,
            "weighted_mean_abs_delta": _mean_abs(cells, weighted=True),
            "unweighted_mean_abs_delta": _mean_abs(cells, weighted=False),
            "max_cell": _max_cell(cells),
        })
    rows.sort(key=lambda row: (-row["weighted_mean_abs_delta"], row["archetype"]))
    return {
        "weighted_mean_abs_delta": _mean_abs(valid, weighted=True),
        "unweighted_mean_abs_delta": _mean_abs(valid, weighted=False),
        "high_residual_cells": sum(abs(c.delta) >= 0.25 for c in valid),
        "max_cell": _max_cell(valid),
        "rows": rows,
    }


def write_validation_manifest(
    directory: str | Path,
    *,
    protocol: dict,
    reports: dict[str, CalibrationReport],
    artifacts: dict[str, str | Path],
    report_paths: dict[str, dict[str, str | Path]],
) -> Path:
    """记录协议、报告汇总和输入资产哈希，供原样复算。"""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "protocol": protocol,
        "report_paths": {
            name: {kind: str(path) for kind, path in paths.items()}
            for name, paths in report_paths.items()
        },
        "reports": {
            name: {
                "group_name": rep.group_name,
                "meta": rep.meta,
                "summary": calibration_summary(rep),
            }
            for name, rep in reports.items()
        },
        "artifacts": {},
    }
    for name, raw_path in artifacts.items():
        path = Path(raw_path)
        payload["artifacts"][name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    path = out / "manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
