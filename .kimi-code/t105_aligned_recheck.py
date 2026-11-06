"""task 105 — 对齐窗重验自动管道（只读；三态 WAIT/EXPLORATORY/RUN）.

协议见 tasks/task 105.md：
  RUN 门槛：池内对局 >=1000 且 >=26 无向格 n>=20
  RUN 态：加权 Pearson（权重 real_n）+ 无向格对 bootstrap 10k；CI 下界>0 → R1 复活；
          CI 含 0/上界<0 → R2 钉死；格数 10–25 → EXPLORATORY 只报点估计。
输出 results/t105-aligned-recheck.json。
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = "file:C:/Vibe Project/Pokearena/data/ptcg-cn.db?mode=ro"
PACK = ROOT / "results/m13-baseline/full/deviation.json"
UPSTREAM_MANIFEST = Path("C:/Vibe Project/Pokearena/dist/manifest.json")
OUT = ROOT / "results/t105-aligned-recheck.json"
BOOT = 10_000

POOL = ["Dragapult Dusknoir", "Grimmsnarl Froslass", "Gardevoir", "Raging Bolt Ogerpon",
        "N's Zoroark", "Dragapult", "Flareon Noctowl", "Charizard Pidgeot", "Joltik Box"]
WINDOW_LO = "2026-09-16"
RUN_MIN_GAMES = 1000
RUN_MIN_PAIRS = 26
PAIR_MIN_N = 20


def corr(xs, ys, w) -> float:
    sw = sum(w)
    mx = sum(a * b for a, b in zip(w, xs)) / sw
    my = sum(a * b for a, b in zip(w, ys)) / sw
    cov = sum(wi * (x - mx) * (y - my) for wi, x, y in zip(w, xs, ys))
    vx = sum(wi * (x - mx) ** 2 for wi, x in zip(w, xs))
    vy = sum(wi * (y - my) ** 2 for wi, y in zip(w, ys))
    return cov / math.sqrt(vx * vy)


def aligned_cells(con) -> dict[tuple[str, str], tuple[float, int]]:
    """对齐窗有向格真实 (wr, decided_n)；口径同 pairings.py。"""
    seq = ",".join("?" * len(POOL))
    cells = {}
    for a, b, w1, w2 in con.execute(
        f"""
        SELECT pp.archetype_name_1, pp.archetype_name_2,
               SUM(CASE WHEN pp.winner_side = 1 THEN 1 ELSE 0 END),
               SUM(CASE WHEN pp.winner_side = 2 THEN 1 ELSE 0 END)
        FROM v_pairing_players pp
        JOIN v_tournament_weights t ON t.tournament_id = pp.tournament_id
        WHERE t.date >= ? AND t.basis = 'intl_aligned'
          AND (t.division = 'master' OR t.division IS NULL)
          AND pp.winner_side IN (1,2)
          AND pp.archetype_name_1 <> pp.archetype_name_2
          AND pp.archetype_name_1 IN ({seq}) AND pp.archetype_name_2 IN ({seq})
        GROUP BY pp.archetype_name_1, pp.archetype_name_2
        """,
        (WINDOW_LO,) + tuple(POOL) + tuple(POOL),
    ):
        n = w1 + w2
        if n > 0:
            cells[(a, b)] = (w1 / n, n)
    return cells


def main() -> None:
    con = sqlite3.connect(DB, uri=True)
    real = aligned_cells(con)
    con.close()

    pack = json.loads(PACK.read_text(encoding="utf-8"))
    sim = {(c["en_archetype"], c["en_opponent"]): c["sim_wr"] for c in pack["cells"]}

    # 无向格对抽样框（36 对全进框，含 0 局对）
    pairs = []
    for i, a in enumerate(POOL):
        for b in POOL[i + 1:]:
            cells = []
            for x, y in ((a, b), (b, a)):
                if (x, y) in real:
                    wr, n = real[(x, y)]
                    cells.append({"dir": f"{x} vs {y}", "sim": sim[(x, y)],
                                  "real": wr, "n": n})
            pairs.append({"pair": f"{a} × {b}", "cells": cells,
                          "n": sum(c["n"] for c in cells)})
    total = sum(p["n"] for p in pairs)
    qualified = [p for p in pairs if p["n"] >= PAIR_MIN_N]

    manifest = {}
    if UPSTREAM_MANIFEST.exists():
        m = json.loads(UPSTREAM_MANIFEST.read_text(encoding="utf-8"))
        manifest = {"version": m.get("version"), "data_version": m.get("data_version"),
                    "built_at": m.get("built_at")}

    state = {"task": 105, "window_from": WINDOW_LO, "upstream": manifest,
             "census": {"pool_games": total,
                        "pairs_with_games": sum(1 for p in pairs if p["n"] > 0),
                        "pairs_n_ge_20": len(qualified),
                        "max_pair_n": max((p["n"] for p in pairs), default=0)}}

    if len(qualified) < 10:
        state["state"] = "WAIT"
        state["note"] = f"功效不足：{len(qualified)} 格 n>=20（需 >=26 且总对局 >=1000）"
        OUT.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(state, ensure_ascii=False, indent=1))
        return

    # 有效有向格：n>=20 且非退化（0/1 只在 n<20 时剔除，此处 n>=20 故保留端点）
    flat = [c for p in pairs for c in p["cells"] if c["n"] >= PAIR_MIN_N]
    dropped = [c for p in pairs for c in p["cells"] if 0 < c["n"] < PAIR_MIN_N]

    def pearson_on(cells) -> float | None:
        if len(cells) < 5:
            return None
        return corr([c["sim"] for c in cells], [c["real"] for c in cells],
                    [c["n"] for c in cells])

    point = pearson_on(flat)
    rng = random.Random(10500)
    boots = []
    for _ in range(BOOT):
        idx = [rng.randrange(len(pairs)) for _ in range(len(pairs))]
        sample = [c for i in idx for c in pairs[i]["cells"] if c["n"] >= PAIR_MIN_N]
        v = pearson_on(sample)
        boots.append(v if v is not None else 0.0)
    boots.sort()
    lo = boots[int(0.025 * BOOT)]
    hi = boots[int(0.975 * BOOT)]

    wmad = (sum(c["n"] * abs(c["sim"] - c["real"]) for c in flat)
            / sum(c["n"] for c in flat))

    if len(qualified) < RUN_MIN_PAIRS or total < RUN_MIN_GAMES:
        state["state"] = "EXPLORATORY"
        state["primary"] = {"pearson": None if point is None else round(point, 3),
                            "ci95": [round(lo, 3), round(hi, 3)],
                            "cells_n": len(flat),
                            "weighted_mad": round(wmad, 4)}
        state["note"] = "格数 10–25 或总对局 <1000：只报点估计，不出判决（R3）"
    else:
        if lo > 0:
            ruling = "R1_revive"
        else:
            ruling = "R2_nail"
        state["state"] = "RUN"
        state["verdict"] = {
            "ruling": ruling,
            "primary_pearson": None if point is None else round(point, 3),
            "ci95": [round(lo, 3), round(hi, 3)],
            "cells_n": len(flat),
            "weighted_mad_pct": round(wmad * 100, 2),
            "dropped_small_cells": dropped,
            "per_cell": flat,
        }
    OUT.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
