"""task 156：bfsim mod-check——改表成对判读（t152_gard_verdict.py 泛化产品化）。

协议（task 141/152 成对核对纪律进代码）：
- 实验命名约定 `{前缀}vs-{slug}`，slug = 对手池卡组 en_archetype 的 slugify；
  base/mod 两前缀同 slug 配对，同种子域 = 成对 CRN（配对键 = 种子）。
- 报名卡组恒为实验 a 侧；胜率 = a 侧胜局 / n（平局计入 n 不计胜）。
- 逐格 Δ + 无连续校正双侧二项配对 p（与 t152 判读脚本同式）；
  场权重 = 快照份额池内归一且剔除报名卡组自身（条件期望口径）。
- 纪律：error 局显式报错；种子缺口逐格显式列出；缺配对的池内对手显式报错。

task 157 批次模式（--batch batch.json）：判读只认 prep 登记的实验 ID 批次
（废弃名称前缀搜全库——防同名两轮静默合批）。校验两臂 code/data version
一致、status=done、种子集 == 预期全集（来自实验定义）；缺/中断 → INCOMPLETE，
第四门 complete=False，三门强制「不可判定」；重复种子显式报错。
"""

from __future__ import annotations

import json
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
    complete: bool = True              # task 157 第四门：批次完整性
    incomplete_reasons: tuple = ()     # INCOMPLETE 逐格原因（slug → 说明）


def _row_outcome(error, draw, winner) -> str:
    if error is not None:
        raise ValueError(
            f"mod-check：存在 error 局（不静默）：{error}")
    return "draw" if draw else ("a" if winner == 0 else "b")


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
        cells.setdefault(slug, {})[int(seed)] = _row_outcome(error, draw, winner)
    return cells


def _load_outcomes_by_exp(db_path: str | Path, exp_id: int) -> dict[int, str]:
    """按实验 ID 取赛果（批次模式：不搜名称，同名旧批次零混入）。
    重复种子显式报错（拒绝静默覆盖）；error 局显式报错。"""
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT seed, winner, is_draw, error FROM games "
            "WHERE experiment_id=? ORDER BY seed", (exp_id,)).fetchall()
    finally:
        con.close()
    outcomes: dict[int, str] = {}
    for seed, winner, draw, error in rows:
        seed = int(seed)
        if seed in outcomes:
            raise ValueError(
                f"mod-check：实验 #{exp_id} 种子 {seed} 重复记录（拒绝静默覆盖）")
        outcomes[seed] = _row_outcome(error, draw, winner)
    return outcomes


def _exp_row(con, exp_id: int) -> tuple:
    row = con.execute(
        "SELECT status, code_version, data_version FROM experiments WHERE id=?",
        (exp_id,)).fetchone()
    if row is None:
        raise ValueError(f"mod-check：batch.json 登记的实验 #{exp_id} 不存在")
    return row


def _load_batch_arms(db_path: str | Path, batch_path: str | Path,
                     slugs: list[str]) -> tuple[dict, dict, dict]:
    """batch.json → (base, mod, incomplete)。
    base/mod: {slug: {seed: outcome}}；incomplete: {slug: [原因]}。
    两臂版本不一致 / 登记 ID 缺失 → 显式报错；status/种子缺口 → INCOMPLETE 原因。"""
    batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    expected = set(range(batch["expected_seeds"][0], batch["expected_seeds"][1]))
    registered = batch.get("slugs", {})
    con = sqlite3.connect(str(db_path))
    try:
        base: dict[str, dict[int, str]] = {}
        mod: dict[str, dict[int, str]] = {}
        incomplete: dict[str, list[str]] = {}
        for slug in slugs:
            arms = registered.get(slug)
            if arms is None or "base_id" not in arms or "mod_id" not in arms:
                raise ValueError(
                    f"mod-check：batch.json 未登记对手 slug「{slug}」的"
                    f" base/mod 两臂（批次缺登记，不猜）")
            row_b = _exp_row(con, arms["base_id"])
            row_m = _exp_row(con, arms["mod_id"])
            if row_b[1:] != row_m[1:]:
                raise ValueError(
                    f"mod-check：「{slug}」两臂版本不一致"
                    f"（base code/data={row_b[1:]}, mod code/data={row_m[1:]}）"
                    f"——跨版本混合拒绝判读")
            reasons: list[str] = []
            if row_b[0] != "done" or row_m[0] != "done":
                reasons.append(
                    f"status={row_b[0]}/{row_m[0]}（非 done）")
            out_b = _load_outcomes_by_exp(db_path, arms["base_id"])
            out_m = _load_outcomes_by_exp(db_path, arms["mod_id"])
            for arm, out in (("base", out_b), ("mod", out_m)):
                missing = sorted(expected - set(out))
                extra = sorted(set(out) - expected)
                if missing:
                    reasons.append(f"{arm} 臂缺种子 {missing}")
                if extra:
                    reasons.append(f"{arm} 臂超种子 {extra}")
            if reasons:
                incomplete[slug] = reasons
            base[slug], mod[slug] = out_b, out_m
        return base, mod, incomplete
    finally:
        con.close()


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


def mod_check_report(db_path: str | Path, *, base_prefix: str | None = None,
                     mod_prefix: str | None = None,
                     batch: str | Path | None = None,
                     field_path: str | Path,
                     pool_path: str | Path, entry: str,
                     alpha: float = 0.05) -> ModReport:
    """成对判读主入口：读结果库 + 场快照 + 池定义 → ModReport。

    取数两模式（task 157）：--batch 批次模式（按 prep 登记的实验 ID 取数 +
    完整性校验 + complete 第四门）∥ --base-prefix/--mod-prefix 前缀模式
    （保留，仅适用一次性干净库）。两模式互斥。
    """
    from battlefrontier.data.pool import load_target_pool

    if batch is not None and (base_prefix or mod_prefix):
        raise ValueError("mod-check：--batch 与 --base-prefix/--mod-prefix 互斥")
    if batch is None and not (base_prefix and mod_prefix):
        raise ValueError("mod-check：须给 --batch 或 --base-prefix/--mod-prefix")

    pool = load_target_pool(pool_path)
    if entry not in {d.archetype for d in pool.decks}:
        raise ValueError(f"报名卡组「{entry}」不在卡池（不猜）")
    share_raw, _ = load_field_snapshot(field_path)
    weights = _weights_for(pool, share_raw, entry)

    opp_slugs = [slugify(d.en_archetype) for d in pool.decks
                 if d.archetype != entry]
    incomplete: dict[str, list[str]] = {}
    if batch is not None:
        base, mod, incomplete = _load_batch_arms(db_path, batch, opp_slugs)
    else:
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
            if slug in incomplete:
                incomplete.setdefault(slug, []).append("无重叠种子，无法成对")
                continue
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
    complete = not incomplete
    return ModReport(
        cells=tuple(cells), weights=weights,
        base_exp=base_exp, mod_exp=mod_exp,
        delta_pp=(mod_exp - base_exp) * 100.0,
        all_positive=complete and all(c.delta_pp > 0 for c in cells),
        all_significant=complete and all(c.p < alpha for c in cells),
        zero_giveback=complete and all(c.delta_pp >= 0 for c in cells),
        seed_gaps=seed_gaps,
        complete=complete,
        incomplete_reasons=tuple(f"{slug}：{'；'.join(rs)}"
                                 for slug, rs in incomplete.items()))


def format_mod_check(rep: ModReport, *, alpha: float = 0.05) -> str:
    """人读判读报告：限定语头注 + 逐格表 + 条件期望 + 三门 + complete 门。"""
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
    if rep.complete:
        lines.append(
            f"门（α={alpha}）：全正 {'✅' if rep.all_positive else '❌'} / "
            f"全显著 {'✅' if rep.all_significant else '❌'} / "
            f"零回吐 {'✅' if rep.zero_giveback else '❌'}")
    else:
        # task 157 第四门：INCOMPLETE 时三门强制「不可判定」
        lines.append(
            f"门（α={alpha}）：全正 不可判定 / 全显著 不可判定 / "
            f"零回吐 不可判定（INCOMPLETE：批次不完整）")
        for r in rep.incomplete_reasons:
            lines.append(f"  - {r}")
    if rep.seed_gaps:
        lines.append(f"⚠ 配对种子缺口：{rep.seed_gaps}（判读强度打折）")
    return "\n".join(lines)
