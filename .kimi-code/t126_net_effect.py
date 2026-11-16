# task 126 净效应门判读：CRN 成对净胜率 + CI 下界 + 成本门
# 预注册（task 126 设计段）：同 seed 区间 on/off 配对；Δ = mean(逐种子 d_i)，
# d_i = +1 on胜off负 / -1 on负off胜 / 0 其他（含双平）；CI = 正态近似
# mean ± 1.96·sd/√n（配对口径，含同种子相关性）；门 = CI 下界 > 0。
# 成本门 = on 墙钟 / off 墙钟 ≤ 3（同格同局数）。
# 用法: .venv/Scripts/python.exe -X utf8 .kimi-code/t126_net_effect.py <db> <格实验名对...>
#   格实验名对 = on名:off名（同 seed 区间配对），如 t126-C1-on:t126-C1-off

import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def cell_results(db_path, on_name, off_name):
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    def games(name):
        eid = cur.execute(
            "select id from experiments where name=?", (name,)).fetchone()
        if eid is None:
            raise SystemExit(f"实验名未找到：{name}")
        return {seed: (winner, is_draw)
                for seed, winner, is_draw in cur.execute(
                    "select seed, winner, is_draw from games where experiment_id=?",
                    (eid[0],))}

    g_on, g_off = games(on_name), games(off_name)
    common = sorted(set(g_on) & set(g_off))
    if not common:
        raise SystemExit(f"{on_name} / {off_name} 无共同种子")
    ds = []
    b = c = 0  # on 胜 off 负 / on 负 off 胜
    for s in common:
        won = g_on[s][0] == 0 and not g_on[s][1]
        won_off = g_off[s][0] == 0 and not g_off[s][1]
        if won and not won_off:
            ds.append(1.0)
            b += 1
        elif won_off and not won:
            ds.append(-1.0)
            c += 1
        else:
            ds.append(0.0)
    n = len(ds)
    mean = sum(ds) / n
    var = sum((d - mean) ** 2 for d in ds) / n
    sd = math.sqrt(var)
    half = 1.96 * sd / math.sqrt(n) if n else 0.0
    lo, hi = mean - half, mean + half
    # McNemar 精确双侧
    if b + c > 0:
        from math import comb
        k = min(b, c)
        p = min(1.0, 2.0 * sum(comb(b + c, i) for i in range(k + 1)) / 2 ** (b + c))
    else:
        p = 1.0
    wr_on = sum(1 for s in common if g_on[s][0] == 0 and not g_on[s][1]) / n * 100
    wr_off = sum(1 for s in common if g_off[s][0] == 0 and not g_off[s][1]) / n * 100
    con.close()
    return {
        "cell": on_name.rsplit("-", 1)[0],
        "n": n, "wr_on": round(wr_on, 2), "wr_off": round(wr_off, 2),
        "delta_pp": round(mean * 100, 2),
        "ci95": [round(lo * 100, 2), round(hi * 100, 2)],
        "ci_lower_pass": lo > 0,
        "mcnemar_p": p,
        "discordant": [b, c],
    }


def main():
    db = sys.argv[1]
    pairs = [a.split(":") for a in sys.argv[2:]]
    cells = [cell_results(db, on, off) for on, off in pairs]
    verdict = {
        "cells": cells,
        "net_effect_gate": (
            "PASS" if sum(1 for c in cells if c["ci_lower_pass"]) >= 3
            else "FAIL"),
        "note": "深档格（4×100）单列加评，不并入 ≥3 格计数（PRD 条款 1）",
    }
    print(json.dumps(verdict, ensure_ascii=False, indent=1))
    out = ROOT / "results" / "t126-gate"
    out.mkdir(parents=True, exist_ok=True)
    (out / "net_effect.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
