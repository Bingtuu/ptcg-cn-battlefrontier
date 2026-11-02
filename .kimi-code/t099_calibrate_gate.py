# task 099 标定脚本（预注册见 tasks/task 099.md）：
# 多龙奇「侦察指令」选择步（拿/不拿）阈值标定。
# 三阶段：z1 拟合 → z2 内嵌验证（一致率 ≥70% 且每规则命中 ≥20）→ 输出钉死参数。
# 用法：PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 .kimi-code/t099_calibrate_gate.py

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battlefrontier.agent.heuristic import HeuristicParams, pokemon_score
from battlefrontier.data.deck import load_deck
from battlefrontier.engine.state import CardInstance, Supertype
from battlefrontier.runner.experiment import load_db_path

DB_PATH = load_db_path()
DECK_A = "mik_moe:677868"  # 多龙侧（task 098 的 A 侧）
DECK_B = "mik_moe:690359"

Z1 = ROOT / "results/m14-drag-zoro-mcts.db"
Z2 = ROOT / "results/m14-drag-zoro-confirm-mcts.db"

GRID_V_JUNK = (0.5, 1.0, 1.5, 2.0)
GRID_V_KEY = (2.0, 3.0, 4.0, 5.0)
GRID_DEEP = (20, 25, 30)
GRID_SHALLOW = (10, 15, 20)
AGREE_MIN = 0.70
SUPPORT_MIN = 20


def card_score_cache() -> dict[str, float]:
    """卡名 → keep 评分（能量 1.0 / 训练家 0.5 / 宝可梦 pokemon_score）。

    优先用两副目标卡组内的 CardDef（同名多印刷取先见）；查不到回退 search_cards。
    """
    params = HeuristicParams()
    cache: dict[str, float] = {}

    def add(card_def, source: str) -> None:
        name = getattr(card_def, "name", None) or getattr(card_def, "name_group", None)
        if not name or name in cache:
            return
        if card_def.supertype == Supertype.ENERGY:
            cache[name] = 1.0
        elif card_def.supertype == Supertype.TRAINER:
            cache[name] = 0.5
        else:
            cache[name] = pokemon_score(CardInstance(iid=0, card=card_def), params)
        cache[name + "@src"] = source

    for deck_id in (DECK_A, DECK_B):
        for cd in load_deck(DB_PATH, deck_id).cards:
            add(cd, deck_id)
    return cache


def resolve_score(name: str, cache: dict[str, float]) -> float | None:
    if name in cache:
        return cache[name]
    from ptcgdb.sdk import open_db

    db = open_db(DB_PATH)
    try:
        hits = db.search_cards(name=name)
    finally:
        db.close()
    if not hits:
        return None
    from battlefrontier.data.cards import carddef_from_db

    cd, _ = carddef_from_db(hits[0])
    params = HeuristicParams()
    if cd.supertype == Supertype.ENERGY:
        score = 1.0
    elif cd.supertype == Supertype.TRAINER:
        score = 0.5
    else:
        score = pokemon_score(CardInstance(iid=0, card=cd), params)
    cache[name] = score
    cache[name + "@src"] = "search_cards"
    return score


def extract_points(db_file: Path, cache: dict[str, float]) -> list[dict]:
    """从 MCTS 结果库提取多龙奇选择步样本。

    每个样本：turn、deck_count（重近似：60 − 6 奖赏 − 7 起手 − 抽牌 − 检索拿取
    + 手回牌库底）、两张顶牌名与评分、MCTS 决策（pass/take）、拿走卡名。
    """
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    samples: list[dict] = []
    misses = 0
    games = con.execute(
        "SELECT id FROM games WHERE error IS NULL OR error=''").fetchall()
    for (gid,) in games:
        deck = {0: 60 - 6 - 7, 1: 60 - 6 - 7}
        events = con.execute(
            "SELECT seq, event_json FROM game_events WHERE game_id=? ORDER BY seq",
            (gid,)).fetchall()
        for row in events:
            d = json.loads(row["event_json"])
            kind = d.get("kind")
            det = d.get("detail") or {}
            player = d.get("player")
            # ── 牌库余量记账（近似，见 docstring）──
            if kind == "effect_primitive":
                act = det.get("action")
                res = det.get("result") or {}
                if act == "draw" and player in deck:
                    deck[player] -= int(res.get("drawn") or 0)
                elif act == "search_deck" and player in deck:
                    deck[player] -= int(res.get("found") or 0)
                elif act == "hand_to_deck_bottom":
                    owner = res.get("owner")
                    if owner in deck:
                        deck[owner] += int(res.get("returned") or 0)
            if not (kind == "use_ability" and det.get("name") == "多龙奇"):
                continue
            if player not in deck:
                misses += 1
                continue
            # ── 前瞻同效果的选择步（挂起帧）事件 ──
            pool_names: list[str] = []
            chosen_names: list[str] = []
            found = False
            for row2 in events:
                if row2["seq"] <= row["seq"]:
                    continue
                e = json.loads(row2["event_json"])
                k2 = e.get("kind")
                d2 = e.get("detail") or {}
                if k2 == "mcts_consider" and not found:
                    for item in d2.get("considered") or []:
                        a = str(item.get("action") or "")
                        if a.startswith("choose："):
                            nm = a.split("：", 1)[1]
                            if nm and nm not in pool_names:
                                pool_names.append(nm)
                elif k2 == "choose" and d2.get("pool") == "own_deck" and d2.get("card") == "多龙奇":
                    chosen_names = list(d2.get("chosen_names") or [])
                    found = True
                    break
                elif k2 == "use_ability":
                    break  # 下一个效果开始，防御
            if not found or len(pool_names) < 1:
                misses += 1
                continue
            scores = []
            for nm in pool_names[:2]:
                sc = resolve_score(nm, cache)
                if sc is None:
                    break
                scores.append(sc)
            if len(scores) < 2:
                misses += 1
                continue
            samples.append({
                "turn": int(d.get("turn") or 0),
                "deck_count": deck[player],
                "s_high": max(scores),
                "s_low": min(scores),
                "mcts": "take" if chosen_names else "pass",
                "taken": chosen_names[0] if chosen_names else None,
                "pool": pool_names[:2],
            })
    con.close()
    return samples, misses


def decide(s: dict, v_junk: float, v_key: float, deep: int, shallow: int) -> str:
    """G1 规则（与 tasks/task 099.md 预注册一致）。"""
    if s["deck_count"] <= shallow:  # R3 薄牌库白拿（覆盖 R1）
        return "take"
    if s["s_high"] < v_junk:  # R1 双废 pass
        return "pass"
    if s["s_low"] >= v_key and s["deck_count"] >= deep:  # R2 关键件保护
        return "pass"
    return "take"


def agreement(samples: list[dict], params: tuple) -> float:
    if not samples:
        return 0.0
    ok = sum(1 for s in samples if decide(s, *params) == s["mcts"])
    return ok / len(samples)


def rule_support(samples: list[dict], params: tuple) -> dict[str, int]:
    """各规则在「相对总是拿最优」基线上的翻转归属计数（优先级 R3>R1>R2）。"""
    v_junk, v_key, deep, shallow = params
    sup = {"R1": 0, "R2": 0, "R3": 0}
    for s in samples:
        if s["deck_count"] <= shallow:
            sup["R3"] += 1
        elif s["s_high"] < v_junk:
            sup["R1"] += 1
        elif s["s_low"] >= v_key and s["deck_count"] >= deep:
            sup["R2"] += 1
    return sup


def main() -> int:
    cache = card_score_cache()
    print(f"评分缓存 {sum(1 for k in cache if not k.endswith('@src'))} 张卡")
    out: dict = {}
    data: dict[str, list[dict]] = {}
    for label, path in (("z1", Z1), ("z2", Z2)):
        samples, misses = extract_points(path, cache)
        data[label] = samples
        n_pass = sum(1 for s in samples if s["mcts"] == "pass")
        print(f"{label}: {len(samples)} 选择点（解析失败/缺窗 {misses}），"
              f"MCTS pass {n_pass}（{n_pass / max(len(samples), 1):.1%}）")
        for lo, hi in ((0, 3), (4, 8), (9, 99)):
            sub = [s for s in samples if lo <= s["turn"] <= hi]
            if sub:
                r = sum(1 for s in sub if s["mcts"] == "pass") / len(sub)
                dk = sorted(s["deck_count"] for s in sub)
                print(f"  turn {lo}-{hi}: n={len(sub)} pass率={r:.1%} "
                      f"deck中位={dk[len(dk) // 2]} 范围[{dk[0]},{dk[-1]}]")

    # ── z1 网格拟合 ──
    best = None
    for vj in GRID_V_JUNK:
        for vk in GRID_V_KEY:
            for dp in GRID_DEEP:
                for sh in GRID_SHALLOW:
                    params = (vj, vk, dp, sh)
                    a = agreement(data["z1"], params)
                    if best is None or a > best[0]:
                        best = (a, params)
    agree_z1, params = best
    print(f"\nz1 最优参数 V_JUNK={params[0]} V_KEY={params[1]} "
          f"DEEP={params[2]} SHALLOW={params[3]} 一致率={agree_z1:.1%}")

    # ── z2 内嵌验证 ──
    agree_z2 = agreement(data["z2"], params)
    sup_z2 = rule_support(data["z2"], params)
    sup_z1 = rule_support(data["z1"], params)
    print(f"z2 一致率={agree_z2:.1%}（门槛 {AGREE_MIN:.0%}）")
    print(f"规则命中 z1={sup_z1} z2={sup_z2}（门槛 {SUPPORT_MIN}/规则）")

    active = all(v >= SUPPORT_MIN for k, v in sup_z2.items() if
                 (k == "R1" and params[0] < 99) or
                 (k == "R2" and True) or (k == "R3" and True))
    verdict = "PASS" if (agree_z2 >= AGREE_MIN and active) else "FAIL"
    print(f"内嵌验证判定：{verdict}")

    out = {
        "params": {"V_JUNK": params[0], "V_KEY": params[1],
                   "DEEP": params[2], "SHALLOW": params[3]},
        "agree_z1": agree_z1, "agree_z2": agree_z2,
        "support_z1": sup_z1, "support_z2": sup_z2, "verdict": verdict,
    }
    dest = ROOT / "results/t099-calibration.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果写入 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
