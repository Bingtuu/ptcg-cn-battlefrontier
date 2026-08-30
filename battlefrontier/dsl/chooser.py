"""chooser 机制（task 009，PRD §5.2）：效果执行中途的运行时选择。

原语执行中需要玩家选择时返回 NeedChoice 哨兵 → 引擎挂起（phase="choice" +
GameState.pending_choice）→ 枚举合法选择行动 → Agent 选择 → 原语带选择结果恢复执行。
选择不消耗随机源（确定性硬规矩）；池在挂起瞬间解析冻结（pool_iids）。

filters 为开放字符串（loader 不校验），本模块是唯一求值点；未知词 = DslError（不猜）。
"""

from __future__ import annotations

from collections.abc import Callable
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
    exclude_iids：池冻结时剔除的栈顶/卡 iid（task 014，如能量转移目标排除来源）。
    flip：挂起瞬间的掷币结果（task 025 节点门控穿透），冻结进 PendingChoice.flip_result。
    """

    def __init__(
        self,
        pool: str,
        filters: tuple[str, ...] = (),
        min_choose: int = 0,
        max_choose: int = 1,
        destination: str | None = None,
        carry: tuple[int, ...] = (),
        exclude_iids: tuple[int, ...] = (),
    ) -> None:
        self.pool = pool
        self.filters = filters
        self.min_choose = min_choose
        self.max_choose = max_choose
        self.destination = destination
        self.carry = carry
        self.exclude_iids = exclude_iids
        self.cursor: int = -1
        self.flip: bool | None = None  # 解释器挂起时标注（ctx.last_flip 快照）
        # 嵌套传播（task 020 copy_attack）：内层效果挂起时标注效果定位与内层游标
        # （外层 run_effect 会覆盖 self.cursor 为外层节点游标，内层游标需另行转存）
        self.inner: tuple[str, str] | None = None
        self.inner_cursor: int = -1


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
    _TRAINER_SUBTYPE_FILTERS = {
        "trainer_item": "物品",
        "trainer_tool": "宝可梦道具",
        "trainer_supporter": "支援者",
        "trainer_stadium": "竞技场",
    }
    if filter_word in _TRAINER_SUBTYPE_FILTERS:
        return (
            c.supertype == Supertype.TRAINER
            and c.trainer_subtype == _TRAINER_SUBTYPE_FILTERS[filter_word]
        )
    if filter_word == "stage2_pokemon":
        return c.supertype == Supertype.POKEMON and c.stage == 2
    if filter_word == "evolved_pokemon":
        # 「进化宝可梦」（task 025 捕获香氛正面检索目标）：1 阶及以上
        return c.supertype == Supertype.POKEMON and c.stage >= 1
    if filter_word == "basic_pokemon_no_rule":
        # 「基础宝可梦（除拥有规则的宝可梦外）」（深钵镇：规则盒 = ex/V/光辉等）
        return (
            c.supertype == Supertype.POKEMON and c.stage == 0 and c.rule_box is None
        )
    if filter_word.startswith("evolves_from:"):
        # 参数化过滤器（task 016）：「从该宝可梦进化而来的卡牌」（学习器 进化 逐只检索）
        return c.evolves_from == filter_word.split(":", 1)[1]
    if filter_word.startswith("hp_max:"):
        # 参数化过滤器（task 024）：「HP 在 N 及以下」（友好宝芬等检索条件）
        return c.hp is not None and c.hp <= int(filter_word.split(":", 1)[1])
    raise DslError(f"未知 filter 词 '{filter_word}'（chooser 求值点；扩展请在 dsl/chooser.py 注册）")


def _match_in_play(
    mon: InPlayPokemon, filter_word: str,
    hp_of: Callable[[InPlayPokemon], int] | None = None,
) -> bool:
    """场上宝可梦（InPlayPokemon 维度）过滤器求值。未知词 = DslError。

    hp_of：有效 HP 提供者（task 015，含勇气护符等 modify_hp 修正）；缺省退回卡面 HP。
    """
    top = mon.current.card
    if filter_word == "pokemon_超":
        return top.supertype == Supertype.POKEMON and top.energy_type == "超"
    if filter_word == "would_survive_20":
        # 「对会被昏厥的宝可梦无法使用」（精神拥抱）：放 2 个指示物（20 伤害）后不昏厥
        hp = hp_of(mon) if hp_of is not None else (top.hp or 0)
        return mon.damage + 20 < hp
    if filter_word.startswith("evolve_skip:"):
        # 参数化过滤器（task 016）：跳阶进化目标 = 同链【基础】（神奇糖果）
        return top.stage == 0 and top.evolution_chain == filter_word.split(":", 1)[1]
    if filter_word == "has_damage_counters":
        # 身上有伤害指示物（亢奋脑力转放来源）
        return mon.damage > 0
    raise DslError(f"未知 in-play filter 词 '{filter_word}'（chooser 求值点；扩展请在 dsl/chooser.py 注册）")


def matches_in_play(
    mon: InPlayPokemon, filters: tuple[str, ...],
    hp_of: Callable[[InPlayPokemon], int] | None = None,
) -> bool:
    return all(_match_in_play(mon, f, hp_of=hp_of) for f in filters)


def resolve_in_play_pool(
    p: PlayerState, filters: tuple[str, ...],
    hp_of: Callable[[InPlayPokemon], int] | None = None,
) -> tuple[InPlayPokemon, ...]:
    """自己场上宝可梦候选池（战斗场 + 备战区）。"""
    mons = ([p.active] if p.active else []) + list(p.bench)
    return tuple(m for m in mons if matches_in_play(m, filters, hp_of=hp_of))


def matches(card: CardInstance, filters: tuple[str, ...]) -> bool:
    """filters 为 AND 语义（OR 用语义组合词，如 pokemon_or_basic_energy）。"""
    return all(_match_one(card, f) for f in filters)


def resolve_pool(
    p: PlayerState, pool: str, filters: tuple[str, ...],
    opponent: PlayerState | None = None,
    hp_of: Callable[[InPlayPokemon], int] | None = None,
) -> tuple:
    """从真实状态计算候选池（挂起瞬间调用一次，结果冻结进 PendingChoice.pool_iids）。

    own_pokemon_in_play / opponent_pokemon_any 返回 InPlayPokemon 维度（iid = 栈顶卡）；
    其余为卡区域。对手池需传 opponent（公开信息：对手场上宝可梦双方可见）。
    hp_of：有效 HP 提供者（task 015），仅作用于 in-play 维度的 HP 类过滤器。
    """
    if pool == "own_pokemon_in_play":
        return resolve_in_play_pool(p, filters, hp_of=hp_of)
    if pool == "own_bench":
        return tuple(m for m in p.bench if matches_in_play(m, filters, hp_of=hp_of))
    if pool == "opponent_pokemon_any":
        if opponent is None:
            raise DslError("opponent_pokemon_any 池需要对手状态（chooser 内部约定）")
        return resolve_in_play_pool(opponent, filters, hp_of=hp_of)
    if pool == "opponent_bench":
        if opponent is None:
            raise DslError("opponent_bench 池需要对手状态（chooser 内部约定）")
        return tuple(m for m in opponent.bench if matches_in_play(m, filters, hp_of=hp_of))
    if pool == "own_attached_energy":
        mons = ([p.active] if p.active else []) + list(p.bench)
        return tuple(e for m in mons for e in m.attached_energy if matches(e, filters))
    if pool == "opponent_active_attack":
        # 招式维度池（task 017 基因侵入）：元素 = 对手战斗宝可梦招式的索引（int），
        # pool_iids 语义 = 招式索引；可复制性（有伤害或有 DSL 绑定）由原语经
        # exclude_iids 预筛（resolve_pool 无 DSL 文档访问权）
        if opponent is None or opponent.active is None:
            raise DslError("opponent_active_attack 池需要对手战斗宝可梦（chooser 内部约定）")
        return tuple(range(len(opponent.active.current.card.attacks)))
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
    inner: tuple[str, str] | None = None, outer_cursor: int = -1,
    outer_choice: tuple[int, ...] = (),
) -> PendingChoice:
    """挂起：解析池并冻结，写 pending_choice + 切 phase。"""
    # 池归属方决定有效 HP 口径（勇气护符 modify_hp 按持有方求值，task 015）
    owner = 1 - player if need.pool.startswith("opponent") else player
    pool_cards = resolve_pool(
        engine.state.players[player], need.pool, need.filters,
        opponent=engine.state.players[1 - player],
        hp_of=lambda m: engine._effective_hp(m, owner),
    )
    iids = tuple(
        iid for c in pool_cards
        if (iid := c if isinstance(c, int) else (
            c.current.iid if isinstance(c, InPlayPokemon) else c.iid))
        not in need.exclude_iids
    )
    return PendingChoice(
        player=player, source=source, effect_index=effect_index, cursor=cursor,
        pool=need.pool, filters=need.filters,
        min_choose=need.min_choose, max_choose=need.max_choose,
        destination=need.destination,
        pool_iids=iids,
        payload=need.carry,
        completion=completion,
        inner=inner,
        outer_cursor=outer_cursor,
        outer_choice=outer_choice,
        flip_result=need.flip,
    )


def playable_feasible(
    effect: Effect, p: PlayerState, bench_full: bool,
    opponent: PlayerState | None = None,
    first_turn: bool = False,
) -> bool:
    """训练家卡打出前的可行性门（成本可支付 + 动作有合法落点；无效果不可使用）。

    支持的成本形式：discard own_hand choose N（手牌除本体外 ≥ N）；
    discard own_hand count=all（全弃，恒可支付）。
    落点检查：search_deck destination=bench（备战区满不可用）；
    switch opponent_bench（对手无备战不可用）；move_energy（无已附着能量或
    场上不足 2 只不可用）；evolve skip_stage（神奇糖果：非自己最初回合 +
    手牌有 stage2 + 场上有同链可进化基础）。
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
    for node in effect.actions:
        if node.action == "search_deck" and node.destination == "bench" and bench_full:
            return False
        if (
            node.action == "switch" and node.selector == "opponent_bench"
            and (opponent is None or not opponent.bench)
        ):
            return False
        if node.action == "switch" and node.selector == "own_bench" and not p.bench:
            return False  # 交替推车等 own 侧互换：无备战宝可梦不可用（task 025）
        if node.action == "move_energy":
            if not resolve_pool(p, "own_attached_energy", node.filters):
                return False
            if len(([p.active] if p.active else []) + list(p.bench)) < 2:
                return False  # 需要「其他」宝可梦作转附目标
        if node.action == "evolve":
            mode = node.args.get("mode")
            if mode != "skip_stage":
                raise DslError(f"可行性门未支持 evolve mode={mode!r}（不猜）")
            # 神奇糖果：「在自己最初的回合…无法使用」+ 手牌有【2阶进化】+
            # 场上有同链【基础】（「刚出场的宝可梦」= entered_play_this_turn 不可）
            if first_turn:
                return False
            stage2s = [c for c in p.hand if matches(c, ("stage2_pokemon",))]
            mons = ([p.active] if p.active else []) + list(p.bench)
            ok = any(
                any(
                    m.current.card.stage == 0
                    and m.current.card.evolution_chain is not None
                    and m.current.card.evolution_chain == c.card.evolution_chain
                    and m.current.iid not in p.entered_play_this_turn
                    for m in mons
                )
                for c in stage2s
            )
            if not ok:
                return False
    return True


# condition 求值注册表（开放字符串；「只有…时才可使用」类前提，task 014）。
# 签名统一 (engine, player, mon)：mon 为道具/特性持有者（task 015 道具 passive_static
# 求值用），与持有者无关的 condition 忽略该参数。
_CONDITIONS = {
    # 反击捕捉器：自己的剩余奖赏卡张数比对手多
    "own_prizes_more_than_opponent": (
        lambda engine, player, mon: len(engine.state.players[player].prizes)
        > len(engine.state.players[1 - player].prizes)
    ),
    # 勇气护符：持有者为基础宝可梦（「身上放有这张卡牌的【基础】宝可梦」）
    "holder_is_basic": (
        lambda engine, player, mon: mon is not None and mon.current.card.stage == 0
    ),
    # 化危为吉：「在上一个对手的回合，自己的宝可梦【昏厥】」（跨回合 KO 标记，task 017）
    "own_ko_during_opponent_turn": (
        lambda engine, player, mon: engine.state.players[player].own_ko_during_opponent_turn
    ),
    # 交替推车：「将自己战斗场上的【基础】宝可梦与备战宝可梦互换」（战斗场须为基础，task 025）
    "own_active_is_basic": (
        lambda engine, player, mon: (
            engine.state.players[player].active is not None
            and engine.state.players[player].active.current.card.stage == 0
        )
    ),
}


def condition_met(
    condition: str | None, engine: GameEngine, player: int,
    mon: InPlayPokemon | None = None,
) -> bool:
    """effect.condition 求值：None 恒真；词表外 = DslError（不猜）。

    参数化前缀（task 017）：`holder_has_energy:<属性>` = 持有者附着该属性能量
    （亢奋脑力「附着了【恶】能量」）。
    """
    if condition is None:
        return True
    if condition.startswith("holder_has_energy:"):
        energy_type = condition.split(":", 1)[1]
        return mon is not None and any(
            e.card.energy_type == energy_type for e in mon.attached_energy
        )
    fn = _CONDITIONS.get(condition)
    if fn is None:
        raise DslError(f"未知 condition 词 '{condition}'（chooser 求值点；扩展请在 dsl/chooser.py 注册）")
    return fn(engine, player, mon)


def ability_feasible(effect: Effect, engine: GameEngine, player: int) -> bool:
    """特性发动前的可行性门（task 011）：关键池为空则不枚举；未知原语形式 DslError（不猜）。

    支持：attach_energy（destination=attach，能量池与目标池双侧非空）；draw（恒可行，
    抽完即止/空结算合法）。HP 类过滤器走有效 HP（task 015）。
    """
    p = engine.state.players[player]
    hp_of = lambda m: engine._effective_hp(m, player)
    for node in (*effect.cost, *effect.actions):
        if node.action == "attach_energy" and node.destination == "attach":
            if node.selector != "own_discard":
                raise DslError(
                    f"特性可行性门未支持 attach_energy selector={node.selector!r}（不猜）"
                )
            if not resolve_pool(p, "own_discard", node.filters):
                return False
            target_filters = tuple(node.args.get("target_filters", ()))
            if not resolve_in_play_pool(p, target_filters, hp_of=hp_of):
                return False
        elif node.action == "draw":
            continue  # 抽牌恒可行（牌库空抽完即止；until_hand 超出空结算）
        elif node.action == "move_damage_counters":
            # 亢奋脑力（task 017）：自己场上有带伤害指示物的宝可梦（来源）+
            # 对手场上有宝可梦（转放落点）
            mons = ([p.active] if p.active else []) + list(p.bench)
            if not any(m.damage > 0 for m in mons):
                return False
            opp = engine.state.players[1 - player]
            if opp.active is None and not opp.bench:
                return False
        else:
            raise DslError(
                f"特性可行性门未支持原语 {node.action!r}（不猜；扩展请在 dsl/chooser.py 注册）"
            )
    return True
