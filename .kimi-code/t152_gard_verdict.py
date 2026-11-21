"""task 152 沙奈朵改表新场核对判读：基线 vs 改表 × 10 对手（同种子成对 CRN）。

逐格胜率/Δ/配对 p 值 + 新场权重（field-snap-2026-11-21 池内归一）条件期望。
"""

import json
import sqlite3
from pathlib import Path

DB = "results/t152-gard-newfield.db"
FIELD = json.loads(Path("results/field-snap-2026-11-21.json").read_text(encoding="utf-8"))

OPP = [
    ("dragapult-dusknoir", "多龙巴鲁托 黑夜魔灵"),
    ("joltik-box", "电电虫Box"),
    ("grimmsnarl", "玛俐的长毛巨魔 雪妖女"),
    ("gholdengo", "赛富豪"),
    ("gholdengo-dudun", "赛富豪 土龙节节"),
    ("raging-bolt", "猛雷鼓 厄诡椪"),
    ("charizard-pidgeot", "喷火龙 大比鸟"),
    ("zoroark", "N的索罗亚克"),
    ("dragapult", "多龙巴鲁托"),
    ("flareon-noctowl", "火伊布 猫头夜鹰"),
]

# 场权重（池内 11 套归一；沙奈朵自身份额不计入对手权重）
share = {d["group_key"]: d["value"] for d in FIELD["data"]}
opp_share = {k: v for k, v in share.items() if k != "沙奈朵"}
tot = sum(opp_share.values())
w = {k: v / tot for k, v in opp_share.items()}

con = sqlite3.connect(DB)
rows = con.execute(
    "SELECT e.name, g.seed, g.winner, g.is_draw FROM games g "
    "JOIN experiments e ON e.id = g.experiment_id "
    "WHERE e.name LIKE 't152-%'").fetchall()
con.close()

from collections import defaultdict

cells = defaultdict(dict)  # (kind, slug) -> seed -> result ('a'|'b'|'draw')
for name, seed, winner, draw in rows:
    parts = name.split("-vs-")
    kind = parts[0].replace("t152-", "")  # base / mod
    slug = parts[1]
    cells[(kind, slug)][seed] = "draw" if draw else ("a" if winner == 0 else "b")

def rate(kind, slug):
    r = cells[(kind, slug)]
    n = len(r)
    wins = sum(1 for v in r.values() if v == "a")
    return wins, n

def paired_p(base_slug, mod_slug):
    """同种子成对 McNemar（无连续校正）：返回 (翻转率, p, 翻转对数)。"""
    rb = cells[("base", base_slug)]
    rm = cells[("mod", mod_slug)]
    b01 = b10 = 0
    for s in rb:
        if s not in rm:
            continue
        vb, vm = rb[s], rm[s]
        if vb == vm:
            continue
        # 每格都从 a(沙奈朵) 视角：base 败 mod 胜之类——但 base/mod 是不同实验，
        # 各自 a 侧都是沙奈朵（基线或改表）。配对的差异 = 同种子下结果翻转。
        if vm == "a" and vb != "a":
            b01 += 1
        elif vb == "a" and vm != "a":
            b10 += 1
    n = b01 + b10
    if n == 0:
        return 0.0, 1.0, 0
    # 二项检验 p = P(X>=b01 | p=0.5) 取双侧
    from math import comb
    p = sum(comb(n, k) for k in range(max(b01, b10), n + 1)) / 2 ** n * 2
    return (b01 - b10) / n, min(1.0, p), n

print(f"{'对手':22s} {'基线':>8s} {'改表':>8s} {'Δpp':>7s} {'配对p':>8s} {'场权':>6s}")
eb = em = 0.0
for slug, arch in OPP:
    wb, nb = rate("base", slug)
    wm, nm = rate("mod", slug)
    rb, rm = wb / nb, wm / nm
    d, p, pn = paired_p(slug, slug)
    wt = w.get(arch, 0.0)
    eb += rb * wt
    em += rm * wt
    print(f"{arch:22s} {rb:8.1%} {rm:8.1%} {(rm-rb)*100:+7.1f} {p:8.4f} {wt:6.1%}")
print(f"\n池内条件期望（新场权重）：基线 {eb:.1%} / 改表 {em:.1%} / Δ {(em-eb)*100:+.1f}pp")
print("缺种子对：", {k: len(v) for k, v in cells.items() if len(v) != 2000})
