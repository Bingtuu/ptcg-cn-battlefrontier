"""task 130：换卡搜索器（纯报告/实验层，零 Agent/DSL/引擎行为变更）。

方法论设计文档：`docs/digs/2026-11-14-deck-swap-search-design.md`（四问定案 +
预注册判据，先于演示跑批冻结）。本模块 = 其最小原型：

- 候选生成：槽位分类（基本能量/特殊能量/进化线位/打手单卡位/训练家位）+
  候选源（同 archetype 邻近卡组高频单卡 top-N + `--include` 手填败因触发件）；
- 过滤链（顺序即管线，拒绝必带 reason）：同印刷 → DSL 覆盖（task 115 纪律：
  换入印刷必须 covered 或豁免，vanilla 异文本拒绝）→ db validate_deck
  （60 张/同名≤4/ACE SPEC≤1，load_deck 同口径）→ 同名多印刷换出槽拒绝
  （SwapCfg.out 仅卡名，不猜印刷）；进化线剪断/能量基底偏低 = 软告警不拒绝；
- 两阶段调度（复用 runner run_group，CRN 成对同种子）：筛选档低局数扫全空间
  → 按 ΔWR 排序取 top-k → 确认档换种子区间高局数成对重验；
- 排序输出：ΔWR 95% CI（复用 sensitivity.diff_ci）+ z/p + Bonferroni α/k 与
  BH 两列校正；「候选刀位」判定 = CI 不过 0 且 |ΔWR|≥3pp 且 p_bonf<0.05
  （设计文档 §2.3/§2.4）；筛选档输出禁含「显著」宣称；
- 一切输出头注带「自对局先验」限定语（SIM_INTERPRETATION_NOTE）。
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from battlefrontier.engine.state import CardDef, Supertype
from battlefrontier.report import SIM_INTERPRETATION_NOTE
from battlefrontier.report.sensitivity import diff_ci, two_proportion_z
from battlefrontier.report.winrate import winrate_report
from battlefrontier.runner.coverage import (
    DSL_COVERED,
    DSL_VANILLA,
    _is_pure_vanilla,
    classify_dsl,
)
from battlefrontier.runner.experiment import (
    DEFAULT_CARDS_DIR,
    AgentCfg,
    AgentSides,
    DeckSides,
    DeckSourceCfg,
    ExperimentDef,
    SwapCfg,
    VariantCfg,
    run_group,
)
from battlefrontier.runner.results_db import ResultsDB

# ── 口径常量（设计文档 §1/§2/§3，改动前先改文档）────────────

SLOT_BASIC_ENERGY = "基本能量"
SLOT_SPECIAL_ENERGY = "特殊能量"
SLOT_EVOLUTION = "进化线位"
SLOT_ATTACKER = "打手单卡位"
SLOT_TRAINER = "训练家位"

SCREEN_FRAC = 0.6          # 预算分配：筛选档占比（设计文档 §3.1）
MIN_SCREEN_GAMES = 60      # 筛选档最低局数（低于此排序无意义）
MIN_CONFIRM_GAMES = 100    # 确认档最低局数
PRACTICAL_MIN_DELTA = 0.03  # 实际显著性阈值 |ΔWR|≥3pp（task 117 口径）
ALPHA = 0.05
PHASE2_SEED_OFFSET = 5_000_000  # 确认档种子区间偏移（与筛选档零重叠，防循环论证）
SIBLING_DECK_LIMIT = 50    # 邻近卡组候选源：取最近同 archetype 卡组数

SCREEN_TABLE_CAP = 20      # 筛选档表打印行数上限

SEARCH_DISCLAIMER = (
    "口径：筛选档（低局数）仅为排序描述量，不宣称任何显著性；"
    "确认档判定以 Bonferroni 校正为准（设计文档 §2.4 两阶段 gatekeeping）"
)


# ── 槽位分类（设计文档 §1.1，纯函数）──────────────────────

def slot_of(card: CardDef) -> str:
    """机械槽位分类：不引入语义判断（拆线/核心卡保护一律不做硬规则）。"""
    if card.supertype == Supertype.ENERGY:
        return SLOT_BASIC_ENERGY if card.is_basic_energy else SLOT_SPECIAL_ENERGY
    if card.supertype == Supertype.TRAINER:
        return SLOT_TRAINER
    return SLOT_EVOLUTION if card.stage >= 1 else SLOT_ATTACKER


# ── 候选源（设计文档 §1.2）────────────────────────────────

def _connect_ro(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _deck_archetype(conn: sqlite3.Connection, deck_id: str) -> str | None:
    row = conn.execute(
        "SELECT archetype_name FROM decks WHERE deck_id = ?", (deck_id,)).fetchone()
    return str(row[0]) if row else None


def candidate_in_cards(
    db_path: str | Path,
    deck_id: str,
    top_n: int,
    include: tuple[str, ...] = (),
    sibling_limit: int = SIBLING_DECK_LIMIT,
) -> tuple[list[CardDef], list[str]]:
    """候选换入单卡 = 同 archetype 邻近卡组高频 top-N（按「含卡组数 desc, 总张数 desc」）
    + `--include` 手填件（败因触发，格式「卡名 [card_id]」，`in_id` 纪律）。

    返回 (CardDef 列表, 解析告警)。全部经 db 解析为印刷级 CardDef。
    """
    from ptcgdb.sdk import open_db

    if top_n <= 0 and not include:
        raise ValueError("候选源为空（top_n=0 且无 --include），不猜：请调参")
    warnings: list[str] = []
    tally: dict[str, list[int]] = {}
    conn = _connect_ro(db_path)
    try:
        archetype = _deck_archetype(conn, deck_id)
        if archetype is None:
            raise ValueError(f"deck_id 未命中（不猜）: {deck_id}")
        siblings = [r[0] for r in conn.execute(
            "SELECT deck_id FROM decks WHERE archetype_name = ?"
            " ORDER BY fetched_at DESC LIMIT ?",
            (archetype, sibling_limit)).fetchall()]
        if siblings:
            marks = ",".join("?" * len(siblings))
            for card_id, n_decks, total in conn.execute(
                    f"SELECT card_id, COUNT(*) AS nd, SUM(count) AS tc"
                    f" FROM deck_cards WHERE deck_id IN ({marks})"
                    f" GROUP BY card_id ORDER BY nd DESC, tc DESC, card_id",
                    siblings).fetchall():
                tally[str(card_id)] = [int(n_decks), int(total)]
    finally:
        conn.close()

    ranked = sorted(tally, key=lambda c: (-tally[c][0], -tally[c][1], c))[:top_n]
    db = open_db(str(db_path))
    try:
        cards: dict[str, CardDef] = {}
        from battlefrontier.data.cards import carddef_from_db

        for card_id in ranked:
            rec = db.get_card(card_id)
            if rec is None:
                warnings.append(f"邻近卡组候选 {card_id} 未命中卡表，跳过")
                continue
            card_def, ws = carddef_from_db(rec)
            warnings.extend(ws)
            cards[card_id] = card_def
        for entry in include:
            name, _, bracket = entry.rpartition("[")
            if bracket.endswith("]"):
                card_id = bracket[:-1].strip()
                name = name.strip()
                rec = db.get_card(card_id)
                if rec is None:
                    raise ValueError(f"--include 印刷 card_id 未命中（不猜）: {card_id}")
                if rec.name_full != name:
                    raise ValueError(
                        f"--include 印刷与卡名不一致（不猜）: {card_id}"
                        f" =「{rec.name_full}」≠「{name}」")
            else:
                name = entry.strip()
                found = db.search_cards(name=name, limit=1)
                if not found:
                    raise ValueError(f"--include 卡名未命中（不猜）: {name}")
                card_id = found[0].card_id
                rec = db.get_card(card_id)
            card_def, ws = carddef_from_db(rec)
            warnings.extend(ws)
            cards[card_id] = card_def
    finally:
        db.close()
    return list(cards.values()), warnings


# ── 过滤链（设计文档 §1.3，逐 reason 计数不猜）────────────

@dataclass(frozen=True)
class SwapCandidate:
    """一个通过过滤链的 1-for-1 候选：out 印刷 ×1 → in 印刷 ×1。"""

    out_card: CardDef
    in_card: CardDef
    swap: SwapCfg


def dsl_reject_reason(card_def: CardDef, library) -> str | None:
    """DSL 覆盖关（task 115 纪律）：covered → None（通过）；豁免（基本能量/纯白板，
    task 131 同源）→ None；其余拒绝并给 reason。library 为 CardLibrary。"""
    status = classify_dsl(card_def.card_id, card_def.name, library)
    if status == DSL_COVERED:
        return None
    if status == DSL_VANILLA:
        # 同名有文档但本印刷未挂：换入即静默退化（设计文档 §1.3 第 2 关）。
        # 豁免（基本能量/纯白板）只适用于 no_doc——与 coverage.py
        # side_coverage 三态归类顺序一致（vanilla 优先于 pure_vanilla）。
        return "换入印刷未挂 DSL（同名异文本 vanilla，静默退化风险，task 115 纪律）"
    if card_def.is_basic_energy or _is_pure_vanilla(card_def):
        return None
    return "换入印刷无 DSL 文档（vanilla 静默退化风险，task 115 纪律）"


def list_deck_ids_minus_one(deck: list[CardDef], out_id: str) -> list[str]:
    """换后卡组 card_id 列表：仅移除 out 印刷的**一张**（apply_swaps out_count=1 同口径）。"""
    ids = [c.card_id for c in deck]
    ids.remove(out_id)
    return ids


def _validate_ids(db, date: str, ids: list[str]) -> list[str]:
    """赛制+结构合法关：db validate_deck（60 张/同名≤4/ACE SPEC≤1），
    装载日期 = 最新 standard 快照 effective_from（load_deck 同口径）。

    db 为调用方持有的 open_db 连接（候选链全程复用一次打开）。
    """
    report = db.validate_deck(ids, date, "standard")
    return [str(v) for v in report.violations]


def build_candidates(
    deck: list[CardDef],
    in_cards: list[CardDef],
    db_path: str | Path,
    library,
) -> tuple[list[SwapCandidate], Counter]:
    """全空间扫描：每 out 印刷位 × 每 in 印刷 → 过滤链 → (候选, reason 计数)。

    同名多印刷槽位（out 仅卡名不可指定印刷，设计文档 §1.4）整槽拒绝。
    """
    by_id: dict[str, CardDef] = {}
    for c in deck:
        by_id.setdefault(c.card_id, c)
    names_to_ids: dict[str, set[str]] = {}
    for cid, c in by_id.items():
        names_to_ids.setdefault(c.name, set()).add(cid)

    drop: Counter = Counter()
    out: list[SwapCandidate] = []
    in_seen = {c.card_id for c in in_cards}
    from ptcgdb.sdk import open_db

    db = open_db(str(db_path))
    try:
        snapshots = db.snapshots("standard")
        if not snapshots:
            raise ValueError("db 无 standard 合法性快照，无法校验候选")
        date = snapshots[-1].effective_from
        for out_id, out_card in sorted(by_id.items(), key=lambda kv: kv[1].name):
            if len(names_to_ids[out_card.name]) > 1:
                drop["换出槽同名多印刷（out_id 未支持）"] += len(in_seen)
                continue
            for in_card in in_cards:
                if in_card.card_id == out_id:
                    drop["同印刷（无意义）"] += 1
                    continue
                reason = dsl_reject_reason(in_card, library)
                if reason is not None:
                    drop[reason] += 1
                    continue
                ids = list_deck_ids_minus_one(deck, out_id)
                ids.append(in_card.card_id)
                violations = _validate_ids(db, date, ids)
                if violations:
                    drop["赛制/结构非法（60张/同名≤4/ACE SPEC≤1）"] += 1
                    continue
                out.append(SwapCandidate(
                    out_card=out_card, in_card=in_card,
                    swap=SwapCfg(side="a", out=out_card.name, out_count=1,
                                 **{"in": in_card.name}, in_count=1,
                                 in_id=in_card.card_id)))
    finally:
        db.close()
    return out, drop


def swap_warnings(deck: list[CardDef], cand: SwapCandidate) -> list[str]:
    """软告警（不拒绝，设计文档 §1.3 第 4 关）：进化线剪断 / 基本能量基底偏低。

    按「移除一张」口径（与 swap out_count=1 同）：4-of 印刷换出一张不告警。
    """
    warnings: list[str] = []
    out_id = cand.out_card.card_id
    remaining = sum(1 for c in deck if c.card_id == out_id) - 1
    if cand.out_card.stage >= 1 and remaining == 0:
        warnings.append(
            f"剪断进化线：{cand.out_card.name}（{out_id}）换出后为最后一张")
    n_basic = (sum(1 for c in deck
                   if c.supertype == Supertype.ENERGY and c.is_basic_energy)
               - (1 if cand.out_card.is_basic_energy else 0))
    if n_basic < 10:
        warnings.append(f"换出后基本能量 {n_basic} 张（<10，能量基底偏低）")
    return warnings


# ── 两阶段预算分配（设计文档 §3.1）────────────────────────

@dataclass(frozen=True)
class PhasePlan:
    screen_games: int
    confirm_games: int
    confirm_top: int


def plan_phases(budget: int, n_candidates: int, confirm_top: int = 3,
                screen_games: int | None = None,
                confirm_games: int | None = None) -> PhasePlan:
    """预算方程：g1 = ⌊B×60%/(C+1)⌋；g2 = 余量/(k+1)。显式给值则以显式为准，
    但仍校预算总量与最低局数（不猜：不足报错要求加预算或收窄候选）。"""
    if budget <= 0:
        raise ValueError("budget 必须为正（不猜）")
    if n_candidates <= 0:
        raise ValueError("候选数为 0（过滤链全灭）——请检查 --top-n/--include 或池覆盖")
    if confirm_top <= 0:
        raise ValueError("confirm_top 必须为正（不猜）")
    if screen_games is None:
        screen_games = int(budget * SCREEN_FRAC) // (n_candidates + 1)
    if confirm_games is None:
        confirm_games = (budget - (n_candidates + 1) * screen_games) // (confirm_top + 1)
    if screen_games < MIN_SCREEN_GAMES:
        raise ValueError(
            f"筛选档局数 {screen_games} < 下限 {MIN_SCREEN_GAMES}："
            f"预算 {budget} 对 {n_candidates} 个候选过薄——"
            "请加 --budget、提高 --screen-games 或收窄候选")
    if confirm_games < MIN_CONFIRM_GAMES:
        raise ValueError(
            f"确认档局数 {confirm_games} < 下限 {MIN_CONFIRM_GAMES}："
            "请加 --budget 或显式 --confirm-games")
    total = (n_candidates + 1) * screen_games + (confirm_top + 1) * confirm_games
    if total > budget:
        raise ValueError(
            f"两阶段合计 {total} 局超预算 {budget}（不猜：不静默截断）——"
            "请调 --budget/--screen-games/--confirm-games")
    return PhasePlan(screen_games=screen_games, confirm_games=confirm_games,
                     confirm_top=confirm_top)


# ── 多重比较校正（设计文档 §2.4）──────────────────────────

def bonferroni(p: float | None, k: int) -> float | None:
    return None if p is None else min(1.0, p * k)


def benjamini_hochberg(pvals: list[float | None]) -> list[float | None]:
    """BH 校正（k 个确认候选）。None 原样保留；返回与输入同序的 q 值。"""
    m = len(pvals)
    indexed = sorted(((i, p) for i, p in enumerate(pvals) if p is not None),
                     key=lambda t: t[1])
    adj = [None] * m
    running = 1.0
    for rank, (i, p) in reversed(list(enumerate(indexed, start=1))):
        running = min(running, p * m / rank)
        adj[i] = running
    return adj


# ── 排序与统计行（复用 report/sensitivity 口径）───────────

@dataclass(frozen=True)
class RankedRow:
    candidate: SwapCandidate
    variant_id: int
    d_wr: float
    d_ci: tuple[float, float] | None


@dataclass(frozen=True)
class ConfirmRow:
    candidate: SwapCandidate
    variant_id: int
    d_wr: float
    d_ci: tuple[float, float] | None
    z: float | None
    p: float | None
    p_bonf: float | None
    p_bh: float | None
    is_knife: bool


def rank_screen(base, variants: list[tuple[SwapCandidate, int, object]]
                ) -> list[RankedRow]:
    """筛选档排序：ΔWR（variant − baseline）降序。纯描述量，无显著性列。"""
    rows = []
    for cand, vid, rep in variants:
        rows.append(RankedRow(candidate=cand, variant_id=vid,
                              d_wr=rep.wr_a - base.wr_a,
                              d_ci=diff_ci(rep.wins_a, rep.decided,
                                           base.wins_a, base.decided)))
    rows.sort(key=lambda r: -r.d_wr)
    return rows


def confirm_rows(base, variants: list[tuple[SwapCandidate, int, object]]
                 ) -> list[ConfirmRow]:
    """确认档统计：ΔCI/z/p + Bonferroni 与 BH 双校正；判定以 Bonferroni 为准。"""
    stats = []
    for cand, vid, rep in variants:
        z, p = two_proportion_z(rep.wins_a, rep.decided,
                                base.wins_a, base.decided)
        stats.append((cand, vid, rep, z, p,
                      diff_ci(rep.wins_a, rep.decided,
                              base.wins_a, base.decided)))
    bh = benjamini_hochberg([s[4] for s in stats])
    k = len(stats)
    out = []
    for (cand, vid, rep, z, p, ci), q in zip(stats, bh, strict=True):
        pb = bonferroni(p, k)
        is_knife = (ci is not None and pb is not None
                    and (ci[0] > 0 or ci[1] < 0)
                    and abs(rep.wr_a - base.wr_a) >= PRACTICAL_MIN_DELTA
                    and pb < ALPHA)
        out.append(ConfirmRow(candidate=cand, variant_id=vid,
                              d_wr=rep.wr_a - base.wr_a, d_ci=ci, z=z, p=p,
                              p_bonf=pb, p_bh=q, is_knife=is_knife))
    out.sort(key=lambda r: -r.d_wr)
    return out


# ── 搜索主流程（两阶段 run_group 调度）────────────────────

@dataclass
class SwapSearchReport:
    deck_id: str
    vs_id: str
    budget: int
    seed_start: int
    plan: PhasePlan
    candidates: list[SwapCandidate]
    drop_reasons: Counter
    warnings: list[str]
    screen_ids: list[int]
    screen_rows: list[RankedRow]
    confirm_ids: list[int]
    confirm: list[ConfirmRow]
    results_path: str
    soft_warnings: list[str] = field(default_factory=list)


def _definition_yaml(defn: ExperimentDef) -> str:
    return yaml.safe_dump(defn.model_dump(by_alias=True, mode="json"),
                          allow_unicode=True, sort_keys=True)


def _make_defn(name: str, deck_id: str, vs_id: str, games: int, seed_start: int,
               candidates: list[SwapCandidate], agent_type: str) -> ExperimentDef:
    return ExperimentDef(
        name=name, games=games, seed_start=seed_start,
        decks=DeckSides(
            a=DeckSourceCfg(source="db", deck_id=deck_id),
            b=DeckSourceCfg(source="db", deck_id=vs_id),
        ),
        agents=AgentSides(a=AgentCfg(type=agent_type),
                          b=AgentCfg(type=agent_type)),
        variants=[VariantCfg(name=f"c{i:03d}", swaps=[c.swap])
                  for i, c in enumerate(candidates)],
    )


def run_swap_search(
    *, deck_id: str, vs_id: str, budget: int, db_path: str,
    results_path: str | Path, seed_start: int = 470000,
    confirm_top: int = 3, screen_games: int | None = None,
    confirm_games: int | None = None, top_n: int = 12,
    include: tuple[str, ...] = (), agent_type: str = "heuristic",
    workers: int = 1, cards_dir: str | Path = DEFAULT_CARDS_DIR,
    name: str | None = None,
) -> SwapSearchReport:
    """两阶段换卡搜索（设计文档 §3）：筛选档扫全空间 → top-k 确认档换种子重验。"""
    from battlefrontier.data.deck import load_deck
    from battlefrontier.dsl.loader import load_card_dir

    search_name = name or (
        f"swapsearch-{deck_id.split(':')[-1]}-vs-{vs_id.split(':')[-1]}")
    base_deck = load_deck(db_path, deck_id).cards  # 合法性由 db 装载层担保
    library = load_card_dir(cards_dir)
    in_cards, src_warnings = candidate_in_cards(db_path, deck_id, top_n, include)
    candidates, drop = build_candidates(base_deck, in_cards, db_path, library)
    if not candidates:
        raise ValueError("过滤链全灭：无候选通过（见 drop reason 计数，不猜）")
    plan = plan_phases(budget, len(candidates), confirm_top,
                       screen_games, confirm_games)

    warnings: list[str] = list(src_warnings)

    # 阶段 1：筛选档（CRN 成对：baseline + 全部候选同种子区间）
    defn1 = _make_defn(f"{search_name}-s1", deck_id, vs_id,
                       plan.screen_games, seed_start, candidates, agent_type)
    screen_ids, ws1 = run_group(defn1, db_path, results_path, workers=workers,
                                cards_dir=cards_dir,
                                definition_yaml=_definition_yaml(defn1))
    warnings.extend(f"[s1] {w}" for w in ws1)

    db = ResultsDB(results_path)
    try:
        base1 = winrate_report(db, screen_ids[0])
        reps1 = [(cand, vid, winrate_report(db, vid))
                 for cand, vid in zip(candidates, screen_ids[1:], strict=True)]
    finally:
        db.close()
    rows = rank_screen(base1, reps1)
    top = rows[:plan.confirm_top]
    top_cands = [r.candidate for r in top]

    # 阶段 2：确认档（换种子区间，仍组内 CRN 成对；不放大筛选档噪声）
    seed2 = seed_start + PHASE2_SEED_OFFSET
    defn2 = _make_defn(f"{search_name}-s2", deck_id, vs_id,
                       plan.confirm_games, seed2, top_cands, agent_type)
    confirm_ids, ws2 = run_group(defn2, db_path, results_path, workers=workers,
                                 cards_dir=cards_dir,
                                 definition_yaml=_definition_yaml(defn2))
    warnings.extend(f"[s2] {w}" for w in ws2)

    db = ResultsDB(results_path)
    try:
        base2 = winrate_report(db, confirm_ids[0])
        reps2 = [(cand, vid, winrate_report(db, vid))
                 for cand, vid in zip(top_cands, confirm_ids[1:], strict=True)]
    finally:
        db.close()
    conf = confirm_rows(base2, reps2)

    soft: list[str] = []
    for r in rows:
        soft.extend(swap_warnings(base_deck, r.candidate))

    return SwapSearchReport(
        deck_id=deck_id, vs_id=vs_id, budget=budget, seed_start=seed_start,
        plan=plan, candidates=candidates, drop_reasons=drop,
        warnings=warnings, screen_ids=screen_ids, screen_rows=rows,
        confirm_ids=confirm_ids, confirm=conf,
        results_path=str(results_path), soft_warnings=soft)


# ── 输出（限定语头注 + 排序表）────────────────────────────

def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _signed_pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _ci_text(ci: tuple[float, float] | None) -> str:
    if ci is None:
        return "不可用"
    return f"{_signed_pct(ci[0])}..{_signed_pct(ci[1])}"


def _knife_direction_text(row) -> str:
    c = row.candidate
    return f"{c.out_card.name} → {c.in_card.name} [{c.in_card.card_id}]"


def format_swap_search(rep: SwapSearchReport) -> str:
    """人读搜索报告：限定语头注 → 管线摘要 → 筛选档排序表 → 确认档判定表。"""
    plan = rep.plan
    screen_seeds = f"{rep.seed_start}..{rep.seed_start + plan.screen_games - 1}"
    confirm_seeds = (f"{rep.seed_start + PHASE2_SEED_OFFSET}.."
                     f"{rep.seed_start + PHASE2_SEED_OFFSET + plan.confirm_games - 1}")
    lines = [
        "换卡搜索报告（task 130 原型：单卡替换 1-for-1 扫描 + 筛选→确认两阶段）",
        SIM_INTERPRETATION_NOTE,
        SEARCH_DISCLAIMER,
        (f"meta：deck = {rep.deck_id} vs {rep.vs_id} / 预算 {rep.budget} 局 / "
         f"候选 {len(rep.candidates)}（过滤拒绝 {sum(rep.drop_reasons.values())} 对）"),
        (f"筛选档：{plan.screen_games} 局 × {len(rep.candidates) + 1} 实验，"
         f"种子 {screen_seeds}（组内 CRN 成对）"),
        (f"确认档：{plan.confirm_games} 局 × {plan.confirm_top + 1} 实验，"
         f"top-{plan.confirm_top} 入选，种子 {confirm_seeds}（换种子重验）"),
        "结果库：" + rep.results_path,
        "",
        "── 过滤链拒绝 reason 计数（不猜，逐类列明）──",
    ]
    if rep.drop_reasons:
        lines.extend(f"  {reason}：{n}" for reason, n in rep.drop_reasons.most_common())
    else:
        lines.append("  （无拒绝）")
    lines.append("")
    lines.append(f"── 筛选档排序（ΔWR = 变体 − baseline，纯描述量；共 "
                 f"{len(rep.screen_rows)} 行，打印前 {SCREEN_TABLE_CAP}）──")
    for r in rep.screen_rows[:SCREEN_TABLE_CAP]:
        lines.append(
            f"  #{r.variant_id} {_knife_direction_text(r)}："
            f"ΔWR {_signed_pct(r.d_wr)}（CI {_ci_text(r.d_ci)}）")
    if len(rep.screen_rows) > SCREEN_TABLE_CAP:
        lines.append(f"  … 其余 {len(rep.screen_rows) - SCREEN_TABLE_CAP} 行见结果库")
    lines.append("")
    lines.append("── 确认档判定（Bonferroni α/k 为准；|ΔWR|≥3pp 且 CI 不过 0 且 "
                 "p_bonf<0.05 = ★候选刀位）──")
    if not rep.confirm:
        lines.append("  （无确认候选）")
    for r in rep.confirm:
        mark = "★" if r.is_knife else " "
        p_txt = f"{r.p:.4g}" if r.p is not None else "不可用"
        pb_txt = f"{r.p_bonf:.4g}" if r.p_bonf is not None else "不可用"
        q_txt = f"{r.p_bh:.4g}" if r.p_bh is not None else "不可用"
        lines.append(
            f" {mark}#{r.variant_id} {_knife_direction_text(r)}："
            f"ΔWR {_signed_pct(r.d_wr)}（CI {_ci_text(r.d_ci)}）"
            f"｜p={p_txt} p_bonf={pb_txt} p_bh={q_txt}")
    if rep.soft_warnings:
        lines.append("")
        lines.append("── 软告警（不拒绝，设计文档 §1.3）──")
        lines.extend(f"  [告警] {w}" for w in sorted(set(rep.soft_warnings)))
    if rep.warnings:
        lines.append("")
        lines.append("── 装载告警 ──")
        lines.extend(f"  [告警] {w}" for w in rep.warnings)
    lines.append("")
    lines.append(SIM_INTERPRETATION_NOTE)
    return "\n".join(lines)
