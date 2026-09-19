"""chooser 机制（task 009，PRD §5.2）：效果执行中途的运行时选择。

原语执行中需要玩家选择时返回 NeedChoice 哨兵 → 引擎挂起（phase="choice" +
GameState.pending_choice）→ 枚举合法选择行动 → Agent 选择 → 原语带选择结果恢复执行。
选择不消耗随机源（确定性硬规矩）；池在挂起瞬间解析冻结（pool_iids）。

filters 为开放字符串（loader 不校验），本模块是唯一求值点；未知词 = DslError（不猜）。
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import combinations, permutations
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
    cost_discarded：挂起瞬间的 cost 段弃置 iid（task 026 WP4 穿透），
    冻结进 PendingChoice.cost_discarded（解释器挂起时标注，同 flip）。
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
        # 解释器挂起时标注（ctx.cost_discarded_iids 快照，task 026 WP4）
        self.cost_discarded: tuple[int, ...] = ()
        # 解释器挂起时标注（ctx.discarded_this_effect 快照，task 026 WP5 ×N 伤害族穿透）
        self.discarded_count: int = 0
        # 解释器挂起时标注（ctx.attacker_iid 快照，task 026 WP6 own_ko_by_attack 穿透）
        self.attacker_iid: int | None = None
        # 嵌套传播（task 020 copy_attack）：内层效果挂起时标注效果定位与内层游标
        # （外层 run_effect 会覆盖 self.cursor 为外层节点游标，内层游标需另行转存）
        # inner = (card_id, 卡名, 招式名)：card_id 供 CardLibrary 精确解析（task 026）
        self.inner: tuple[str, str, str] | None = None
        self.inner_cursor: int = -1
        # task 026 WP6 选择规格扩展（三者互斥，由原语校验保证）：
        # ordered——选择顺序有语义（deck_top 牌顶 FIFO），枚举展开为排列；
        # distinct——分桶互异（distinct=energy_type），桶值随 build_pending 冻结；
        # choose_groups——组间互斥（(组池 iids, 组 cap)），各组独立 up-to 取并集
        self.ordered: bool = False
        self.distinct: str | None = None
        self.choose_groups: tuple[tuple[tuple[int, ...], int], ...] | None = None


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
    if filter_word == "pokemon_no_rule_or_basic_energy":
        # 「宝可梦（除拥有规则的宝可梦外）和基本能量」（水莲的照顾 合计回收目标）
        return (
            (c.supertype == Supertype.POKEMON and c.rule_box is None)
            or _match_one(card, "basic_energy")
        )
    if filter_word.startswith("name:"):
        # 参数化过滤器（task 026 WP1）：「夜巡灵」式按卡名指定（同名回收/检索）
        return c.name == filter_word.split(":", 1)[1]
    if filter_word.startswith("not_name:"):
        # 参数化过滤器（task 026 WP5）：「（除「百变怪」外）」式按卡名排除
        return c.name != filter_word.split(":", 1)[1]
    if filter_word.startswith("owner_pokemon:"):
        # 参数化过滤器（task 026 WP1）：「玛俐的宝可梦」（db cards.owner 供数；
        # db 未覆盖的主人组恒不匹配——不回落卡名硬推）
        return (
            c.supertype == Supertype.POKEMON
            and c.owner is not None
            and c.owner == filter_word.split(":", 1)[1]
        )
    if filter_word.startswith("energy_"):
        # 参数化过滤器（task 026 WP1 泛化，原字面词 energy_超 并入）：
        # 能量卡属性（「基本【草】能量」等的基本约束用 basic_energy 组合）
        return (
            c.supertype == Supertype.ENERGY
            and c.energy_type == filter_word.split("_", 1)[1]
        )
    if filter_word.startswith("trait:"):
        # 参数化过滤器（task 026 WP1）：机制特质（trait：古代/trait：未来；
        # CardDef.labels ← db effect_tags.labels）
        return filter_word.split(":", 1)[1] in c.labels
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
    if filter_word == "basic_pokemon":
        # 场上维度的基础宝可梦（task 026 WP1，与卡维度同词同义复用：栈顶 stage==0）
        return top.supertype == Supertype.POKEMON and top.stage == 0
    if filter_word.startswith("trait:"):
        # 场上维度的机制特质（task 026 WP1，如奥琳博士的气魄的 attach 目标过滤）
        return filter_word.split(":", 1)[1] in top.labels
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
    task 026 WP6 扩展（三者互斥，原语侧已校验）：
    choose_groups——组间互斥：各组池独立 up-to 子集取并集，跨组混合不可达；
    pool_buckets——distinct 分桶互异：只产桶值两两互异的子集；
    ordered——选择顺序有语义：每个子集展开为全排列（deck_top 牌顶 FIFO）。
    """
    if pending.choose_groups:
        subsets: set[tuple[int, ...]] = {()}
        for group_pool, cap in pending.choose_groups:
            g = tuple(sorted(group_pool))
            for n in range(min(cap, len(g)) + 1):
                subsets.update(combinations(g, n))
        return [Action(kind="choose", choices=s) for s in sorted(subsets)]
    if pending.pool_buckets:
        pairs = sorted(zip(pending.pool_iids, pending.pool_buckets, strict=True))
        actions = []
        for n in range(pending.min_choose, min(pending.max_choose, len(pairs)) + 1):
            for combo in combinations(pairs, n):
                if len({b for _, b in combo}) == len(combo):
                    actions.append(Action(kind="choose",
                                          choices=tuple(i for i, _ in combo)))
        return actions
    pool = tuple(sorted(pending.pool_iids))
    actions = []
    for n in range(pending.min_choose, min(pending.max_choose, len(pool)) + 1):
        for subset in combinations(pool, n):
            if pending.ordered:
                for perm in permutations(subset):
                    actions.append(Action(kind="choose", choices=perm))
            else:
                actions.append(Action(kind="choose", choices=subset))
    return actions


def build_pending(
    engine: GameEngine, player: int, source: CardInstance, effect_index: int,
    cursor: int, need: NeedChoice, completion: str = "trainer",
    inner: tuple[str, str, str] | None = None, outer_cursor: int = -1,
    outer_choice: tuple[int, ...] = (),
) -> PendingChoice:
    """挂起：解析池并冻结，写 pending_choice + 切 phase。"""
    # choose_groups（task 026 WP6，D-WP6-3）：各组池已由原语按牌库序解析冻结进
    # need.choose_groups，此处只取并集（保序去重）作 pool_iids，不再经 resolve_pool
    if need.choose_groups:
        seen: list[int] = []
        for group_pool, _cap in need.choose_groups:
            for iid in group_pool:
                if iid not in seen:
                    seen.append(iid)
        return PendingChoice(
            player=player, source=source, effect_index=effect_index, cursor=cursor,
            pool=need.pool, filters=need.filters,
            min_choose=need.min_choose, max_choose=need.max_choose,
            destination=need.destination,
            pool_iids=tuple(seen),
            payload=need.carry,
            completion=completion,
            inner=inner,
            outer_cursor=outer_cursor,
            outer_choice=outer_choice,
            flip_result=need.flip,
            cost_discarded=need.cost_discarded,
            discarded_count=need.discarded_count,
            attacker_iid=need.attacker_iid,
            choose_groups=need.choose_groups,
        )
    # 池归属方决定有效 HP 口径（勇气护符 modify_hp 按持有方求值，task 015）
    owner = 1 - player if need.pool.startswith("opponent") else player
    pool_cards = resolve_pool(
        engine.state.players[player], need.pool, need.filters,
        opponent=engine.state.players[1 - player],
        hp_of=lambda m: engine._effective_hp(m, owner),
    )
    kept = [
        c for c in pool_cards
        if (c if isinstance(c, int) else (
            c.current.iid if isinstance(c, InPlayPokemon) else c.iid))
        not in need.exclude_iids
    ]
    iids = tuple(
        c if isinstance(c, int) else (
            c.current.iid if isinstance(c, InPlayPokemon) else c.iid)
        for c in kept
    )
    buckets: tuple[int, ...] = ()
    if need.distinct == "energy_type":
        # 分桶互异（task 026 WP6，D-WP6-4）：按能量属性首现映射桶号，与 pool_iids 对齐
        order: dict[str, int] = {}
        buckets = tuple(
            order.setdefault(c.card.energy_type, len(order))
            for c in kept
            if isinstance(c, CardInstance)
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
        cost_discarded=need.cost_discarded,
        discarded_count=need.discarded_count,
        attacker_iid=need.attacker_iid,
        ordered=need.ordered,
        distinct=need.distinct or "",
        pool_buckets=buckets,
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
        if node.action == "attach_energy":
            # task 026 WP4：bench-only 附着（target_pool=own_bench）能量池/备战池
            # 为空不可使用（无效果不可使用）；既有 own_pokemon_in_play 形式保持
            # 不门控（奥琳博士的气魄「无合法目标仍抽 3」存量行为回归）
            target_pool = node.args.get("target_pool", "own_pokemon_in_play")
            if target_pool == "own_bench":
                if not resolve_pool(p, "own_discard", node.filters):
                    return False
                if not resolve_pool(p, "own_bench", tuple(node.args.get("target_filters", ()))):
                    return False
            elif target_pool != "own_pokemon_in_play":
                raise DslError(
                    f"可行性门未支持 attach_energy target_pool={target_pool!r}（不猜）"
                )
        if node.action == "recover_from_discard":
            # task 026 WP3：新形式（bench 去向 / hand up-to）弃牌区无匹配不可使用
            # （无效果不可使用）；既有形式（hand 默认 / deck）保持不门控（存量行为回归）
            if node.destination not in ("hand", "deck", "bench"):
                raise DslError(
                    f"可行性门未支持 recover_from_discard destination={node.destination!r}（不猜）"
                )
            if node.destination == "bench" or (
                node.destination == "hand" and node.args.get("up_to")
            ):
                if not resolve_pool(p, "own_discard", node.filters):
                    return False
                if node.destination == "bench" and bench_full:
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
def _is_active_holder(engine: GameEngine, player: int, mon: InPlayPokemon | None) -> bool:
    active = engine.state.players[player].active
    return mon is not None and active is not None and active.current.iid == mon.current.iid


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
    # task 026 WP1：自身/持有者为战斗宝可梦（「如果这只宝可梦在战斗场上的话」，栈顶 iid 比对）
    "self_is_active": _is_active_holder,
    "holder_is_active": _is_active_holder,
    # task 026 WP1：自己最初的回合（turn 仅在先攻方回合开始递增，双方首回合均为 turn==1）
    "first_own_turn": (
        lambda engine, player, mon: engine.state.turn == 1
    ),
    # task 026 WP5（百变怪 变身启动「战斗场上、最初回合限1次」）：双条件组合词
    "self_is_active_and_first_own_turn": (
        lambda engine, player, mon: _is_active_holder(engine, player, mon)
        and engine.state.turn == 1
    ),
    # task 026 WP1：自己场上有太晶宝可梦（依赖 CardDef.is_tera ← db cards.is_tera）
    "own_tera_in_play": (
        lambda engine, player, mon: any(
            m.current.card.is_tera
            for m in ([engine.state.players[player].active]
                      if engine.state.players[player].active else [])
            + list(engine.state.players[player].bench)
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
    if condition.startswith("opponent_prizes_eq:"):
        # 参数化条件（task 026 WP1）：「对手的剩余奖赏卡张数为 N 张」（白蕾雅）
        raw = condition.split(":", 1)[1]
        try:
            n = int(raw)
        except ValueError:
            raise DslError(f"condition 参数畸形 '{condition}'（opponent_prizes_eq 需 int）") from None
        return len(engine.state.players[1 - player].prizes) == n
    if condition.startswith("opponent_prizes_in:"):
        # 参数化条件（task 026 WP1）：「对手的剩余奖赏卡张数不为4张、3张的话…失败」
        # （赫普的古月鸟）——集合写法 [4,3]
        raw = condition.split(":", 1)[1]
        if not (raw.startswith("[") and raw.endswith("]")):
            raise DslError(f"condition 参数畸形 '{condition}'（opponent_prizes_in 需 [a,b,…]）")
        try:
            allowed = {int(x) for x in raw[1:-1].split(",")}
        except ValueError:
            raise DslError(f"condition 参数畸形 '{condition}'（opponent_prizes_in 元素需 int）") from None
        return len(engine.state.players[1 - player].prizes) in allowed
    if condition.startswith("holder_hp_le:"):
        # 参数化条件（task 026 WP1）：「剩余 HP 在 N 及以下」（紧急滑板）；
        # 剩余 HP = 有效 HP（含 modify_hp 常驻修正）− 已受伤害
        raw = condition.split(":", 1)[1]
        try:
            n = int(raw)
        except ValueError:
            raise DslError(f"condition 参数畸形 '{condition}'（holder_hp_le 需 int）") from None
        return mon is not None and engine._effective_hp(mon, player) - mon.damage <= n
    fn = _CONDITIONS.get(condition)
    if fn is None:
        raise DslError(f"未知 condition 词 '{condition}'（chooser 求值点；扩展请在 dsl/chooser.py 注册）")
    return fn(engine, player, mon)


def ability_feasible(effect: Effect, engine: GameEngine, player: int) -> bool:
    """特性发动前的可行性门（task 011）：关键池为空则不枚举；未知原语形式 DslError（不猜）。

    支持：attach_energy（destination=attach，能量池与目标池双侧非空）；draw（恒可行，
    抽完即止/空结算合法）；recover_from_discard / search_deck（task 026 WP3：匹配池
    非空，bench 去向备战区须有余量）。HP 类过滤器走有效 HP（task 015）。
    """
    p = engine.state.players[player]
    hp_of = lambda m: engine._effective_hp(m, player)
    for node in (*effect.cost, *effect.actions):
        if node.action == "attach_energy" and node.destination == "attach":
            if node.selector != "own_discard":
                raise DslError(
                    f"特性可行性门未支持 attach_energy selector={node.selector!r}（不猜）"
                )
            target_pool = node.args.get("target_pool", "own_pokemon_in_play")
            if target_pool not in ("own_pokemon_in_play", "own_bench"):
                raise DslError(
                    f"特性可行性门未支持 attach_energy target_pool={target_pool!r}（不猜）"
                )
            if not resolve_pool(p, "own_discard", node.filters):
                return False
            target_filters = tuple(node.args.get("target_filters", ()))
            if target_pool == "own_bench":
                # task 026 WP4：bench-only 附着——备战区无合法目标不可行
                if not resolve_pool(p, "own_bench", target_filters, hp_of=hp_of):
                    return False
            elif not resolve_in_play_pool(p, target_filters, hp_of=hp_of):
                return False
        elif node.action == "discard":
            # task 026 WP4（怒鹦哥ex 英武重抽）：手牌全弃恒可支付（后续 draw 有效）
            # task 026 WP6（火恐龙 大字爆炎）：弃来源宝可梦 1 张附着能量——
            # 无能量时 no-op 合法（伤害照算），恒可行
            if not (
                (
                    node.selector == "own_hand"
                    and node.count == "all"
                    and node.choose is None
                )
                or (
                    node.selector == "own_attached_energy"
                    and node.choose == 1
                    and node.count is None
                )
            ):
                raise DslError(
                    f"特性可行性门未支持 discard 形式 selector={node.selector!r}"
                    f"/count={node.count!r}/choose={node.choose!r}（不猜）"
                )
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
        elif node.action == "ko_self":
            # 自我昏厥恒可行（task 026 WP2；来源宝可梦在场上由枚举保证）
            continue
        elif node.action == "recover_from_discard":
            # task 026 WP3：弃牌区无匹配 / bench 去向备战区满 → 不可行
            if node.destination not in ("hand", "deck", "bench"):
                raise DslError(
                    f"特性可行性门未支持 recover_from_discard "
                    f"destination={node.destination!r}（不猜）"
                )
            if not resolve_pool(p, "own_discard", node.filters):
                return False
            if node.destination == "bench" and len(p.bench) >= engine._bench_size(player):
                return False
        elif node.action == "search_deck":
            # task 026 WP3（多龙奇 侦察指令等检索特性）：牌库无匹配 → 不可行
            # （top_n 检视池 ⊆ 全库匹配池，此处按全库口径判空即可）；
            # bench 去向备战区满 → 不可行；deck_top（task 026 WP6）牌库空则不可行
            if node.destination not in ("hand", "bench", "deck_top"):
                raise DslError(
                    f"特性可行性门未支持 search_deck destination={node.destination!r}（不猜）"
                )
            if not resolve_pool(p, "own_deck", node.filters):
                return False
            if node.destination == "bench" and len(p.bench) >= engine._bench_size(player):
                return False
        elif node.action == "place_damage_counters":
            # 放置伤害指示物（task 026 WP2）：对手场上有宝可梦（放置落点）
            if node.selector not in ("opponent_pokemon_any", "opponent_bench"):
                raise DslError(
                    f"特性可行性门未支持 place_damage_counters selector={node.selector!r}（不猜）"
                )
            opp = engine.state.players[1 - player]
            if opp.active is None and not opp.bench:
                return False
        elif node.action == "reveal":
            # task 026 WP4（米立龙 揽客「给对手看过」）：展示恒可行——无落点约束，
            # 空池 = 空 reveal 事件（不改变状态）
            continue
        elif node.action == "shuffle_deck":
            # task 026 WP5（百变怪 变身启动「并重洗牌库」）：重洗恒可行（空库洗牌 = no-op）
            continue
        elif node.action == "transform":
            # task 026 WP5（D-WP5-3）：检索 up-to——牌库无合法目标时 no-op 但重洗
            # 仍执行（清单 17），故不按池空门控；战斗场/首回合门由 effect.condition 承担
            if node.selector != "self" or node.choose != 1:
                raise DslError(
                    f"特性可行性门未支持 transform 形式 selector={node.selector!r}"
                    f"/choose={node.choose!r}（不猜）"
                )
            continue
        elif node.action == "hand_disrupt":
            # task 026 WP6（雪童子 惊吓）：对手手牌空 → 扰乱 no-op，不可行门由
            # 「无效果不可使用」适用于独立效果；此处校验形态 + 对手空手不门控
            # （伤害等其他节点可能仍有效，单节点空结算合法）
            if node.selector != "opponent_hand" or node.choose is not None or node.count is not None:
                raise DslError(
                    f"特性可行性门未支持 hand_disrupt 形式 selector={node.selector!r}"
                    f"/choose={node.choose!r}/count={node.count!r}（不猜）"
                )
            continue
        elif node.action == "lock_retreat":
            # task 026 WP6（沙铃仙人掌 穷追不舍）：锁对手战斗场撤退，恒可行
            if node.selector != "opponent_active" or node.choose is not None:
                raise DslError(
                    f"特性可行性门未支持 lock_retreat 形式 selector={node.selector!r}"
                    f"/choose={node.choose!r}（不猜）"
                )
            continue
        elif node.action == "devolve":
            # task 026 WP6（招式学习器 退化）：对手全场退化，无已进化时 no-op 合法
            if node.selector != "opponent_pokemon_all" or node.choose is not None:
                raise DslError(
                    f"特性可行性门未支持 devolve 形式 selector={node.selector!r}"
                    f"/choose={node.choose!r}（不猜）"
                )
            continue
        else:
            raise DslError(
                f"特性可行性门未支持原语 {node.action!r}（不猜；扩展请在 dsl/chooser.py 注册）"
            )
    return True
