# task 145 冒烟 arm 1：蒸馏学生 agreement（arm 2 已由 t145_eval_probe.py 承接，预注册修订）
# 预注册下限：≥25%（v1 参考 35.1/34.7/42.0 → v1min−10pp）；读数落 stdout 供任务书回填。
import os
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path("C:/Vibe Project/Pokebattle")
PY = ROOT / ".venv/Scripts/python.exe"
SNAPS = sorted((ROOT / "results/t145-teacher-v2x").glob("pair-*.jsonl"))
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")

FLOOR = 25.0
rows = []
for snap in SNAPS:
    r = subprocess.run(
        [str(PY), "-X", "utf8", "-m", "battlefrontier.cli", "agreement",
         str(snap), "--policy", "models/policy-m12-v2.json"],
        capture_output=True, text=True, cwd=ROOT, timeout=1800, env=ENV,
        check=False)
    m = re.findall(r"一致率\s+([\d.]+)", r.stdout + r.stderr)
    d = float(m[-1]) * 100 if m else None
    rows.append((snap.name, r.returncode, d))
    print(f"{snap.name}: rc={r.returncode} 一致率={d}%", flush=True)

bad = [r for r in rows if r[1] != 0 or (r[2] is not None and r[2] < FLOOR)]
print()
print(f"snapshots: {len(rows)}, below floor / rc!=0: {len(bad)}")
for b in bad:
    print("  LOW:", b)
print("SMOKE:", "FAIL" if bad else "PASS")
