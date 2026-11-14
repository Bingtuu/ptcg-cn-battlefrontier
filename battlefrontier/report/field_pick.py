"""task 123：metamages 式选卡器（field_pick，四期 PRD M14）。

给定 field 分布（使用率快照）+ matchup 矩阵（intl 真实格 / sim 同口径格 /
缺口 low_confidence），输出候选卡组期望胜率排序 + 蒙特卡洛 field 模拟的
排序稳定性。所有输出限「参考」定位：sim 格 = 同模拟器内；intl 格 = 国际
线上周赛 meta 弱参照——头注限定语必嵌。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

QUALIFIER_HEADER = (
    "限定语：\n"
    "  · 来源 sim 的 matchup 格 = 同模拟器内对比，不构成真实胜率预测\n"
    "  · 来源 intl 的 matchup 格 = 国际线上周赛 meta 弱参照（≠ 简中官方环境）\n"
    "  · low_confidence 格（无真实/模拟数据）按 50% 计，仅作占位"
)

MISSING_WR = 0.5  # 缺格占位胜率（不猜方向）


@dataclass(frozen=True)
class MatchupCell:
    """有向格：a 对 b 的胜率（a 视角）。source = intl|sim|missing。"""
    a: str
    b: str
    wr_a: float
    n: int = 0
    source: str = "sim"


@dataclass
class FieldPickReport:
    """选卡报告：期望胜率排序 + 蒙特卡洛排序稳定性。"""
    rows: list[dict] = field(default_factory=list)  # deck/exp_wr/mc_mean/mc_p5/mc_p95/top1_rate/low_conf_cells
    n_sim: int = 0
    n_low_conf_cells: int = 0
    field_share: dict[str, float] = field(default_factory=dict)


def load_field_distribution(path: str | Path) -> dict[str, float]:
    """field 快照（JSON：{decks: [{display_name, value}, ...]} 或裸 {名: 份额}）。

    份额自动归一化；忽略池外项由调用方决定（此处保留全部，匹配时自然过滤）。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        raw = {d["display_name"]: float(d["value"]) for d in data["data"]}
    elif isinstance(data, dict) and "decks" in data:
        raw = {d["display_name"]: float(d["value"]) for d in data["decks"]}
    elif isinstance(data, dict):
        raw = {k: float(v) for k, v in data.items()}
    else:
        raise ValueError("field 快照格式不支持（应为 JSON 对象或含 decks 数组）")
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("field 快照份额和为 0")
    return {k: v / total for k, v in raw.items()}


def assemble_matrix(intl_cells: list[MatchupCell],
                    sim_cells: list[MatchupCell],
                    pool_names: list[str]) -> dict[tuple[str, str], MatchupCell]:
    """三层合成矩阵（有向）。同一格 intl 优先；镜像格 = 1 - wr（平按 0 计）。"""
    matrix: dict[tuple[str, str], MatchupCell] = {}
    for cell in sim_cells:
        if cell.a in pool_names and cell.b in pool_names:
            matrix[(cell.a, cell.b)] = cell
    for cell in intl_cells:
        if cell.a not in pool_names or cell.b not in pool_names:
            continue
        matrix[(cell.a, cell.b)] = cell  # intl 覆盖 sim
        matrix.setdefault((cell.b, cell.a), MatchupCell(
            cell.b, cell.a, 1.0 - cell.wr_a, n=cell.n, source="intl"))
    # 反向格补全：有向格缺反向时按镜像补（同 source 降级可信）
    for (a, b), cell in list(matrix.items()):
        if (b, a) not in matrix:
            matrix[(b, a)] = MatchupCell(b, a, 1.0 - cell.wr_a, n=cell.n,
                                         source=cell.source)
    # 缺格占位
    for a in pool_names:
        for b in pool_names:
            if a != b and (a, b) not in matrix:
                matrix[(a, b)] = MatchupCell(a, b, MISSING_WR, source="missing")
    return matrix


def expected_winrate(deck: str, field_share: dict[str, float],
                     matrix: dict[tuple[str, str], MatchupCell]) -> float:
    """deck 对 field 的期望胜率 = Σ share × wr(deck vs f)（镜像不计）。"""
    return sum(share * matrix[(deck, f)].wr_a
               for f, share in field_share.items() if f != deck)


def field_pick(field_share: dict[str, float],
               matrix: dict[tuple[str, str], MatchupCell],
               pool_names: list[str],
               n_sim: int = 1000, seed: int = 123,
               concentration: float = 100.0) -> FieldPickReport:
    """蒙特卡洛 field 模拟：钉种子 Dirichlet 抖动 share × n_sim 次，
    每次重算全部候选期望胜率 → 排序稳定性统计。"""
    import numpy as np

    candidates = [d for d in pool_names]
    names = list(field_share)
    base = np.array([field_share[n] for n in names])
    rng = np.random.default_rng(seed)

    samples: list[dict[str, float]] = []
    top1_count = {c: 0 for c in candidates}
    exp_by_deck = {c: [] for c in candidates}
    for _ in range(n_sim):
        w = rng.dirichlet(base * concentration + 1e-9)
        jittered = dict(zip(names, w))
        exps = {c: sum(jittered[f] * matrix[(c, f)].wr_a
                       for f in jittered if f != c) for c in candidates}
        samples.append(exps)
        top1_count[max(exps, key=exps.get)] += 1
        for c in candidates:
            exp_by_deck[c].append(exps[c])

    n_low = sum(1 for c in matrix.values() if c.source == "missing")
    rows = []
    for c in candidates:
        arr = np.array(exp_by_deck[c])
        rows.append({
            "deck": c,
            "exp_wr": expected_winrate(c, field_share, matrix),
            "mc_mean": float(arr.mean()),
            "mc_p5": float(np.percentile(arr, 5)),
            "mc_p95": float(np.percentile(arr, 95)),
            "top1_rate": top1_count[c] / n_sim,
            "low_conf_cells": sum(1 for f in field_share if f != c
                                  and matrix[(c, f)].source == "missing"),
        })
    rows.sort(key=lambda r: -r["exp_wr"])
    return FieldPickReport(rows=rows, n_sim=n_sim,
                           n_low_conf_cells=n_low,
                           field_share=field_share)


def format_field_pick(rep: FieldPickReport) -> str:
    """人读报告：头注限定语 + 排序表。"""
    lines = [QUALIFIER_HEADER, "",
             f"选卡参考（field 蒙特卡洛 n={rep.n_sim}；缺格格数 {rep.n_low_conf_cells}）",
             "卡组 | 期望胜率 | MC均值 [P5..P95] | 登顶率 | 缺格"]
    for r in rep.rows:
        lines.append(
            f"{r['deck']} | {r['exp_wr'] * 100:.1f}% | "
            f"{r['mc_mean'] * 100:.1f}% [{r['mc_p5'] * 100:.1f}..{r['mc_p95'] * 100:.1f}%] | "
            f"{r['top1_rate'] * 100:.0f}% | {r['low_conf_cells']}")
    return "\n".join(lines)


# ── CLI 数据适配（task 123）──────────────────────────────

def pool_name_maps(pool) -> tuple[dict[str, str], list[str]]:
    """池映射：(中文名 → en名), en 名列表。"""
    cn_to_en = {d.archetype: d.en_archetype for d in pool.decks}
    return cn_to_en, [d.en_archetype for d in pool.decks]


def adapt_field_share(raw: dict[str, float], cn_to_en: dict[str, str]
                      ) -> dict[str, float]:
    """field 份额（中文名）→ en 名空间；池外项剔除后重归一（不猜）。"""
    mapped: dict[str, float] = {}
    for name, share in raw.items():
        en = cn_to_en.get(name)
        if en is not None:
            mapped[en] = mapped.get(en, 0.0) + share
    total = sum(mapped.values())
    if total <= 0:
        raise ValueError("field 快照与卡池无交集（检查池配置/快照口径）")
    return {k: v / total for k, v in mapped.items()}


def intl_cells_from_contrast(contrast) -> list[MatchupCell]:
    """pairing_contrast 输出 → MatchupCell（en 名空间有向格）。"""
    return [MatchupCell(c.archetype, c.opponent, c.winrate, n=c.n,
                        source="intl") for c in contrast.cells]


def sim_cells_from_pack(cells: list[dict],
                        cn_to_en: dict[str, str] | None = None) -> list[MatchupCell]:
    """偏差包 cells → MatchupCell（en 名空间）；无 sim_wr 的格跳过。

    偏差包 archetype 字段为中文名时经 cn_to_en 映射；映射失败的格显式报错（不猜）。
    """
    out = []
    for c in cells:
        if c.get("sim_wr") is None:
            continue
        a, b = c["archetype"], c["opponent"]
        if cn_to_en is not None:
            missing = [n for n in (a, b) if n not in cn_to_en]
            if missing:
                raise ValueError(f"偏差包含池外卡组（不猜）: {missing}")
            a, b = cn_to_en[a], cn_to_en[b]
        out.append(MatchupCell(a, b, float(c["sim_wr"]),
                               n=c.get("sim_decided", 0), source="sim"))
    return out
