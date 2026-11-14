"""task 131：跑前 DSL 覆盖率门槛（run 子命令三态报告 + --strict-coverage）。

判定与 check-deck 同源（classify_dsl 共用，deck_check 改调本模块）；
只读装载产物做归类，零 Agent/DSL/引擎行为变更。strict 白名单 = 基本能量
（引擎原生支持）+ vanilla 异文本（同名有文档，装载告警已有口径）+ 无文档
纯白板卡面（无特性、招式全固定伤害——引擎原生结算语义无损，task 131 目标
口径「影响语义的无文档卡」才拒绝）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from battlefrontier.dsl.loader import CardLibrary, load_card_dir
from battlefrontier.engine.state import CardDef, Supertype
from battlefrontier.runner.experiment import DEFAULT_CARDS_DIR

DSL_COVERED = "covered"
DSL_VANILLA = "vanilla"
DSL_NO_DOC = "no_doc"


def classify_dsl(card_id: str, name: str, library: CardLibrary) -> str:
    """单卡 DSL 三态判定（与 check-deck 同一口径）：card_id 精确挂载 → covered；
    未覆盖但同名存在效果文档 → vanilla（异文本印刷合法）；同名也无文档 → no_doc。"""
    if card_id in library:
        return DSL_COVERED
    if library.by_name(name):
        return DSL_VANILLA
    return DSL_NO_DOC


@dataclass(frozen=True)
class CoverEntry:
    count: int
    name: str
    card_id: str


@dataclass(frozen=True)
class SideCoverage:
    """单侧卡组覆盖率。no_doc = 无文档且非豁免（阻断 strict）；basic_energy /
    pure_vanilla = 无文档但豁免（基本能量 / 纯白板卡面，引擎原生结算语义无损）。"""

    label: str
    total: int
    covered: tuple[CoverEntry, ...]
    vanilla: tuple[CoverEntry, ...]
    no_doc: tuple[CoverEntry, ...]
    basic_energy: tuple[CoverEntry, ...]
    pure_vanilla: tuple[CoverEntry, ...] = ()


def _is_pure_vanilla(card_def: CardDef) -> bool:
    """无文档但卡面纯白板：宝可梦、无特性、全部招式固定伤害（无效果修饰）。
    引擎按 db 招式名/伤害/费用原生结算，无 DSL 文档语义无损（不猜：训练家/
    能量卡不走此豁免——其效果就是文档本身，缺失即丢语义）。"""
    return (card_def.supertype == Supertype.POKEMON
            and not card_def.has_ability
            and all(a.damage_modifier is None for a in card_def.attacks))


def side_coverage(label: str, cards: list[CardDef],
                  library: CardLibrary) -> SideCoverage:
    """卡组侧覆盖率：按印刷聚合计数 → 三态归类（豁免项从 no_doc 中拆出）。"""
    agg: dict[str, tuple[CardDef, int]] = {}
    for c in cards:
        card_def, n = agg.get(c.card_id, (c, 0))
        agg[c.card_id] = (card_def, n + 1)
    covered, vanilla, no_doc, basic_energy, pure_vanilla = [], [], [], [], []
    for card_id in sorted(agg, key=lambda k: agg[k][0].name):
        card_def, n = agg[card_id]
        entry = CoverEntry(count=n, name=card_def.name, card_id=card_id)
        status = classify_dsl(card_id, card_def.name, library)
        if status == DSL_COVERED:
            covered.append(entry)
        elif status == DSL_VANILLA:
            vanilla.append(entry)
        elif card_def.is_basic_energy:
            basic_energy.append(entry)
        elif _is_pure_vanilla(card_def):
            pure_vanilla.append(entry)
        else:
            no_doc.append(entry)
    return SideCoverage(
        label=label, total=len(cards),
        covered=tuple(covered), vanilla=tuple(vanilla),
        no_doc=tuple(no_doc), basic_energy=tuple(basic_energy),
        pure_vanilla=tuple(pure_vanilla))


def run_coverages(defn, db_path: str,
                  cards_dir: str | Path = DEFAULT_CARDS_DIR) -> list[SideCoverage]:
    """按实验定义枚举参赛卡组（单实验 a/b；variants 含各变体；matrix 按池去重）。"""
    from battlefrontier.runner import experiment as experiment_mod

    library = load_card_dir(cards_dir)
    if defn.matrix is not None:
        from battlefrontier.data.deck import load_deck
        from battlefrontier.data.pool import load_target_pool

        pool = load_target_pool(defn.matrix.pool)
        return [
            side_coverage(f"卡组 {d.archetype}（{d.deck_id}）",
                          load_deck(db_path, d.deck_id).cards, library)
            for d in pool.decks
        ]
    prep = experiment_mod.prepare_experiment(defn, db_path, cards_dir=cards_dir)
    if not defn.variants:
        return [side_coverage("卡组 a", prep.deck_a, library),
                side_coverage("卡组 b", prep.deck_b, library)]
    covers = [
        side_coverage("baseline 卡组 a", prep.deck_a, library),
        side_coverage("baseline 卡组 b", prep.deck_b, library),
    ]
    for variant in defn.variants:
        vp = experiment_mod.prepare_variant(prep, variant, db_path,
                                            cards_dir=cards_dir)
        covers.append(side_coverage(f"variant[{variant.name}] 卡组 a",
                                    vp.deck_a, library))
        covers.append(side_coverage(f"variant[{variant.name}] 卡组 b",
                                    vp.deck_b, library))
    return covers


def strict_violations(covers: list[SideCoverage]) -> list[str]:
    """strict 阻断清单：无文档非基本能量卡，逐条指明卡组侧与卡名。"""
    return [
        f"{c.label}：{e.count} 张 {e.name}（{e.card_id}）无 DSL 文档"
        for c in covers for e in c.no_doc
    ]


def format_coverage(covers: list[SideCoverage]) -> str:
    """人读三态覆盖率报告：每侧总张数 + 三态计数（无文档含豁免细分）+ 卡名清单。"""
    lines = ["── DSL 覆盖率（跑前门槛，task 131）──"]
    for c in covers:
        n_basic = sum(e.count for e in c.basic_energy)
        n_pure = sum(e.count for e in c.pure_vanilla)
        n_block = sum(e.count for e in c.no_doc)
        lines.append(
            f"{c.label}：{c.total} 张｜覆盖 {sum(e.count for e in c.covered)} · "
            f"vanilla 异文本 {sum(e.count for e in c.vanilla)} · "
            f"无文档 {n_block + n_basic + n_pure}"
            f"（基本能量豁免 {n_basic} · 纯白板豁免 {n_pure}，阻断 {n_block}）")
        for e in c.vanilla:
            lines.append(f"  vanilla 异文本：{e.count} {e.name}（{e.card_id}）")
        for e in c.no_doc:
            lines.append(f"  无文档·阻断：{e.count} {e.name}（{e.card_id}）")
        for e in c.basic_energy:
            lines.append(f"  无文档·豁免（基本能量）：{e.count} {e.name}（{e.card_id}）")
        for e in c.pure_vanilla:
            lines.append(f"  无文档·豁免（纯白板）：{e.count} {e.name}（{e.card_id}）")
    return "\n".join(lines)
