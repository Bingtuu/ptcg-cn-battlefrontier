"""原语实现（task 007：draw / discard-all；task 009：chooser 选择类四件）。

其余词表原语归后续 task 逐个注册（PRD §5.3 原语先行、逐卡落地）。
选择类原语协议：无 choice 时被调用 → 返回 NeedChoice 挂起（池空则尽力而为不挂起）；
带 choice 恢复 → 应用选择结果并返回结果字典。
"""

from __future__ import annotations

from battlefrontier.dsl.chooser import NeedChoice, matches, resolve_pool
from battlefrontier.dsl.interpreter import ExecutionContext, register
from battlefrontier.dsl.loader import DslError
from battlefrontier.dsl.schema import ActionNode
from battlefrontier.engine.state import InPlayPokemon


def _require_no_choose(node: ActionNode, name: str) -> None:
    if node.choose is not None:
        raise DslError(f"原语 {name} 不支持 choose（收到 choose={node.choose}）")


@register("draw")
def _draw(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """从牌库上方抽 N 张；或 args.until_hand=N 抽至手牌 N 张（梦幻ex「再起动」）。

    【规则书·胜负判定】效果导致牌库抽空不判负——判负只发生在回合开始的抽牌
    （core._begin_turn）；此处抽完即止。until_hand 超出（手牌已 ≥N）空结算合法。
    """
    _require_no_choose(node, "draw")
    p = ctx.player_state
    if node.count is None and "until_hand" in node.args:
        until = node.args["until_hand"]
        if not isinstance(until, int) or until < 0:
            raise DslError(f"draw 的 until_hand 须为非负 int（收到 {until!r}）")
        n = min(max(until - len(p.hand), 0), len(p.deck))
        drawn = p.deck[:n]
        ctx.set_player_state(p.model_copy(update={"hand": p.hand + drawn, "deck": p.deck[n:]}))
        return {"until_hand": until, "drawn": n, "iids": [c.iid for c in drawn]}
    count = node.count
    if not isinstance(count, int):
        raise DslError(f"draw 的计数表达式 {count!r} 尚未支持（随首批原语 task 010+ 落地）")
    n = min(count, len(p.deck))
    drawn = p.deck[:n]
    ctx.set_player_state(p.model_copy(update={"hand": p.hand + drawn, "deck": p.deck[n:]}))
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
    """弃牌区回收：过滤器 + 选择 up-to-N + 去向（本期仅 hand；夜间担架）。

    无合法目标时不挂起、效果 no-op（result 记录 found=0）。
    """
    if node.selector != "own_discard":
        raise DslError(f"recover_from_discard 暂仅支持 selector=own_discard（收到 {node.selector!r}）")
    if node.destination != "hand":
        raise DslError(f"recover_from_discard 暂仅支持 destination=hand（收到 {node.destination!r}）")
    choose = node.choose or (node.count if isinstance(node.count, int) else None)
    if choose is None:
        raise DslError("recover_from_discard 需要 choose=N 或 count=int")
    if choice is None:
        targets = tuple(c for c in ctx.player_state.discard if matches(c, node.filters))
        if not targets:
            return {"found": 0, "iids": [], "destination": "hand"}
        return NeedChoice(
            pool="own_discard", filters=node.filters,
            min_choose=1, max_choose=choose, destination="hand",
        )
    p = ctx.player_state
    picked = tuple(c for c in p.discard if c.iid in choice)
    ctx.set_player_state(p.model_copy(update={
        "discard": tuple(c for c in p.discard if c.iid not in choice),
        "hand": p.hand + picked,
    }))
    return {"found": len(picked), "iids": list(choice), "destination": "hand"}


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
    备战区不计算是贯穿规则）。伤害后统一 check_knockouts（rules-manual §8）。
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
    # 弱点/抗性仅对战斗场目标（rules-manual §6）
    final = _weakness_resistance(ctx.source.card, target, amount) if slot == "active" else amount
    engine._set_player(defender_idx, engine._replace_in_play(
        d, slot, idx, target.model_copy(update={"damage": target.damage + final}),
    ))
    engine.check_knockouts()
    return {
        "amount": amount, "final": final, "target_iid": target.current.iid,
        "target": target.current.card.name, "to_bench": slot == "bench",
    }


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
