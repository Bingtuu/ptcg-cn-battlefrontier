"""真实对阵对照的双轨导出（task 073）。

Markdown 内嵌 `format_pairing_contrast`。HTML 由该 Markdown 转义。
CSV/JSON 的 n、wins、winrate 来自同一个 `PairingCell`。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from battlefrontier.data.pairings import PairingContrast, PairingSample
from battlefrontier.report.deviation_pack import deviation_html


def format_pairing_contrast(rep: PairingContrast) -> str:
    names = "、".join(rep.archetypes)
    lines = [
        (f"真实对阵对照：basis {rep.basis} / 窗口 {rep.date_from}..{rep.date_to}"
         f" / division {rep.division}"),
        f"池内 archetype：{names}",
        "口径：双方都在池内；镜像剔除；winner_side 为 0 不进分母；Δ 不在这里算",
    ]
    if not rep.cells:
        lines.append("有向格：无决定局（不猜、不填数字）")
    for cell in rep.cells:
        lines.append(
            f"{cell.archetype} vs {cell.opponent} | n={cell.n} wins={cell.wins}"
            f" winrate {cell.winrate * 100:.1f}%"
        )
    lines.append(
        f"抽样原始行 {len(rep.sample)}/{rep.sample_total}"
        "（按 tournament_id, phase, round, table_no；不是分母）"
    )
    for row in rep.sample:
        lines.append(_sample_line(row))
    return "\n".join(lines)


def _sample_line(row: PairingSample) -> str:
    return (
        f"{row.tournament_id} phase={row.phase} round={row.round}"
        f" table={row.table_no} {row.archetype_1} vs {row.archetype_2}"
        f" winner_side={row.winner_side}"
    )


def _cell_row(cell) -> dict[str, object]:
    return {
        "archetype": cell.archetype,
        "opponent": cell.opponent,
        "n": cell.n,
        "wins": cell.wins,
        "winrate": cell.winrate,
    }


def pairing_markdown(rep: PairingContrast) -> str:
    body = format_pairing_contrast(rep)
    return (
        "# 真实对阵对照\n\n"
        "代码块内是 `format_pairing_contrast` 的原文，不另算数字。\n\n"
        "```\n"
        f"{body}\n"
        "```\n"
    )


def write_pairing_pack(directory: str | Path, rep: PairingContrast) -> dict[str, Path]:
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    markdown = pairing_markdown(rep)
    md_path = out / "pairings.md"
    html_path = out / "pairings.html"
    csv_path = out / "pairings.csv"
    json_path = out / "pairings.json"
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(deviation_html(markdown), encoding="utf-8")
    rows = [_cell_row(c) for c in rep.cells]
    fields = ["archetype", "opponent", "n", "wins", "winrate"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "date_from": rep.date_from,
        "date_to": rep.date_to,
        "basis": rep.basis,
        "division": rep.division,
        "archetypes": list(rep.archetypes),
        "sample_total": rep.sample_total,
        "cells": rows,
        "sample": [row.__dict__ for row in rep.sample],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return {"md": md_path, "html": html_path, "csv": csv_path, "json": json_path}
