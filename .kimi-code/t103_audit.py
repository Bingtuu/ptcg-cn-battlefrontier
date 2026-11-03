"""task 103 — 校准参考面赛制一致性审计（只读；零行为变更）.

门定义见 tasks/task 103.md §3：
  D1 低混因子图（两端连续型）加权 Pearson：≥+0.4 降档 task 102 / ≤+0.2 钉死 / 灰区人工判读
  D2 真实窗半窗稳定性（前半 vs 后半真实格相关）
  D3 审计完整性（脚本复现 + 包 real_wr 与重算一致性）
输出 results/t103-regulation-audit.json。
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = "file:C:/Vibe Project/Pokearena/data/ptcg-cn.db?mode=ro"
PACK = ROOT / "results/m13-baseline/full/deviation.json"
DEV_PACK = ROOT / "results/m13-baseline/development/deviation.json"
OUT = ROOT / "results/t103-regulation-audit.json"

DECKS = {  # sim deck_id -> en archetype（config/target-pool.v2.yml 对齐）
    "mik_moe:676344": "Dragapult Dusknoir",
    "mik_moe:687339": "Grimmsnarl Froslass",
    "mik_moe:678647": "Gardevoir",
    "mik_moe:676249": "Raging Bolt Ogerpon",
    "mik_moe:690359": "N's Zoroark",
    "mik_moe:677868": "Dragapult",
    "mik_moe:689871": "Flareon Noctowl",
    "mik_moe:676151": "Charizard Pidgeot",
    "mik_moe:685310": "Joltik Box",
}
REAL_WIN = ("2025-04-11", "2025-08-31")
HALF_SPLIT = "2025-06-15"
CONTINUOUS_CUTOFF = 0.75
NN = "COALESCE(c.name_en, c.name_full, c.card_id)"


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


def deck_name_slots(con, deck_id) -> Counter:
    rows = con.execute(
        f"SELECT {NN}, dc.count FROM deck_cards dc "
        f"JOIN cards c ON c.card_id = dc.card_id WHERE dc.deck_id = ?",
        (deck_id,),
    ).fetchall()
    return Counter(dict(rows))


def main() -> None:
    con = sqlite3.connect(DB, uri=True)

    # ---- Q2 结构性事实 ----
    pmin, pmax, ptotal = con.execute(
        "SELECT MIN(t.date), MAX(t.date), COUNT(*) FROM pairings p "
        "JOIN tournaments t ON t.tournament_id = p.tournament_id"
    ).fetchone()
    q2 = {"pairings_min": pmin, "pairings_max": pmax, "pairings_total": ptotal,
          "aligned_window_feasible": pmax >= "2026-09-16"}

    # ---- Q1a 卡名级错配度 ----
    name_first = {}
    for nm, rd in con.execute(
        f"SELECT {NN}, MIN(COALESCE(s.release_date,'9999-12-31')) FROM cards c "
        f"LEFT JOIN sets s ON s.set_id = c.set_id GROUP BY {NN}"
    ):
        name_first[nm] = rd
    q1a = {}
    for did, en in DECKS.items():
        slots = deck_name_slots(con, did)
        total = sum(slots.values())
        late = sum(n for nm, n in slots.items() if name_first.get(nm, "9999-12-31") > REAL_WIN[1])
        q1a[en] = {"slots": total, "post_window": late,
                   "post_window_pct": round(late / total, 3)}

    # ---- Q1b 跨窗卡名重合度（vs 真实窗同 archetype 最常见表） ----
    q1b = {}
    for did, en in DECKS.items():
        top = con.execute(
            "SELECT da.deck_id, COUNT(*) n FROM deck_appearances da "
            "JOIN decks d ON d.deck_id = da.deck_id "
            "JOIN tournaments t ON t.tournament_id = da.tournament_id "
            "WHERE d.archetype_name = ? AND t.date BETWEEN ? AND ? "
            "GROUP BY da.deck_id ORDER BY n DESC LIMIT 1",
            (en, REAL_WIN[0], REAL_WIN[1]),
        ).fetchone()
        sim = deck_name_slots(con, did)
        real = deck_name_slots(con, top[0])
        inter = sum(min(sim[k], real[k]) for k in sim.keys() & real.keys())
        q1b[en] = {"real_top_deck": top[0], "real_top_n": top[1],
                   "overlap_slots": inter, "sim_slots": sum(sim.values()),
                   "overlap_pct": round(inter / sum(sim.values()), 3)}

    continuous = sorted([e for e, v in q1b.items() if v["overlap_pct"] >= CONTINUOUS_CUTOFF])
    discontinuous = sorted([e for e in q1b if e not in continuous])

    # ---- Q3 判别式验证 ----
    # 主数据源 = full 包（real 侧覆盖全窗 04-11..08-31；sim 侧与 dev 包 72/72 一致）
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    cells = pack["cells"]

    # 自检：包 real_wr == 本脚本按同口径重算（全部 72 格）
    recompute = {}
    names = list(DECKS.values())
    seq = ",".join("?" * len(names))
    for a, b, w1, w2, ntot in con.execute(
        f"""
        SELECT pp.archetype_name_1 AS a, pp.archetype_name_2 AS b,
               SUM(CASE WHEN pp.winner_side = 1 THEN 1 ELSE 0 END) AS w1,
               SUM(CASE WHEN pp.winner_side = 2 THEN 1 ELSE 0 END) AS w2,
               COUNT(*) AS ntot
        FROM v_pairing_players pp
        JOIN v_tournament_weights t ON t.tournament_id = pp.tournament_id
        WHERE t.date BETWEEN ? AND ?
          AND t.basis = ? AND (t.division = ? OR t.division IS NULL)
          AND pp.winner_side IN (1,2)
          AND pp.archetype_name_1 IN ({seq}) AND pp.archetype_name_2 IN ({seq})
        GROUP BY pp.archetype_name_1, pp.archetype_name_2
        """,
        (REAL_WIN[0], REAL_WIN[1], "intl_aligned", "master") + tuple(names) + tuple(names),
    ):
        if ntot > 0:
            recompute[(a, b)] = w1 / (w1 + w2)

    mismatches = []
    delta_acc = 0.0
    n_acc = 0
    for c in cells:
        key = (c["en_archetype"], c["en_opponent"])
        if key in recompute:
            delta = abs(recompute[key] - c["real_wr"])
            delta_acc += c["real_n"] * delta
            n_acc += c["real_n"]
            if delta > 0.02:
                mismatches.append({"cell": key, "pack": c["real_wr"], "recomputed": recompute[key]})
        else:
            mismatches.append({"cell": key, "pack": c["real_wr"], "recomputed": None})
    # D3：包构建后 db 有数据刷新（v20261025.1），容差 2pts/格；整体按 real_n 加权平均偏差 ≤ 1pt
    d3_weighted_delta = delta_acc / n_acc if n_acc else None
    d3_pass = (d3_weighted_delta is not None and d3_weighted_delta <= 0.01
               and all(m["recomputed"] is not None for m in mismatches))

    # 低混因子图：两端均连续型的有向格
    sub = [c for c in cells
           if c["en_archetype"] in continuous and c["en_opponent"] in continuous]
    s = [c["sim_wr"] for c in sub]
    r = [c["real_wr"] for c in sub]
    n = [c["real_n"] for c in sub]
    d1_pearson = corr(s, r, n) if len(sub) >= 3 else None
    d1_spearman = corr(ranks(s), ranks(r), n) if len(sub) >= 3 else None
    d1_cells = [{"pair": f'{c["en_archetype"]} vs {c["en_opponent"]}',
                 "sim": c["sim_wr"], "real": c["real_wr"], "n": c["real_n"]} for c in sub]

    # 全 72 格基线（复算 task 102 dev 口径）
    s72 = [c["sim_wr"] for c in cells]
    r72 = [c["real_wr"] for c in cells]
    n72 = [c["real_n"] for c in cells]
    base_pearson = corr(s72, r72, n72)

    # D2 半窗稳定性：真实格 WR 前半 vs 后半（72 有向格）
    halves = {}
    for label, lo, hi in (("first", REAL_WIN[0], HALF_SPLIT), ("second", "2025-06-16", REAL_WIN[1])):
        halves[label] = {}
        for a, b, w1, w2 in con.execute(
            f"""
            SELECT pp.archetype_name_1, pp.archetype_name_2,
                   SUM(CASE WHEN pp.winner_side = 1 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN pp.winner_side = 2 THEN 1 ELSE 0 END)
            FROM v_pairing_players pp
            JOIN v_tournament_weights t ON t.tournament_id = pp.tournament_id
            WHERE t.date BETWEEN ? AND ?
              AND t.basis = ? AND (t.division = ? OR t.division IS NULL)
              AND pp.winner_side IN (1,2)
              AND pp.archetype_name_1 <> pp.archetype_name_2
              AND pp.archetype_name_1 IN ({seq}) AND pp.archetype_name_2 IN ({seq})
            GROUP BY pp.archetype_name_1, pp.archetype_name_2
            """,
            (lo, hi, "intl_aligned", "master") + tuple(names) + tuple(names),
        ):
            if w1 + w2 >= 20:
                halves[label][(a, b)] = w1 / (w1 + w2)
    common = sorted(set(halves["first"]) & set(halves["second"]))
    if len(common) >= 10:
        xs = [halves["first"][k] for k in common]
        ys = [halves["second"][k] for k in common]
        # 权重：两半窗合计对局数未知，用无权重相关 + 有向格重数
        w = [1.0] * len(common)
        d2_corr = corr(xs, ys, w)
    else:
        d2_corr = None

    # ---- 判定 ----
    if d1_pearson is None:
        d1 = "gray"
    elif d1_pearson >= 0.4:
        d1 = "confound_explains"
    elif d1_pearson <= 0.2:
        d1 = "zero_signal_robust"
    else:
        d1 = "gray"
    d2 = "stable" if (d2_corr is not None and d2_corr >= 0) else "unstable"

    verdict = {
        "D1_low_confound_subgraph_pearson": None if d1_pearson is None else round(d1_pearson, 3),
        "D1_spearman": None if d1_spearman is None else round(d1_spearman, 3),
        "D1_cells_n": len(sub),
        "D1_cells": d1_cells,
        "D1_ruling": d1,
        "D1_robustness_db_current_pearson": None,  # 填入下方重算
        "baseline_all72_pearson_dev": round(base_pearson, 3),
        "D2_half_window_corr": None if d2_corr is None else round(d2_corr, 3),
        "D2_pairs_n": len(common),
        "D2_ruling": d2,
        "D3_pack_recompute_mismatches_gt2pts": mismatches,
        "D3_weighted_mean_abs_delta": None if d3_weighted_delta is None else round(d3_weighted_delta, 4),
        "D3_pass": d3_pass,
    }

    # 稳健性：D1 用当前 db 重算的 real 值再算一遍（包构建后上游数据有修订）
    sub_cur = []
    for c in sub:
        key = (c["en_archetype"], c["en_opponent"])
        if key in recompute:
            sub_cur.append((c["sim_wr"], recompute[key], c["real_n"]))
    if len(sub_cur) >= 3:
        verdict["D1_robustness_db_current_pearson"] = round(
            corr([x[0] for x in sub_cur], [x[1] for x in sub_cur], [x[2] for x in sub_cur]), 3)

    out = {"task": 103, "q2_structure": q2, "q1a_name_level": q1a, "q1b_overlap": q1b,
           "continuous_archetypes": continuous, "discontinuous_archetypes": discontinuous,
           "verdict": verdict}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
