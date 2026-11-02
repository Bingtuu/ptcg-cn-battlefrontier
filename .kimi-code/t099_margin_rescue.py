# task 099 遗留分析（只读）：margin 过滤后 task 098 候选的存活检查 + G2 方向评估。
# 用法：PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 .kimi-code/t099_margin_rescue.py

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = "use_ability：多龙奇"
TURN_MAX = 3
MARGIN_MIN = 10

BATCHES = {
    "z1": ("results/m14-drag-zoro-mcts.db", "results/m14-drag-zoro-heuristic.db"),
    "z2": ("results/m14-drag-zoro-confirm-mcts.db",
           "results/m14-drag-zoro-confirm-heuristic.db"),
    "j1": ("results/m14-drag-joltik-mcts.db", "results/m14-drag-joltik-heuristic.db"),
    "j2": ("results/m14-drag-joltik-confirm-mcts.db",
           "results/m14-drag-joltik-confirm-heuristic.db"),
}


def outcomes(db_file: str) -> dict[int, int]:
    """seed → A 侧结局（+1 胜 / 0 平 / −1 负）。"""
    con = sqlite3.connect(ROOT / db_file)
    out = {}
    for seed, winner, draw in con.execute(
            "SELECT seed, winner, is_draw FROM games WHERE experiment_id=1"):
        if draw:
            out[seed] = 0
        else:
            out[seed] = 1 if winner == 0 else -1
    con.close()
    return out


def early_points(db_file: str) -> list[dict]:
    """MCTS 库：player 0 主线决策点中「可用多龙奇特性」的点。"""
    con = sqlite3.connect(ROOT / db_file)
    con.row_factory = sqlite3.Row
    pts = []
    for (ej,) in con.execute(
            "SELECT event_json FROM game_events WHERE json_extract(event_json,'$.kind')='mcts_consider'"):
        d = json.loads(ej)
        if d.get("player") != 0:
            continue
        turn = int(d.get("turn") or 0)
        if not (1 <= turn <= TURN_MAX):
            continue
        det = d.get("detail") or {}
        cons = det.get("considered") or []
        if not any(c.get("action") == TARGET for c in cons):
            continue
        chosen = det.get("chosen")
        cv = det.get("chosen_visits") or 0
        others = [int(c.get("visits") or 0) for c in cons if c.get("action") != chosen]
        margin = cv - max(others) if others else cv
        pts.append({"turn": turn, "used": chosen == TARGET, "margin": margin})
    con.close()
    return pts


def early_use_seeds_by_game(db_file: str) -> set[int]:
    """任意库：player 0 在 turn≤3 实际用过多龙奇特性的种子集合（game 级扫描）。"""
    con = sqlite3.connect(ROOT / db_file)
    con.row_factory = sqlite3.Row
    seeds = set()
    for r in con.execute("SELECT id, seed FROM games WHERE experiment_id=1"):
        hit = con.execute(
            "SELECT 1 FROM game_events WHERE game_id=? AND "
            "json_extract(event_json,'$.kind')='use_ability' AND "
            "json_extract(event_json,'$.player')=0 AND "
            "json_extract(event_json,'$.detail.name')='多龙奇' AND "
            "json_extract(event_json,'$.turn') BETWEEN 1 AND ? LIMIT 1",
            (r["id"], TURN_MAX)).fetchone()
        if hit:
            seeds.add(r["seed"])
    con.close()
    return seeds


def ci95(vals: list[float]) -> tuple[float, float, float]:
    import math

    n = len(vals)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = sum(vals) / n
    if n < 2:
        return mean, mean, mean
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    half = 1.96 * math.sqrt(var / n)
    return mean, mean - half, mean + half


def main() -> int:
    print(f"margin 过滤阈 = {MARGIN_MIN}；早期 = turn 1-{TURN_MAX}；目标 = {TARGET}\n")
    for label, (mcts_db, heur_db) in BATCHES.items():
        pts = early_points(mcts_db)
        if not pts:
            print(f"{label}: 无 player0 早期可用点\n")
            continue
        dec = [p for p in pts if p["margin"] >= MARGIN_MIN]
        n_used = sum(1 for p in pts if p["used"])
        d_used = sum(1 for p in dec if p["used"])
        print(f"{label}: 可用点 {len(pts)}（决断点 margin≥{MARGIN_MIN}: {len(dec)}）")
        print(f"  全部点使用率 {n_used}/{len(pts)} = {n_used/len(pts):.1%}；"
              f"决断点使用率 {d_used}/{len(dec)} = "
              f"{d_used/len(dec) if dec else 0:.1%}")

        # 逐种子 CRN：MCTS A 侧结局 − 启发式 A 侧结局，限制在 MCTS 有早期可用的种子
        om, oh = outcomes(mcts_db), outcomes(heur_db)
        # MCTS 侧哪些种子有早期可用点：需要 seed 关联点——重扫一次带 seed
        con = sqlite3.connect(ROOT / mcts_db)
        con.row_factory = sqlite3.Row
        seeds_with_pts: dict[int, list[dict]] = {}
        for r in con.execute(
                "SELECT g.seed, e.event_json FROM games g JOIN game_events e ON e.game_id=g.id "
                "WHERE g.experiment_id=1 AND json_extract(e.event_json,'$.kind')='mcts_consider'"):
            d = json.loads(r["event_json"])
            if d.get("player") != 0 or not (1 <= int(d.get("turn") or 0) <= TURN_MAX):
                continue
            det = d.get("detail") or {}
            cons = det.get("considered") or []
            if not any(c.get("action") == TARGET for c in cons):
                continue
            chosen = det.get("chosen")
            cv = det.get("chosen_visits") or 0
            others = [int(c.get("visits") or 0) for c in cons if c.get("action") != chosen]
            seeds_with_pts.setdefault(r["seed"], []).append({
                "used": chosen == TARGET, "margin": cv - (max(others) if others else 0)})
        con.close()
        mcts_used = early_use_seeds_by_game(mcts_db)
        heur_used = early_use_seeds_by_game(heur_db)

        def effect(pred, om_, oh_, swp) -> tuple:
            diffs = [om_[s] - oh_[s] for s in swp if s in om_ and s in oh_
                     and pred(swp[s])]
            return (len(diffs), *ci95([float(x) for x in diffs]))

        e_all = effect(lambda _: True, om, oh, seeds_with_pts)
        e_used = effect(lambda l: any(p["used"] for p in l), om, oh, seeds_with_pts)
        e_not = effect(lambda l: not any(p["used"] for p in l), om, oh, seeds_with_pts)
        e_dused = effect(
            lambda l: any(p["used"] and p["margin"] >= MARGIN_MIN for p in l),
            om, oh, seeds_with_pts)
        # MCTS 库内部：用/不用特性种子的 A 侧纯结局（剔除 MCTS-vs-启发式全局差）
        m_used = [float(om[s]) for s in seeds_with_pts if s in om
                  and any(p["used"] for p in seeds_with_pts[s])]
        m_not = [float(om[s]) for s in seeds_with_pts if s in om
                 and not any(p["used"] for p in seeds_with_pts[s])]
        m_dec = [float(om[s]) for s in seeds_with_pts if s in om
                 and any(p["used"] and p["margin"] >= MARGIN_MIN
                         for p in seeds_with_pts[s])]
        print(f"  逐种子 CRN（MCTS−启发式，A 侧）：全可用种子 n={e_all[0]} "
              f"mean={e_all[1]:+.3f} CI[{e_all[2]:+.3f},{e_all[3]:+.3f}]")
        print(f"    MCTS 用过特性种子: n={e_used[0]} mean={e_used[1]:+.3f} "
              f"CI[{e_used[2]:+.3f},{e_used[3]:+.3f}]")
        print(f"    MCTS 未用特性种子: n={e_not[0]} mean={e_not[1]:+.3f} "
              f"CI[{e_not[2]:+.3f},{e_not[3]:+.3f}]")
        print(f"    MCTS 决断使用(margin≥{MARGIN_MIN})种子: n={e_dused[0]} "
              f"mean={e_dused[1]:+.3f} CI[{e_dused[2]:+.3f},{e_dused[3]:+.3f}]")
        mu = ci95(m_used) if m_used else (0, 0, 0)
        mn = ci95(m_not) if m_not else (0, 0, 0)
        md = ci95(m_dec) if m_dec else (0, 0, 0)
        print(f"  MCTS 库内 A 侧结局：用特性 n={len(m_used)} mean={mu[0]:+.3f} "
              f"CI[{mu[1]:+.3f},{mu[2]:+.3f}] | 未用 n={len(m_not)} mean={mn[0]:+.3f} "
              f"CI[{mn[1]:+.3f},{mn[2]:+.3f}] | 决断用 n={len(m_dec)} mean={md[0]:+.3f} "
              f"CI[{md[1]:+.3f},{md[2]:+.3f}]")
        denom = [s for s in seeds_with_pts if s in oh]
        n_seeds = len(denom)
        print(f"  每局早用率（分母=有可用点的 {n_seeds} 种子）："
              f"MCTS {len(mcts_used & set(denom))}/{n_seeds} = "
              f"{len(mcts_used & set(denom)) / max(n_seeds, 1):.1%} vs "
              f"启发式 {len(heur_used & set(denom))}/{n_seeds} = "
              f"{len(heur_used & set(denom)) / max(n_seeds, 1):.1%}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
