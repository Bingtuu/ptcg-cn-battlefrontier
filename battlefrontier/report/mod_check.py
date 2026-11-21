"""task 156：bfsim mod-check——改表成对判读（t152_gard_verdict.py 泛化产品化）。

协议（task 141/152 成对核对纪律进代码）：
- 实验命名约定 `{前缀}vs-{slug}`，slug = 对手池卡组 en_archetype 的 slugify；
  base/mod 两前缀同 slug 配对，同种子域 = 成对 CRN（配对键 = 种子）。
- 报名卡组恒为实验 a 侧；胜率 = a 侧胜局 / n（平局计入 n 不计胜）。
- 逐格 Δ + 无连续校正双侧二项配对 p（与 t152 判读脚本同式）；
  场权重 = 快照份额池内归一且剔除报名卡组自身（条件期望口径）。
- 纪律：error 局显式报错；种子缺口逐格显式列出；缺配对的池内对手显式报错。
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from math import comb
from pathlib import Path

from battlefrontier.report.field_pick import QUALIFIER_HEADER, load_field_snapshot


def slugify(en_name: str) -> str:
    """en_archetype → 实验名 slug（小写、非字母数字压 '-'）。"""
    return re.sub(r"[^a-z0-9]+", "-", en_name.lower()).strip("-")


def paired_flip_p(b01: int, b10: int) -> float:
    """无连续校正双侧二项配对 p（与 t152 判读脚本同式）。

    b01 = 正向翻转数（mod a 胜 & base 非 a），b10 = 反向翻转数。
    n=0（无翻转）→ 1.0 不显著。
    """
    n = b01 + b10
    if n == 0:
        return 1.0
    p = sum(comb(n, k) for k in range(max(b01, b10), n + 1)) / 2 ** n * 2
    return min(1.0, p)


@dataclass(frozen=True)
class ModCell:
    """单对手判读格。"""
    slug: str
    opponent: str          # 池内中文名
    base_wr: float
    mod_wr: float
    delta_pp: float
    p: float
    flips: int
    n_base: int
    n_mod: int
    n_missing: int         # 配对种子缺口（对称差计数）


@dataclass(frozen=True)
class ModReport:
    cells: tuple[ModCell, ...]
    weights: dict          # slug → 场权重（池内归一、剔除报名卡组）
    base_exp: float
    mod_exp: float
    delta_pp: float
    all_positive: bool     # 门：逐格 Δ 全 > 0
    all_significant: bool  # 门：逐格 p < alpha
    zero_giveback: bool    # 门：无格 Δ < 0
    seed_gaps: dict = field(default_factory=dict)  # slug → 缺口种子数


def _load_outcomes(db_path: str | Path, prefix: str) -> dict[str, dict[int, str]]:
    """实验名前缀 → {slug: {seed: 'a'|'b'|'draw'}}。error 局显式报错。"""
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT e.name, g.seed, g.winner, g.is_draw, g.error "
            "FROM games g JOIN experiments e ON e.id = g.experiment_id "
            "WHERE e.name LIKE ?", (prefix + "%",)).fetchall()
    finally:
        con.close()
    cells: dict[str, dict[int, str]] = {}
    for name, seed, winner, draw, error in rows:
        slug = name[len(prefix):]
        if error is not None:
            raise ValueError(
                f"mod-check：实验 {name} 种子 {seed} 存在 error 局（不静默）：{error}")
        outcome = "draw" if draw else ("a" if winner == 0 else "b")
        cells.setdefault(slug, {})[int(seed)] = outcome
    return cells


def _weights_for(pool, share_raw: dict, entry: str) -> dict[str, float]:
    """场权重：池内对手（cn 名）按快照份额归一，报名卡组自身剔除。"""
    raw = {d.archetype: float(share_raw.get(d.archetype, 0.0))
           for d in pool.decks if d.archetype != entry}
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("场快照与池内对手无交集（无法加权，不猜）")
    return {slugify(d.en_archetype): v / total
            for d in pool.decks if d.archetype != entry
            for k, v in [(d.archetype, raw[d.archetype])]}


def mod_check_report(db_path: str | Path, *, base_prefix: str,
                     mod_prefix: str, field_path: str | Path,
                     pool_path: str | Path, entry: str,
                     alpha: float = 0.05) -> ModReport:
    """成对判读主入口：读结果库 + 场快照 + 池定义 → ModReport。"""
    from battlefrontier.data.pool import load_target_pool

    pool = load_target_pool(pool_path)
    if entry not in {d.archetype for d in pool.decks}:
        raise ValueError(f"报名卡组「{entry}」不在卡池（不猜）")
    share_raw, _ = load_field_snapshot(field_path)
    weights = _weights_for(pool, share_raw, entry)

    base = _load_outcomes(db_path, base_prefix)
    mod = _load_outcomes(db_path, mod_prefix)

    cells: list[ModCell] = []
    seed_gaps: dict[str, int] = {}
    for d in pool.decks:
        if d.archetype == entry:
            continue
        slug = slugify(d.en_archetype)
        rb, rm = base.get(slug), mod.get(slug)
        if rb is None or rm is None:
            raise ValueError(
                f"无配对实验：对手「{d.archetype}」({slug}) 缺 "
                f"{'base' if rb is None else 'mod'} 臂（纪律：改表核对必须成对）")
        seeds_b, seeds_m = set(rb), set(rm)
        n_missing = len(seeds_b ^ seeds_m)
        if n_missing:
            seed_gaps[slug] = n_missing
        paired = seeds_b & seeds_m
        if not paired:
            raise ValueError(f"对手「{d.archetype}」({slug}) 无重叠种子，无法成对")

        b01 = b10 = flips = 0
        for s in paired:
            vb, vm = rb[s], rm[s]
            if vb == vm:
                continue
            flips += 1
            if vm == "a" and vb != "a":
                b01 += 1
            elif vb == "a" and vm != "a":
                b10 += 1
        base_wr = sum(1 for v in rb.values() if v == "a") / len(rb)
        mod_wr = sum(1 for v in rm.values() if v == "a") / len(rm)
        cells.append(ModCell(
            slug=slug, opponent=d.archetype,
            base_wr=base_wr, mod_wr=mod_wr,
            delta_pp=(mod_wr - base_wr) * 100.0,
            p=paired_flip_p(b01, b10), flips=flips,
            n_base=len(rb), n_mod=len(rm), n_missing=n_missing))

    weights = {slug: w for slug, w in weights.items()
               if any(c.slug == slug for c in cells)}
    base_exp = sum(weights[c.slug] * c.base_wr for c in cells)
    mod_exp = sum(weights[c.slug] * c.mod_wr for c in cells)
    return ModReport(
        cells=tuple(cells), weights=weights,
        base_exp=base_exp, mod_exp=mod_exp,
        delta_pp=(mod_exp - base_exp) * 100.0,
        all_positive=all(c.delta_pp > 0 for c in cells),
        all_significant=all(c.p < alpha for c in cells),
        zero_giveback=all(c.delta_pp >= 0 for c in cells),
        seed_gaps=seed_gaps)


def format_mod_check(rep: ModReport, *, alpha: float = 0.05) -> str:
    """人读判读报告：限定语头注 + 逐格表 + 条件期望 + 三门。"""
    lines = [QUALIFIER_HEADER, "",
             "改表成对判读（sim 口径：全部数字为同模拟器内对比，不构成真实胜率预测）",
             "对手 | 基线 | 改表 | Δpp | 配对p | 场权"]
    for c in rep.cells:
        lines.append(
            f"{c.opponent} | {c.base_wr * 100:.1f}% | {c.mod_wr * 100:.1f}% | "
            f"{c.delta_pp:+.1f} | {c.p:.4f} | {rep.weights.get(c.slug, 0.0) * 100:.1f}%")
    lines.append("")
    lines.append(f"池内条件期望：基线 {rep.base_exp * 100:.1f}% / "
                 f"改表 {rep.mod_exp * 100:.1f}% / Δ {rep.delta_pp:+.1f}pp")
    lines.append(
        f"门（α={alpha}）：全正 {'✅' if rep.all_positive else '❌'} / "
        f"全显著 {'✅' if rep.all_significant else '❌'} / "
        f"零回吐 {'✅' if rep.zero_giveback else '❌'}")
    if rep.seed_gaps:
        lines.append(f"⚠ 配对种子缺口：{rep.seed_gaps}（判读强度打折）")
    return "\n".join(lines)
