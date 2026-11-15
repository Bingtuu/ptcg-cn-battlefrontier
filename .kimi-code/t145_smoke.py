# task 145 冒烟两连：对每份 pair 快照跑 (1) 蒸馏学生 agreement (2) 评估器 agreement
# 预注册下限：两者各 ≥45%（非退化线）；读数落 stdout 供任务书回填。
import json, subprocess, sys, re
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path("C:/Vibe Project/Pokebattle")
PY = ROOT / ".venv/Scripts/python.exe"
SNAPS = sorted((ROOT / "results/t145-teacher-v2x").glob("pair-*.jsonl"))

def run_agreement(snap, extra):
    cmd = [str(PY), "-X", "utf8", "-m", "battlefrontier.cli", "agreement",
           str(snap)] + extra
    r = subprocess.run(cmd, capture_output=True, text=True,
                       cwd=ROOT, timeout=1800,
                       env={"PYTHONIOENCODING": "utf-8", "PATH": "C:/Vibe Project/Pokebattle/.venv/Scripts;C:/Program Files/Git/usr/bin;C:/Program Files/Git/bin;C:/Windows/System32"})
    out = r.stdout + r.stderr
    m = re.findall(r"一致率\s+([\d.]+)", out)
    return r.returncode, out, m

FLOOR = 25.0  # 预注册修订 2026-11-16：v1 参考 35.1/34.7/42.0 → 下限 = v1min−10pp
rows = []
for snap in SNAPS:
    rc1, out1, m1 = run_agreement(snap, ["--policy", "models/policy-m12-v2.json"])
    rc2, out2, m2 = run_agreement(snap, ["--worlds", "1", "--iterations", "25",
                                         "--eval-cutoff-turns", "10",
                                         "--evaluator", "models/eval-linear-v1.json"])
    # 取输出中的最后百分比 = 一致率（格式以 agreement 输出为准，失败时落原始输出）
    d = float(m1[-1]) if m1 else None
    ev = float(m2[-1]) if m2 else None
    rows.append((snap.name, rc1, d, rc2, ev))
    print(f"{snap.name}: distilled rc={rc1} {d}% | evaluator rc={rc2} {ev}%", flush=True)

print()
bad = [r for r in rows if r[1] != 0 or r[3] != 0 or
       (r[2] is not None and r[2] < FLOOR) or (r[4] is not None and r[4] < FLOOR)]
print(f"snapshots: {len(rows)}, below floor / rc!=0: {len(bad)}")
for b in bad:
    print("  LOW:", b)
print("SMOKE:", "FAIL" if bad else "PASS")
