"""卡组装载：db（只读）→ 60 张 CardDef + 构筑合法性校验 + 告警汇集。

数据契约：主库只读（AGENTS.md「数据只进不出」）；装载即跑 db validate_deck
（60 张/同名/ACE SPEC 限 1 由 db 侧判定，本项目不重复实现），违规抛错不猜。
装载日期默认取当前最新 standard 快照的 effective_from（对齐 db 口径）。
"""

from dataclasses import dataclass, field

from ptcgdb.sdk import open_db

from battlefrontier.data.cards import carddef_from_db
from battlefrontier.engine.state import CardDef


@dataclass(frozen=True)
class LoadedDeck:
    """装载结果：60 张 CardDef（按 count 展开，顺序 = db 卡组条目顺序）+ 汇集告警。"""

    cards: list[CardDef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_deck(db_path: str, deck_id: str, *, fmt: str = "standard") -> LoadedDeck:
    """从 db 装载卡组。合法性校验失败抛 ValueError（带 violations 明细）。"""
    db = open_db(db_path)
    try:
        deck = db.get_deck(deck_id)

        snapshots = db.snapshots(fmt)
        if not snapshots:
            raise ValueError(f"db 无 {fmt} 合法性快照，无法确定装载日期")
        date = snapshots[-1].effective_from

        ids = [entry.card_id for entry in deck.cards for _ in range(entry.count)]
        report = db.validate_deck(ids, date, fmt)
        if not report.ok:
            raise ValueError(f"卡组 {deck_id} 构筑校验失败: {report.violations}")

        cards: list[CardDef] = []
        warnings: list[str] = []
        for entry in deck.cards:
            card_def, ws = carddef_from_db(db.get_card(entry.card_id))
            warnings.extend(ws)
            cards.extend([card_def] * entry.count)
        return LoadedDeck(cards=cards, warnings=warnings)
    finally:
        db.close()
