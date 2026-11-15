# task 147 数据级 M15 readiness 验证（本机执行；仓库级断言见 tests/test_m15_readiness.py）
# 判定：组合标签集完整（40 格 × 2000 局零失败）+ 标签 CSV 落盘 + L01 阳性锚同向
#      + t145 教师快照 10 份落盘 → 全部满足才 exit 0。
import sqlite3, sys, csv
from math import erf, sqrt
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path("C:/Vibe Project/Pokebattle")
failures = []

CELLS = [("dragapult-dusknoir", "多龙黑夜"), ("joltik", "电电虫"),
         ("grimmsnarl", "玛俐"), ("gholdengo-dudun", "土龙节节")]


def load(db, name):
    con = sqlite3.connect(db)
    rows = con.execute(
        "select g.seed, g.winner from games g join experiments e "
        "on e.id=g.experiment_id where e.name=? and g.error is null", (name,)).fetchall()
    errs = con.execute(
        "select count(*) from games g join experiments e on e.id=g.experiment_id "
        "where e.name=? and g.error is not null", (name,)).fetchone()[0]
    con.close()
    return {s: w for s, w in rows}, errs


# ── 1. 标签集完整性 + 标签计算 ─────────────────────────
COMBOS = [f"L{i:02d}" for i in range(1, 11)] + ["C01", "C02", "C03"]
labels = {}
total_games = 0
for L in COMBOS:
    per_cell = []
    for suffix, tag in CELLS:
        mod, merr = load(ROOT / "results/t146-combo-labels.db", f"t146-{L}-vs-{suffix}")
        base, _ = load(ROOT / "results/t141-gardevoir-prep.db", f"t141-gard-vs-{suffix}")
        if merr:
            failures.append(f"{L}/{suffix}: {merr} 局失败")
        common = set(mod) & set(base)
        if len(mod) != 2000:
            failures.append(f"{L}/{suffix}: 改表局数 {len(mod)} != 2000")
        bw = sum(1 for s in common if base[s] == 0)
        mw = sum(1 for s in common if mod[s] == 0)
        n = len(common)
        b_only = sum(1 for s in common if base[s] == 0 and mod[s] != 0)
        m_only = sum(1 for s in common if mod[s] == 0 and base[s] != 0)
        disc = b_only + m_only
        z = (b_only - m_only) / sqrt(disc) if disc else 0.0
        p = 2 * (1 - erf(abs(z) / sqrt(2))) if disc else 1.0
        per_cell.append((tag, mw / n * 100, (mw - bw) / n * 100, p))
        total_games += len(mod)
    mean = sum(c[2] for c in per_cell) / 4
    label = "有害" if mean < -1 or any(c[3] < 0.05 and c[2] < 0 for c in per_cell) else (
        "正向" if mean > 1 else "中性")
    labels[L] = (per_cell, mean, label)

print(f"[1] 标签集：{total_games} 局，{len(failures)} 个失败项")
for L, (cells, mean, label) in labels.items():
    row = "  ".join(f"{t} {d:+.1f}pp" for t, _, d, _ in cells)
    print(f"  {L}: 均值 {mean:+.1f}pp → {label}   {row}")

with open(ROOT / "results/t146-combo-labels.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["combo", "cell", "winrate", "delta_pp", "mcnemar_p", "combo_mean", "label"])
    for L, (cells, mean, label) in labels.items():
        for tag, wr, d, p in cells:
            w.writerow([L, tag, f"{wr:.1f}", f"{d:+.1f}", f"{p:.4f}", f"{mean:+.1f}", label])
print("[2] results/t146-combo-labels.csv 落盘")

# ── 2. L01 阳性锚互证 ──────────────────────────────────
l01_mean = labels["L01"][1]
if not l01_mean > 0:
    failures.append(f"L01 阳性锚未复现正向（{l01_mean:+.1f}pp）")
print(f"[3] L01 阳性锚：{l01_mean:+.1f}pp（task 141 v2: +2.7~+6.7pp 区间同向）")

# ── 3. t145 教师快照落盘 ───────────────────────────────
snaps = sorted((ROOT / "results/t145-teacher-v2x").glob("pair-*.jsonl"))
empties = [p.name for p in snaps if p.stat().st_size == 0]
if len(snaps) != 10 or empties:
    failures.append(f"教师快照 {len(snaps)}/10 份，空文件 {empties}")
print(f"[4] 教师快照：{len(snaps)}/10 份落盘")

print()
if failures:
    print("READINESS: FAIL")
    for f_ in failures:
        print("  -", f_)
    sys.exit(1)
print("READINESS: PASS — M15 可以开始（门槛实验的地真值与教师证据链已就绪）")
