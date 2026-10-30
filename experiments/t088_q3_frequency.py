# -*- coding: utf-8 -*-
"""
task 088 Q3 frequency gate (read-only) — strict first-touch window.

分母: dig 40 局触及负且首触未转化。

首触窗口: 事件 turn == 首触暗夜的 turn，且限制在该次攻击结算链内
  （从本回合 B 侧行动起点到首触 copy/damage 链结束；若 turn 字段与对手重叠，
   则硬裁到首触 attack 起至下一次任一方 attack / turn 递增之前的结算尾）。

机会 A: 窗口内 B 的 switch 类 opponent_bench choose（老大的指令/反击捕捉器），
  且对手备战存在 remaining HP ≤ 首触已付清复制对战斗场 final 伤害（>0）。
机会 B: 首触攻击结算链内的 opponent_bench / 攻击效果伤害 choose，
  且候选存在 remaining HP ≤ 该下伤害。

Would-change: 上述 choose 上 C 键最优 ≠ 实际 chosen。

Pass: 机会局 ≥15/40。
"""
from __future__ import annotations
import collections, json, sqlite3, sys
from dataclasses import dataclass, field
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

DB = Path("results/t086-gard-zoro.db")
SUM = json.loads(Path("results/t088-posttouch-dig-summary.json").read_text(encoding="utf-8"))
OUT_MD = Path("docs/digs/2026-10-30-task-088-q3-frequency.md")
OUT_JSON = Path("results/t088-q3-frequency.json")
ACE = "暗夜王牌"
SWITCH_CARDS = {"老大的指令", "反击捕捉器"}
PRIZE_BY_RULE_BOX = {"ex": 2, "V": 2, "VSTAR": 2, "VMAX": 3}

conn_cards = sqlite3.connect(r"C:\Vibe Project\Pokearena\data\ptcg-cn.db")
HP, RULE, ATKMAX = {}, {}, {}
for name, h, rb, attacks in conn_cards.execute(
    "SELECT name_full, hp, rule_box_type, attacks FROM cards WHERE card_type='pokemon'"
):
    if h is not None:
        HP[name] = max(int(h), HP.get(name, 0))
    if rb:
        RULE[name] = rb
    mx = 0
    if attacks:
        try:
            arr = json.loads(attacks) if isinstance(attacks, str) else attacks
            for a in arr or []:
                d = a.get("damage") if isinstance(a, dict) else None
                if isinstance(d, int):
                    mx = max(mx, d)
                elif isinstance(d, str):
                    digits = "".join(ch for ch in d if ch.isdigit())
                    if digits:
                        mx = max(mx, int(digits))
        except Exception:
            pass
    ATKMAX[name] = max(mx, ATKMAX.get(name, 0))


def hp_of(name: str) -> int:
    if name in HP:
        return HP[name]
    for k, v in HP.items():
        if name == k or name in k or k.startswith(name) or name.startswith(k):
            return v
    return 0


def rule_of(name: str):
    if name in RULE:
        return RULE[name]
    for k, v in RULE.items():
        if name == k or name in k or k.startswith(name):
            return v
    return None


def prize_for(name: str) -> int:
    rb = rule_of(name)
    if rb:
        for k, v in PRIZE_BY_RULE_BOX.items():
            if rb == k or k in str(rb):
                return v
    if "ex" in name:
        return 2
    return 1


@dataclass
class Mon:
    iid: int
    name: str
    damage: int = 0
    zone: str = "bench"

    @property
    def remaining(self) -> int:
        h = hp_of(self.name)
        return max(0, h - self.damage) if h else 0


def owner(iid: int) -> int:
    return 1 if iid >= 10000 else 0


@dataclass
class Board:
    mons: dict = field(default_factory=dict)
    active: dict = field(default_factory=lambda: {0: None, 1: None})
    prizes_left: dict = field(default_factory=lambda: {0: 6, 1: 6})

    def bench(self, player: int):
        act = self.active.get(player)
        return [m for m in self.mons.values() if m.zone == "bench" and owner(m.iid) == player]

    def all_in_play(self, player: int):
        return [m for m in self.mons.values() if m.zone in ("active", "bench") and owner(m.iid) == player]


def apply_event(board: Board, e: dict):
    kind = e.get("kind")
    pl = e.get("player")
    det = e.get("detail") or {}
    if kind == "place_active":
        iid = det.get("iid")
        if iid is not None:
            board.mons[iid] = Mon(iid, det.get("name") or "?", 0, "active")
            board.active[pl] = iid
    elif kind == "place_bench":
        iid = det.get("iid")
        if iid is not None:
            board.mons[iid] = Mon(iid, det.get("name") or "?", 0, "bench")
    elif kind == "evolve":
        iid = det.get("iid")
        onto = det.get("onto")
        name = det.get("name") or "?"
        if onto in board.mons:
            old = board.mons[onto]
            zone, dmg = old.zone, old.damage
            if board.active.get(owner(onto)) == onto:
                board.active[owner(onto)] = iid if iid is not None else onto
            if iid is not None and iid != onto:
                board.mons.pop(onto, None)
                board.mons[iid] = Mon(iid, name, dmg, zone)
            else:
                old.name = name
        elif iid in board.mons:
            board.mons[iid].name = name
        elif iid is not None:
            board.mons[iid] = Mon(iid, name, 0, "bench")
    elif kind == "retreat":
        act = board.active.get(pl)
        into_name = det.get("into")
        if act in board.mons:
            board.mons[act].zone = "bench"
        for m in board.all_in_play(pl):
            if m.name == into_name and m.iid != act:
                m.zone = "active"
                board.active[pl] = m.iid
                break
    elif kind == "promote":
        name = det.get("name")
        for m in board.bench(pl):
            if m.name == name:
                m.zone = "active"
                board.active[pl] = m.iid
                break
    elif kind == "knockout":
        name = det.get("name")
        act = board.active.get(pl)
        if act in board.mons and (not name or board.mons[act].name == name):
            board.mons[act].zone = "out"
            board.active[pl] = None
        else:
            for m in list(board.all_in_play(pl)):
                if m.name == name:
                    m.zone = "out"
                    if board.active.get(pl) == m.iid:
                        board.active[pl] = None
                    break
    elif kind == "effect_primitive":
        actn = det.get("action")
        res = det.get("result") or {}
        if actn == "damage":
            tid = res.get("target_iid")
            final = int(res.get("final") or res.get("amount") or 0)
            if tid in board.mons:
                board.mons[tid].damage += final
        elif actn == "switch":
            into_n, out_n = res.get("into"), res.get("out")
            out_m = into_m = None
            for m in board.mons.values():
                if m.zone == "active" and m.name == out_n:
                    out_m = m
                if m.zone == "bench" and m.name == into_n:
                    into_m = m
            if out_m and into_m:
                out_m.zone = "bench"
                into_m.zone = "active"
                board.active[owner(into_m.iid)] = into_m.iid
        elif actn == "move_damage_counters":
            src, tgt = res.get("source_iid"), res.get("target_iid")
            moved = int(res.get("moved") or 0) * 10
            if src in board.mons:
                board.mons[src].damage = max(0, board.mons[src].damage - moved)
            if tgt in board.mons:
                board.mons[tgt].damage += moved
    elif kind == "move_damage_counters":
        src, tgt = det.get("source_iid"), det.get("target_iid")
        moved = int(det.get("counters") or 0) * 10
        if src in board.mons:
            board.mons[src].damage = max(0, board.mons[src].damage - moved)
        if tgt in board.mons:
            board.mons[tgt].damage += moved
    elif kind == "take_prize" and pl in (0, 1) and "left" in det:
        board.prizes_left[pl] = det["left"]


def atk_name(det):
    return det.get("attack") or det.get("name") or det.get("move")


def score_key(m: Mon):
    return (m.remaining + ATKMAX.get(m.name, 0), m.remaining, m.name)


def c_key(m: Mon, dmg: int, own_left: int):
    can_ko = 1 if (hp_of(m.name) and m.remaining <= dmg) else 0
    pz = prize_for(m.name)
    completes = 1 if can_ko and pz >= own_left else 0
    return (can_ko, completes, pz if can_ko else 0)


def main():
    db = sqlite3.connect(str(DB))
    eid = db.execute("SELECT id FROM experiments").fetchone()[0]
    code = db.execute("SELECT code_version FROM experiments WHERE id=?", (eid,)).fetchone()[0]
    games = {s: (gid, w) for gid, s, w in db.execute(
        "SELECT id, seed, winner FROM games WHERE experiment_id=?", (eid,)
    )}
    touch_loss = SUM["touch_loss_seeds"]
    gids = [games[s][0] for s in touch_loss]
    by = collections.defaultdict(list)
    q = f"SELECT game_id, seq, event_json FROM game_events WHERE game_id IN ({','.join('?'*len(gids))}) ORDER BY game_id, seq"
    for gid, seq, ej in db.execute(q, gids):
        by[gid].append((seq, json.loads(ej)))

    results = []
    # Alternate diagnostic: whole-game after first ace
    alt_wc_seeds = set()
    alt_opp_seeds = set()

    for seed in touch_loss:
        gid, _ = games[seed]
        evs = by[gid]
        first_i = None
        for i, (seq, e) in enumerate(evs):
            if e.get("kind") == "attack" and e.get("player") == 1 and atk_name(e.get("detail") or {}) == ACE:
                first_i = i
                break
        if first_i is None:
            continue

        # conversion
        converted = False
        for j in range(first_i + 1, len(evs)):
            e = evs[j][1]
            if e.get("kind") == "knockout" and e.get("player") == 0:
                converted = True
                break
            if e.get("kind") == "take_prize" and e.get("player") == 1:
                converted = True
                break
            if e.get("kind") == "end_turn" and e.get("player") == 1:
                break
            if e.get("kind") == "attack" and e.get("player") == 0:
                break
            # turn bump past first
            if e.get("turn") is not None and evs[first_i][1].get("turn") is not None:
                if e.get("turn") > evs[first_i][1].get("turn") and e.get("player") == 0 and e.get("kind") == "attack":
                    break
        if converted:
            continue

        T = evs[first_i][1].get("turn")

        # window start: walk back while same turn and B actions / setup; stop at previous A attack or lower turn
        start = first_i
        for k in range(first_i - 1, -1, -1):
            e = evs[k][1]
            if e.get("turn") is not None and T is not None and e.get("turn") < T:
                start = k + 1
                break
            if e.get("kind") == "attack" and e.get("player") == 0:
                start = k + 1
                break
            if e.get("kind") == "end_turn" and e.get("player") == 0:
                start = k + 1
                break
            start = k
        # window end: after first ace, through copy/damage chain until next attack or turn>
        end = first_i
        for k in range(first_i + 1, len(evs)):
            e = evs[k][1]
            if e.get("kind") == "attack":
                break
            if e.get("turn") is not None and T is not None and e.get("turn") > T:
                break
            if e.get("kind") == "end_turn":
                end = k
                break
            end = k

        # board to start
        board = Board()
        for i in range(0, start):
            apply_event(board, evs[i][1])

        # First pass: find paid_dmg from first ace chain
        paid_dmg = 0
        for k in range(first_i + 1, end + 1):
            e = evs[k][1]
            if e.get("kind") == "effect_primitive" and (e.get("detail") or {}).get("action") == "damage":
                det = e.get("detail") or {}
                res = det.get("result") or {}
                params = det.get("params") or {}
                if params.get("selector") == "opponent_active" or res.get("to_bench") is False:
                    paid_dmg = max(paid_dmg, int(res.get("final") or res.get("amount") or 0))

        opp_A = opp_B = would_change = False
        examples = []
        switch_n = bench_n = 0

        # walk window with board
        board = Board()
        for i in range(0, start):
            apply_event(board, evs[i][1])

        for i in range(start, end + 1):
            seq, e = evs[i]
            kind = e.get("kind")
            pl = e.get("player")
            det = e.get("detail") or {}
            if kind == "choose" and pl == 1:
                pool = det.get("pool")
                card = det.get("card")
                chosen = (det.get("chosen_names") or [None])[0]
                eid = str(det.get("effect_id") or "")
                if pool == "opponent_bench" and card in SWITCH_CARDS:
                    switch_n += 1
                    cands = board.bench(0)
                    if paid_dmg > 0 and cands:
                        ko = [m for m in cands if hp_of(m.name) and m.remaining <= paid_dmg]
                        if ko:
                            opp_A = True
                            c_pick = max(cands, key=lambda m: c_key(m, paid_dmg, board.prizes_left[1]))
                            if chosen and c_pick.name != chosen:
                                would_change = True
                                examples.append({
                                    "seed": seed, "seq": seq, "kind": "switch", "card": card,
                                    "chosen": chosen, "c_pick": c_pick.name, "dmg": paid_dmg,
                                    "cands": [(m.name, m.remaining) for m in cands],
                                })
                elif pool in ("opponent_bench", "opponent_pokemon_any") and (
                    "焚身" in eid or "on_attack" in eid or "copy>" in eid
                    or card in {"N的达摩狒狒", "N的索罗亚克ex"}
                ):
                    # only count if this choose is part of first ace chain (i >= first_i)
                    if i >= first_i:
                        bench_n += 1
                        dmg_amt = 90
                        for k2 in range(i, min(i + 10, end + 1)):
                            e2 = evs[k2][1]
                            if e2.get("kind") == "effect_primitive" and (e2.get("detail") or {}).get("action") == "damage":
                                res = (e2.get("detail") or {}).get("result") or {}
                                params = (e2.get("detail") or {}).get("params") or {}
                                if params.get("selector") in ("opponent_bench", "opponent_pokemon_any") or res.get("to_bench"):
                                    dmg_amt = int(res.get("final") or res.get("amount") or dmg_amt)
                                    break
                        cands = board.bench(0) if pool == "opponent_bench" else board.all_in_play(0)
                        ko = [m for m in cands if hp_of(m.name) and m.remaining <= dmg_amt]
                        if ko:
                            opp_B = True
                            c_pick = max(cands, key=lambda m: c_key(m, dmg_amt, board.prizes_left[1]))
                            if chosen and c_pick.name != chosen:
                                would_change = True
                                examples.append({
                                    "seed": seed, "seq": seq, "kind": "bench_dmg", "card": card,
                                    "chosen": chosen, "c_pick": c_pick.name, "dmg": dmg_amt,
                                    "cands": [(m.name, m.remaining) for m in cands],
                                })
            apply_event(board, e)

        opportunity = opp_A or opp_B
        results.append({
            "seed": seed, "turn": T, "start_seq": evs[start][0], "end_seq": evs[end][0],
            "first_seq": evs[first_i][0], "paid_dmg": paid_dmg,
            "opp_A": opp_A, "opp_B": opp_B, "opportunity": opportunity,
            "would_change": would_change, "switch_n": switch_n, "bench_n": bench_n,
            "examples": examples,
        })

        # ALT diagnostic: after first ace to game end, any C choose would-change with dmg>0
        board = Board()
        for i, (seq, e) in enumerate(evs):
            det = e.get("detail") or {}
            pl = e.get("player")
            if i >= first_i and e.get("kind") == "choose" and pl == 1:
                pool = det.get("pool")
                card = det.get("card")
                chosen = (det.get("chosen_names") or [None])[0]
                eid = str(det.get("effect_id") or "")
                if pool == "opponent_bench" and card in SWITCH_CARDS:
                    # estimate upcoming ace damage: look forward to next B ace damage
                    fut = 0
                    for k2 in range(i, min(i + 80, len(evs))):
                        e2 = evs[k2][1]
                        if e2.get("kind") == "attack" and e2.get("player") == 1 and atk_name(e2.get("detail") or {}) == ACE:
                            for k3 in range(k2 + 1, min(k2 + 40, len(evs))):
                                e3 = evs[k3][1]
                                if e3.get("kind") == "effect_primitive" and (e3.get("detail") or {}).get("action") == "damage":
                                    res = (e3.get("detail") or {}).get("result") or {}
                                    params = (e3.get("detail") or {}).get("params") or {}
                                    if params.get("selector") == "opponent_active" or res.get("to_bench") is False:
                                        fut = max(fut, int(res.get("final") or 0))
                                        break
                                if e3.get("kind") == "attack":
                                    break
                            break
                        if e2.get("kind") == "attack" and e2.get("player") == 0:
                            break
                    cands = board.bench(0)
                    if fut > 0 and any(hp_of(m.name) and m.remaining <= fut for m in cands):
                        alt_opp_seeds.add(seed)
                        c_pick = max(cands, key=lambda m: c_key(m, fut, board.prizes_left[1])) if cands else None
                        if c_pick and chosen and c_pick.name != chosen:
                            alt_wc_seeds.add(seed)
                elif pool == "opponent_bench" and (
                    "焚身" in eid or "on_attack" in eid or "copy>" in eid
                    or card in {"N的达摩狒狒", "N的索罗亚克ex"}
                ):
                    dmg_amt = 90
                    cands = board.bench(0)
                    if any(hp_of(m.name) and m.remaining <= dmg_amt for m in cands):
                        alt_opp_seeds.add(seed)
                        c_pick = max(cands, key=lambda m: c_key(m, dmg_amt, board.prizes_left[1])) if cands else None
                        if c_pick and chosen and c_pick.name != chosen:
                            alt_wc_seeds.add(seed)
            apply_event(board, e)

    denom = len(results)
    num_opp = sum(1 for r in results if r["opportunity"])
    num_wc = sum(1 for r in results if r["would_change"])
    passed = num_opp >= 15

    summary = {
        "db": str(DB),
        "code_version": code,
        "denominator_def": "touch_loss & first-ace no KO/prize; strict first-touch window",
        "denominator": denom,
        "opportunity_numerator": num_opp,
        "would_change_numerator": num_wc,
        "pass_threshold": 15,
        "pass": passed,
        "n_opp_A": sum(1 for r in results if r["opp_A"]),
        "n_opp_B": sum(1 for r in results if r["opp_B"]),
        "n_with_switch_choose": sum(1 for r in results if r["switch_n"]),
        "n_with_bench_choose": sum(1 for r in results if r["bench_n"]),
        "paid_dmg_hist": dict(collections.Counter(r["paid_dmg"] for r in results)),
        "opp_seeds": [r["seed"] for r in results if r["opportunity"]],
        "would_change_seeds": [r["seed"] for r in results if r["would_change"]],
        "examples": [ex for r in results for ex in r["examples"]][:12],
        "alt_posttouch_opportunity_seeds_n": len(alt_opp_seeds),
        "alt_posttouch_opportunity_seeds": sorted(alt_opp_seeds)[:20],
        "alt_posttouch_would_change_n": len(alt_wc_seeds),
        "alt_posttouch_would_change_seeds": sorted(alt_wc_seeds)[:20],
        "all": results,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = []
    md.append("# task 088 Q3 频数门（只读）\n")
    md.append(f"> 2026-10-30 Diupi-Yun · `{DB}` · `{code}` · **不改** heuristic\n")
    md.append("## 定义\n\n" + (__doc__ or "") + "\n")
    md.append("## 结果（门禁口径 = 首触窗口）\n")
    md.append("| 项 | 值 |")
    md.append("|---|---|")
    md.append(f"| 分母 | **{denom}** |")
    md.append(f"| 机会局 opp A∨B | **{num_opp}/{denom}** |")
    md.append(f"| would-change | **{num_wc}/{denom}** |")
    md.append(f"| opp_A / opp_B | {summary['n_opp_A']} / {summary['n_opp_B']} |")
    md.append(f"| 窗口内有 switch choose 的局 | {summary['n_with_switch_choose']} |")
    md.append(f"| 首触链上有 bench-dmg choose 的局 | {summary['n_with_bench_choose']} |")
    md.append(f"| 阈值 | ≥15/40 |")
    md.append(f"| **判定** | {'**PASS**' if passed else '**FAIL / 收口**'} |")
    md.append("\n首触 paid_dmg 分布：`" + json.dumps(summary["paid_dmg_hist"]) + "`\n")
    md.append("\n机会种子：" + (", ".join(map(str, summary["opp_seeds"])) or "（无）") + "\n")
    md.append("\n### would-change 例\n")
    for ex in summary["examples"]:
        md.append(f"- seed **{ex['seed']}** seq {ex['seq']}: {ex['kind']} {ex['card']} chosen={ex['chosen']} → C={ex['c_pick']} dmg={ex['dmg']} cands={ex['cands']}")
    md.append("\n## 诊断（非门禁）：首触之后整局\n")
    md.append(f"- 机会局 {summary['alt_posttouch_opportunity_seeds_n']}/40：{summary['alt_posttouch_opportunity_seeds']}\n")
    md.append(f"- would-change {summary['alt_posttouch_would_change_n']}/40：{summary['alt_posttouch_would_change_seeds']}\n")
    md.append("\n说明：首触 39/40 paid_dmg=0（自拷/空供体），故首触窗口内机制 C 几乎无杠杆；")
    md.append("即使放宽到触后整局，机会仍需单独评估，**不能**替代 D-088-6 的首触门。\n")
    md.append("\n## 未做\n\n改 heuristic、写测试、开 TDD、跑 100 局。\n")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "all"}, ensure_ascii=False, indent=2))
    print("GATE", "PASS" if passed else "FAIL", f"{num_opp}/{denom}")

if __name__ == "__main__":
    main()
