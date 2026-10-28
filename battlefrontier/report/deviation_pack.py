"""校准偏差包双轨导出（task 072）。

人读 Markdown 内嵌 `format_calibration` 全文（与 CLI 标准输出同一段文字）。
HTML 由该 Markdown 转义生成，不另算数字。
CSV / JSON 的字段来自同一个 `CalibrationReport.cells`。
"""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from battlefrontier.report.calibration import (
    CalibrationCell,
    CalibrationReport,
    format_calibration,
)


def deviation_markdown(rep: CalibrationReport) -> str:
    """人读报告。代码块内文字与 `bfsim calibration` 打印的正文相同。"""
    body = format_calibration(rep)
    return (
        f"# 校准偏差包：{rep.group_name}\n\n"
        "代码块内是 `format_calibration` 的原文，与命令行标准输出一致，不另算数字。\n\n"
        "```\n"
        f"{body}\n"
        "```\n"
    )


def deviation_html(markdown: str) -> str:
    """由已生成的 Markdown 转义得到 HTML，避免第二条格式化路径。"""
    escaped = html.escape(markdown)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>校准偏差包</title></head>\n"
        f"<body><pre>{escaped}</pre></body></html>\n"
    )


_COLUMNS = (
    "archetype", "opponent", "en_archetype", "en_opponent",
    "sim_decided", "sim_wins", "sim_draws", "sim_failed",
    "sim_wr", "sim_ci_low", "sim_ci_high",
    "real_n", "real_wr", "real_low_confidence", "delta",
)


def _cell_row(cell: CalibrationCell) -> dict[str, object]:
    return {
        "archetype": cell.archetype,
        "opponent": cell.opponent,
        "en_archetype": cell.en_archetype,
        "en_opponent": cell.en_opponent,
        "sim_decided": cell.sim_decided,
        "sim_wins": cell.sim_wins,
        "sim_draws": cell.sim_draws,
        "sim_failed": cell.sim_failed,
        "sim_wr": cell.sim_wr,
        "sim_ci_low": cell.sim_ci[0],
        "sim_ci_high": cell.sim_ci[1],
        "real_n": cell.real_n,
        "real_wr": cell.real_wr,
        "real_low_confidence": cell.real_low_confidence,
        "delta": cell.delta,
    }


def deviation_payload(rep: CalibrationReport) -> dict[str, object]:
    return {
        "group_name": rep.group_name,
        "weighted_mean_abs_delta": rep.weighted_mean_abs_delta,
        "ci_coverage": rep.ci_coverage,
        "meta": rep.meta,
        "cells": [_cell_row(c) for c in rep.cells],
    }


def write_deviation_pack(directory: str | Path, rep: CalibrationReport) -> dict[str, Path]:
    """写出 md / html / csv / json。返回路径。"""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    markdown = deviation_markdown(rep)
    md_path = out / "deviation.md"
    html_path = out / "deviation.html"
    csv_path = out / "deviation.csv"
    json_path = out / "deviation.json"
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(deviation_html(markdown), encoding="utf-8")
    payload = deviation_payload(rep)
    rows = payload["cells"]
    assert isinstance(rows, list)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if v is None else v for k, v in row.items()})
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"md": md_path, "html": html_path, "csv": csv_path, "json": json_path}
