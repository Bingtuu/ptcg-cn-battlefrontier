"""task 130 演示恢复驱动：筛选档已在三个结果库落盘（2026-11-15 并行开发红窗口——
task 138 DSL 文件中途落地导致确认档 run_group 装载崩溃，屏幕档数据完整有效）。
本脚本只做确认档：从各库 s1 组内嵌 definition_yaml 重建候选 → 按 ΔWR 取 top-3 →
换种子区间（seed_start+5_000_000，与冻结口径一致）跑确认档 → 输出完整搜索报告。
"""

import sys

import yaml

from battlefrontier.data.deck import load_deck
from battlefrontier.report.swap_search import (
    PHASE2_SEED_OFFSET,
    SwapCandidate,
    SwapSearchReport,
    _definition_yaml,
    _make_defn,
    confirm_rows,
    format_swap_search,
    rank_screen,
)
from battlefrontier.report.winrate import winrate_report
from battlefrontier.runner.experiment import SwapCfg, run_group
from battlefrontier.runner.results_db import ResultsDB

DB_PATH = r"C:/Vibe Project/Pokearena/data/ptcg-cn.db"
SEED_START = 470000
CONFIRM_GAMES = 500
CONFIRM_TOP = 3
SEARCHES = [
    ("mik_moe:711874", "mik_moe:711851", "results/t130-swap-search-dragapult.db"),
    ("mik_moe:711874", "mik_moe:692446", "results/t130-swap-search-grimmsnarl.db"),
    ("mik_moe:711874", "mik_moe:677291", "results/t130-swap-search-joltik.db"),
]
WORKERS = 7


def rebuild_candidates(defn_yaml: str, deck) -> list[SwapCandidate]:
    """从组内嵌定义重建 SwapCandidate（out 卡从基线卡组按名取印刷，in 卡按 in_id）。"""
    raw = yaml.safe_load(defn_yaml)
    by_name = {}
    for c in deck:
        by_name.setdefault(c.name, c)
    out = []
    for v in raw["variants"]:
        s = v["swaps"][0]
        swap = SwapCfg(**s)
        from ptcgdb.sdk import open_db

        from battlefrontier.data.cards import carddef_from_db

        db = open_db(DB_PATH)
        try:
            in_def, _ = carddef_from_db(db.get_card(swap.in_id))
        finally:
            db.close()
        out.append(SwapCandidate(out_card=by_name[swap.out], in_card=in_def, swap=swap))
    return out


def emit_report_only(deck_id, vs_id, results_path):
    """确认档已落库时只重发报告（不改任何实验数据）。"""
    db = ResultsDB(results_path)
    try:
        s1 = [r[0] for r in db._conn.execute(
            "SELECT id FROM experiments WHERE group_name LIKE '%-s1' ORDER BY id")]
        s2 = [r[0] for r in db._conn.execute(
            "SELECT id FROM experiments WHERE group_name LIKE '%-s2' ORDER BY id")]
        defn_yaml = db.experiment(s1[0])["definition_yaml"]
    finally:
        db.close()

    deck = load_deck(DB_PATH, deck_id).cards
    candidates = rebuild_candidates(defn_yaml, deck)
    db = ResultsDB(results_path)
    try:
        base1 = winrate_report(db, s1[0])
        reps1 = [(cand, vid, winrate_report(db, vid))
                 for cand, vid in zip(candidates, s1[1:], strict=True)]
        base2 = winrate_report(db, s2[0])
        top_cands = [r.candidate for r in rank_screen(base1, reps1)[:CONFIRM_TOP]]
        reps2 = [(cand, vid, winrate_report(db, vid))
                 for cand, vid in zip(top_cands, s2[1:], strict=True)]
    finally:
        db.close()

    from collections import Counter

    from battlefrontier.report.swap_search import PhasePlan

    rep = SwapSearchReport(
        deck_id=deck_id, vs_id=vs_id, budget=80000, seed_start=SEED_START,
        plan=PhasePlan(screen_games=base1.games_total,
                       confirm_games=CONFIRM_GAMES, confirm_top=CONFIRM_TOP),
        candidates=candidates, drop_reasons=Counter(), warnings=[],
        screen_ids=s1, screen_rows=rank_screen(base1, reps1),
        confirm_ids=s2, confirm=confirm_rows(base2, reps2),
        results_path=results_path, soft_warnings=[])
    print(format_swap_search(rep))


def resume_one(deck_id, vs_id, results_path):
    db = ResultsDB(results_path)
    try:
        s1 = [(r[0], r[1]) for r in db._conn.execute(
            "SELECT id, definition_yaml FROM experiments"
            " WHERE group_name LIKE '%-s1' ORDER BY id").fetchall()]
        screen_ids = [r[0] for r in s1]
        defn_yaml = s1[0][1]
    finally:
        db.close()

    deck = load_deck(DB_PATH, deck_id).cards
    candidates = rebuild_candidates(defn_yaml, deck)

    db = ResultsDB(results_path)
    try:
        base1 = winrate_report(db, screen_ids[0])
        reps1 = [(cand, vid, winrate_report(db, vid))
                 for cand, vid in zip(candidates, screen_ids[1:], strict=True)]
    finally:
        db.close()
    rows = rank_screen(base1, reps1)
    top_cands = [r.candidate for r in rows[:CONFIRM_TOP]]

    name = yaml.safe_load(defn_yaml)["name"][:-3]  # 去 -s1
    seed2 = SEED_START + PHASE2_SEED_OFFSET
    defn2 = _make_defn(f"{name}-s2", deck_id, vs_id,
                       CONFIRM_GAMES, seed2, top_cands, "heuristic")
    confirm_ids, ws2 = run_group(defn2, DB_PATH, results_path, workers=WORKERS,
                                 cards_dir="cards",
                                 definition_yaml=_definition_yaml(defn2))
    if ws2:
        print(f"[装载告警 s2] {ws2}")

    db = ResultsDB(results_path)
    try:
        base2 = winrate_report(db, confirm_ids[0])
        reps2 = [(cand, vid, winrate_report(db, vid))
                 for cand, vid in zip(top_cands, confirm_ids[1:], strict=True)]
    finally:
        db.close()
    conf = confirm_rows(base2, reps2)

    # 从原 defn 重建报告骨架（drop reason/软告警以确认档时刻重算近似——
    # 筛选档判定早已固化，这里只补齐展示字段）
    from collections import Counter

    from battlefrontier.report.swap_search import PhasePlan

    rep = SwapSearchReport(
        deck_id=deck_id, vs_id=vs_id, budget=80000, seed_start=SEED_START,
        plan=PhasePlan(screen_games=base1.games_total,
                       confirm_games=CONFIRM_GAMES, confirm_top=CONFIRM_TOP),
        candidates=candidates, drop_reasons=Counter(), warnings=[],
        screen_ids=screen_ids, screen_rows=rows, confirm_ids=confirm_ids,
        confirm=conf, results_path=results_path, soft_warnings=[])
    print(format_swap_search(rep))
    print(f"\n[resume] {vs_id} 确认档完成：实验 id {confirm_ids}")


if __name__ == "__main__":
    targets = sys.argv[1:] or [s[1] for s in SEARCHES]
    report_only = "report-only" in targets
    if report_only:
        targets.remove("report-only")
    for deck_id, vs_id, path in SEARCHES:
        if vs_id in targets or path in targets or report_only:
            if report_only:
                emit_report_only(deck_id, vs_id, path)
            else:
                resume_one(deck_id, vs_id, path)
