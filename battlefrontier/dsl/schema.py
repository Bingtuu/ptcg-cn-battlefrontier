"""DSL AST 层：Pydantic v2 schema（PRD §5.1 强校验：写错字段名直接报错）。

词表（原语/选择器/触发器等）一律开放字符串 + vocabularies.yml，本文件不写死；
词表成员校验在 loader 层完成（schema 保持纯结构）。
"""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CardRef(FrozenModel):
    """卡身份：name_group 主键（对齐 db 归组），card_ids 列已知印刷。"""

    name_group: str
    card_ids: tuple[str, ...] = ()


class ActionNode(FrozenModel):
    """动作原语节点：公共字段强校验；原语私有参数走 args 逃逸口。

    逐原语的 args 参数校验随原语实现（task 008+）注册，AST 层不预设。
    count：非负 int，或 counters 词表表达式（含 all）。
    choose：运行时由 Agent 选择的数量（PRD §5.2，chooser 机制 task 009）；
    与 count 互斥——count 是自动量，choose 是交互选择。
    """

    action: str
    selector: str | None = None
    count: Annotated[int, Field(ge=0)] | str | None = None
    choose: Annotated[int, Field(ge=1)] | None = None
    filters: tuple[str, ...] = ()
    destination: str | None = None
    args: dict[str, Any] = {}


class Effect(FrozenModel):
    """一个效果块：触发器 + 可选条件/限次 + 成本 + 动作序列 + 统计锚点。

    condition 为开放字符串（条件内容解析归解释器）；limit 取 limits 词表。
    attack：on_attack 触发器的招式绑定（task 012，PRD §5.1）——绑定后该招式的
    伤害与效果全部由本效果块结算；仅 on_attack 使用，其余触发器须为 None。
    """

    trigger: str
    attack: str | None = None
    condition: str | None = None
    limit: str | None = None
    cost: tuple[ActionNode, ...] = ()
    actions: tuple[ActionNode, ...]
    observe: tuple[str, ...] = ()


class CardEffectDoc(FrozenModel):
    """每卡一份 DSL 文档（一卡一 YAML）。"""

    card: CardRef
    effects: tuple[Effect, ...] = ()
