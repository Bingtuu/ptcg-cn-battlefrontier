"""chooser 机制（task 009，PRD §5.2）：效果执行中途的运行时选择。

原语执行中需要玩家选择时返回 NeedChoice 哨兵 → 引擎挂起（phase="choice" +
GameState.pending_choice）→ 枚举合法选择行动 → Agent 选择 → 原语带选择结果恢复执行。
选择不消耗随机源（确定性硬规矩）；池在挂起瞬间解析冻结（pool_iids）。

filters 为开放字符串（loader 不校验），本模块是唯一求值点；未知词 = DslError（不猜）。
"""

from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

from battlefrontier.dsl.loader import DslError
from battlefrontier.dsl.schema import Effect
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import (
    CardInstance,
    InPlayPokemon,
    PendingChoice,
    PlayerState,
    Supertype,
)

if TYPE_CHECKING:
    from battlefrontier.engine.core import GameEngine


class NeedChoice:
    """原语挂起信号：携带选择规格（pool/filters/min~max/destination）。

    cursor 由解释器在挂起时标注（指向未完成的扁平步骤），原语自身不感知。
    carry：同节点两段式选择的中间结果（task 011，如 attach_energy 第一段选定的
    能量 iids），随挂起冻结进 PendingChoice.payload，恢复时经 ctx.carry 传回。
    """

    def __init__(
        self,
        pool: str,
        filters: tuple[str, ...] = (),
        min_choose: int = 0,
        max_choose: int = 1,
        destination: str | None = None,
        carry: tuple[int, ...] = (),
    ) -> None:
        self.pool = pool
        self.filters = filters
        self.min_choose = min_choose
        self.max_choose = max_choose
        self.destination = destination
        self.carry = carry
        self.cursor: int = -1


def _match_one(card: CardInstance, filter_word: str) -> bool:
    """单个过滤器词求值。未知词 = DslError（词表开放，扩展在此注册）。"""
    c = card.card
    if filter_word == "pokemon":
        return c.supertype == Supertype.POKEMON
    if filter_word == "basic_pokemon":
        return c.supertype == Supertype.POKEMON and c.stage == 0
    if filter_word == "energy":
        return c.supertype == Supertype.ENERGY
    if filter_word == "basic_energy":
        return c.supertype == Supertype.ENERGY and c.is_basic_energy
    if filter_word == "trainer":
        return c.supertype == Supertype.TRAINER
    if filter_word == "pokemon_or_basic_energy":
        return _match_one(card, "pokemon") or _match_one(card, "basic_energy")
    if filter_word == "energy_超":
        return c.supertype == Supertype.ENERGY and c.energy_type == "超"
    raise DslError(f"未知 filter 词 '{filter_word}'（chooser 求值点；扩展请在 dsl/chooser.py 注册）")


def _match_in_play(mon: InPlayPokemon, filter_word: str) -> bool:
    """场上宝可梦（InPlayPokemon 维度）过滤器求值。未知词 = DslError。"""
    top = mon.current.card
    if filter_word == "pokemon_超":
        return top.supertype == Supertype.POKEMON and top.energy_type == "超"
    if filter_word == "would_survive_20":
        # 「对会被昏厥的宝可梦无法使用」（精神拥抱）：放 2 个指示物（20 伤害）后不昏厥
        return mon.damage + 20 < (top.hp or 0)
    raise DslError(f"未知 in-play filter 词 '{filter_word}'（chooser 求值点；扩展请在 dsl/chooser.py 注册）")


def matches_in_play(mon: InPlayPokemon, filters: tuple[str, ...]) -> bool:
    return all(_match_in_play(mon, f) for f in filters)


def resolve_in_play_pool(p: PlayerState, filters: tuple[str, ...]) -> tuple[InPlayPokemon, ...]:
    """自己场上宝可梦候选池（战斗场 + 备战区）。"""
    mons = ([p.active] if p.active else []) + list(p.bench)
    return tuple(m for m in mons if matches_in_play(m, filters))


def matches(card: CardInstance, filters: tuple[str, ...]) -> bool:
    """filters 为 AND 语义（OR 用语义组合词，如 pokemon_or_basic_energy）。"""
    return all(_match_one(card, f) for f in filters)


def resolve_pool(
    p: PlayerState, pool: str, filters: tuple[str, ...],
    opponent: PlayerState | None = None,
) -> tuple:
    """从真实状态计算候选池（挂起瞬间调用一次，结果冻结进 PendingChoice.pool_iids）。

    own_pokemon_in_play / opponent_pokemon_any 返回 InPlayPokemon 维度（iid = 栈顶卡）；
    其余为卡区域。对手池需传 opponent（公开信息：对手场上宝可梦双方可见）。
    """
    if pool == "own_pokemon_in_play":
        return resolve_in_play_pool(p, filters)
    if pool == "opponent_pokemon_any":
        if opponent is None:
            raise DslError("opponent_pokemon_any 池需要对手状态（chooser 内部约定）")
        return resolve_in_play_pool(opponent, filters)
    if pool == "own_hand":
        cards = p.hand
    elif pool == "own_deck":
        cards = p.deck
    elif pool == "own_discard":
        cards = p.discard
    else:
        raise DslError(f"未知选择池 '{pool}'（chooser 求值点；扩展请在 dsl/chooser.py 注册）")
    return tuple(c for c in cards if matches(c, filters))


def enumerate_choices(pending: PendingChoice) -> list[Action]:
    """合法选择行动枚举：min~max 的全部 iid 子集（iid 排序保确定序）。

    min_choose=0 时空集（）即「不找/放弃」（检索类 up-to 语义）。
    """
    pool = tuple(sorted(pending.pool_iids))
    actions: list[Action] = []
    for n in range(pending.min_choose, min(pending.max_choose, len(pool)) + 1):
        for subset in combinations(pool, n):
            actions.append(Action(kind="choose", choices=subset))
    return actions


def build_pending(
    engine: GameEngine, player: int, source: CardInstance, effect_index: int,
    cursor: int, need: NeedChoice, completion: str = "trainer",
) -> PendingChoice:
    """挂起：解析池并冻结，写 pending_choice + 切 phase。"""
    pool_cards = resolve_pool(
        engine.state.players[player], need.pool, need.filters,
        opponent=engine.state.players[1 - player],
    )
    iids = tuple(
        c.current.iid if isinstance(c, InPlayPokemon) else c.iid for c in pool_cards
    )
    return PendingChoice(
        player=player, source=source, effect_index=effect_index, cursor=cursor,
        pool=need.pool, filters=need.filters,
        min_choose=need.min_choose, max_choose=need.max_choose,
        destination=need.destination,
        pool_iids=iids,
        payload=need.carry,
        completion=completion,
    )


def playable_feasible(effect: Effect, p: PlayerState, bench_full: bool) -> bool:
    """训练家卡打出前的可行性门（成本可支付 + 动作有合法落点）。

    支持的成本形式：discard own_hand choose N（手牌除本体外 ≥ N）；
    discard own_hand count=all（全弃，恒可支付）。
    支持的落点检查：search_deck destination=bench（备战区满则不可用）。
    未知形式 = DslError（不猜， DSL 编写期即暴露）。
    """
    for node in effect.cost:
        if node.action == "discard" and node.selector == "own_hand":
            if node.count == "all":
                continue  # 全弃恒可支付
            if node.choose is not None:
                if len(p.hand) - 1 < node.choose:  # 本体打出后手牌 -1
                    return False
                continue
        raise DslError(
            f"成本形式未支持：{node.action}/{node.selector}/count={node.count}/choose={node.choose}"
            f"（可行性门不猜；扩展请在 dsl/chooser.py 注册）"
        )
    if bench_full:
        for node in effect.actions:
            if node.action == "search_deck" and node.destination == "bench":
                return False
    return True


def ability_feasible(effect: Effect, p: PlayerState) -> bool:
    """特性发动前的可行性门（task 011）：关键池为空则不枚举；未知原语形式 DslError（不猜）。

    支持：attach_energy（destination=attach，能量池与目标池双侧非空）；draw（恒可行，
    抽完即止/空结算合法）。
    """
    for node in (*effect.cost, *effect.actions):
        if node.action == "attach_energy" and node.destination == "attach":
            if node.selector != "own_discard":
                raise DslError(
                    f"特性可行性门未支持 attach_energy selector={node.selector!r}（不猜）"
                )
            if not resolve_pool(p, "own_discard", node.filters):
                return False
            target_filters = tuple(node.args.get("target_filters", ()))
            if not resolve_in_play_pool(p, target_filters):
                return False
        elif node.action == "draw":
            continue  # 抽牌恒可行（牌库空抽完即止；until_hand 超出空结算）
        else:
            raise DslError(
                f"特性可行性门未支持原语 {node.action!r}（不猜；扩展请在 dsl/chooser.py 注册）"
            )
    return True
