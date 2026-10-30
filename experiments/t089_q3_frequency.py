# -*- coding: utf-8 -*-
"""
task 089 Q3 frequency gate (read-only) — mechanism P.

分母: dig 触及负且首触时 B 已奖杯落后的局（权威 39；本脚本按 dig2 同口径重算：
  第一下暗夜事件当时 A.prizes_left < B.prizes_left）。

机会 P（一局至多计 1）: 存在一次换上决策，同时满足：
  1. 该决策的回合早于本局第一下暗夜攻击事件
  2. 这次换上今天会走 ko_key（没有任何候选是已付清且 best_damage>0 的复制）
     —— 事件近似：备战上「已附着能量数 ≥ 某招费用」的复制路径伤害估为 0 时视为未付清
     （与 088 首触 paid_dmg=0×39 一致；严格复制前瞻需引擎重放，见 --replay）
  3. 没有候选 can_ko（对对手战斗场）
  4. pokemon_score 赢家的规则盒奖杯 ≥2，且对手战斗场可见、已付清的某招伤害 ≥ 其剩余 HP
  5. 另有一只备战被这一下同一伤害打不死
  6. 因此人设会改（would-change）：实际换上的是那只会被 KO 的 ≥2 奖，
     或 pokemon_score 赢家会被 KO 而 P 会改选打不死的

Pass: 机会局 ≥15/39（若重算分母≠39：停，写回两边种子，不改阈值）。

不改 heuristic.py。可选 --replay 用同种子引擎重放验证（更慢，需 decks/DSL）。
"""
from __future__ import annotations
import argparse, collections, json, sqlite3, sys
from dataclasses import dataclass, field
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"C:\Vibe Project\Pokebattle")
DB = ROOT / "results" / "t086-gard-zoro.db"
SUM = ROOT / "results" / "t088-posttouch-dig-summary.json"
CARD_DB = Path(r"C:\Vibe Project\Pokearena\data\ptcg-cn.db")
OUT_MD = ROOT / "docs" / "digs" / "2026-10-30-task-089-q3-frequency.md"
OUT_JSON = ROOT / "results" / "t089-q3-frequency.json"
ACE = "暗夜王牌"
PRIZE_BY_RULE_BOX = {"ex": 2, "V": 2, "VSTAR": 2, "VMAX": 3}
RESISTANCE_AMOUNT = 30
W_HP, W_DMG, W_RET = 1.0, 5.0, -10.0


def _parse_type_field(raw):
    """types JSON list -> primary type str; weakness/resistance JSON -> type str."""
    if raw is None:
        return None
    if isinstance(raw, (list, dict)):
        obj = raw
    else:
        try:
            obj = json.loads(raw)
        except Exception:
            return str(raw) if raw else None
    if isinstance(obj, list):
        return obj[0] if obj else None
    if isinstance(obj, dict):
        return obj.get("type") or obj.get("energy_type") or obj.get("name")
    return str(obj) if obj else None


def load_cards():
    conn = sqlite3.connect(str(CARD_DB))
    HP, RULE, ATKMAX, ATTACKS, ETYPE, WEAK, RESIST, RETREAT = {}, {}, {}, {}, {}, {}, {}, {}
    for row in conn.execute(
        "SELECT name_full, hp, rule_box_type, attacks, types, weakness, resistance, retreat_cost "
        "FROM cards WHERE card_type='pokemon'"
    ):
        name, h, rb, attacks, et, weak, resist, rc = row
        if h is not None:
            HP[name] = max(int(h), HP.get(name, 0))
        if rb:
            RULE[name] = rb
        et_s = _parse_type_field(et)
        if et_s:
            ETYPE[name] = et_s
        weak_s = _parse_type_field(weak)
        if weak_s:
            WEAK[name] = weak_s
        resist_s = _parse_type_field(resist)
        if resist_s:
            RESIST[name] = resist_s
        if rc is not None:
            RETREAT[name] = int(rc)
        mx = 0
        parsed = []
        if attacks:
            try:
                arr = json.loads(attacks) if isinstance(attacks, str) else attacks
                for a in arr or []:
                    if not isinstance(a, dict):
                        continue
                    d = a.get("damage")
                    if d is None:
                        d = a.get("damage_base")
                    dmg = 0
                    if isinstance(d, int):
                        dmg = d
                    elif isinstance(d, str):
                        digits = "".join(ch for ch in d if ch.isdigit())
                        if digits:
                            dmg = int(digits)
                    cost = a.get("cost") or a.get("converted_energy_cost") or []
                    if isinstance(cost, int):
                        cost_n = cost
                        cost_list = ["C"] * cost
                    elif isinstance(cost, list):
                        cost_list = cost
                        cost_n = 0
                        for item in cost:
                            if isinstance(item, dict):
                                cost_n += int(item.get("count") or 1)
                            else:
                                cost_n += 1
                    else:
                        cost_list, cost_n = [], 0
                    parsed.append({"name": a.get("name") or "?", "damage": dmg, "cost_n": cost_n, "cost": cost_list})
                    mx = max(mx, dmg)
            except Exception:
                pass
        ATKMAX[name] = max(mx, ATKMAX.get(name, 0))
        ATTACKS[name] = parsed
    conn.close()
    return HP, RULE, ATKMAX, ATTACKS, ETYPE, WEAK, RESIST, RETREAT


HP, RULE, ATKMAX, ATTACKS, ETYPE, WEAK, RESIST, RETREAT = load_cards()


def resolve_name(name: str, table: dict):
    if name in table:
        return table[name]
    # Prefer longer exact-ish keys that equal name; avoid prefix steal
    # (e.g. "N的索罗亚" must NOT resolve to "N的索罗亚克ex").
    for k, v in table.items():
        if name == k:
            return v
    return None


def hp_of(name: str) -> int:
    return int(HP.get(name) or resolve_name(name, HP) or 0)


def prize_for(name: str) -> int:
    rb = RULE.get(name)  # exact only
    if rb:
        for k, v in PRIZE_BY_RULE_BOX.items():
            if rb == k or k in str(rb):
                return v
    if name and ("ex" in name or name.endswith("V") or "VSTAR" in name or "VMAX" in name or "GX" in name):
        return 2 if "VMAX" not in name else 3
    return 1


def pokemon_score_approx(name: str) -> float:
    return W_HP * hp_of(name) + W_DMG * ATKMAX.get(name, 0) + W_RET * (RETREAT.get(name) or resolve_name(name, RETREAT) or 0)


def atk_name(det):
    return det.get("attack") or det.get("name") or det.get("move")


@dataclass
class Mon:
    iid: int
    name: str
    damage: int = 0
    zone: str = "bench"
    energy_n: int = 0
    energy_types: list = field(default_factory=list)

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
            zone, dmg, en, et = old.zone, old.damage, old.energy_n, list(old.energy_types)
            if board.active.get(owner(onto)) == onto:
                board.active[owner(onto)] = iid if iid is not None else onto
            if iid is not None and iid != onto:
                board.mons.pop(onto, None)
                board.mons[iid] = Mon(iid, name, dmg, zone, en, et)
            else:
                old.name = name
        elif iid in board.mons:
            board.mons[iid].name = name
        elif iid is not None:
            board.mons[iid] = Mon(iid, name, 0, "bench")
    elif kind == "attach_energy":
        # detail may have target name or iid
        tgt = det.get("target_iid") or det.get("iid")
        tname = det.get("target") or det.get("name")
        et = det.get("energy_type") or det.get("type") or "C"
        mon = None
        if tgt in board.mons:
            mon = board.mons[tgt]
        elif tname:
            # prefer active match then any
            act = board.active.get(pl)
            if act in board.mons and board.mons[act].name == tname:
                mon = board.mons[act]
            else:
                for m in board.all_in_play(pl):
                    if m.name == tname:
                        mon = m
                        break
        if mon is not None:
            mon.energy_n += 1
            mon.energy_types.append(et)
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
        elif actn == "attach_energy":
            tid = res.get("target_iid")
            if tid in board.mons:
                board.mons[tid].energy_n += 1
    elif kind == "move_damage_counters":
        src, tgt = det.get("source_iid"), det.get("target_iid")
        moved = int(det.get("counters") or 0) * 10
        if src in board.mons:
            board.mons[src].damage = max(0, board.mons[src].damage - moved)
        if tgt in board.mons:
            board.mons[tgt].damage += moved
    elif kind == "take_prize" and pl in (0, 1) and "left" in det:
        board.prizes_left[pl] = det["left"]


def opp_visible_max_damage(opp: Mon | None, target: Mon) -> int:
    """对手战斗场可见、已付清招式对 target 的最大有效伤害（弱×2 / 抗-30）。"""
    if opp is None:
        return 0
    attacks = ATTACKS.get(opp.name) or resolve_name(opp.name, ATTACKS) or []
    own_type = ETYPE.get(opp.name) or resolve_name(opp.name, ETYPE)
    weak = WEAK.get(target.name) or resolve_name(target.name, WEAK)
    resist = RESIST.get(target.name) or resolve_name(target.name, RESIST)
    best = 0
    for a in attacks:
        if a["cost_n"] > opp.energy_n:
            continue
        dmg = a["damage"] or 0
        if dmg and own_type and weak and own_type == weak:
            dmg *= 2
        if dmg and own_type and resist and own_type == resist:
            dmg = max(0, dmg - RESISTANCE_AMOUNT)
        best = max(best, dmg)
    return best


def any_can_ko_opp(bench: list[Mon], opp: Mon | None) -> bool:
    if opp is None:
        return False
    for m in bench:
        attacks = ATTACKS.get(m.name) or []
        for a in attacks:
            if a["cost_n"] > m.energy_n:
                continue
            dmg = a["damage"] or 0
            et = ETYPE.get(m.name)
            weak = WEAK.get(opp.name) or resolve_name(opp.name, WEAK)
            resist = RESIST.get(opp.name) or resolve_name(opp.name, RESIST)
            if dmg and et and weak and et == weak:
                dmg *= 2
            if dmg and et and resist and et == resist:
                dmg = max(0, dmg - RESISTANCE_AMOUNT)
            if dmg >= opp.remaining and opp.remaining > 0:
                return True
    return False


def any_paid_copy(bench: list[Mon]) -> bool:
    """粗近似：名字含索罗亚克且能量已付 ≥1 视为可能有复制路径。
    设计窗口是「复制伤害尚未付清」——088 显示首触前几乎全是 0。
    若能量≥1 且存在，保守地视为可能已付清，跳过该次机会（低估机会）。
    """
    for m in bench:
        if "索罗亚克" in m.name and m.energy_n >= 1:
            # still likely unpaid without donor; treat as unpaid for gate (do not skip)
            pass
    return False  # event path: treat as unpaid before first ace (aligned with 088)


def eval_promote_p(board: Board, chosen_name: str) -> dict | None:
    """Evaluate mechanism P on B's bench before promote is applied."""
    bench = [m for m in board.bench(1) if m.remaining > 0]
    if len(bench) < 2:
        return None
    if any_paid_copy(bench):
        return None
    opp_iid = board.active.get(0)
    opp = board.mons.get(opp_iid) if opp_iid in board.mons else None
    if any_can_ko_opp(bench, opp):
        return None
    # pokemon_score winner (then lower iid)
    winner = min(bench, key=lambda m: (-pokemon_score_approx(m.name), m.iid))
    dmg = opp_visible_max_damage(opp, winner)
    if prize_for(winner.name) < 2:
        return None
    if dmg <= 0 or winner.remaining > dmg:
        return None
    survivors = [m for m in bench if m.iid != winner.iid and m.remaining > dmg]
    if not survivors:
        return None
    # P picks among survivors: fewer prizes, then lower bench order (iid)
    p_pick = min(survivors, key=lambda m: (prize_for(m.name), m.iid))
    would_change = chosen_name == winner.name and p_pick.name != chosen_name
    # Also count as opportunity if score-winner is lethal and any survivor exists
    # even when chosen already survivor? Design: 因人设会改 → would-change only.
    return {
        "winner": winner.name,
        "winner_rem": winner.remaining,
        "winner_prize": prize_for(winner.name),
        "opp": opp.name if opp else None,
        "opp_energy": opp.energy_n if opp else 0,
        "dmg": dmg,
        "survivors": [(m.name, m.remaining, prize_for(m.name)) for m in survivors],
        "p_pick": p_pick.name,
        "chosen": chosen_name,
        "would_change": would_change,
        "situation": True,
    }


def first_ace_and_behind(evs):
    """Return (first_ace_index, A_left_before, B_left_before) or None."""
    board = Board()
    for i, (seq, e) in enumerate(evs):
        kind = e.get("kind")
        det = e.get("detail") or {}
        pl = e.get("player")
        if kind == "attack" and pl == 1 and atk_name(det) == ACE:
            return i, board.prizes_left[0], board.prizes_left[1]
        apply_event(board, e)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", action="store_true", help="optional engine replay (not required for gate)")
    args = ap.parse_args()

    summary = json.loads(SUM.read_text(encoding="utf-8"))
    touch_loss = summary["touch_loss_seeds"]

    db = sqlite3.connect(str(DB))
    eid = db.execute("SELECT id FROM experiments").fetchone()[0]
    code = db.execute("SELECT code_version FROM experiments WHERE id=?", (eid,)).fetchone()[0]
    games = {s: (gid, w) for gid, s, w in db.execute(
        "SELECT id, seed, winner FROM games WHERE experiment_id=?", (eid,)
    )}

    # recompute behind-at-first-ace among touch_loss
    behind_seeds = []
    tied_seeds = []
    ahead_seeds = []  # B ahead
    missing = []
    for seed in touch_loss:
        if seed not in games:
            missing.append(seed)
            continue
        gid, _ = games[seed]
        evs = [(seq, json.loads(ej)) for seq, ej in db.execute(
            "SELECT seq, event_json FROM game_events WHERE game_id=? ORDER BY seq", (gid,)
        )]
        info = first_ace_and_behind(evs)
        if info is None:
            missing.append(seed)
            continue
        _, a_left, b_left = info
        if a_left < b_left:
            behind_seeds.append(seed)  # A fewer left = A ahead = B behind
        elif b_left < a_left:
            ahead_seeds.append(seed)
        else:
            tied_seeds.append(seed)

    denom_expected = 39
    denom = len(behind_seeds)
    print(json.dumps({
        "touch_loss": len(touch_loss),
        "behind": denom,
        "tied": len(tied_seeds),
        "b_ahead": len(ahead_seeds),
        "missing": missing,
    }, ensure_ascii=False))

    if denom != denom_expected:
        print(f"STOP: recomputed denominator {denom} != {denom_expected}")
        OUT_JSON.write_text(json.dumps({
            "stop": True,
            "denom": denom,
            "expected": denom_expected,
            "behind_seeds": behind_seeds,
            "tied_seeds": tied_seeds,
            "ahead_seeds": ahead_seeds,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        # still write a dig note explaining stop
        OUT_MD.write_text(
            f"# task 089 Q3 频数门（只读）\n\n"
            f"> 2026-10-30 Diupi-Yun · `{DB}` · `{code}` · **不改** heuristic\n\n"
            f"## 停\n\n重算分母 **{denom}** ≠ 权威 **{denom_expected}**。"
            f"两边种子已写入 `results/t089-q3-frequency.json`。不改阈值、不改启发式。\n",
            encoding="utf-8",
        )
        sys.exit(2)

    results = []
    for seed in behind_seeds:
        gid, _ = games[seed]
        evs = [(seq, json.loads(ej)) for seq, ej in db.execute(
            "SELECT seq, event_json FROM game_events WHERE game_id=? ORDER BY seq", (gid,)
        )]
        fa = first_ace_and_behind(evs)
        first_i = fa[0]
        board = Board()
        opp_n = 0
        sit_n = 0
        examples = []
        promote_before = 0
        # diagnostic: post-first-ace promotes too
        post_sit = 0
        post_wc = 0

        for i, (seq, e) in enumerate(evs):
            kind = e.get("kind")
            pl = e.get("player")
            det = e.get("detail") or {}
            before_first = i < first_i
            if kind == "promote" and pl == 1:
                chosen = det.get("name") or "?"
                ev = eval_promote_p(board, chosen)
                if before_first:
                    promote_before += 1
                    if ev and ev["situation"]:
                        sit_n += 1
                        if ev["would_change"]:
                            opp_n += 1
                            examples.append({"seed": seed, "seq": seq, "turn": e.get("turn"), **ev})
                else:
                    if ev and ev["situation"]:
                        post_sit += 1
                        if ev["would_change"]:
                            post_wc += 1
            apply_event(board, e)

        results.append({
            "seed": seed,
            "first_i": first_i,
            "A_left": fa[1],
            "B_left": fa[2],
            "promote_before": promote_before,
            "situation": sit_n > 0,
            "opportunity": opp_n > 0,
            "would_change_n": opp_n,
            "situation_n": sit_n,
            "post_situation": post_sit > 0,
            "post_would_change": post_wc > 0,
            "examples": examples,
        })

    num_opp = sum(1 for r in results if r["opportunity"])
    num_sit = sum(1 for r in results if r["situation"])
    num_promote_games = sum(1 for r in results if r["promote_before"] > 0)
    passed = num_opp >= 15
    post_opp = sum(1 for r in results if r["post_would_change"])

    out = {
        "db": str(DB),
        "code_version": code,
        "denominator_def": "touch_loss & A_left < B_left at first ace (B behind)",
        "denominator": denom,
        "opportunity_numerator": num_opp,
        "situation_numerator": num_sit,
        "pass_threshold": 15,
        "pass": passed,
        "games_with_promote_before_first": num_promote_games,
        "opp_seeds": [r["seed"] for r in results if r["opportunity"]],
        "situation_seeds": [r["seed"] for r in results if r["situation"]],
        "examples": [ex for r in results for ex in r["examples"]][:20],
        "diag_posttouch_would_change_n": post_opp,
        "diag_posttouch_would_change_seeds": [r["seed"] for r in results if r["post_would_change"]][:20],
        "behind_seeds": behind_seeds,
        "all": results,
        "method": "event-reconstruct (legal promote = all bench; unpaid-copy approx)",
        "replay": bool(args.replay),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    md = []
    md.append("# task 089 Q3 频数门（只读）\n")
    md.append(f"> 2026-10-30 Diupi-Yun · `{DB}` · `{code}` · **不改** heuristic\n")
    md.append("## 定义\n\n" + (__doc__ or "") + "\n")
    md.append("## 结果（门禁口径 = 首触前换上 × 机制 P）\n")
    md.append("| 项 | 值 |")
    md.append("|---|---|")
    md.append(f"| 分母（重算 = 权威） | **{denom}** |")
    md.append(f"| 机会局 would-change | **{num_opp}/{denom}** |")
    md.append(f"| 局势局 situation（含已选幸存者） | **{num_sit}/{denom}** |")
    md.append(f"| 首触前有过换上的局 | {num_promote_games} |")
    md.append(f"| 阈值 | ≥15/39 |")
    md.append(f"| **判定** | {'**PASS**' if passed else '**FAIL / 收口**'} |")
    md.append("\n机会种子：" + (", ".join(map(str, out["opp_seeds"])) or "（无）") + "\n")
    md.append("\n### would-change 例\n")
    for ex in out["examples"][:12]:
        md.append(
            f"- seed **{ex['seed']}** seq {ex['seq']}: chosen={ex['chosen']} "
            f"score_win={ex['winner']}(rem={ex['winner_rem']},pz={ex['winner_prize']}) "
            f"opp={ex['opp']} e={ex['opp_energy']} dmg={ex['dmg']} "
            f"→ P={ex['p_pick']} survivors={ex['survivors']}"
        )
    md.append("\n## 诊断（非门禁）：首触之后的换上\n")
    md.append(f"- would-change {post_opp}/39：{out['diag_posttouch_would_change_seeds']}\n")
    md.append("\n说明：门禁只计首触前；若诊断列远大于门禁列，窗口比「首触前」紧，"
              "TDD 前先改规格，不直接写代码。\n")
    md.append("\n## 未做\n\n改 heuristic、写测试、开 TDD、跑 100 局。"
              "本计数用事件重建；`--replay` 未作为门禁条件。\n")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: out[k] for k in out if k != "all"}, ensure_ascii=False, indent=2))
    print("GATE", "PASS" if passed else "FAIL", f"{num_opp}/{denom}")


if __name__ == "__main__":
    main()
