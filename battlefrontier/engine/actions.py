"""行动模型（PRD §6.2：引擎枚举合法行动，Agent 选择，非法拒绝）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Action:
    """一个合法行动。kind 为开放字符串（词表随阶段机扩展）；iid/target 指向卡实例。

    task 037 WP2：pydantic FrozenModel → dataclass——合法行动枚举是引擎最热路径
    （MCTS rollout 每节点一次，单局百万级构造），pydantic 校验/快构造的双端开销
    在这里是纯浪费；dataclass frozen 保持同等不可变 + 值相等 + 可哈希语义。
    """

    kind: str
    iid: int | None = None
    target_iid: int | None = None
    bench_index: int | None = None
    attack_index: int = 0  # 多招式卡的招式下标（CardDef.attacks）
    choices: tuple[int, ...] = ()  # chooser 选择的 iid 集合（phase="choice"）


class IllegalActionError(Exception):
    """Agent 选择了不在 legal_actions 列表中的行动。"""
