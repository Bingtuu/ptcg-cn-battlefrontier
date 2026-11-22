"""task 119：`bfsim check-deck` 卡表预检（跑前体检，零跑批）。

复用 decklist 解析/校验口径（不猜纪律与 run 装载完全一致，经
experiment._resolve_decklist_entry）：格式错误 / 未命中 / 卡名不一致 /
张数≠60 全部显式报错；DSL 状态按 card_id 精确挂载（覆盖 / 同名有文档
vanilla / 无文档）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from battlefrontier.data.cards import carddef_from_db
from battlefrontier.dsl.loader import load_card_dir
from battlefrontier.runner.coverage import classify_dsl
from battlefrontier.runner.experiment import (
    DEFAULT_CARDS_DIR,
    _resolve_decklist_entry,
    parse_decklist,
)

DSL_STATUS_LABEL = {
    "covered": "覆盖",
    "vanilla": "vanilla（同名有文档）",
    "no_doc": "无文档",
}


@dataclass
class DeckEntryCheck:
    count: int
    name: str
    card_id: str
    supertype: str
    dsl: str  # covered | vanilla | no_doc


@dataclass
class DeckCheckReport:
    entries: list[DeckEntryCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_cards(self) -> int:
        return sum(e.count for e in self.entries)


def check_decklist(db_path: str, path: str | Path,
                   cards_dir: str | Path = DEFAULT_CARDS_DIR) -> DeckCheckReport:
    """卡表体检：逐行解析（同 run 装载口径）→ 60 张校验 → DSL 状态。"""
    from battlefrontier.data.backend import open_backend

    entries = parse_decklist(Path(path).read_text(encoding="utf-8"))
    lib = load_card_dir(cards_dir)
    db = open_backend(db_path)
    rep = DeckCheckReport()
    try:
        for count, name, card_id in entries:
            resolved_id, rec = _resolve_decklist_entry(db, name, card_id)
            card_def, ws = carddef_from_db(rec)
            rep.warnings.extend(ws)
            dsl = classify_dsl(resolved_id, name, lib)
            rep.entries.append(DeckEntryCheck(
                count=count, name=name, card_id=resolved_id,
                supertype=card_def.supertype, dsl=dsl))
    finally:
        db.close()
    total = rep.total_cards
    if total != 60:
        raise ValueError(f"decklist 展开后为 {total} 张，应为 60")
    return rep


def format_deck_check(rep: DeckCheckReport) -> str:
    """人读体检报告：构成汇总 + 每卡 DSL 状态 + 装载告警。"""
    counts = {"pokemon": 0, "trainer": 0, "energy": 0}
    per_card: list[str] = []
    for e in rep.entries:
        counts[e.supertype] = counts.get(e.supertype, 0) + e.count
        per_card.append(
            f"  {e.count:>2}  {e.name} [{e.card_id}]  DSL: {DSL_STATUS_LABEL[e.dsl]}")
    lines = [
        (f"卡表体检：{rep.total_cards} 张"
         f"（宝可梦 {counts['pokemon']} / 训练家 {counts['trainer']} / 能量 {counts['energy']}）")
    ]
    lines.extend(per_card)
    lines.extend(f"  [告警] {w}" for w in rep.warnings)
    return "\n".join(lines)
