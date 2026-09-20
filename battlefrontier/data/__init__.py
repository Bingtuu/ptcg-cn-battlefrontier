"""数据层：ptcgdb SDK（只读）→ CardDef / 卡组装载（PRD 架构分层最底层）。"""

from battlefrontier.data.cards import carddef_from_db
from battlefrontier.data.deck import LoadedDeck, load_deck

__all__ = ["LoadedDeck", "carddef_from_db", "load_deck"]
