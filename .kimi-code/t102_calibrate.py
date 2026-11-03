"""task 102 — 报告层经验校准预注册验证（只读；零行为变更）.

门定义见 tasks/task 102.md §3：
  G1 判别式：val 成对逐格 |误差| 校准 vs flat，改善 > 0.5pts 且 bootstrap CI 下界 > 0
  G2       ：val 加权 |Δ| ≤ 13%
  G3       ：dev logit 线性斜率 b 的 95% CI 不含 0
  G4       ：映射单调、值域 [0,1]
输出 results/t102-calibration.json。
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "results/m13-baseline/development/deviation.json"
VAL = ROOT / "results/m13-baseline/validation/deviation.json"
V1 = ROOT / "results/t102-v1-deviation/deviation.json"
OUT = ROOT / "results/t102-calibration.json"
BOOT = 10_000


def load_cells(path: Path) -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return [
        {"sim": c["sim_wr"], "real": c["real_wr"], "n": c["real_n"]}
        for c in d["cells"]
    ]


def logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def wmad(cells: list[dict], f) -> float:
    num = sum(c["n"] * abs(f(c["sim"]) - c["real"]) for c in cells)
    den = sum(c["n"] for c in cells)
    return num / den


def fit_logit_linear(cells: list[dict]) -> tuple[float, float, tuple[float, float]]:
    """加权最小二乘 logit(real)=a+b*logit(sim)；返回 (a, b, b 的 CI)。"""
    xs = [logit(c["sim"]) for c in cells]
    ws = [c["n"] for c in cells]
    ys = [logit(c["real"]) for c in cells]
    sw = sum(ws)
    mx = sum(w * x for w, x in zip(ws, xs)) / sw
    my = sum(w * y for w, y in zip(ws, ys)) / sw
    cov = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys))
    var = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    b = cov / var
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    dof = len(cells) - 2
    s2 = sum(w * e * e for w, e in zip(ws, resid)) / max(dof, 1) / (sw / len(cells))
    se = math.sqrt(max(s2, 0.0) / max(var / (sw / len(cells)), 1e-12))
    tcrit = 1.96  # n=72，正态近似
    return a, b, (b - tcrit * se, b + tcrit * se)


def fit_isotonic(cells: list[dict]):
    """PAVA（real_n 加权），返回阶跃函数。"""
    pts = sorted((c["sim"], c["real"], c["n"]) for c in cells)
    xs = [p[0] for p in pts]
    lvl_y: list[float] = []
    lvl_w: list[float] = []
    starts: list[int] = []
    ends: list[int] = []
    for i, (_, y, w) in enumerate(pts):
        lvl_y.append(y)
        lvl_w.append(w)
        starts.append(i)
        ends.append(i)
        while len(lvl_y) >= 2 and lvl_y[-2] > lvl_y[-1]:
            wy = lvl_y[-2] * lvl_w[-2] + lvl_y[-1] * lvl_w[-1]
            ww = lvl_w[-2] + lvl_w[-1]
            lvl_y[-2] = wy / ww
            lvl_w[-2] = ww
            ends[-2] = ends[-1]
            for L in (lvl_y, lvl_w, starts, ends):
                L.pop()

    def f(s: float) -> float:
        if s <= xs[starts[0]]:
            return lvl_y[0]
        for j in range(len(lvl_y)):
            hi = xs[ends[j]] if j == len(lvl_y) - 1 else xs[starts[j + 1]]
            if xs[starts[j]] <= s <= hi:
                return lvl_y[j]
        return lvl_y[-1]

    return f, list(zip(starts, ends, lvl_y))


def corr(xs, ys, w) -> float:
    sw = sum(w)
    mx = sum(a * b for a, b in zip(w, xs)) / sw
    my = sum(a * b for a, b in zip(w, ys)) / sw
    cov = sum(wi * (x - mx) * (y - my) for wi, x, y in zip(w, xs, ys))
    vx = sum(wi * (x - mx) ** 2 for wi, x in zip(w, xs))
    vy = sum(wi * (y - my) ** 2 for wi, y in zip(w, ys))
    return cov / math.sqrt(vx * vy)


def ranks(xs) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def corr_report(cells: list[dict]) -> dict:
    s = [c["sim"] for c in cells]
    r = [c["real"] for c in cells]
    n = [c["n"] for c in cells]
    return {
        "n": len(cells),
        "pearson": round(corr(s, r, n), 3),
        "spearman": round(corr(ranks(s), ranks(r), n), 3),
    }


def bootstrap_gate(val: list[dict], f_cal, flat: float, seed: int = 10200):
    """G1：成对逐格 |误差| 改善（校准 − flat，负值=校准更优）的 bootstrap CI。"""
    diffs = [abs(f_cal(c["sim"]) - c["real"]) - abs(flat - c["real"]) for c in val]
    point = sum(diffs) / len(diffs)
    rng = random.Random(seed)
    boots = []
    m = len(diffs)
    for _ in range(BOOT):
        idx = [rng.randrange(m) for _ in range(m)]
        boots.append(sum(diffs[i] for i in idx) / m)
    boots.sort()
    lo = boots[int(0.025 * BOOT)]
    hi = boots[int(0.975 * BOOT)]
    return {"point_pts": round(-point * 100, 3), "ci_low_pts": round(-lo * 100, 3),
            "ci_high_pts": round(-hi * 100, 3),
            "pass": (-point * 100 > 0.5) and (-lo * 100 > 0)}


def check_monotonic_range(f, samples=201) -> str:
    """返回 'increasing' | 'decreasing' | 'fail'（值域 [0,1] 且单调，任一方向）。"""
    grid = [i / (samples - 1) for i in range(samples)]
    vals = [f(x) for x in grid]
    if not all(0.0 <= v <= 1.0 for v in vals):
        return "fail"
    up = all(vals[i] <= vals[i + 1] + 1e-12 for i in range(len(vals) - 1))
    dn = all(vals[i] >= vals[i + 1] - 1e-12 for i in range(len(vals) - 1))
    if up:
        return "increasing"
    if dn:
        return "decreasing"
    return "fail"


def main() -> None:
    dev = load_cells(DEV)
    val = load_cells(VAL)
    v1 = load_cells(V1)
    v1_nolc = [c for c in v1 if c["n"] >= 100]

    # 预检复算（v2 dev/val、v1 全窗口）
    precheck = {
        "v2_dev": corr_report(dev),
        "v2_val": corr_report(val),
        "v1_full": corr_report(v1),
        "v1_no_low_conf": corr_report(v1_nolc),
    }

    # 参照
    dev_mean = sum(c["n"] * c["real"] for c in dev) / sum(c["n"] for c in dev)
    identity_val = wmad(val, lambda s: s)
    flat_val = wmad(val, lambda s: dev_mean)

    # 臂 A：logit 线性
    a, b, b_ci = fit_logit_linear(dev)
    f_a = lambda s: sig(a + b * logit(s))
    # 臂 B：等渗
    f_b, iso_levels = fit_isotonic(dev)

    monotonic_a = check_monotonic_range(f_a)
    monotonic_b = check_monotonic_range(f_b)

    arms = {}
    for name, f, mono in (("logit_linear", f_a, monotonic_a), ("isotonic", f_b, monotonic_b)):
        arms[name] = {
            "val_weighted_mad_pct": round(wmad(val, f) * 100, 2),
            "g1": bootstrap_gate(val, f, dev_mean),
            "g4_monotonic_range": mono,
        }

    g2_pass = any(v["val_weighted_mad_pct"] <= 13.0 for v in arms.values())
    g3_pass = not (b_ci[0] <= 0 <= b_ci[1])

    verdict = (
        "PASS"
        if all(v["g1"]["pass"] and v["g4_monotonic_range"] != "fail" for v in arms.values())
        and g2_pass and g3_pass
        else "FAIL"
    )

    out = {
        "task": 102,
        "precheck_correlations": precheck,
        "references": {
            "identity_val_weighted_mad_pct": round(identity_val * 100, 2),
            "flat_val_weighted_mad_pct": round(flat_val * 100, 2),
            "dev_real_weighted_mean": round(dev_mean, 4),
        },
        "arm_a_fit": {"a": round(a, 4), "b": round(b, 4), "b_ci95": [round(x, 4) for x in b_ci]},
        "iso_levels_n": len(iso_levels),
        "arms": arms,
        "gates": {
            "G1_discriminating": {k: v["g1"] for k, v in arms.items()},
            "G2_val_wmad_le_13": g2_pass,
            "G3_slope_ci_excludes_0": g3_pass,
            "G4_monotonic_range": {k: v["g4_monotonic_range"] for k, v in arms.items()},
        },
        "verdict": verdict,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
