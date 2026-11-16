# task 126 净效应门正式跑批编排（预注册：task 126 设计段）
# 顺序跑 8 个实验定义（3 格 × on/off 400 局 + C1 深档 4×100 × on/off 200 局），
# 逐实验计时（成本门 = on/off 墙钟比 ≤3），完成后自动调判读脚本。
# 用法: .venv/Scripts/python.exe -X utf8 .kimi-code/t126_run_acceptance.py [workers]
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "results" / "t126-net-effect.db"
EXPS = [
    ("t126-C1-on", "t126/t126-C1-on"), ("t126-C1-off", "t126/t126-C1-off"),
    ("t126-C2-on", "t126/t126-C2-on"), ("t126-C2-off", "t126/t126-C2-off"),
    ("t126-C3-on", "t126/t126-C3-on"), ("t126-C3-off", "t126/t126-C3-off"),
    ("t126-C1deep-on", "t126/t126-C1deep-on"), ("t126-C1deep-off", "t126/t126-C1deep-off"),
]

def main():
    workers = sys.argv[1] if len(sys.argv) > 1 else "14"
    timings = {}
    for name, yml in EXPS:
        t0 = time.perf_counter()
        r = subprocess.run(
            [".venv/Scripts/python.exe", "-X", "utf8", "-m", "battlefrontier.cli",
             "run", f"experiments/{yml}.yml", "--results", str(DB),
             "--workers", workers],
            cwd=ROOT)
        dt = time.perf_counter() - t0
        timings[name] = round(dt, 1)
        print(f"[timing] {name}: {dt:.1f}s", flush=True)
        if r.returncode != 0:
            print(f"[FAIL] {name} rc={r.returncode}", flush=True)
            sys.exit(1)
    (ROOT / "results" / "t126-gate").mkdir(parents=True, exist_ok=True)
    (ROOT / "results" / "t126-gate" / "timings.json").write_text(
        __import__("json").dumps(timings, indent=1), encoding="utf-8")
    # 成本门判读
    cost = {}
    for cell in ("C1", "C2", "C3", "C1deep"):
        on, off = timings[f"t126-{cell}-on"], timings[f"t126-{cell}-off"]
        cost[cell] = {"on_s": on, "off_s": off, "ratio": round(on / off, 2),
                      "pass": on / off <= 3.0}
    print("[cost-gate]", __import__("json").dumps(cost, ensure_ascii=False), flush=True)
    # 判读
    subprocess.run(
        [".venv/Scripts/python.exe", "-X", "utf8",
         ".kimi-code/t126_net_effect.py", str(DB),
         "t126-C1-on:t126-C1-off", "t126-C2-on:t126-C2-off",
         "t126-C3-on:t126-C3-off"],
        cwd=ROOT)
    subprocess.run(
        [".venv/Scripts/python.exe", "-X", "utf8",
         ".kimi-code/t126_net_effect.py", str(DB),
         "t126-C1deep-on:t126-C1deep-off"],
        cwd=ROOT)

if __name__ == "__main__":
    main()
