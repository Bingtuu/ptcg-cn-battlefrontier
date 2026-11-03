# task 101 CRN 统计（只读）：base vs gate 两臂同种子逐局配对，A 侧结局差 + 95% CI。
# 用法：PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 .kimi-code/t101_crn.py

from __future__ import annotations

import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIRS = [
    ("ragingbolt-drag", "results/t101-ragingbolt-drag-base.db",
     "results/t101-ragingbolt-drag-gate.db"),
    ("flareon-drag", "results/t101-flareon-drag-base.db",
     "results/t101-flareon-drag-gate.db"),
    ("control-drag-zoro", "results/t101-control-drag-zoro-base.db",
     "results/t101-control-drag-zoro-gate.db"),
]


def outcomes(db_file: str) -> dict[int, int]:
    con = sqlite3.connect(ROOT / db_file)
    out = {}
    fails = 0
    for seed, winner, draw, err in con.execute(
            "SELECT seed, winner, is_draw, error FROM games"):
        if err:
            fails += 1
            continue
        out[seed] = 0 if draw else (1 if winner == 0 else -1)
    con.close()
    return out, fails


def ci95(vals: list[float]) -> tuple[float, float, float]:
    n = len(vals)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = sum(vals) / n
    if n < 2:
        return mean, mean, mean
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    half = 1.96 * math.sqrt(var / n)
    return mean, mean - half, mean + half


def main() -> int:
    all_diffs: list[float] = []
    for label, base, gate in PAIRS:
        ob, fb = outcomes(base)
        og, fg = outcomes(gate)
        common = sorted(set(ob) & set(og))
        diffs = [float(og[s] - ob[s]) for s in common]
        mean, lo, hi = ci95(diffs)
        wr_b = sum(ob[s] for s in common) / len(common)
        wr_g = sum(og[s] for s in common) / len(common)
        print(f"{label}: n={len(diffs)} 失败 base={fb} gate={fg}")
        print(f"  A 侧 WR base={wr_b:.3f} gate={wr_g:.3f} "
              f"(Δ={wr_g - wr_b:+.3f})")
        print(f"  逐种子差 mean={mean:+.4f} CI[{lo:+.4f},{hi:+.4f}]")
        if label != "control-drag-zoro":
            all_diffs.extend(diffs)
    m, lo, hi = ci95(all_diffs)
    print(f"\n两目标对合并（池化 {len(all_diffs)} 种子）：mean={m:+.4f} "
          f"CI[{lo:+.4f},{hi:+.4f}]")
    print("主指标判定：合并 mean>0 且 CI 下界>0 且两对点估计>0 → 过线")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
