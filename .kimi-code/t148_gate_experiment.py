# task 148 · M15 门槛实验（判别测试：Elo 辅助推荐流程）
# 预注册脚本：task 148 任务书（tasks/task 148.md）的可执行实现。
# 零新模拟局——纯冻结数据重分析：t146 标签集 + t141 基线格 + field-snap-2026-11 权重。
# 用法: .venv/Scripts/python.exe -X utf8 .kimi-code/t148_gate_experiment.py
# 输出: results/t148-gate/verdict.json（含预注册判据逐项数值）

import json
import math
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "t148-gate"
OUT.mkdir(parents=True, exist_ok=True)

# ---- 冻结输入（task 148 任务书 §冻结输入）----
T146_DB = ROOT / "results" / "t146-combo-labels.db"
T141_DB = ROOT / "results" / "t141-gardevoir-prep.db"
LABELS_CSV = ROOT / "results" / "t146-combo-labels.csv"
FIELD_SNAP = ROOT / "results" / "field-snap-2026-11.json"

OPP_NAMES = {  # 实验名后缀 -> (opponent id, field group_key)
    "dragapult-dusknoir": ("676344", "多龙巴鲁托 黑夜魔灵"),
    "joltik": ("677291", "电电虫Box"),
    "grimmsnarl": ("711855", "玛俐的长毛巨魔 雪妖女"),
    "gholdengo-dudun": ("711850", "赛富豪 土龙节节"),
}
BASE = "BASE"
COMBOS = [f"L{i:02d}" for i in range(1, 11)] + ["C01", "C02", "C03"]

K_ELO, R0, N_PASSES = 32.0, 1500.0, 30  # 仅敏感性对照用（K 扫描留档；判定用 BT-MLE）
NAIVE_BASELINE_MEAN_PP = 4.6      # L01 冻结值（t146 CSV）
CRITERION_B_FLOOR_PP = 3.6        # +4.6 - 1pp 容差（任务书预注册）


def bt_mle(games, entities, tol=1e-10, max_iters=500):
    """Bradley-Terry MLE（MM 迭代，确定性）。返回 {entity: log-strength}（均值归零）。"""
    import math as _m

    alpha = {e: 0.0 for e in entities}
    pairs = {}
    for x, y, s in games:
        key = (x, y)
        pairs.setdefault(key, [0.0, 0.0])  # [a侧得分, 局数]
        pairs[key][0] += s
        pairs[key][1] += 1
    for _ in range(max_iters):
        obs = {e: 0.0 for e in entities}
        exp = {e: 0.0 for e in entities}
        for (x, y), (sa, n) in pairs.items():
            p = 1.0 / (1.0 + _m.exp(alpha[y] - alpha[x]))
            obs[x] += sa
            exp[x] += n * p
            obs[y] += n - sa
            exp[y] += n * (1.0 - p)
        steps = {}
        for e in entities:
            if exp[e] > 0.0 and obs[e] > 0.0:
                steps[e] = _m.log(obs[e] / exp[e])
            else:
                steps[e] = 0.0
        m = sum(steps.values()) / len(steps)
        for e in entities:
            alpha[e] += steps[e] - m
        if max(abs(v - m) for v in steps.values()) < tol:
            break
    return alpha


def elo_from_logstrength(a):
    """BT log-strength -> 传统 Elo 标度（仅用于报告展示）。"""
    return {e: 1500.0 + 400.0 * v / math.log(10.0) for e, v in a.items()}


def load_games():
    """返回 games: list of (a_entity, b_entity, score_a) — score_a ∈ {1.0, 0.5, 0.0}。
    winner=0 -> a 侧胜（task 148 预检验证）。"""
    games = []
    con = sqlite3.connect(T146_DB)
    cur = con.cursor()
    exps = cur.execute("select id, name from experiments order by id").fetchall()
    for eid, name in exps:
        m = re.match(r"t146-([LC]\d+)-vs-(\S+)$", name)
        assert m, f"unexpected experiment name: {name}"
        combo, opp = m.group(1), OPP_NAMES[m.group(2)][0]
        rows = cur.execute(
            "select winner, is_draw from games where experiment_id=? order by seed", (eid,)
        ).fetchall()
        for winner, is_draw in rows:
            if is_draw:
                games.append((combo, opp, 0.5))
            else:
                assert winner in (0, 1)
                games.append((combo, opp, 1.0 if winner == 0 else 0.0))
    con.close()
    con = sqlite3.connect(T141_DB)
    cur = con.cursor()
    name_map = {  # t141 实验名后缀与 t146 一致
        "t141-gard-vs-dragapult-dusknoir": "676344",
        "t141-gard-vs-joltik": "677291",
        "t141-gard-vs-grimmsnarl": "711855",
        "t141-gard-vs-gholdengo-dudun": "711850",
    }
    exps = cur.execute("select id, name from experiments order by id").fetchall()
    for eid, name in exps:
        opp = name_map[name]
        rows = cur.execute(
            "select winner, is_draw from games where experiment_id=? order by seed", (eid,)
        ).fetchall()
        for winner, is_draw in rows:
            if is_draw:
                games.append((BASE, opp, 0.5))
            else:
                assert winner in (0, 1)
                games.append((BASE, opp, 1.0 if winner == 0 else 0.0))
    con.close()
    return games


def fit_elo(games, entities):
    ratings = {e: R0 for e in entities}
    order = sorted(range(len(games)), key=lambda i: (games[i][0], games[i][1], i))
    for _ in range(N_PASSES):
        delta_max = 0.0
        for i in order:
            a, b, sa = games[i]
            ea = 1.0 / (1.0 + 10.0 ** ((ratings[b] - ratings[a]) / 400.0))
            da = K_ELO * (sa - ea)
            ratings[a] += da
            ratings[b] -= da
            delta_max = max(delta_max, abs(da))
        if delta_max < 1e-9:
            break
    return ratings


def expected(ra, rb):
    return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))


def score_combos(ratings, weights):
    """weights: {opp: w}（已归一）。返回 {combo: field 加权期望胜率}。"""
    return {
        c: sum(w * expected(ratings[c], ratings[o]) for o, w in weights.items())
        for c in COMBOS
    }


def spearman(xs, ys):
    n = len(xs)

    def ranks(vs):
        idx = sorted(range(n), key=lambda i: vs[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vs[idx[j + 1]] == vs[idx[i]]:
                j += 1
            for k in range(i, j + 1):
                r[idx[k]] = (i + j) / 2.0 + 1.0
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    vy = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    return cov / (vx * vy) if vx > 0 and vy > 0 else 0.0


def main():
    games = load_games()
    n_draws = sum(1 for g in games if g[2] == 0.5)
    print(f"games loaded: {len(games)} (draws={n_draws})")

    labels = {}
    for line in LABELS_CSV.read_text(encoding="utf-8").splitlines()[1:]:
        combo, cell, wr, d, p, mean, label = line.split(",")
        labels.setdefault(combo, {"cells": {}, "mean": float(mean), "label": label})
        labels[combo]["cells"][cell] = float(d)

    # field 权重（四对手内归一）
    snap = json.loads(FIELD_SNAP.read_text(encoding="utf-8"))
    shares = {d["group_key"]: d["value"] for d in snap["data"]}
    raw_w = {o: shares[gk] for o, gk in ((v[0], v[1]) for v in OPP_NAMES.values())}
    tot = sum(raw_w.values())
    w_field = {o: v / tot for o, v in raw_w.items()}
    w_equal = {o: 1.0 / len(raw_w) for o in raw_w}
    print("field weights (renormalized):", {o: round(w, 4) for o, w in w_field.items()})

    all_entities = [BASE] + COMBOS + list(raw_w)
    opps = list(raw_w)

    # ---- 估计子敏感性对照（预注册修正条款的证据，K 扫描留档）----
    ksweep = {}
    for kk in (32.0, 8.0, 2.0):
        globals()["K_ELO"] = kk
        rk = fit_elo(games, all_entities)
        ksweep[f"K={kk:g}"] = {
            "elo_C01": round(rk["C01"], 1),
            "elo_BASE": round(rk[BASE], 1),
            "c01_below_base": rk["C01"] < rk[BASE],
            "top1_fieldw": max(
                COMBOS, key=lambda c: sum(w_field[o] * expected(rk[c], rk[o]) for o in w_field)
            ),
        }
    globals()["K_ELO"] = K_ELO  # 复原常量

    # ---- Phase 1: in-sample（判定估计子 = BT-MLE，预注册修正条款）----
    ratings = elo_from_logstrength(bt_mle(games, all_entities))
    sc_field = score_combos(ratings, w_field)
    sc_equal = score_combos(ratings, w_equal)

    # base 的 field 分（用同一权重集）
    base_field = sum(w * expected(ratings[BASE], ratings[o]) for o, w in w_field.items())
    base_equal = sum(w * expected(ratings[BASE], ratings[o]) for o, w in w_equal.items())

    top1_field = max(sc_field, key=sc_field.get)
    top1_equal = max(sc_equal, key=sc_equal.get)

    # (a): C01 被拒（field 权判定，等权对照列）
    a_field = sc_field["C01"] < base_field
    a_equal = sc_equal["C01"] < base_equal

    # (b): top-1 标签均值 ≥ +3.6pp
    b_field = labels[top1_field]["mean"] >= CRITERION_B_FLOOR_PP
    b_equal = labels[top1_equal]["mean"] >= CRITERION_B_FLOOR_PP

    # 支撑③：score 排名 vs 标签均值排名 Spearman
    rho = spearman([sc_field[c] for c in COMBOS], [labels[c]["mean"] for c in COMBOS])

    # ---- Phase 2: LOCO（留一对手胞）----
    # 支撑指标口径：held-out 对手分取 in-sample 全量拟合值（对手强度是对手属性，
    # 3 胞拟合中无该对手任何对局；此为支撑性指标，泄漏风险仅限单个标量平移，如实记录）。
    loco = {}
    for held in opps:
        fit = [g for g in games if g[1] != held]
        # 3 胞权重归一
        w3 = {o: w_field[o] for o in opps if o != held}
        t3 = sum(w3.values())
        w3 = {o: v / t3 for o, v in w3.items()}
        r3 = elo_from_logstrength(
            bt_mle(fit, [BASE] + COMBOS + [o for o in opps if o != held])
        )
        r3[held] = ratings[held]  # in-sample 对手分（口径见上注）
        sc3 = score_combos(r3, w3)
        base3 = sum(w * expected(r3[BASE], r3[o]) for o, w in w3.items())
        c01_rejected = sc3["C01"] < base3
        # held-out 预测 vs 实际
        held_games = [g for g in games if g[1] == held]
        actual = {e: [0.0, 0] for e in [BASE] + COMBOS}
        for a, b, sa in held_games:
            actual[a][0] += sa
            actual[a][1] += 1
        ents = [BASE] + COMBOS
        pred = [expected(r3[e], r3[held]) for e in ents]
        act = [actual[e][0] / actual[e][1] for e in ents]
        rho_held = spearman(pred, act)
        loco[held] = {
            "c01_rejected_3cell": c01_rejected,
            "heldout_spearman": round(rho_held, 4),
            "top1_3cell": max(sc3, key=sc3.get),
        }

    verdict = {
        "meta": {
            "task": 148,
            "games": len(games),
            "draws": n_draws,
            "estimator": "Bradley-Terry MLE (MM, deterministic)——预注册修正条款：K=32 固定步长顺序 Elo 未收敛至自身数据的 BT-MLE（见 estimator_ksweep 留档）",
            "elo_legacy_constants": {"K": K_ELO, "R0": R0, "passes": N_PASSES},
            "field_weights": {o: round(w, 6) for o, w in w_field.items()},
            "naive_baseline": {"combo": "L01", "frozen_mean_pp": NAIVE_BASELINE_MEAN_PP},
            "criterion_b_floor_pp": CRITERION_B_FLOOR_PP,
        },
        "estimator_ksweep": ksweep,
        "phase1_insample": {
            "criterion_a_C01_rejected_fieldw": a_field,
            "criterion_a_C01_rejected_equalw": a_equal,
            "score_C01": round(sc_field["C01"], 6),
            "score_BASE": round(base_field, 6),
            "score_gap_C01_vs_BASE_pp": round((sc_field["C01"] - base_field) * 100, 2),
            "criterion_b_top1_fieldw": top1_field,
            "criterion_b_top1_label_mean_pp": labels[top1_field]["mean"],
            "criterion_b_pass_fieldw": b_field,
            "top1_equalw": top1_equal,
            "criterion_b_pass_equalw": b_equal,
            "score_ranking": {c: round(sc_field[c], 6) for c in sorted(COMBOS, key=lambda c: -sc_field[c])},
            "spearman_score_vs_label_mean": round(rho, 4),
        },
        "phase2_loco": loco,
        "labels": {c: {"mean": labels[c]["mean"], "label": labels[c]["label"]} for c in COMBOS},
    }

    n_rej = sum(1 for v in loco.values() if v["c01_rejected_3cell"])
    n_rho = sum(1 for v in loco.values() if v["heldout_spearman"] > 0)
    gate_a = a_field  # 判定以 field 权为准（预注册）
    gate_b = b_field
    verdict["verdict"] = {
        "criterion_a_pass": gate_a,
        "criterion_b_pass": gate_b,
        "support_loco_c01_rejected": f"{n_rej}/4",
        "support_loco_heldout_spearman_positive": f"{n_rho}/4",
        "GATE": "PASS" if (gate_a and gate_b) else "FAIL",
        "consequence": (
            "M15 门槛通过：task 126 按 PRD 原预注册验收标准开发"
            if (gate_a and gate_b)
            else "M15 no-go：task 127 不激活，value_guide 维持默认关（PRD 条款 4）"
        ),
    }

    out = OUT / "verdict.json"
    out.write_text(json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(verdict["verdict"], ensure_ascii=False, indent=1))
    print("phase1:", json.dumps({k: v for k, v in verdict["phase1_insample"].items()
                                 if "score_ranking" not in k}, ensure_ascii=False, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
