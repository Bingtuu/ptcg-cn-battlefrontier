"""目标卡组池锁定资产 loader（task 024，M5）。

`config/target-pool.v1.yml` 是 M5/M6 的卡池事实源：WUR top-N 名单 + 代表卡组
deck_id + 完整复算口径（查询窗口/赛区/快照/rules_hash）。结构强校验，畸形显式
报错（不猜）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DECK_ID_RE = re.compile(r"^[^\s:]+:\d+$")

REQUIRED_QUERY_KEYS = (
    "window", "division", "basis", "min_n", "n_tournaments",
    "snapshot", "name_group_rules_hash",
)


class PoolEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    archetype: str = Field(min_length=1)
    wur: float = Field(gt=0)
    n: int = Field(gt=0)
    deck_id: str
    note: str = ""

    @model_validator(mode="after")
    def _check_deck_id(self) -> PoolEntry:
        if not DECK_ID_RE.match(self.deck_id):
            raise ValueError(f"deck_id 格式错误（应为「来源:数字」）: {self.deck_id}")
        return self


class TargetPool(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int
    locked_at: str
    query: dict
    decks: list[PoolEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> TargetPool:
        missing = [k for k in REQUIRED_QUERY_KEYS if k not in self.query]
        if missing:
            raise ValueError(f"query 缺复算口径字段（不猜）: {missing}")
        wurs = [d.wur for d in self.decks]
        if wurs != sorted(wurs, reverse=True):
            raise ValueError("decks 须按 WUR 降序排列")
        return self


def load_target_pool(path: str | Path) -> TargetPool:
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{p.name}: 卡组池定义须为 YAML 映射")
    try:
        return TargetPool.model_validate(raw)
    except ValueError as e:
        raise ValueError(f"{p.name}: {e}") from e
