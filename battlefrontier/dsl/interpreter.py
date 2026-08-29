"""效果解释器（PRD §5.4）：执行 Effect 节点树，逐节点产出结构化事件。

事件流是回放 / 人工 check / 过程统计三者的共同数据源：
effect_start → effect_primitive（每原语节点一条）→ effect_observe（统计锚点）→ effect_end。
状态读写遵循引擎的不可变更新惯例（model_copy 产出新状态）。

chooser 挂起/恢复（task 009）：原语返回 NeedChoice 即中断，引擎存 PendingChoice
（扁平步骤游标）；Agent 选择后带 choices 从游标恢复续跑。Effect 树不入状态，
恢复时按 (来源卡名, effect_index) 从 card_effects 重取（单一事实源 = DSL 文档）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from battlefrontier.dsl.chooser import NeedChoice
from battlefrontier.dsl.loader import DslError
from battlefrontier.dsl.schema import ActionNode, Effect
from battlefrontier.engine.state import CardInstance, PlayerState

if TYPE_CHECKING:
    from battlefrontier.engine.core import GameEngine

# 原语注册表：词表（vocabularies.yml）是"允许的词"，本表是"已实现的词"——
# 词表有而未实现 = DslError「未实现」；不在词表 = loader 层 DslError「未知词」。
# choice 参数：非 None 表示本节点是挂起恢复（Agent 选择的 iid 集合）。
PrimitiveFn = Callable[["ExecutionContext", ActionNode, "tuple[int, ...] | None"], "dict[str, Any] | NeedChoice"]
PRIMITIVES: dict[str, PrimitiveFn] = {}


def register(name: str) -> Callable[[PrimitiveFn], PrimitiveFn]:
    """注册原语实现（task 008+ 逐个扩充）。"""

    def deco(fn: PrimitiveFn) -> PrimitiveFn:
        PRIMITIVES[name] = fn
        return fn

    return deco


class ExecutionContext:
    """单次效果执行的上下文：引擎引用 / 操控玩家 / 来源卡 / effect_id。"""

    def __init__(
        self,
        engine: GameEngine,
        player: int,
        source: CardInstance,
        effect_id: str,
        trigger: str,
    ) -> None:
        self.engine = engine
        self.player = player
        self.source = source
        self.effect_id = effect_id
        self.trigger = trigger
        # 同节点两段式选择的中间结果（task 011 chooser carry 协议，恢复时注入）
        self.carry: tuple[int, ...] = ()

    @property
    def player_state(self) -> PlayerState:
        return self.engine.state.players[self.player]

    def set_player_state(self, p: PlayerState) -> None:
        self.engine._set_player(self.player, p)

    def emit(self, kind: str, **detail: object) -> None:
        self.engine._emit(kind, self.player, **detail)


def _node_params(node: ActionNode) -> dict[str, Any]:
    """节点参数快照（空值剔除，事件流 JSON 可序列化）。"""
    return {
        k: v
        for k, v in node.model_dump(mode="json").items()
        if v is not None and v != [] and v != {} and k != "action"
    }


def flatten_steps(effect: Effect) -> list[tuple[str, ActionNode]]:
    """效果块扁平化为步骤序列：cost 段在前，actions 段在后（游标语义）。"""
    return [("cost", n) for n in effect.cost] + [("actions", n) for n in effect.actions]


def run_effect(
    ctx: ExecutionContext,
    effect: Effect,
    start: int = 0,
    choice: tuple[int, ...] | None = None,
    carry: tuple[int, ...] = (),
) -> NeedChoice | None:
    """执行效果块：成本 → 动作序列；逐节点发事件（PRD §5.4）。

    返回 NeedChoice = 挂起（游标指向未完成的节点）；返回 None = 执行完毕。
    start>0 或带 choice 为恢复执行：choice 是游标节点的选择结果，effect_start 不重复发；
    carry 是同节点此前挂起的中间选择（chooser carry 协议，task 011）。
    condition / limit 在本期仅随 effect_start 事件记录，强制约束（特性限次等）
    由引擎在行动枚举/执行层完成（task 011）。
    """
    ctx.carry = carry
    card_name = ctx.source.card.name
    if start == 0 and choice is None:  # 恢复执行（带 choice）不重复发 effect_start
        ctx.emit(
            "effect_start",
            effect_id=ctx.effect_id,
            card=card_name,
            trigger=effect.trigger,
            condition=effect.condition,
            limit=effect.limit,
        )
    steps = flatten_steps(effect)
    for cursor in range(start, len(steps)):
        phase, node = steps[cursor]
        fn = PRIMITIVES.get(node.action)
        if fn is None:
            raise DslError(
                f"原语未实现：{node.action}（词表已有此词，实现归 task 008+ 逐个注册）"
            )
        result = fn(ctx, node, choice if cursor == start else None)
        if isinstance(result, NeedChoice):
            result.cursor = cursor
            return result
        ctx.emit(
            "effect_primitive",
            effect_id=ctx.effect_id,
            card=card_name,
            phase=phase,
            action=node.action,
            params=_node_params(node),
            result=result,
        )
    for anchor in effect.observe:
        ctx.emit("effect_observe", effect_id=ctx.effect_id, anchor=anchor)
    ctx.emit("effect_end", effect_id=ctx.effect_id)
    return None
