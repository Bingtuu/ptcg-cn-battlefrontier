"""效果解释器（PRD §5.4）：执行 Effect 节点树，逐节点产出结构化事件。

事件流是回放 / 人工 check / 过程统计三者的共同数据源：
effect_start → effect_primitive（每原语节点一条）→ effect_observe（统计锚点）→ effect_end。
状态读写遵循引擎的不可变更新惯例（model_copy 产出新状态）。

chooser 挂起/恢复（task 009）：原语返回 NeedChoice 即中断，引擎存 PendingChoice
（扁平步骤游标）；Agent 选择后带 choices 从游标恢复续跑。Effect 树不入状态，
恢复时按来源卡身份（card_id；朴素 dict 兼容路径按卡名）+ effect_index 从
card_effects 重取（单一事实源 = DSL 文档，task 026 精确挂载口径）。
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
        # 嵌套恢复标记（task 020）：内层效果已完成后恢复外层 copy 节点时置位，
        # copy_attack 据此只回结果、不重复执行内层
        self.inner_done: bool = False
        # 最近一次 coin_flip 结果（task 025 节点级门控 if_flip_heads/if_flip_tails 读取）；
        # 挂起恢复时经 PendingChoice.flip_result 穿透重建（choice 阶段不消耗随机源，值稳定）
        self.last_flip: bool | None = None
        # 本效果 cost 段已弃置的卡 iid（task 026 WP4，超级能量回收「无法选择因为这张
        # 卡牌的效果而被放于弃牌区的能量」）；挂起恢复时经 PendingChoice.cost_discarded
        # 穿透重建（cost 段在恢复游标之前已执行，不重跑）
        self.cost_discarded_iids: tuple[int, ...] = ()
        # 本效果块绑定的招式名（on_attack 的 attack 字段；lock_attack 原语读取，
        # task 026 WP4 裁决 2）。run_effect 每次进入时按 effect 重设（恢复同值）
        self.bound_attack: str | None = None
        # 本效果内前序 discard 节点累计弃置张数（task 026 WP5，D-WP5-1 ×N 伤害族；
        # 计数词 discarded_this_effect 读取）；挂起恢复时经 PendingChoice.discarded_count
        # 穿透重建（同 flip/cost_discarded 口径）
        self.discarded_this_effect: int = 0
        # 本效果内掷币正面次数（task 026 WP5 until_tails；计数词 flip_heads_count 读取，
        # 无前置掷币 = None → DslError 不猜，同 last_flip 口径）
        self.flip_heads_count: int | None = None
        # 造成本效果的攻击方栈顶 iid（task 026 WP6 own_ko_by_attack 触发效果；
        # place_damage_counters 的 opponent_attacker 选择器读取；非该触发 = None）
        self.attacker_iid: int | None = None

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


# 节点级运行时门控词表（task 025）：注册在代码里（同 filters/condition 纪律），
# 词表文件不含 condition 段。if_flip_* 求值读 ctx.last_flip（最近一次 coin_flip 结果）；
# if_self_active（task 026 WP5 赛富豪ex 嘉奖硬币「战斗场则额外抽1」）读来源卡是否
# 在操控方战斗场，无需前置掷币。
# if_own_ko_by_attack_during_opponent_turn（task 026 WP7 古玉鱼 嫉妒业火）读
# PlayerState.own_ko_by_attack_during_opponent_turn（精确口径跨回合标记），无需掷币。
_NODE_CONDITIONS = (
    "if_flip_heads", "if_flip_tails", "if_self_active",
    "if_own_ko_by_attack_during_opponent_turn",
)


def _node_condition_met(ctx: ExecutionContext, condition: str) -> bool:
    """节点 condition 求值：未知词 = DslError（不猜）。"""
    if condition not in _NODE_CONDITIONS:
        raise DslError(
            f"未知节点 condition 词 {condition!r}（不猜；扩展请在 dsl/interpreter.py 注册）"
        )
    if condition == "if_self_active":
        active = ctx.engine.state.players[ctx.player].active
        return active is not None and active.current.iid == ctx.source.iid
    if condition == "if_own_ko_by_attack_during_opponent_turn":
        return ctx.engine.state.players[ctx.player].own_ko_by_attack_during_opponent_turn
    if ctx.last_flip is None:
        raise DslError(
            f"节点 condition {condition!r} 需要本效果内前置 coin_flip"
            f"（无掷币结果，不猜；请在该节点前放 coin_flip 原语）"
        )
    return ctx.last_flip if condition == "if_flip_heads" else not ctx.last_flip


def run_effect(
    ctx: ExecutionContext,
    effect: Effect,
    start: int = 0,
    choice: tuple[int, ...] | None = None,
    carry: tuple[int, ...] = (),
    flip: bool | None = None,
    cost_discarded: tuple[int, ...] = (),
    discarded_count: int = 0,
) -> NeedChoice | None:
    """执行效果块：成本 → 动作序列；逐节点发事件（PRD §5.4）。

    返回 NeedChoice = 挂起（游标指向未完成的节点）；返回 None = 执行完毕。
    start>0 或带 choice 为恢复执行：choice 是游标节点的选择结果，effect_start 不重复发；
    carry 是同节点此前挂起的中间选择（chooser carry 协议，task 011）；
    flip 是挂起瞬间冻结的掷币结果（task 025，恢复时重建 ctx.last_flip）；
    cost_discarded 是挂起瞬间冻结的 cost 段弃置 iid（task 026 WP4，恢复时重建
    ctx.cost_discarded_iids）；
    discarded_count 是挂起瞬间冻结的本效果前序弃置张数（task 026 WP5，恢复时重建
    ctx.discarded_this_effect）。
    condition / limit 在本期仅随 effect_start 事件记录，强制约束（特性限次等）
    由引擎在行动枚举/执行层完成（task 011）。
    """
    ctx.carry = carry
    ctx.last_flip = flip
    ctx.cost_discarded_iids = cost_discarded
    ctx.discarded_this_effect = discarded_count
    ctx.bound_attack = effect.attack
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
        # 终局守卫（task 026 WP2）：效果中途 game_over（奖赏拿完/判负）→ 后续节点不执行
        if ctx.engine.state.phase == "game_over":
            break
        phase, node = steps[cursor]
        # 节点级门控（task 025）：condition 不满足 → 跳过该节点并落 skipped 事件；
        # 跳过的节点不占选择游标（游标 = 扁平步骤序号，跳过即越过，恢复语义不变）
        if node.condition is not None and not _node_condition_met(ctx, node.condition):
            ctx.emit(
                "effect_primitive",
                effect_id=ctx.effect_id,
                card=card_name,
                phase=phase,
                action=node.action,
                params=_node_params(node),
                result={"skipped": True, "condition": node.condition},
            )
            continue
        fn = PRIMITIVES.get(node.action)
        if fn is None:
            raise DslError(
                f"原语未实现：{node.action}（词表已有此词，实现归 task 008+ 逐个注册）"
            )
        result = fn(ctx, node, choice if cursor == start else None)
        if isinstance(result, NeedChoice):
            result.cursor = cursor
            result.flip = ctx.last_flip  # 掷币结果随挂起冻结（恢复时穿透重建）
            # cost 段弃置 iid 随挂起冻结（task 026 WP4，恢复时穿透重建）
            result.cost_discarded = ctx.cost_discarded_iids
            # 本效果前序弃置张数随挂起冻结（task 026 WP5，恢复时穿透重建）
            result.discarded_count = ctx.discarded_this_effect
            # 攻击方栈顶 iid 随挂起冻结（task 026 WP6 own_ko_by_attack 穿透，同三件套口径）
            result.attacker_iid = ctx.attacker_iid
            return result
        # cost 段弃置记录（task 026 WP4，D-WP4-3）：供 recover_from_discard 的
        # exclude_cost_discarded 池剔除（「无法选择因为这张卡牌的效果而被弃置的能量」）
        if phase == "cost" and node.action == "discard" and result.get("iids"):
            ctx.cost_discarded_iids = (*ctx.cost_discarded_iids, *result["iids"])
        # 本效果弃置张数累计（task 026 WP5，D-WP5-1）：供 damage 的
        # discarded_this_effect 计数词读取（仅前序节点——本节点之后的 damage 才得数）
        if node.action == "discard":
            ctx.discarded_this_effect += result.get("discarded", 0)
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
