"""task 109 M12 残留盲区诊断预检（只读；预注册见 tasks/task 109.md）。

三个盲区 kind：use_ability / play_stadium / end_turn。双证据流：
- Stream A（m14-mcts 库）：教师以 margin >=10（chosen_visits - max(其他行动 visits)）
  选择 K 行动的点；覆盖局数、点作者方胜率 vs 全库基线（lift）。
- Stream B（m14-heuristic 对照库）：K 类事件（use_ability/play_stadium/end_turn
  kind 计数）每局利用率，教师侧用 mcts_consider chosen=K 计数；冷落 = 启发式 <
  教师 1/3。
预注册判定门：A >=15 局 且 lift >= +10pp 且 B 冷落成立 -> 有实证（开修复 task）；
任一不过 -> 关闭定性（A 不过=教师信号噪声主导；B 不过=kind 上限问题）。

用法：PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 .kimi-code/t109_blindspot_precheck.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIRS = ["drag-zoro", "drag-joltik", "char-grim"]
KINDS = ["use_ability", "play_stadium", "end_turn"]
MARGIN = 10
GATE_GAMES = 15
GATE_LIFT = 10.0
GATE_NEGLECT = 1.0 / 3.0

# 事件 kind 与 mcts_consider chosen kind 同名直接对应；margin = chosen_visits
# − max(其他行动 visits)（task 099 口径，>=10 才算教师强信号）


def main() -> int:
    out = {"kinds": {}, "pairs": PAIRS, "gates": {
        "margin": MARGIN, "games": GATE_GAMES,
        "lift_pp": GATE_LIFT, "neglect_ratio": GATE_NEGLECT,
    }}
    for k in KINDS:
        out["kinds"][k] = {"A": {}, "B": {}, "verdict": None, "samples": []}

    # ── Stream A：教师强信号（mcts 库）───────────────────────────────
    for pair in PAIRS:
        db_path = ROOT / f"results/m14-{pair}-mcts.db"
        con = sqlite3.connect(db_path)
        seed_of = dict(con.execute("SELECT id, seed FROM games").fetchall())
        result_of = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT id, winner, is_draw FROM games").fetchall()}
        rows = con.execute(
            "SELECT game_id, event_json FROM game_events "
            "WHERE event_json LIKE '%mcts_consider%'").fetchall()
        con.close()
        # 基线：含任意 consider 点的局，点作者方胜率（按点计）
        base_pts = 0
        base_wins = 0
        strong = defaultdict(list)  # kind -> [(seed, player, turn, chosen, margin)]
        for gid, j in rows:
            d = json.loads(j)
            det = d["detail"]
            winner, is_draw = result_of[gid]
            if is_draw or winner is None:
                continue
            maker_win = 1 if winner == d["player"] else 0
            base_pts += 1
            base_wins += maker_win
            considered = det.get("considered", [])
            other = [c["visits"] for c in considered
                     if c["action"] != det["chosen"]]
            margin = det["chosen_visits"] - (max(other) if other else 0)
            kind = det.get("kind") or det["chosen"].split("：")[0]
            if margin >= MARGIN and kind in KINDS:
                strong[kind].append({
                    "pair": pair, "seed": seed_of[gid], "player": d["player"],
                    "turn": d["turn"], "chosen": det["chosen"],
                    "chosen_visits": det["chosen_visits"], "margin": margin,
                    "maker_win": maker_win,
                })
        base_rate = 100.0 * base_wins / max(base_pts, 1)
        for k in KINDS:
            a = out["kinds"][k]["A"].setdefault(pair, {})
            pts = strong[k]
            games_hit = len({(p["seed"], p["player"]) for p in pts})
            games_any = len({(seed_of[g], pl) for g, _ in rows
                             for pl in (0, 1)})
            wins = sum(p["maker_win"] for p in pts)
            rate = 100.0 * wins / len(pts) if pts else 0.0
            a.update({
                "strong_points": len(pts),
                "maker_games": games_hit,
                "maker_winrate": round(rate, 1),
                "baseline_winrate": round(base_rate, 1),
                "lift_pp": round(rate - base_rate, 1),
            })
            out["kinds"][k]["samples"].extend(pts[:8])

    # ── Stream B：启发式冷落度 ────────────────────────────────────────
    for k in KINDS:
        b = out["kinds"][k]["B"]
        for pair in PAIRS:
            hdb = ROOT / f"results/m14-{pair}-heuristic.db"
            mdb = ROOT / f"results/m14-{pair}-mcts.db"
            con = sqlite3.connect(hdb)
            h_games = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
            h_cnt = con.execute(
                "SELECT COUNT(*) FROM game_events WHERE event_json LIKE ?",
                (f'%"kind": "{k}"%',)).fetchone()[0]
            con.close()
            con = sqlite3.connect(mdb)
            m_games = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
            m_cnt = 0
            for (j,) in con.execute(
                "SELECT event_json FROM game_events "
                "WHERE event_json LIKE '%mcts_consider%'"
            ):
                d = json.loads(j)
                det = d["detail"]
                kind = det.get("kind") or det["chosen"].split("：")[0]
                if kind == k:
                    m_cnt += 1
            con.close()
            b[pair] = {
                "heuristic_per_game": round(h_cnt / max(h_games, 1), 3),
                "teacher_per_game": round(m_cnt / max(m_games, 1), 3),
                "ratio": round((h_cnt / max(h_games, 1))
                               / max(m_cnt / max(m_games, 1), 1e-9), 3),
            }

    # ── 预注册判定 ────────────────────────────────────────────────────
    for k in KINDS:
        agg = out["kinds"][k]
        tot_games = sum(p["maker_games"] for p in agg["A"].values())
        # lift 用总点数的加权胜率
        tot_pts = sum(p["strong_points"] for p in agg["A"].values())
        tot_wins = sum(
            round(p["maker_winrate"] / 100 * p["strong_points"])
            for p in agg["A"].values())
        rate = 100.0 * tot_wins / tot_pts if tot_pts else 0.0
        base = sum(p["baseline_winrate"] * p["strong_points"]
                   for p in agg["A"].values()) / tot_pts if tot_pts else 0.0
        lift = rate - base
        neglects = [p["ratio"] for p in agg["B"].values()]
        neglect_ok = bool(neglects) and all(r < GATE_NEGLECT for r in neglects)
        a_ok = tot_games >= GATE_GAMES and lift >= GATE_LIFT
        if a_ok and neglect_ok:
            verdict = "EVIDENCE"
        elif not a_ok:
            verdict = "CLOSE_noise_dominated"
        else:
            verdict = "CLOSE_kind_ceiling"
        agg["verdict"] = verdict
        agg["totals"] = {
            "strong_points": tot_pts, "maker_games": tot_games,
            "maker_winrate": round(rate, 1), "lift_pp": round(lift, 1),
            "neglect_ratios": [round(r, 3) for r in neglects],
        }

    out_path = ROOT / "results/t109-blindspot-precheck.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(json.dumps({k: v["verdict"] for k, v in out["kinds"].items()},
                     ensure_ascii=False, indent=1))
    for k in KINDS:
        print(k, json.dumps(out["kinds"][k]["totals"], ensure_ascii=False))
    print(f"-> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
