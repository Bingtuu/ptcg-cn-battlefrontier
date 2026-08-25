"""行动模型（PRD §6.2：引擎枚举合法行动，Agent 选择，非法拒绝）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Action(BaseModel):
    """一个合法行动。kind 为开放字符串（词表随阶段机扩展）；iid/target 指向卡实例。"""

    model_config = ConfigDict(frozen=True)

    kind: str
    iid: int | None = None
    target_iid: int | None = None
    bench_index: int | None = None


class IllegalActionError(Exception):
    """Agent 选择了不在 legal_actions 列表中的行动。"""
