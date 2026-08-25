"""结构化事件流（PRD §5.4：回放 / 人工 check / 过程统计共用一份数据）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GameEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    turn: int
    phase: str
    player: int | None
    kind: str
    detail: dict[str, object] = {}
