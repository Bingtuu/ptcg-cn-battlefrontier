"""task 105 — 对齐窗重验自动管道（只读；三态 WAIT/EXPLORATORY/RUN）.

协议见 tasks/task 105.md；RUN 门槛经 task 110 修订为可达子池口径：
  判定池 = 9 池构筑中在该对齐窗有 >=1 非镜像对局者（每次运行动态重取）
  K = C(|判定池|, 2)；RUN 门 = qualified >= min(26, ceil(0.85*K)) 且池内对局 >=1000
  RUN 态：加权 Pearson（权重 real_n）+ 无向格对 bootstrap 10k；CI 下界>0 → R1 复活；
          CI 含 0/上界<0 → R2 钉死；10 <= qualified < 门 → EXPLORATORY 只报点估计。
输出 results/t105-aligned-recheck.json。
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = "file:C:/Vibe Project/Pokearena/data/ptcg-cn.db?mode=ro"
PACK = ROOT / "results/m13-baseline/full/deviation.json"
UPSTREAM_MANIFEST = Path("C:/Vibe Project/Pokearena/dist/manifest.json")
OUT = ROOT / "results/t105-aligned-recheck.json"
HISTORY = ROOT / "results/t105-sentinel-history.jsonl"
BOOT = 10_000


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def emit(state: dict) -> None:
    """写当前状态 JSON + append-only 历史行（周检增量对比基座）。"""
    text = json.dumps(state, ensure_ascii=False, indent=1)
    OUT.write_text(text, encoding="utf-8")
    line = {"checked_at": state.get("checked_at"), "state": state.get("state"),
            "pool_games": state["census"]["pool_games"],
            "pairs_n_ge_20": state["census"]["pairs_n_ge_20"],
            "upstream_version": state["upstream"].get("version"),
            "upstream_data_version": state["upstream"].get("data_version")}
    if state.get("state") == "RUN":
        line["ruling"] = state["verdict"]["ruling"]
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(text)

POOL = ["Dragapult Dusknoir", "Grimmsnarl Froslass", "Gardevoir", "Raging Bolt Ogerpon",
        "N's Zoroark", "Dragapult", "Flareon Noctowl", "Charizard Pidgeot", "Joltik Box"]
WINDOW_LO = "2026-09-16"
RUN_MIN_GAMES = 1000
ORIGINAL_RUN_MIN_PAIRS = 26  # task 105 原门；task 110 起仅作上限
PAIR_MIN_N = 20
GATE_COVER = 0.85  # task 110 冻结常数：覆盖可达 meta 的绝大多数交叉格


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

    # task 110：判定池 = 窗内有非镜像出场的池构筑；门 = min(26, ceil(0.85*K))
    active_pool = sorted({a for a, _ in real} | {b for _, b in real})
    k_reachable = len(active_pool) * (len(active_pool) - 1) // 2
    run_gate = min(ORIGINAL_RUN_MIN_PAIRS, math.ceil(GATE_COVER * k_reachable))

    manifest = {}
    if UPSTREAM_MANIFEST.exists():
        m = json.loads(UPSTREAM_MANIFEST.read_text(encoding="utf-8"))
        manifest = {"version": m.get("version"), "data_version": m.get("data_version"),
                    "built_at": m.get("built_at")}

    state = {"task": 105, "checked_at": _now(), "window_from": WINDOW_LO, "upstream": manifest,
             "census": {"pool_games": total,
                        "pairs_with_games": sum(1 for p in pairs if p["n"] > 0),
                        "pairs_n_ge_20": len(qualified),
                        "max_pair_n": max((p["n"] for p in pairs), default=0),
                        "active_pool": active_pool,
                        "reachable_pairs": k_reachable,
                        "run_gate": run_gate}}

    if len(qualified) < 10:
        state["state"] = "WAIT"
        state["note"] = (f"功效不足：{len(qualified)} 格 n>=20"
                         f"（需 >={run_gate} 对且总对局 >={RUN_MIN_GAMES}，"
                         f"task 110 可达子池门）")
        emit(state)
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

    if len(qualified) < run_gate or total < RUN_MIN_GAMES:
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
    emit(state)


if __name__ == "__main__":
    main()
