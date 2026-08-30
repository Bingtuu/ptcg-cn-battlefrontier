"""原语实现（task 007：draw / discard-all；task 009：chooser 选择类四件）。

其余词表原语归后续 task 逐个注册（PRD §5.3 原语先行、逐卡落地）。
选择类原语协议：无 choice 时被调用 → 返回 NeedChoice 挂起（池空则尽力而为不挂起）；
带 choice 恢复 → 应用选择结果并返回结果字典。
"""

from __future__ import annotations

from battlefrontier.dsl.chooser import (
    NeedChoice,
    matches,
    resolve_in_play_pool,
    resolve_pool,
)
from battlefrontier.dsl.interpreter import ExecutionContext, register, run_effect
from battlefrontier.dsl.loader import DslError
from battlefrontier.dsl.schema import ActionNode
from battlefrontier.engine.state import InPlayPokemon, PlayerState, SpecialCondition


def _require_no_choose(node: ActionNode, name: str) -> None:
    if node.choose is not None:
        raise DslError(f"原语 {name} 不支持 choose（收到 choose={node.choose}）")


@register("draw")
def _draw(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """从牌库上方抽 N 张；或 args.until_hand=N 抽至手牌 N 张（梦幻ex「再起动」）。

    【规则书·胜负判定】效果导致牌库抽空不判负——判负只发生在回合开始的抽牌
    （core._begin_turn）；此处抽完即止。until_hand 超出（手牌已 ≥N）空结算合法。
    count 支持计数表达式（counters 词表，task 017 奇树：own_remaining_prizes）；
    selector=opponent_deck 时抽进对手手牌（奇树「双方各抽」）。
    """
    _require_no_choose(node, "draw")
    if node.selector not in (None, "own_deck", "opponent_deck"):
        raise DslError(f"draw 暂仅支持 selector=own_deck/opponent_deck（收到 {node.selector!r}）")
    owner_idx = 1 - ctx.player if node.selector == "opponent_deck" else ctx.player
    p = ctx.engine.state.players[owner_idx]

    def apply_draw(n: int) -> tuple:
        n = min(n, len(p.deck))
        return p.deck[:n], n

    if node.count is None and "until_hand" in node.args:
        until = node.args["until_hand"]
        if not isinstance(until, int) or until < 0:
            raise DslError(f"draw 的 until_hand 须为非负 int（收到 {until!r}）")
        drawn, n = apply_draw(max(until - len(p.hand), 0))
        ctx.engine._set_player(owner_idx, p.model_copy(update={
            "hand": p.hand + drawn, "deck": p.deck[len(drawn):],
        }))
        return {"until_hand": until, "drawn": n, "iids": [c.iid for c in drawn]}
    count = node.count
    if isinstance(count, str):
        count = _eval_counter(ctx, count)  # 计数表达式（未知词 _eval_counter 内 DslError）
    if not isinstance(count, int):
        raise DslError(f"draw 的 count 须为 int 或计数表达式（收到 {node.count!r}）")
    drawn, n = apply_draw(count)
    ctx.engine._set_player(owner_idx, p.model_copy(update={
        "hand": p.hand + drawn, "deck": p.deck[len(drawn):],
    }))
    return {"requested": count, "drawn": n, "iids": [c.iid for c in drawn]}


@register("discard")
def _discard(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """手牌→弃牌区：count=all 全弃（自动）；choose=N 由 Agent 选 N 张（chooser）。"""
    if node.selector != "own_hand":
        raise DslError(f"discard 暂仅支持 selector=own_hand（收到 {node.selector!r}）")
    if node.count == "all" and node.choose is None:
        p = ctx.player_state
        n = len(p.hand)
        ctx.set_player_state(p.model_copy(update={"hand": (), "discard": p.discard + p.hand}))
        return {"discarded": n}
    if node.choose is not None:
        if choice is None:
            return NeedChoice(pool="own_hand", min_choose=node.choose, max_choose=node.choose)
        p = ctx.player_state
        chosen = tuple(c for c in p.hand if c.iid in choice)
        ctx.set_player_state(p.model_copy(update={
            "hand": tuple(c for c in p.hand if c.iid not in choice),
            "discard": p.discard + chosen,
        }))
        return {"discarded": len(chosen), "iids": list(choice)}
    raise DslError(f"discard 需要 count=all 或 choose=N（收到 count={node.count!r}）")


@register("search_deck")
def _search_deck(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """检索牌库：过滤器 + 选择 up-to-N + 去向（hand / bench）。

    规则出处：检索为 up-to 语义（牌库非公开区域，可以不找，min_choose=0）；
    检索后必须洗牌（由后续 shuffle_deck 节点表达，DSL 编写纪律）。
    destination=bench = 直放备战区（巢穴球/深钵镇），登场联动 entered_play_this_turn。
    """
    if node.selector != "own_deck":
        raise DslError(f"search_deck 暂仅支持 selector=own_deck（收到 {node.selector!r}）")
    if node.destination not in ("hand", "bench"):
        raise DslError(f"search_deck 暂仅支持 destination=hand/bench（收到 {node.destination!r}）")
    if node.choose is None:
        raise DslError("search_deck 需要 choose=N（检索必须经 chooser 交互选择）")
    choose = node.choose
    if choice is None:
        # 池空不挂起：尽力而为（空结算，洗牌仍由后续节点执行）
        if not resolve_pool(ctx.player_state, "own_deck", node.filters):
            return {"found": 0, "iids": [], "destination": node.destination}
        return NeedChoice(
            pool="own_deck", filters=node.filters,
            min_choose=0, max_choose=choose, destination=node.destination,
        )
    p = ctx.player_state
    picked = tuple(c for c in p.deck if c.iid in choice)
    p = p.model_copy(update={"deck": tuple(c for c in p.deck if c.iid not in choice)})
    if node.destination == "hand":
        p = p.model_copy(update={"hand": p.hand + picked})
    else:  # bench：直放备战区，当回合登场（不可进化联动）
        bench = p.bench
        entered = p.entered_play_this_turn
        for c in picked:
            bench = bench + (InPlayPokemon(stack=(c,)),)
            entered = entered | {c.iid}
        p = p.model_copy(update={"bench": bench, "entered_play_this_turn": entered})
    ctx.set_player_state(p)
    return {"found": len(picked), "iids": list(choice), "destination": node.destination}


@register("shuffle_deck")
def _shuffle_deck(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """重洗牌库（规则：检索牌库后必须洗牌）。"""
    _require_no_choose(node, "shuffle_deck")
    p = ctx.player_state
    ctx.set_player_state(p.model_copy(update={"deck": ctx.engine.rng.shuffle(p.deck)}))
    return {"shuffled": len(p.deck)}


@register("recover_from_discard")
def _recover_from_discard(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """弃牌区回收：过滤器 + 选择 + 去向（hand 入手 / deck 回牌库）。

    hand：至少 1 张（夜间担架）；deck：up-to 语义（厉害钓竿「最多3张」，min_choose=0，
    洗牌由后续 shuffle_deck 节点表达）。无合法目标时不挂起、效果 no-op。
    """
    if node.selector != "own_discard":
        raise DslError(f"recover_from_discard 暂仅支持 selector=own_discard（收到 {node.selector!r}）")
    if node.destination not in ("hand", "deck"):
        raise DslError(f"recover_from_discard 暂仅支持 destination=hand/deck（收到 {node.destination!r}）")
    choose = node.choose or (node.count if isinstance(node.count, int) else None)
    if choose is None:
        raise DslError("recover_from_discard 需要 choose=N 或 count=int")
    if choice is None:
        targets = tuple(c for c in ctx.player_state.discard if matches(c, node.filters))
        if not targets:
            return {"found": 0, "iids": [], "destination": node.destination}
        return NeedChoice(
            pool="own_discard", filters=node.filters,
            min_choose=1 if node.destination == "hand" else 0,
            max_choose=choose, destination=node.destination,
        )
    p = ctx.player_state
    picked = tuple(c for c in p.discard if c.iid in choice)
    update: dict[str, object] = {"discard": tuple(c for c in p.discard if c.iid not in choice)}
    if node.destination == "hand":
        update["hand"] = p.hand + picked
    else:  # deck：回牌库上方（洗牌由后续节点执行）
        update["deck"] = p.deck + picked
    ctx.set_player_state(p.model_copy(update=update))
    return {"found": len(picked), "iids": list(choice), "destination": node.destination}


@register("attach_energy")
def _attach_energy(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """效果附着能量（不受每回合 1 次限制）：selector 区域 → 自己场上宝可梦。

    两段式选择（chooser carry 协议，task 011）：第一段选能量卡（池 = selector），
    第二段选目标宝可梦（池 = own_pokemon_in_play，args.target_filters 过滤，
    如 would_survive_20 = 「对会被昏厥的宝可梦无法使用」精神拥抱守卫）；
    args.damage_counters 附着后在目标身上放伤害指示物（每个 10 伤害）。
    完成后统一 check_knockouts（守卫外的理论兜底）。
    """
    if node.destination != "attach":
        raise DslError(f"attach_energy 暂仅支持 destination=attach（收到 {node.destination!r}）")
    if node.selector != "own_discard":
        raise DslError(f"attach_energy 暂仅支持 selector=own_discard（收到 {node.selector!r}）")
    if node.choose is None:
        raise DslError("attach_energy 需要 choose=N（附着必须经 chooser 交互选择）")
    target_filters = tuple(node.args.get("target_filters", ()))
    counters = node.args.get("damage_counters", 0)
    if not isinstance(counters, int) or counters < 0:
        raise DslError(f"attach_energy 的 damage_counters 须为非负 int（收到 {counters!r}）")

    if choice is None:
        # 第一段：选能量（池空不挂起，尽力而为空结算）
        if not resolve_pool(ctx.player_state, node.selector, node.filters):
            return {"attached": 0, "iids": [], "destination": "attach"}
        return NeedChoice(
            pool=node.selector, filters=node.filters,
            min_choose=node.choose, max_choose=node.choose, destination="attach",
        )
    if not ctx.carry:
        # 第二段：选目标宝可梦（能量选择经 carry 冻结传递）
        return NeedChoice(
            pool="own_pokemon_in_play", filters=target_filters,
            min_choose=1, max_choose=1, destination="attach", carry=tuple(choice),
        )

    # 恢复完成：carry = 能量 iids，choice = 目标栈顶 iid
    energy_iids = set(ctx.carry)
    target_iid = choice[0]
    p = ctx.player_state
    energies = tuple(c for c in p.discard if c.iid in energy_iids)
    p = p.model_copy(update={
        "discard": tuple(c for c in p.discard if c.iid not in energy_iids),
    })

    def attach(mon: InPlayPokemon) -> InPlayPokemon:
        if mon.current.iid != target_iid:
            return mon
        return mon.model_copy(update={
            "attached_energy": mon.attached_energy + energies,
            "damage": mon.damage + counters * 10,
        })

    ctx.set_player_state(p.model_copy(update={
        "active": attach(p.active) if p.active else None,
        "bench": tuple(attach(m) for m in p.bench),
    }))
    ctx.engine.check_knockouts()
    return {
        "attached": len(energies), "energy_iids": sorted(energy_iids),
        "target_iid": target_iid, "damage_counters": counters,
    }


# ── task 012：on_attack 招式效果（伤害 / 计数表达式 / 状态恢复）────────────


def _eval_counter(ctx: ExecutionContext, word: str, target: InPlayPokemon | None = None) -> int:
    """计数表达式求值（counters 词表；damage 等数值上下文）。

    未知词 / 非数值词（如 all）= DslError（不猜）。target 仅供 *_on_target 词。
    """
    engine, player = ctx.engine, ctx.player
    p = engine.state.players[player]
    opp = engine.state.players[1 - player]
    if word == "own_remaining_prizes":
        return len(p.prizes)
    if word == "opponent_remaining_prizes":
        return len(opp.prizes)
    if word == "damage_counters_on_self":
        mons = ([p.active] if p.active else []) + list(p.bench)
        mon = next((m for m in mons if m.current.iid == ctx.source.iid), None)
        if mon is None:
            raise DslError("damage_counters_on_self：来源宝可梦不在场上")
        return mon.damage // 10
    if word == "damage_counters_on_target":
        if target is None:
            raise DslError("damage_counters_on_target 需要已选目标（choose 挂起后求值）")
        return target.damage // 10
    if word == "attached_energy_on_opponent_active":
        return len(opp.active.attached_energy) if opp.active else 0
    if word == "bench_count_both":
        return len(p.bench) + len(opp.bench)
    raise DslError(f"计数表达式 {word!r} 非数值或未知（数值上下文不猜）")


def _resolve_damage_amount(ctx: ExecutionContext, node: ActionNode, target: InPlayPokemon | None) -> int:
    """伤害公式：args.amount 固定 / {base, per, op:"+"} / {per, op:"×"}（count=计数词）。"""
    args = node.args
    if "amount" in args:
        if node.count is not None:
            raise DslError("damage 的 amount 与 count 互斥（公式二选一）")
        amount = args["amount"]
        if not isinstance(amount, int) or amount < 0:
            raise DslError(f"damage 的 amount 须为非负 int（收到 {amount!r}）")
        return amount
    if not isinstance(node.count, str):
        raise DslError("damage 需要 args.amount 或 count=计数表达式（counters 词表）")
    n = _eval_counter(ctx, node.count, target)
    op, per = args.get("op"), args.get("per")
    if not isinstance(per, int) or per <= 0:
        raise DslError(f"damage 公式的 per 须为正 int（收到 {per!r}）")
    if op == "×":
        return n * per
    if op == "+":
        base = args.get("base", 0)
        if not isinstance(base, int) or base < 0:
            raise DslError(f"damage 公式的 base 须为非负 int（收到 {base!r}）")
        return base + n * per
    raise DslError(f"damage 公式的 op 须为 + 或 ×（收到 {op!r}）")


@register("damage")
def _damage(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """造成伤害：selector=opponent_active（自动目标）/ opponent_pokemon_any（choose=1 挂起选目标）。

    弱点 ×2 / 抗性 -30 由引擎规则骨架结算、仅对战斗场目标生效（rules-manual §6；
    备战区不计算是贯穿规则）。on_attack 触发的招式伤害落点为对手战斗场时，
    先加攻方持有者的声明式伤害修正（task 025 modify_damage，§6 顺序 2，
    在弱点抗性前）。伤害后统一 check_knockouts（rules-manual §8）。
    """
    from battlefrontier.engine.core import _weakness_resistance

    if node.selector not in ("opponent_active", "opponent_pokemon_any"):
        raise DslError(f"damage 暂仅支持 opponent_active / opponent_pokemon_any（收到 {node.selector!r}）")
    engine = ctx.engine
    defender_idx = 1 - ctx.player
    d = engine.state.players[defender_idx]

    if node.selector == "opponent_pokemon_any":
        if node.choose != 1:
            raise DslError("damage 选目标暂仅支持 choose=1")
        if choice is None:
            return NeedChoice(pool="opponent_pokemon_any", min_choose=1, max_choose=1)
        slot, idx, target = engine._find_in_play(d, choice[0])
    else:
        _require_no_choose(node, "damage")
        if d.active is None:
            raise DslError("damage opponent_active：对手战斗场为空")
        slot, idx, target = "active", -1, d.active

    amount = _resolve_damage_amount(ctx, node, target)
    # 攻方持有者伤害修正（task 025）：仅招式伤害（on_attack）+ 落点对手战斗场
    mod = 0
    if slot == "active" and ctx.trigger == "on_attack":
        attacker = _find_source_mon(ctx)
        if attacker is not None:
            mod = engine._effective_damage_modifier(attacker, ctx.player)
    # 弱点/抗性仅对战斗场目标（rules-manual §6）
    final = (
        _weakness_resistance(ctx.source.card, target, amount + mod,
                             weakness=ctx.engine._effective_weakness(ctx.player, target))
        if slot == "active" else amount
    )
    engine._set_player(defender_idx, engine._replace_in_play(
        d, slot, idx, target.model_copy(update={"damage": target.damage + final}),
    ))
    engine.check_knockouts()
    return {
        "amount": amount, "damage_mod": mod, "final": final,
        "target_iid": target.current.iid,
        "target": target.current.card.name, "to_bench": slot == "bench",
    }


def _find_source_mon(ctx: ExecutionContext) -> InPlayPokemon | None:
    """按效果来源定位攻方持有宝可梦（来源可为宝可梦栈顶或其道具——授予招式路径）。"""
    p = ctx.engine.state.players[ctx.player]
    for m in ([p.active] if p.active else []) + list(p.bench):
        if m.current.iid == ctx.source.iid:
            return m
        if m.attached_tool is not None and m.attached_tool.iid == ctx.source.iid:
            return m
    return None


@register("clear_status")
def _clear_status(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """恢复特殊状态（selector=self：来源宝可梦全部状态，如奇迹之力）。"""
    _require_no_choose(node, "clear_status")
    if node.selector != "self":
        raise DslError(f"clear_status 暂仅支持 selector=self（收到 {node.selector!r}）")
    p = ctx.player_state
    slot, idx, mon = ctx.engine._find_in_play(p, ctx.source.iid)
    cleared = sorted(mon.conditions)
    ctx.set_player_state(ctx.engine._replace_in_play(
        p, slot, idx, mon.model_copy(update={"conditions": frozenset()}),
    ))
    return {"cleared": cleared}


@register("apply_status")
def _apply_status(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """施加特殊状态（task 013）：args.status 对齐 SpecialCondition 枚举（未知词 DslError）。

    本期 selector 仅 opponent_active（精神幻觉：令对手战斗宝可梦混乱）。
    """
    _require_no_choose(node, "apply_status")
    status_word = node.args.get("status")
    try:
        status = SpecialCondition(status_word)
    except ValueError:
        raise DslError(
            f"未知特殊状态 {status_word!r}（对齐 SpecialCondition 枚举；扩展请在 engine/state.py 注册）"
        ) from None
    if node.selector != "opponent_active":
        raise DslError(f"apply_status 暂仅支持 selector=opponent_active（收到 {node.selector!r}）")
    engine = ctx.engine
    defender_idx = 1 - ctx.player
    d = engine.state.players[defender_idx]
    if d.active is None:
        # 效果序列中前序节点已致昏厥（等待换上）：目标不存在，状态施加空结算
        # （昏厥宝可梦进弃牌区，状态随之消失——rules-manual §4）
        return {"applied": None, "reason": "target_knocked_out"}
    engine._set_player(defender_idx, d.model_copy(update={
        "active": d.active.model_copy(update={
            "conditions": d.active.conditions | {status},
        }),
    }))
    return {"applied": str(status_word), "target": d.active.current.card.name}


# ── task 014：物品批（gust 互换 / 能量转附）──────────────────────────────


@register("switch")
def _switch(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """换位：opponent_bench = gust 强制对手（反击捕捉器）；own_bench = own 侧互换
    （task 025 交替推车：自己战斗场 ↔ 所选备战）。

    回备战区的宝可梦特殊状态清除（rules-manual §7.1「恢复途径：回到备战区
    （撤退或效果）」），伤害指示物与附着能量保留（§5 撤退条目同理）；
    效果互换不占每回合撤退次数（非撤退行动）。无备战时不挂起、no-op
    （可行性门已提前拦截枚举）。
    """
    if node.selector not in ("opponent_bench", "own_bench"):
        raise DslError(f"switch 暂仅支持 selector=opponent_bench/own_bench（收到 {node.selector!r}）")
    if node.choose != 1:
        raise DslError(f"switch 需要 choose=1（收到 choose={node.choose}）")
    engine = ctx.engine
    side_idx = ctx.player if node.selector == "own_bench" else 1 - ctx.player
    o = engine.state.players[side_idx]
    if choice is None:
        if not o.bench:
            return {"switched": False}
        return NeedChoice(pool=node.selector, min_choose=1, max_choose=1)
    if o.active is None:
        raise DslError("switch：战斗场为空，无法互换")
    idx = next(i for i, b in enumerate(o.bench) if b.current.iid == choice[0])
    promoted = o.bench[idx]
    retreated = o.active.model_copy(update={"conditions": frozenset()})
    bench = o.bench[:idx] + (retreated,) + o.bench[idx + 1:]
    engine._set_player(side_idx, o.model_copy(update={"active": promoted, "bench": bench}))
    return {"switched": True, "into": promoted.current.card.name,
            "out": retreated.current.card.name}


@register("move_energy")
def _move_energy(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """场上转附能量（不增量）：两段式——选自己场上附着的能量 → 转附自己其他宝可梦。

    第一段池 = own_attached_energy（filters 如 basic_energy）；第二段目标池 =
    own_pokemon_in_play 排除来源（exclude_iids，carry 传递能量 iids）。
    """
    if node.selector != "own_attached_energy":
        raise DslError(f"move_energy 暂仅支持 selector=own_attached_energy（收到 {node.selector!r}）")
    if node.choose is None:
        raise DslError("move_energy 需要 choose=N（转附必须经 chooser 交互选择）")
    target_filters = tuple(node.args.get("target_filters", ()))
    p = ctx.player_state
    mons = ([p.active] if p.active else []) + list(p.bench)
    if choice is None:
        if not resolve_pool(p, "own_attached_energy", node.filters):
            return {"moved": 0, "iids": []}
        return NeedChoice(pool="own_attached_energy", filters=node.filters,
                          min_choose=node.choose, max_choose=node.choose)
    if not ctx.carry:
        # 第二段：选转附目标（排除来源宝可梦——「其他宝可梦」）
        src = next(m for m in mons if any(e.iid in choice for e in m.attached_energy))
        return NeedChoice(pool="own_pokemon_in_play", filters=target_filters,
                          min_choose=1, max_choose=1,
                          carry=tuple(choice), exclude_iids=(src.current.iid,))
    energy_iids = set(ctx.carry)
    target_iid = choice[0]
    moved = tuple(e for m in mons for e in m.attached_energy if e.iid in energy_iids)

    def upd(mon: InPlayPokemon) -> InPlayPokemon:
        if any(e.iid in energy_iids for e in mon.attached_energy):
            return mon.model_copy(update={
                "attached_energy": tuple(e for e in mon.attached_energy if e.iid not in energy_iids),
            })
        if mon.current.iid == target_iid:
            return mon.model_copy(update={"attached_energy": mon.attached_energy + moved})
        return mon

    ctx.set_player_state(p.model_copy(update={
        "active": upd(p.active) if p.active else None,
        "bench": tuple(upd(m) for m in p.bench),
    }))
    return {"moved": len(moved), "energy_iids": sorted(energy_iids), "target_iid": target_iid}


# ── task 016：evolve 原语（神奇糖果跳阶 / 招式学习器「进化」）──────────────


def _apply_evolution(ctx: ExecutionContext, card_iid: int, target_iid: int, zone: str) -> dict[str, object]:
    """进化突变（规则书·进化：特殊状态恢复、伤害保留；当回合不可再进化）。

    card 从 zone（hand/deck）取出压上目标栈顶；发 evolve 引擎事件（与 _do_evolve 对齐）。
    """
    engine = ctx.engine
    p = ctx.player_state
    cards = p.hand if zone == "hand" else p.deck
    card = next(c for c in cards if c.iid == card_iid)
    p = p.model_copy(update={zone: tuple(c for c in cards if c.iid != card_iid)})
    slot, idx, target = engine._find_in_play(p, target_iid)
    evolved = target.model_copy(update={
        "stack": target.stack + (card,),
        "conditions": frozenset(),
    })
    p = engine._replace_in_play(p, slot, idx, evolved)
    ctx.set_player_state(p.model_copy(update={
        "evolved_this_turn": p.evolved_this_turn | {card.iid},
    }))
    ctx.emit("evolve", iid=card.iid, name=card.card.name, onto=target.current.card.name)
    return {"iid": card.iid, "name": card.card.name, "target_iid": target_iid}


def _evolve_skip_stage(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """神奇糖果：手牌【2阶进化】跳过 1 阶放到同链【基础】身上。

    两段式 chooser：①手牌 stage2（filters 如 stage2_pokemon，池剔除无同链可进化
    目标的卡——可行性门已拦截整体不可用情形，这里兜中段状态变化）；②同链基础目标
    （参数化过滤器 evolve_skip:<chain>，exclude 当回合登场——「刚出场的宝可梦不可」）。
    链拓扑读 CardDef.evolution_chain（db 数据），引擎零硬编码。
    """
    if node.selector != "own_hand":
        raise DslError(f"evolve skip_stage 暂仅支持 selector=own_hand（收到 {node.selector!r}）")
    if node.choose != 1:
        raise DslError(f"evolve skip_stage 需要 choose=1（收到 choose={node.choose}）")
    p = ctx.player_state
    mons = ([p.active] if p.active else []) + list(p.bench)

    def eligible_targets(chain: str | None) -> list[InPlayPokemon]:
        if chain is None:
            return []
        return [
            m for m in mons
            if m.current.card.stage == 0
            and m.current.card.evolution_chain == chain
            and m.current.iid not in p.entered_play_this_turn
        ]

    if choice is None:
        pool = resolve_pool(p, "own_hand", node.filters)
        excluded = tuple(c.iid for c in pool if not eligible_targets(c.card.evolution_chain))
        if len(excluded) == len(pool):
            return {"evolved": False, "reason": "no_eligible_target"}
        return NeedChoice(pool="own_hand", filters=node.filters,
                          min_choose=1, max_choose=1, exclude_iids=excluded)
    if not ctx.carry:
        card = next(c for c in p.hand if c.iid == choice[0])
        entered = tuple(m.current.iid for m in mons if m.current.iid in p.entered_play_this_turn)
        return NeedChoice(
            pool="own_pokemon_in_play",
            filters=(f"evolve_skip:{card.card.evolution_chain}",),
            min_choose=1, max_choose=1, carry=(card.iid,), exclude_iids=entered,
        )
    applied = _apply_evolution(ctx, ctx.carry[0], choice[0], zone="hand")
    return {"evolved": True, **applied}


def _evolve_from_deck(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """招式学习器「进化」：选 ≤N 只备战宝可梦，逐只从牌库检索其进化形态各 1 张进化。

    第一段 own_bench（exclude 牌库中无 evolves_from 匹配的备战——无可进化形态不进池）；
    之后逐只挂起 own_deck（参数化过滤器 evolves_from:<栈顶名>，min_choose=0 up-to 语义，
    牌库非公开区域可以不找）。carry = (已进化数, 当前目标, *剩余目标)；即选即进化，
    洗牌由后续 shuffle_deck 节点表达（DSL 编写纪律）。
    """
    if node.selector != "own_bench":
        raise DslError(f"evolve from_deck 暂仅支持 selector=own_bench（收到 {node.selector!r}）")
    if node.choose is None:
        raise DslError("evolve from_deck 需要 choose=N（「最多N只」上限）")
    p = ctx.player_state

    def deck_has_evolution(mon: InPlayPokemon) -> bool:
        return any(c.card.evolves_from == mon.current.card.name for c in p.deck)

    if choice is None:
        excluded = tuple(m.current.iid for m in p.bench if not deck_has_evolution(m))
        if len(excluded) == len(p.bench):
            return {"evolved": 0, "reason": "no_evolution_in_deck"}
        return NeedChoice(pool="own_bench", min_choose=0, max_choose=node.choose,
                          exclude_iids=excluded)
    if not ctx.carry:
        if not choice:
            return {"evolved": 0, "targets": []}
        targets = list(choice)
    else:
        # 恢复：carry = (已进化数, 当前目标, *剩余目标)；先结算当前目标的牌库选择
        count, current, rest = ctx.carry[0], ctx.carry[1], ctx.carry[2:]
        if choice:
            _apply_evolution(ctx, choice[0], current, zone="deck")
            count += 1
        if not rest:
            return {"evolved": count}
        targets = list(rest)
        # 继续下一只：fall through 挂起（已进化数随 carry 传递）
        p = ctx.player_state
        nxt = next(m for m in p.bench if m.current.iid == targets[0])
        return NeedChoice(
            pool="own_deck", filters=(f"evolves_from:{nxt.current.card.name}",),
            min_choose=0, max_choose=1, carry=(count, *targets),
        )
    # 第一段恢复后：对第一只挂起牌库检索
    nxt = next(m for m in p.bench if m.current.iid == targets[0])
    return NeedChoice(
        pool="own_deck", filters=(f"evolves_from:{nxt.current.card.name}",),
        min_choose=0, max_choose=1, carry=(0, *targets),
    )


@register("evolve")
def _evolve(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """进化（task 016）：args.mode 分派——skip_stage（神奇糖果）/ from_deck（学习器）。

    未知 mode = DslError（不猜；普通手牌进化是引擎规则行动 _do_evolve，不走 DSL）。
    """
    mode = node.args.get("mode")
    if mode == "skip_stage":
        return _evolve_skip_stage(ctx, node, choice)
    if mode == "from_deck":
        return _evolve_from_deck(ctx, node, choice)
    raise DslError(f"evolve 未知 mode {mode!r}（不猜；扩展请在 dsl/primitives.py 注册）")


# ── task 017：M2 收口原语（转伤 / 复制招式 / 手牌回库底 / draw 扩展）─────


@register("move_damage_counters")
def _move_damage_counters(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """转放伤害指示物（亢奋脑力）：自己场上来源 → 对手场上落点。

    两段式 chooser：①自己场上有指示物的宝可梦（has_damage_counters 过滤器）；
    ②对手场上 1 只（args.target_pool=opponent_pokemon_any）。
    降级决策（rules-reference 附录 A）：「最多 N 个」不建模数值选择——
    转放数量 = min(args.max_counters, 来源指示物数) 全转。
    """
    if node.selector != "own_pokemon_in_play":
        raise DslError(f"move_damage_counters 暂仅支持 selector=own_pokemon_in_play（收到 {node.selector!r}）")
    if node.choose != 1:
        raise DslError(f"move_damage_counters 需要 choose=1（收到 choose={node.choose}）")
    max_counters = node.args.get("max_counters")
    if not isinstance(max_counters, int) or max_counters <= 0:
        raise DslError(f"move_damage_counters 需要 args.max_counters 正 int（收到 {max_counters!r}）")
    target_pool = node.args.get("target_pool", "opponent_pokemon_any")
    engine = ctx.engine
    opp_idx = 1 - ctx.player

    if choice is None:
        if not resolve_in_play_pool(ctx.player_state, ("has_damage_counters",)):
            return {"moved": 0, "reason": "no_counters"}
        return NeedChoice(pool="own_pokemon_in_play", filters=("has_damage_counters",),
                          min_choose=1, max_choose=1)
    if not ctx.carry:
        return NeedChoice(pool=target_pool, min_choose=1, max_choose=1,
                          carry=tuple(choice))

    src_iid, dst_iid = ctx.carry[0], choice[0]
    p = ctx.player_state
    slot, idx, src = engine._find_in_play(p, src_iid)
    n = min(max_counters, src.damage // 10)
    ctx.set_player_state(engine._replace_in_play(
        p, slot, idx, src.model_copy(update={"damage": src.damage - n * 10}),
    ))
    o = engine.state.players[opp_idx]
    slot2, idx2, dst = engine._find_in_play(o, dst_iid)
    engine._set_player(opp_idx, engine._replace_in_play(
        o, slot2, idx2, dst.model_copy(update={"damage": dst.damage + n * 10}),
    ))
    ctx.emit("move_damage_counters", source_iid=src_iid, target_iid=dst_iid, counters=n)
    engine.check_knockouts()  # 转放可致对手昏厥（rules-manual §8 统一入口）
    return {"moved": n, "source_iid": src_iid, "target_iid": dst_iid}


@register("copy_attack")
def _copy_attack(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """复制招式（基因侵入）：「选择对手战斗宝可梦所拥有的1个招式，作为这个招式使用。」

    池 = opponent_active_attack（元素 = 招式索引；可复制性预筛：有伤害或有
    on_attack DSL 绑定，其余 exclude）。被复制招式不需再付能量（原文「作为这个
    招式使用」）；DSL 绑定招式以我方视角跑对方效果块（selector 相对使用者）；
    白板伤害按我方来源卡属性结算弱点抗性（rules-manual §6）。
    """
    if node.selector != "opponent_active_attack":
        raise DslError(f"copy_attack 暂仅支持 selector=opponent_active_attack（收到 {node.selector!r}）")
    if node.choose != 1:
        raise DslError(f"copy_attack 需要 choose=1（收到 choose={node.choose}）")
    engine = ctx.engine
    opp_idx = 1 - ctx.player
    opp_active = engine.state.players[opp_idx].active
    if opp_active is None:
        return {"copied": None, "reason": "no_opponent_active"}
    opp_attacks = opp_active.current.card.attacks
    opp_doc = engine.card_effects.get(opp_active.current.card.name)

    def copyable(idx: int) -> bool:
        a = opp_attacks[idx]
        if a.damage is not None:
            return True
        return opp_doc is not None and any(
            e.trigger == "on_attack" and e.attack == a.name for e in opp_doc.effects
        )

    if choice is None:
        excluded = tuple(i for i in range(len(opp_attacks)) if not copyable(i))
        if len(excluded) == len(opp_attacks):
            return {"copied": None, "reason": "no_copyable_attack"}
        return NeedChoice(pool="opponent_active_attack", min_choose=1, max_choose=1,
                          exclude_iids=excluded)

    idx = choice[0]
    attack = opp_attacks[idx]
    effect = next(
        (e for e in (opp_doc.effects if opp_doc else ())
         if e.trigger == "on_attack" and e.attack == attack.name),
        None,
    )
    if ctx.inner_done:
        # 嵌套恢复（task 020）：内层效果已完成，本节点只回结果——不重复执行内层、
        # 不重复发 copy_attack 事件（内层首次执行时已发）
        return {"copied": attack.name, "via": "dsl" if effect is not None else "whiteboard",
                "resumed": True}
    ctx.emit("copy_attack", attack=attack.name, source=opp_active.current.card.name)
    if effect is not None:
        # DSL 绑定招式：以我方视角结算对方效果块（selector 相对使用者）。
        # 嵌套挂起（task 020）：被复制招式自身含运行时选择时，标注内层效果定位
        # （inner）与内层游标（inner_cursor）向上传播，由引擎建立嵌套帧挂起；
        # 嵌套层级 >1（套娃复制）在引擎恢复路径显式 DslError（不猜）。
        sub_ctx = ExecutionContext(
            engine=engine, player=ctx.player, source=ctx.source,
            effect_id=f"{ctx.effect_id}>copy:{attack.name}", trigger=effect.trigger,
        )
        sub = run_effect(sub_ctx, effect, start=0)
        if isinstance(sub, NeedChoice):
            sub.inner = (opp_active.current.card.name, attack.name)
            sub.inner_cursor = sub.cursor
            return sub
        return {"copied": attack.name, "via": "dsl"}
    # 白板伤害：按我方来源卡属性结算弱点抗性（有效弱点，task 017）；
    # 攻方持有者伤害修正同样接入（task 025：复制招式也是我方宝可梦「所使用的招式」）
    from battlefrontier.engine.core import _attack_damage

    d = engine.state.players[opp_idx]
    attacker = _find_source_mon(ctx)
    dmg = _attack_damage(attack, ctx.source.card, d.active,
                         weakness=engine._effective_weakness(ctx.player, d.active),
                         damage_mod=(
                             engine._effective_damage_modifier(attacker, ctx.player)
                             if attacker is not None else 0
                         ))
    engine._set_player(opp_idx, d.model_copy(update={
        "active": d.active.model_copy(update={"damage": d.active.damage + dmg}),
    }))
    engine.check_knockouts()
    return {"copied": attack.name, "via": "whiteboard", "damage": dmg}


@register("hand_to_deck_bottom")
def _hand_to_deck_bottom(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """手牌洗回牌库下方（奇树：「反面朝上重洗，放回牌库下方」）。

    selector = own_hand / opponent_hand；count=all（本期唯一形式）。
    手牌先经 rng.shuffle 洗匀再置库底（单一随机源，确定性硬规矩）。
    """
    _require_no_choose(node, "hand_to_deck_bottom")
    if node.count != "all":
        raise DslError(f"hand_to_deck_bottom 暂仅支持 count=all（收到 count={node.count!r}）")
    if node.selector == "own_hand":
        owner_idx = ctx.player
    elif node.selector == "opponent_hand":
        owner_idx = 1 - ctx.player
    else:
        raise DslError(f"hand_to_deck_bottom 暂仅支持 own_hand/opponent_hand（收到 {node.selector!r}）")
    engine = ctx.engine
    p = engine.state.players[owner_idx]
    shuffled = engine.rng.shuffle(p.hand)
    engine._set_player(owner_idx, p.model_copy(update={
        "hand": (), "deck": p.deck + shuffled,
    }))
    return {"returned": len(shuffled), "owner": owner_idx}


# ── task 025：小原语批（掷币 / 恢复 / 放回手牌 / own 侧换位）───────────────


@register("heal")
def _heal(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """恢复 HP = 去伤害指示物（task 025）：卡面「恢复 N」= 去 N 点伤害（N/10 个指示物）。

    不超过已有伤害（floor 0；恢复类效果无过回复，rules-manual §7.1 恢复途径
    「使用恢复类效果」+ §6 伤害以伤害指示物累计）。昏厥检查无必要（恢复只减伤）。
    selector=own_active 自动目标；own_pokemon_in_play + choose=1 经 chooser 选目标
    （filters 如 has_damage_counters；池空不挂起，尽力而为空结算）。
    """
    amount = node.args.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        raise DslError(f"heal 需要 args.amount 非负 int（收到 {amount!r}）")

    def apply_heal(p: PlayerState, target_iid: int) -> dict[str, object]:
        slot, idx, mon = ctx.engine._find_in_play(p, target_iid)
        healed = min(amount, mon.damage)
        ctx.set_player_state(ctx.engine._replace_in_play(
            p, slot, idx, mon.model_copy(update={"damage": mon.damage - healed}),
        ))
        return {"healed": healed, "target_iid": target_iid,
                "target": mon.current.card.name}

    if node.selector == "own_active":
        _require_no_choose(node, "heal")
        p = ctx.player_state
        if p.active is None:
            raise DslError("heal own_active：自己战斗场为空")
        return apply_heal(p, p.active.current.iid)
    if node.selector == "own_pokemon_in_play":
        if node.choose != 1:
            raise DslError(f"heal 选目标暂仅支持 choose=1（收到 choose={node.choose}）")
        if choice is None:
            if not resolve_in_play_pool(ctx.player_state, node.filters):
                return {"healed": 0, "reason": "no_eligible_target"}
            return NeedChoice(pool="own_pokemon_in_play", filters=node.filters,
                              min_choose=1, max_choose=1)
        return apply_heal(ctx.player_state, choice[0])
    raise DslError(f"heal 暂仅支持 selector=own_active/own_pokemon_in_play（收到 {node.selector!r}）")


@register("coin_flip")
def _coin_flip(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """掷币（task 025）：args.times 次（默认 1），走引擎单一随机源（RandomSource.flip_coin，
    与混乱判定同款，rules-manual §2 所需物品/§7 特殊状态掷币）。

    逐次结果存 ExecutionContext.last_flip（= 最后一次），节点级门控
    if_flip_heads / if_flip_tails 据此求值（interpreter）；明细落 effect_primitive 事件。
    多掷计数（正面数×N 计伤/计奖）本期不做——遇卡按不猜纪律标 blocked（task 025 设计表）。
    """
    _require_no_choose(node, "coin_flip")
    times = node.args.get("times", 1)
    if not isinstance(times, int) or isinstance(times, bool) or times < 1:
        raise DslError(f"coin_flip 的 times 须为正 int（收到 {times!r}）")
    flips = [ctx.engine.rng.flip_coin() for _ in range(times)]
    ctx.last_flip = flips[-1]
    return {
        "flips": ["heads" if f else "tails" for f in flips],
        "heads": sum(flips),
    }


@register("bounce")
def _bounce(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """放回手牌（task 025 弗图博士的剧本）：自己场上 1 只宝可梦整叠（含进化链）回手牌，
    附着能量/道具进弃牌区（卡面 rule_reference 句：「（除宝可梦以外的卡牌，全部放于弃牌区。）」；
    规则决议见 rules-reference 附录 A·2026-08-30 bounce 条目）。

    战斗场目标被放回（rules-reference 附录 A 决议）：
    有备战 → 换上流程（promote_to_main：主阶段内换上后继续当前回合，不推进/不抽牌）；
    无备战 → 场上无宝可梦判负（reason=no_pokemon，🔲 待核）。
    回手牌不触发昏厥/奖赏；特殊状态随离场消失（rules-manual §7.1 恢复途径）。
    """
    if node.selector != "own_pokemon_in_play":
        raise DslError(f"bounce 暂仅支持 selector=own_pokemon_in_play（收到 {node.selector!r}）")
    if node.choose != 1:
        raise DslError(f"bounce 需要 choose=1（收到 choose={node.choose}）")
    engine = ctx.engine
    if choice is None:
        return NeedChoice(pool="own_pokemon_in_play", min_choose=1, max_choose=1)
    p = ctx.player_state
    slot, idx, mon = engine._find_in_play(p, choice[0])
    returned = mon.stack  # 整叠宝可梦卡（底→顶）回手牌
    attachments = mon.attached_energy + (
        (mon.attached_tool,) if mon.attached_tool is not None else ()
    )
    if slot == "active":
        p = p.model_copy(update={"active": None})
    else:
        p = p.model_copy(update={"bench": p.bench[:idx] + p.bench[idx + 1:]})
    p = p.model_copy(update={
        "hand": p.hand + returned,
        "discard": p.discard + attachments,
    })
    ctx.set_player_state(p)
    if slot == "active":
        if ctx.player_state.bench:
            # 战斗场空置：换上后继续当前主阶段（附录 A 决议）
            engine.state = engine.state.model_copy(update={
                "phase": "promote", "current_player": ctx.player,
                "promote_to_main": True,
            })
        else:
            # 场上无宝可梦判负（附录 A 决议，🔲 待核）
            engine._game_over(winner=1 - ctx.player, reason="no_pokemon")
    return {
        "returned": [c.iid for c in returned],
        "discarded": [c.iid for c in attachments],
        "from": slot,
        "name": mon.current.card.name,
    }
