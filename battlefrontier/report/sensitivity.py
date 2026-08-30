"""换卡敏感性报告（PRD §9，task 023）：baseline vs variants 并排 ΔWR + 显著性检验。

统计口径（与 winrate.py 一致：胜率分母 = 决定局，即完成且非平局）：

- ΔWR 95% CI（非合并 SE）：diff ± z·√(p₁(1-p₁)/n₁ + p₂(1-p₂)/n₂)；
- 显著性 = 两比例 z 检验（合并 SE，双侧），Φ 用 math.erf 手写——
  不引 scipy（公式简单，正确性靠测试内参考值对拍，见 tests/test_sensitivity.py）；
- 配对设计指「同种子区间跨组可比」，检验本身不假设逐局配对；
- n=0 不除零：CI/检验记 None，报告标注「不可用」。

meta 回显：双方实验 id / 名称 / 种子区间 / 代码+数据版本 / 局数（可复算纪律）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from battlefrontier.report.winrate import Z_95, WinrateReport, winrate_report
from battlefrontier.runner.results_db import ResultsDB


def normal_cdf(x: float) -> float:
    """标准正态 CDF：Φ(x) = ½(1 + erf(x/√2))。"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def two_proportion_z(w1: int, n1: int, w2: int,
                     n2: int) -> tuple[float | None, float | None]:
    """两比例 z 检验（合并 SE，双侧）。任一分母为 0 → (None, None)。"""
    if n1 == 0 or n2 == 0:
        return (None, None)
    p1, p2 = w1 / n1, w2 / n2
    pooled = (w1 + w2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0.0:
        return (None, None)  # 两组全胜或全负：检验无意义
    z = (p1 - p2) / se
    return (z, 2.0 * (1.0 - normal_cdf(abs(z))))


def diff_ci(w1: int, n1: int, w2: int, n2: int,
            z: float = Z_95) -> tuple[float, float] | None:
    """两比例之差的 CI（非合并 SE）。任一分母为 0 → None。"""
    if n1 == 0 or n2 == 0:
        return None
    p1, p2 = w1 / n1, w2 / n2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    diff = p1 - p2
    return (diff - z * se, diff + z * se)


@dataclass(frozen=True)
class VariantComparison:
    experiment_id: int
    variant: str
    report: WinrateReport
    d_wr: float                        # variant WR − baseline WR
    d_ci: tuple[float, float] | None
    z: float | None
    p: float | None

    @property
    def wr_a(self) -> float:
        return self.report.wr_a

    @property
    def wins_a(self) -> int:
        return self.report.wins_a

    @property
    def decided(self) -> int:
        return self.report.decided


@dataclass(frozen=True)
class SensitivityReport:
    base: WinrateReport
    variants: tuple[VariantComparison, ...]


def sensitivity_report(db: ResultsDB, base_id: int,
                       variant_ids: list[int]) -> SensitivityReport:
    base = winrate_report(db, base_id)
    comps: list[VariantComparison] = []
    for vid in variant_ids:
        rep = winrate_report(db, vid)
        exp = db.experiment(vid)
        z, p = two_proportion_z(rep.wins_a, rep.decided, base.wins_a, base.decided)
        comps.append(VariantComparison(
            experiment_id=vid, variant=exp["variant"] or exp["name"], report=rep,
            d_wr=rep.wr_a - base.wr_a,
            d_ci=diff_ci(rep.wins_a, rep.decided, base.wins_a, base.decided),
            z=z, p=p))
    return SensitivityReport(base=base, variants=tuple(comps))


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _signed_pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _sig_marker(p: float | None) -> str:
    if p is None:
        return "不可用"
    if p < 0.01:
        return "显著(p<0.01)"
    if p < 0.05:
        return "显著(p<0.05)"
    return "不显著"


def format_sensitivity(rep: SensitivityReport) -> str:
    """并排表：baseline 一行 + 每 variant 一行（WR/CI/ΔWR/ΔCI/z/p/显著性）。"""
    base = rep.base
    seeds = (f"{base.seed_min}..{base.seed_max}"
             if base.seed_min is not None else "（无局）")
    lines = [
        f"实验 #{base.experiment_id}「{base.name}」换卡敏感性报告",
        (f"meta：种子区间 {seeds} / 代码 {base.code_version} / 数据 {base.data_version}"
         f" / baseline 局数 {base.games_total}"),
        (f"baseline：A 胜率 {_pct(base.wr_a)}（{base.wins_a}/{base.decided} 决定局，"
         f"平 {base.draws}，失败 {base.games_failed}）"),
    ]
    for comp in rep.variants:
        r = comp.report
        if comp.d_ci is None or comp.p is None:
            lines.append(
                f"  #{comp.experiment_id} [{comp.variant}]：决定局不足"
                f"（{r.decided}），ΔWR/显著性不可用")
            continue
        lines.append(
            f"  #{comp.experiment_id} [{comp.variant}]：A 胜率 {_pct(r.wr_a)}"
            f"（{r.wins_a}/{r.decided}）｜ΔWR {_signed_pct(comp.d_wr)}"
            f"（CI {_signed_pct(comp.d_ci[0])}..{_signed_pct(comp.d_ci[1])}）"
            f"｜z={comp.z:+.2f} p={comp.p:.4g} {_sig_marker(comp.p)}")
    return "\n".join(lines)
