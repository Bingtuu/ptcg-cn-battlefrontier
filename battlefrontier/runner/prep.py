"""task 156：bfsim prep——备赛流程编排器。

一条命令驱动备赛五件套中可自动化的四件：场刷新（field-snap）→
field-pick（matchup 快照 × 新场）→（可选）报名卡组 × 池内全对手成对跑批
（同种子域 CRN）→ mod-check 判读 → 统一报告 md。败局解剖（report --autopsy）
与换卡搜索（swap-search）预算/交互驱动，报告只给下一步命令指针。

纪律进代码：实验名 `{prep名}-base-vs-{slug}`/`-mod-vs-` 同后缀配对、
全实验同 seed_start + 同 games（成对键 = 种子）、报名卡组恒 a 侧、
报告头注限定语（复用 field_pick.QUALIFIER_HEADER + 改表增益 sim 口径声明）。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, model_validator

from battlefrontier.report.field_pick import (
    QUALIFIER_HEADER,
    adapt_field_share,
    assemble_matrix,
    field_pick,
    format_field_pick,
    load_field_snapshot,
    load_matrix_snapshot,
)
from battlefrontier.report.mod_check import (
    _load_outcomes,
    _weights_for,
    format_mod_check,
    mod_check_report,
    slugify,
)
from battlefrontier.runner.experiment import (
    AGENT_TYPES,
    AgentCfg,
    AgentSides,
    DeckSides,
    DeckSourceCfg,
    ExperimentDef,
    FrozenModel,
    run_experiment,
)
from battlefrontier.runner.field_snap import export_field_snap, today_iso

PREP_HEADER_EXTRA = (
    "  · 改表增益 = 同模拟器内对比（sim 口径），不构成真实胜率预测\n"
    "  · 本报告为备赛参考流程产物：报名决策与最终卡表由牌手拍板"
)


class FieldWinCfg(FrozenModel):
    date_from: str = Field(min_length=1)
    date_to: str = Field(min_length=1)


class EntryCfg(FrozenModel):
    """报名卡组：池内中文名 + 基线 deck_id（缺省用池代表表）+ 可选改表 decklist。"""
    archetype: str = Field(min_length=1)
    deck_id: str | None = None
    modified: str | None = None

    @model_validator(mode="after")
    def _check_arm(self) -> EntryCfg:
        if not self.deck_id and not self.modified:
            raise ValueError("entry 须给 deck_id 或 modified（不猜）")
        return self


class PrepCfg(FrozenModel):
    name: str = Field(min_length=1)
    pool: str = Field(min_length=1)
    matrix_snap: str = Field(min_length=1)
    field: FieldWinCfg
    entry: EntryCfg | None = None
    games_per_cell: int = Field(default=2000, gt=0)
    seed_start: int = Field(ge=0)
    agents: str = "heuristic"

    @model_validator(mode="after")
    def _check_agents(self) -> PrepCfg:
        if self.agents not in AGENT_TYPES:
            raise ValueError(f"未知 agent type: {self.agents}（支持 {AGENT_TYPES}）")
        return self

    def load_pool(self):
        from battlefrontier.data.pool import load_target_pool
        return load_target_pool(self.pool)


def load_prep_cfg(path: str | Path) -> PrepCfg:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{Path(path).name}: prep 定义须为 YAML 映射")
    try:
        return PrepCfg.model_validate(raw)
    except ValueError as e:
        raise ValueError(f"{Path(path).name}: {e}") from e


def generate_prep_experiments(cfg: PrepCfg, pool) -> list[ExperimentDef]:
    """报名卡组 × 池内对手 → 成对实验定义（base/mod 同种子域 = CRN 配对）。

    无改表臂（entry.modified 缺省）→ 只出 base 组。
    """
    entry = cfg.entry
    if entry is None:
        raise ValueError("prep 未定义 entry（pick-only 请用 run_prep(pick_only=True)）")
    pool_entry = next((d for d in pool.decks if d.archetype == entry.archetype), None)
    if pool_entry is None:
        raise ValueError(f"报名卡组「{entry.archetype}」不在卡池（不猜）")
    if entry.modified and not Path(entry.modified).exists():
        raise ValueError(f"改表 decklist 不存在: {entry.modified}")

    agents = AgentSides(a=AgentCfg(type=cfg.agents),
                        b=AgentCfg(type=cfg.agents))
    base_a = DeckSourceCfg(source="db",
                           deck_id=entry.deck_id or pool_entry.deck_id)
    mod_a = (DeckSourceCfg(source="file", path=entry.modified)
             if entry.modified else None)

    exps: list[ExperimentDef] = []
    for opp in pool.decks:
        if opp.archetype == entry.archetype:
            continue
        slug = slugify(opp.en_archetype)
        b = DeckSourceCfg(source="db", deck_id=opp.deck_id)
        exps.append(ExperimentDef(
            name=f"{cfg.name}-base-vs-{slug}", games=cfg.games_per_cell,
            seed_start=cfg.seed_start, decks=DeckSides(a=base_a, b=b),
            agents=agents))
        if mod_a is not None:
            exps.append(ExperimentDef(
                name=f"{cfg.name}-mod-vs-{slug}", games=cfg.games_per_cell,
                seed_start=cfg.seed_start, decks=DeckSides(a=mod_a, b=b),
                agents=agents))
    return exps


def _field_section(field_out: Path, cfg: PrepCfg) -> str:
    share_raw, meta = load_field_snapshot(field_out)
    top = sorted(share_raw.items(), key=lambda kv: -kv[1])[:10]
    title = (f"## 场快照（{meta.get('date_from', '?')}..{meta.get('date_to', '?')}，"
             f"合格赛事 {meta.get('n_tournaments', '?')} 场，"
             f"as_of {meta.get('as_of', '?')}）")
    lines = [title, "",
             "| 构筑 | 份额 |", "|---|---|"]
    lines += [f"| {k} | {v * 100:.2f}% |" for k, v in top]
    return "\n".join(lines)


def _pick_section(cfg: PrepCfg, field_out: Path, pool) -> str:
    cn_to_en, en_names = {}, []
    for d in pool.decks:
        cn_to_en[d.archetype] = d.en_archetype
        en_names.append(d.en_archetype)
    share_raw, _ = load_field_snapshot(field_out)
    share = adapt_field_share(share_raw, cn_to_en)
    snap_cells, _snap_meta = load_matrix_snapshot(cfg.matrix_snap)
    matrix = assemble_matrix([], snap_cells, en_names)
    rep = field_pick(share, matrix, en_names)
    return "## 选卡参考（field-pick）\n\n" + format_field_pick(rep)


def _base_only_section(cfg: PrepCfg, results_path: Path, field_out: Path,
                       pool) -> str:
    """无改表臂：只报基线逐格读数 + 条件期望（门不适用）。"""
    entry = cfg.entry
    share_raw, _ = load_field_snapshot(field_out)
    weights = _weights_for(pool, share_raw, entry.archetype)
    base = _load_outcomes(results_path, f"{cfg.name}-base-vs-")
    lines = ["## 基线场适配读数（无改表臂——判读门不适用）", "",
             "对手 | 基线 | 场权"]
    exp = 0.0
    for d in pool.decks:
        if d.archetype == entry.archetype:
            continue
        slug = slugify(d.en_archetype)
        outcomes = base.get(slug)
        if outcomes is None:
            raise ValueError(f"缺基线实验：对手「{d.archetype}」({slug})")
        wr = sum(1 for v in outcomes.values() if v == "a") / len(outcomes)
        w = weights.get(slug, 0.0)
        exp += wr * w
        lines.append(f"{d.archetype} | {wr * 100:.1f}% | {w * 100:.1f}%")
    lines.append("")
    lines.append(f"池内条件期望（基线）：{exp * 100:.1f}%")
    return "\n".join(lines)


def _next_steps(cfg: PrepCfg, results_path: Path) -> str:
    entry = cfg.entry
    lines = ["## 下一步（人工驱动，不自动跑）", ""]
    if entry and entry.deck_id:
        lines.append(
            f"- 败局解剖：`bfsim report <实验id> --results {results_path} --autopsy`"
            "（逐对手实验 id 见结果库）")
        lines.append(
            f"- 换卡搜索：`bfsim swap-search --deck {entry.deck_id} --vs <对手deck_id>"
            " --budget <总局数> --results ...`（多刀组合须同种子对照复核）")
    lines.append("- 场数据再刷：上游新窗落地后重跑本命令（窗口推进）")
    return "\n".join(lines)


def run_prep(cfg: PrepCfg, *, db_path: str, results_path: str | Path,
             field_out: str | Path | None = None,
             out_dir: str | Path | None = None, workers: int = 1,
             pick_only: bool = False) -> str:
    """编排执行：场刷新 → field-pick →（可选）成对跑批 + 判读 → 统一报告。

    返回报告路径。报告头注限定语必嵌（ claims register 守则）。
    """
    pool = cfg.load_pool()
    results_path = Path(results_path)
    field_out = Path(field_out) if field_out else Path(
        f"results/field-snap-{cfg.name}.json")
    out_dir = Path(out_dir) if out_dir else Path(f"results/prep-{cfg.name}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # ① 场刷新
    export_field_snap(db_path, cfg.field.date_from, cfg.field.date_to, field_out)
    # ② field-pick
    sections = [_field_section(Path(field_out), cfg),
                _pick_section(cfg, Path(field_out), pool)]

    # ③ 成对跑批 + 判读
    mod_text = None
    if cfg.entry is not None and not pick_only:
        exps = generate_prep_experiments(cfg, pool)
        for defn in exps:
            run_experiment(defn, db_path, results_path, workers=workers)
        if cfg.entry.modified:
            rep = mod_check_report(
                results_path, base_prefix=f"{cfg.name}-base-vs-",
                mod_prefix=f"{cfg.name}-mod-vs-", field_path=field_out,
                pool_path=cfg.pool, entry=cfg.entry.archetype)
            mod_text = "## 改表成对判读（mod-check）\n\n" + format_mod_check(rep)
        else:
            mod_text = _base_only_section(cfg, results_path, Path(field_out), pool)
    if mod_text:
        sections.append(mod_text)

    # ④ 统一报告
    header = (f"# 备赛报告 {cfg.name}（{today_iso()}）\n\n"
              + QUALIFIER_HEADER + "\n" + PREP_HEADER_EXTRA)
    body = "\n\n".join([header] + sections + [_next_steps(cfg, results_path)])
    report_path = out_dir / "report.md"
    report_path.write_text(body, encoding="utf-8")
    return str(report_path)
