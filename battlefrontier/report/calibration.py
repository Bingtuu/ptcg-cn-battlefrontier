"""M6 校准偏差表（task 030 WP3）：模拟 matchup 矩阵 vs 真实赛事（EN 对齐段）。

口径（D-030-1/2/3/5）：

- 真实侧 = db `stats_matchup` EN 对齐段（basis/window/min_n 常量钉死，meta 回显）；
- 模拟侧 = 结果库 group_name=实验定义名的 matrix 子实验（`组名::A×B` 命名，WP1 跑批）；
- 胜率分母 = 决定局（完成且非平局；平局单列剔除，失败局单列不进分母），
  对齐 report/winrate.py 既有口径；Δ = sim_wr − real_wr；
- 真实侧缺格 → real_n/real_wr/Δ = None，排序排尾，不进加权平均与 CI 覆盖率。
"""

from __future__ import annotations

from dataclasses import dataclass

from battlefrontier.data.pool import TargetPool
from battlefrontier.report.winrate import wilson_ci
from battlefrontier.runner.experiment import ExperimentDef
from battlefrontier.runner.results_db import ResultsDB

# D-030-1 真实侧口径（meta 回显 + CLI 查询参数单点来源）
REAL_BASIS = "intl_aligned"
REAL_DATE_FROM = "2025-04-11"
REAL_DATE_TO = "2025-08-31"
REAL_AS_OF = "2026-10-03"   # matchup 统计不做时间衰减；as_of 仅为口径钉住回显
REAL_MIN_N = 30


@dataclass(frozen=True)
class CalibrationCell:
    """一个有向格：视角方 archetype vs opponent。"""

    archetype: str          # 池 CN 名（视角方）
    opponent: str
    en_archetype: str
    en_opponent: str
    sim_decided: int
    sim_wins: int           # 视角方胜场
    sim_draws: int
    sim_failed: int
    sim_wr: float
    sim_ci: tuple[float, float]
    real_n: int | None      # 真实侧缺格 = None
    real_wr: float | None
    delta: float | None     # sim_wr - real_wr


@dataclass(frozen=True)
class CalibrationReport:
    group_name: str
    cells: tuple[CalibrationCell, ...]            # 72 有向格，|Δ| 降序（None 排尾）
    weighted_mean_abs_delta: float | None         # 权重 = real_n；无有效格 = None
    ci_coverage: float | None                     # sim CI 覆盖 real_wr 的格占比（仅双侧有数据格）
    meta: dict                                    # 代码/数据版本、种子区间、真实侧 meta


def calibration_report(db: ResultsDB, defn: ExperimentDef, pool: TargetPool,
                       real_rows: list, real_meta: dict) -> CalibrationReport:
    """按池无向对聚合子实验 → 72 有向格；真实侧经 (en_archetype, en_opponent) 对表。

    组内同名子实验 >1 套 → ValueError 列出重复名（task 038，D-038-6：「不猜」
    口径，与缺子实验同级——静默取最新会混入口径不明的重跑数据；项目惯例
    重跑用新库文件）。
    """
    rows = db.experiments_by_group(defn.name)
    names = [r["name"] for r in rows]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(
            f"结果库组「{defn.name}」存在同名子实验 {dupes}"
            f"（不猜取最新——重跑请用新库文件）")
    exps = {r["name"]: r for r in rows}
    real = {(row.archetype, row.opponent): row for row in real_rows}

    cells: list[CalibrationCell] = []
    seeds: list[int] = []
    code_versions: list[str] = []
    data_versions: list[str] = []
    warnings: list[str] = []  # 非完成态子实验告警（task 038，D-038-4；告警不排除数据）
    for a, b in pool.matchup_pairs():
        name = f"{defn.name}::{a.archetype}×{b.archetype}"
        exp = exps.get(name)
        if exp is None:
            raise ValueError(
                f"结果库组「{defn.name}」缺少子实验「{name}」（不猜——先补跑该配对）")
        if exp["status"] != "done":
            warnings.append(
                f"子实验「{name}」status={exp['status']}（非完成态，数据为部分结果）")
        games = db.games(exp["id"])
        seeds.extend(g["seed"] for g in games)
        code_versions.append(exp["code_version"])
        data_versions.append(exp["data_version"])
        failed = sum(1 for g in games if g["error"])
        played = [g for g in games if not g["error"]]
        decided = [g for g in played if not g["is_draw"]]
        draws = len(played) - len(decided)
        wins_a = sum(1 for g in decided if g["winner"] == 0)
        for view, opp, wins in ((a, b, wins_a), (b, a, len(decided) - wins_a)):
            wr = wins / len(decided) if decided else 0.0
            row = real.get((view.en_archetype, opp.en_archetype))
            real_n = row.n if row is not None else None
            real_wr = row.winrate if row is not None else None
            cells.append(CalibrationCell(
                archetype=view.archetype, opponent=opp.archetype,
                en_archetype=view.en_archetype, en_opponent=opp.en_archetype,
                sim_decided=len(decided), sim_wins=wins, sim_draws=draws,
                sim_failed=failed, sim_wr=wr, sim_ci=wilson_ci(wins, len(decided)),
                real_n=real_n, real_wr=real_wr,
                delta=wr - real_wr if real_wr is not None else None))

    cells.sort(key=lambda c: (c.delta is None,
                              -abs(c.delta) if c.delta is not None else 0.0))
    valid = [c for c in cells if c.delta is not None]
    if valid:
        wmad = sum(abs(c.delta) * c.real_n for c in valid) / sum(c.real_n for c in valid)
        covered = sum(1 for c in valid if c.sim_ci[0] <= c.real_wr <= c.sim_ci[1])
        ci_cov = covered / len(valid)
    else:
        wmad = ci_cov = None

    code_versions = list(dict.fromkeys(code_versions))
    data_versions = list(dict.fromkeys(data_versions))
    meta = {
        "group_name": defn.name,
        "experiment": defn.name,
        "seed_min": min(seeds) if seeds else None,
        "seed_max": max(seeds) if seeds else None,
        "code_version": code_versions[0] if len(code_versions) == 1 else code_versions,
        "data_version": data_versions[0] if len(data_versions) == 1 else data_versions,
        "real": dict(real_meta),
        "warnings": warnings,
    }
    return CalibrationReport(group_name=defn.name, cells=tuple(cells),
                             weighted_mean_abs_delta=wmad, ci_coverage=ci_cov,
                             meta=meta)


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _signed_pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def format_calibration(rep: CalibrationReport) -> str:
    """文本报告：meta 全要素回显（可复算）→ 逐格行（|Δ| 降序）→ 汇总行。"""
    m = rep.meta
    real = m.get("real", {})

    def rget(k: str):  # 缺键标「未知」不报错
        return real.get(k, "未知")

    seeds = (f"{m['seed_min']}..{m['seed_max']}"
             if m.get("seed_min") is not None else "（无局）")
    lines = [
        f"M6 校准偏差表：组「{rep.group_name}」（{len(rep.cells)} 有向格，|Δ| 降序）",
        (f"meta：实验定义 {m['experiment']} / 种子区间 {seeds}"
         f" / 代码 {m['code_version']} / 数据 {m['data_version']}"),
        (f"真实侧：窗口 {rget('date_from')}..{rget('date_to')} / basis {rget('basis')}"
         f" / min_n {rget('min_n')} / n_games_used {rget('n_games_used')}"
         f" / 口径哈希 rules={rget('name_group_rules_hash')}"
         f" tiers={rget('tournament_tiers_hash')}"),
        "口径：分母 = 决定局（平局剔除单列）；失败局单列不进分母；Δ = sim − real",
    ]
    for w in m.get("warnings", []):  # 非完成态子实验告警（task 038，D-038-4）
        lines.append(f"⚠ 告警：{w}")
    for c in rep.cells:
        sim_part = (f"sim {_pct(c.sim_wr)}"
                    f"（CI {_pct(c.sim_ci[0])}..{_pct(c.sim_ci[1])}，"
                    f"n={c.sim_decided}，平 {c.sim_draws} 失 {c.sim_failed}）")
        if c.real_n is None:
            lines.append(f"{c.archetype} vs {c.opponent} | {sim_part} | 真实侧缺数据")
        else:
            lines.append(
                f"{c.archetype} vs {c.opponent} | {sim_part}"
                f" | real {_pct(c.real_wr)}（n={c.real_n}） | Δ {_signed_pct(c.delta)}")
    if rep.weighted_mean_abs_delta is None:
        lines.append("汇总：无双侧有数据格（真实侧全缺，不猜）")
    else:
        valid = [c for c in rep.cells if c.delta is not None]
        covered = sum(1 for c in valid if c.sim_ci[0] <= c.real_wr <= c.sim_ci[1])
        worst = valid[0]  # cells 已按 |Δ| 降序
        lines.append(
            f"汇总：加权平均 |Δ| {_pct(rep.weighted_mean_abs_delta)}"
            f"（权重=real_n，{len(valid)} 格）"
            f" / CI 覆盖率 {_pct(rep.ci_coverage)}（{covered}/{len(valid)}）"
            f" / 最大偏差：{worst.archetype} vs {worst.opponent}"
            f" Δ {_signed_pct(worst.delta)}")
    return "\n".join(lines)
