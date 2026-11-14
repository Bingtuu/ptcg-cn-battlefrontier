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


# ── task 121：森林图（手写轻量 SVG，零图表依赖）────────────

_FOREST_W, _FOREST_ROW_H = 720, 48
_FOREST_PAD_L, _FOREST_PAD_R, _FOREST_PAD_T, _FOREST_PAD_B = 200, 40, 40, 40


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def forest_svg(rep: SensitivityReport) -> str:
    """每变体一行：ΔWR 点估计 + CI 须线 + 零线参照；CI 不跨零加粗着色。

    数值直接取 VariantComparison（与 md/csv/json 同一来源，不另算）。
    """
    rows = [c for c in rep.variants if c.d_ci is not None]
    if not rows:
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="360" height="60">'
                '<text x="10" y="30" font-size="14">无可用 CI 的变体</text></svg>')
    lows = [c.d_ci[0] * 100 for c in rows]
    highs = [c.d_ci[1] * 100 for c in rows]
    lo, hi = min(lows + [0.0]), max(highs + [0.0])
    span = (hi - lo) or 1.0
    plot_w = _FOREST_W - _FOREST_PAD_L - _FOREST_PAD_R

    def x(v: float) -> float:
        return _FOREST_PAD_L + (v - lo) / span * plot_w

    height = _FOREST_PAD_T + _FOREST_PAD_B + _FOREST_ROW_H * len(rows)
    parts = [
        (f'<svg xmlns="http://www.w3.org/2000/svg" width="{_FOREST_W}" height="{height}" '
         'font-family="sans-serif">'),
        (f'<text x="{_FOREST_W // 2}" y="22" text-anchor="middle" font-size="15">'
         '换卡敏感性森林图（ΔWR %，95% CI；同模拟器内对比，不构成真实预测）</text>'),
    ]
    zero_x = x(0.0)
    parts.append(f'<line x1="{zero_x:.1f}" y1="{_FOREST_PAD_T - 8}" '
                 f'x2="{zero_x:.1f}" y2="{height - _FOREST_PAD_B + 8}" '
                 'stroke="#888" stroke-dasharray="4 3"/>')
    for tick in range(int(lo) // 5 * 5, int(hi) + 6, 5):
        tx = x(tick)
        parts.append(f'<line x1="{tx:.1f}" y1="{height - _FOREST_PAD_B}" '
                     f'x2="{tx:.1f}" y2="{height - _FOREST_PAD_B + 6}" stroke="#444"/>')
        parts.append(f'<text x="{tx:.1f}" y="{height - _FOREST_PAD_B + 22}" '
                     f'text-anchor="middle" font-size="12">{tick}%</text>')
    for i, comp in enumerate(rows):
        y = _FOREST_PAD_T + _FOREST_ROW_H * i + _FOREST_ROW_H // 2
        d = comp.d_wr * 100
        c_lo, c_hi = comp.d_ci[0] * 100, comp.d_ci[1] * 100
        sig = comp.p is not None and comp.p < 0.05
        color = "#c0392b" if sig else "#2c3e50"
        parts.append(f'<text x="{_FOREST_PAD_L - 10}" y="{y + 4}" '
                     f'text-anchor="end" font-size="13">{_esc(comp.variant)}</text>')
        parts.append(f'<line x1="{x(c_lo):.1f}" y1="{y}" x2="{x(c_hi):.1f}" y2="{y}" '
                     f'stroke="{color}" stroke-width="2"/>')
        for v in (c_lo, c_hi):
            parts.append(f'<line x1="{x(v):.1f}" y1="{y - 5}" x2="{x(v):.1f}" '
                         f'y2="{y + 5}" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<circle cx="{x(d):.1f}" cy="{y}" r="5" fill="{color}"/>')
        parts.append(f'<text x="{x(c_hi) + 8:.1f}" y="{y + 4}" font-size="12" '
                     f'fill="{color}">{d:+.1f}%</text>')
    parts.append("</svg>")
    return "\n".join(parts)


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
        "svg": out / "swap.svg",  # task 121：森林图
    }
    paths["md"].write_text(markdown, encoding="utf-8")
    svg = forest_svg(rep)
    paths["svg"].write_text(svg, encoding="utf-8")
    html = deviation_html(markdown)
    # 森林图内嵌（自生成 SVG，变体名已转义；置于转义正文之后）
    html = html.replace("</pre></body>", f"</pre>\n<h2>森林图</h2>\n{svg}\n</body>")
    paths["html"].write_text(html, encoding="utf-8")
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
