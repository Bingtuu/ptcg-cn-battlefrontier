"""换卡报告双轨导出（task 075）。

站在现有 `format_sensitivity` 上。Markdown 内嵌该原文。HTML 由它转义。
CSV/JSON 的 d_wr 等于同一个 `VariantComparison`。抽样回放复用 `sample_replays`，
不扫描卡池，不编造理由。
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.report.battle_log import sample_replays
from battlefrontier.report.deviation_pack import deviation_html
from battlefrontier.report.sensitivity import (
    SensitivityReport,
    VariantComparison,
    format_sensitivity,
)
from battlefrontier.runner.results_db import ResultsDB


@dataclass(frozen=True)
class SwapReplay:
    label: str
    experiment_id: int
    game_id: int
    seed: int
    text: str


def swap_replays(db: ResultsDB, rep: SensitivityReport,
                 sample_n: int) -> tuple[SwapReplay, ...]:
    """baseline 与每个 variant 各抽 sample_n 局。0 表示不抽。"""
    if sample_n < 0:
        raise ValueError("sample_n 不能为负")
    groups = [("baseline", rep.base.experiment_id)]
    groups.extend((comp.variant, comp.experiment_id) for comp in rep.variants)
    out: list[SwapReplay] = []
    for label, exp_id in groups:
        for replay in sample_replays(db, exp_id, sample_n):
            out.append(SwapReplay(
                label=label, experiment_id=replay.experiment_id,
                game_id=replay.game_id, seed=replay.seed, text=replay.text,
            ))
    return tuple(out)


def _variant_row(comp: VariantComparison) -> dict[str, object]:
    low = None if comp.d_ci is None else comp.d_ci[0]
    high = None if comp.d_ci is None else comp.d_ci[1]
    return {
        "role": "variant",
        "experiment_id": comp.experiment_id,
        "name": comp.variant,
        "wr_a": comp.wr_a,
        "wins_a": comp.wins_a,
        "decided": comp.decided,
        "draws": comp.report.draws,
        "games_failed": comp.report.games_failed,
        "d_wr": comp.d_wr,
        "d_ci_low": low,
        "d_ci_high": high,
        "z": comp.z,
        "p": comp.p,
    }


def swap_rows(rep: SensitivityReport) -> list[dict[str, object]]:
    base = rep.base
    rows: list[dict[str, object]] = [{
        "role": "baseline",
        "experiment_id": base.experiment_id,
        "name": base.name,
        "wr_a": base.wr_a,
        "wins_a": base.wins_a,
        "decided": base.decided,
        "draws": base.draws,
        "games_failed": base.games_failed,
        "d_wr": None,
        "d_ci_low": None,
        "d_ci_high": None,
        "z": None,
        "p": None,
    }]
    rows.extend(_variant_row(comp) for comp in rep.variants)
    return rows


def format_swap_replays(replays: tuple[SwapReplay, ...]) -> str:
    if not replays:
        return "抽样回放：无（sample 为 0，或完成局为 0）"
    lines = [f"抽样回放：{len(replays)} 局（换卡前后各按种子升序，不渲染全部）"]
    for replay in replays:
        lines.append(
            f"## {replay.label} 实验 #{replay.experiment_id}"
            f" 种子 {replay.seed} 局 #{replay.game_id}"
        )
        lines.append(replay.text or "（空事件流）")
    return "\n".join(lines)


def swap_markdown(rep: SensitivityReport, replays: tuple[SwapReplay, ...]) -> str:
    return (
        "# 换卡报告\n\n"
        "代码块内是 `format_sensitivity` 的原文，不另算数字。\n\n"
        "```\n"
        f"{format_sensitivity(rep)}\n"
        "```\n\n"
        "```\n"
        f"{format_swap_replays(replays)}\n"
        "```\n"
    )


_FIELDS = (
    "role", "experiment_id", "name", "wr_a", "wins_a", "decided", "draws",
    "games_failed", "d_wr", "d_ci_low", "d_ci_high", "z", "p",
)


def write_swap_pack(directory: str | Path, rep: SensitivityReport,
                    replays: tuple[SwapReplay, ...]) -> dict[str, Path]:
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    markdown = swap_markdown(rep, replays)
    paths = {
        "md": out / "swap.md",
        "html": out / "swap.html",
        "csv": out / "swap.csv",
        "json": out / "swap.json",
    }
    paths["md"].write_text(markdown, encoding="utf-8")
    paths["html"].write_text(deviation_html(markdown), encoding="utf-8")
    rows = swap_rows(rep)
    with paths["csv"].open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if row[k] is None else row[k] for k in _FIELDS})
    payload = {
        "baseline_id": rep.base.experiment_id,
        "rows": rows,
        "replays": [
            {"label": r.label, "experiment_id": r.experiment_id,
             "game_id": r.game_id, "seed": r.seed, "text": r.text}
            for r in replays
        ],
    }
    paths["json"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return paths
