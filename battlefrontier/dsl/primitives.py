"""原语实现（task 007：draw / discard-all；task 009：chooser 选择类四件）。

其余词表原语归后续 task 逐个注册（PRD §5.3 原语先行、逐卡落地）。
选择类原语协议：无 choice 时被调用 → 返回 NeedChoice 挂起（池空则尽力而为不挂起）；
带 choice 恢复 → 应用选择结果并返回结果字典。
"""

from __future__ import annotations

from battlefrontier.dsl.chooser import (
    NeedChoice,
    matches,
    matches_in_play,
    resolve_in_play_pool,
    resolve_pool,
)
from battlefrontier.dsl.interpreter import ExecutionContext, register, run_effect
from battlefrontier.dsl.loader import DslError
from battlefrontier.dsl.schema import ActionNode
from battlefrontier.engine.actions import IllegalActionError
from battlefrontier.engine.state import (
    CardInstance,
    InPlayPokemon,
    PlayerState,
    SpecialCondition,
)


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
    """手牌/场上附着能量→弃牌区：count=all 全弃（自动）；choose=N 由 Agent 选 N 张。

    args.any_count=true（task 026 WP5，D-WP5-1）：「任意数量」= up-to all
    （min_choose=0，max=池大小；选 0 张合法）；与 count/choose 互斥。
    selector=own_attached_energy（task 026 WP5 猛雷鼓ex 极雷轰）：自己场上全体
    宝可梦附着能量池（filters 如 basic_energy），摘下弃置——仅 any_count 形式。
    结果字典恒带 discarded 张数：解释器累计进 ctx.discarded_this_effect，
    供 damage 的 discarded_this_effect 计数词读取（×N 伤害族）。
    """
    if node.selector not in ("own_hand", "own_attached_energy"):
        raise DslError(
            f"discard 暂仅支持 selector=own_hand/own_attached_energy（收到 {node.selector!r}）"
        )
    any_count = node.args.get("any_count", False)
    if not isinstance(any_count, bool):
        raise DslError(f"discard 的 any_count 须为 bool（收到 {any_count!r}）")
    if any_count and (node.choose is not None or node.count is not None):
        raise DslError("discard 的 any_count 与 count/choose 互斥（「任意数量」= up-to all）")
    if (
        node.selector == "own_attached_energy" and not any_count
        and not (node.choose == 1 and node.count is None)
    ):
        raise DslError(
            "discard own_attached_energy 暂仅支持 args.any_count=true（任意数量）"
            "或 choose=1（「这只宝可梦身上」定点弃 1，task 026 WP6）形式"
            f"（收到 choose={node.choose!r}/count={node.count!r}，不猜）"
        )
    if node.count == "all" and node.choose is None and not any_count:
        p = ctx.player_state
        n = len(p.hand)
        ctx.set_player_state(p.model_copy(update={"hand": (), "discard": p.discard + p.hand}))
        return {"discarded": n}
    if any_count:
        p = ctx.player_state
        if choice is None:
            pool = resolve_pool(p, node.selector, node.filters)
            if not pool:
                return {"discarded": 0, "iids": []}  # 池空不挂起，尽力而为空结算
            return NeedChoice(pool=node.selector, filters=node.filters,
                              min_choose=0, max_choose=len(pool))
        chosen_ids = set(choice)
        if node.selector == "own_hand":
            chosen = tuple(c for c in p.hand if c.iid in chosen_ids)
            ctx.set_player_state(p.model_copy(update={
                "hand": tuple(c for c in p.hand if c.iid not in chosen_ids),
                "discard": p.discard + chosen,
            }))
            return {"discarded": len(chosen), "iids": list(choice)}
        # own_attached_energy：从各持有宝可梦身上摘下弃置
        def strip(mon: InPlayPokemon) -> InPlayPokemon:
            if not any(e.iid in chosen_ids for e in mon.attached_energy):
                return mon
            return mon.model_copy(update={
                "attached_energy": tuple(
                    e for e in mon.attached_energy if e.iid not in chosen_ids
                ),
            })

        mons = ([p.active] if p.active else []) + list(p.bench)
        moved = tuple(e for m in mons for e in m.attached_energy if e.iid in chosen_ids)
        ctx.set_player_state(p.model_copy(update={
            "active": strip(p.active) if p.active else None,
            "bench": tuple(strip(m) for m in p.bench),
            "discard": p.discard + moved,
        }))
        return {"discarded": len(moved), "iids": list(choice)}
    if node.selector == "own_attached_energy":
        # choose=1（task 026 WP6，火恐龙 大字爆炎「选择这只宝可梦身上附着的1张能量」）：
        # 池收窄为来源宝可梦附着能量（其他自己宝可梦的能量经 exclude_iids 剔除）；
        # 来源无匹配能量 → no-op 不挂起（伤害等前序/后续节点照算，清单 28）
        source_mon = _find_source_mon(ctx)
        if source_mon is None:
            raise DslError("discard own_attached_energy choose=1：来源宝可梦不在场上")
        p = ctx.player_state
        if choice is None:
            pool = tuple(e for e in source_mon.attached_energy
                         if matches(e, node.filters))
            if not pool:
                return {"discarded": 0, "iids": []}
            others = tuple(
                e.iid
                for m in ([p.active] if p.active else []) + list(p.bench)
                if m.current.iid != source_mon.current.iid
                for e in m.attached_energy
            )
            return NeedChoice(pool="own_attached_energy", filters=node.filters,
                              min_choose=1, max_choose=1, exclude_iids=others)
        slot, idx, holder = ctx.engine._find_in_play(p, source_mon.current.iid)
        moved = tuple(e for e in holder.attached_energy if e.iid in choice)
        holder = holder.model_copy(update={
            "attached_energy": tuple(e for e in holder.attached_energy
                                     if e.iid not in choice),
        })
        ctx.set_player_state(
            ctx.engine._replace_in_play(p, slot, idx, holder).model_copy(update={
                "discard": p.discard + moved,
            })
        )
        return {"discarded": len(moved), "iids": list(choice)}
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
    destination=bench = 直放备战区（巢穴球/深钵镇），登场联动 entered_play_this_turn；
    备战区 5 只容量上限在池解析即截断（task 026 WP3，超出容量的匹配经 exclude 剔除）。

    top_n 检视（task 026 WP3，多龙奇 侦察指令）：args.top_n=N 检视牌库顶 N 张为选择池
    （其余牌经 exclude_iids 剔除）；args.rest=deck_top|deck_bottom 指定未选卡归位
    （按原序，不洗牌——检视语义无洗牌义务，DSL 不写 shuffle_deck 节点）；
    args.rest=shuffle（task 026 WP4，米立龙 揽客/宝可装置3.0「剩余放回牌库并重洗」）：
    未选卡与牌库其余合并后整库重洗（本节点直接洗牌，DSL 不再写 shuffle_deck 节点——
    重复洗牌 = 种子消耗差异）；空选（选 0 张）/窗内无匹配时重洗依然成立（清单 3）。
    私密检视观测纪律：事件流只落选择结果，未选卡不落任何事件（清单 9）。
    """
    if node.selector != "own_deck":
        raise DslError(f"search_deck 暂仅支持 selector=own_deck（收到 {node.selector!r}）")
    if node.destination not in ("hand", "bench", "deck_top"):
        raise DslError(
            f"search_deck 暂仅支持 destination=hand/bench/deck_top"
            f"（收到 {node.destination!r}）"
        )
    # ── task 026 WP6 扩展形态校验（choose_groups / distinct+split / deck_top ordered）
    choose_groups = node.args.get("choose_groups")
    distinct = node.args.get("distinct")
    split = node.args.get("split")
    ordered = node.args.get("ordered", False)
    if not isinstance(ordered, bool):
        raise DslError(f"search_deck 的 ordered 须为 bool（收到 {ordered!r}）")
    if choose_groups is not None:
        # 小刚的发掘 二选一组合约束（D-WP6-3）：组间互斥、组内自带 choose/filters，
        # 仅 hand 去向，与 top_n/rest 检视互斥
        if node.choose is not None or node.filters:
            raise DslError(
                "search_deck 的 choose_groups 与 choose/filters 互斥"
                "（组内自带 choose/filters，不猜混合语义）"
            )
        if node.destination != "hand":
            raise DslError(
                f"search_deck 的 choose_groups 暂仅支持 destination=hand"
                f"（收到 {node.destination!r}）"
            )
        if node.args.get("top_n") is not None or node.args.get("rest") is not None:
            raise DslError("search_deck 的 choose_groups 与 top_n/rest 互斥（不猜）")
        if not isinstance(choose_groups, (list, tuple)) or not choose_groups:
            raise DslError(
                f"search_deck 的 choose_groups 须为非空组列表（收到 {choose_groups!r}）"
            )
        for g in choose_groups:
            if (
                not isinstance(g, dict)
                or "choose" not in g
                or "filters" not in g
                or not isinstance(g["choose"], int)
                or isinstance(g["choose"], bool)
                or g["choose"] <= 0
            ):
                raise DslError(
                    f"search_deck 的 choose_groups 组需要 choose=正 int + filters"
                    f"（收到 {g!r}）"
                )
    if distinct is not None:
        # 赤松 属性互异 + 拆分去向（D-WP6-4）：distinct 与 split 必须成对出现
        if distinct != "energy_type":
            raise DslError(
                f"search_deck 的 distinct 暂仅支持 energy_type（收到 {distinct!r}）"
            )
        if split is None:
            raise DslError(
                "search_deck 的 distinct 需要配合 args.split（拆分去向，不猜）"
            )
    if split is not None:
        if split != "hand_attach":
            raise DslError(
                f"search_deck 的 split 暂仅支持 hand_attach（收到 {split!r}）"
            )
        if distinct is None:
            raise DslError("search_deck 的 split 需要配合 args.distinct（不猜）")
        if node.destination != "hand":
            raise DslError(
                f"search_deck 的 split=hand_attach 暂仅支持 destination=hand"
                f"（收到 {node.destination!r}）"
            )
    if node.destination == "deck_top":
        # 暗码迷的解读（D-WP6-5）：选择顺序即牌顶 FIFO，必须显式 ordered=true
        if ordered is not True:
            raise DslError(
                "search_deck destination=deck_top 需要 args.ordered=true"
                "（选择顺序即牌顶 FIFO；不猜无序语义）"
            )
    elif ordered:
        raise DslError(
            f"search_deck 的 ordered 仅 deck_top 去向可用"
            f"（收到 destination={node.destination!r}）"
        )
    if node.choose is None and choose_groups is None:
        raise DslError("search_deck 需要 choose=N（检索必须经 chooser 交互选择）")
    choose = node.choose
    top_n = node.args.get("top_n")
    rest = node.args.get("rest")
    if top_n is not None:
        if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n <= 0:
            raise DslError(f"search_deck 的 top_n 须为正 int（收到 {top_n!r}）")
        if choose > top_n:
            raise DslError(f"search_deck 的 choose={choose} 不可超过 top_n={top_n}（不猜）")
        if rest not in ("deck_top", "deck_bottom", "shuffle"):
            raise DslError(
                f"search_deck top_n 检视需要 args.rest=deck_top/deck_bottom/shuffle"
                f"（收到 {rest!r}）"
            )
    elif rest is not None:
        raise DslError("search_deck 的 args.rest 需配合 top_n 使用（不猜）")
    if choose_groups is not None:
        return _search_deck_choose_groups(ctx, node, choose_groups, choice)
    if distinct is not None:
        return _search_deck_distinct_split(ctx, node, choice)
    if choice is None:
        p = ctx.player_state
        window = p.deck[:top_n] if top_n is not None else p.deck
        pool = tuple(c for c in window if matches(c, node.filters))
        excluded: tuple[int, ...] = ()
        if top_n is not None:
            excluded += tuple(c.iid for c in p.deck[len(window):])  # 检视窗外不进池
        if node.destination == "bench":
            capacity = ctx.engine._bench_size(ctx.player) - len(p.bench)
            excluded += tuple(c.iid for c in pool[capacity:])
            pool = pool[:capacity]
        # 池空不挂起：尽力而为（空结算）；rest=shuffle 时「剩余放回牌库并重洗」
        # 在窗内无匹配（=空选）时依然成立（task 026 WP4 清单 3）——整库重洗；
        # deck_top（task 026 WP6）同口径：余库重洗义务不随空池免除
        if not pool:
            if rest == "shuffle" or node.destination == "deck_top":
                ctx.set_player_state(p.model_copy(update={
                    "deck": ctx.engine.rng.shuffle(p.deck),
                }))
            return {"found": 0, "iids": [], "destination": node.destination}
        if node.destination in ("bench", "deck_top"):
            max_choose = min(choose, len(pool))
        else:
            max_choose = choose
        need = NeedChoice(
            pool="own_deck", filters=node.filters,
            min_choose=0, max_choose=max_choose, destination=node.destination,
            exclude_iids=excluded,
        )
        need.ordered = ordered  # deck_top：选择顺序即牌顶 FIFO（排列枚举）
        return need
    p = ctx.player_state
    if node.destination == "deck_top":
        # deck_top 恢复（task 026 WP6 暗码迷的解读，D-WP6-5）：选择顺序即牌顶 FIFO，
        # 未选余库在本节点内整库重洗（DSL 不写 shuffle_deck 节点——重复洗牌 =
        # 种子消耗差异）；选 0 → 仅整库重洗（「剩余的牌库重洗」空选依然成立）
        picked_top = tuple(
            next(c for c in p.deck if c.iid == iid) for iid in choice
        )
        rest_deck = tuple(c for c in p.deck if c.iid not in choice)
        ctx.set_player_state(p.model_copy(update={
            "deck": picked_top + ctx.engine.rng.shuffle(rest_deck),
        }))
        return {"found": len(picked_top), "iids": list(choice),
                "destination": "deck_top"}
    picked = tuple(c for c in p.deck if c.iid in choice)
    if top_n is not None:
        # 检视模式：rest=shuffle 时未选卡与牌库其余合并后整库重洗（task 026 WP4）；
        # deck_bottom / deck_top 按原序归位，窗口外不动、不洗牌
        window = p.deck[:top_n]
        rest_cards = tuple(c for c in window if c.iid not in choice)
        tail = p.deck[top_n:]
        if rest == "shuffle":
            deck = ctx.engine.rng.shuffle(rest_cards + tail)
        else:
            deck = tail + rest_cards if rest == "deck_bottom" else rest_cards + tail
        p = p.model_copy(update={"deck": deck})
    else:
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


def _search_deck_choose_groups(
    ctx: ExecutionContext, node: ActionNode,
    groups: list | tuple, choice: tuple[int, ...] | None,
) -> dict[str, object] | NeedChoice:
    """choose_groups 组间互斥检索（task 026 WP6 小刚的发掘，D-WP6-3）：各组按自身
    filters 在牌库解析候选池、独立 up-to 组 cap，枚举取并集、跨组混合不可达；
    仅 hand 去向（形态校验在主函数）。恢复：选中各张入手、牌库移除，
    重洗由后续 shuffle_deck 节点表达。
    """
    p = ctx.player_state
    if choice is None:
        resolved = tuple(
            (tuple(c.iid for c in p.deck if matches(c, tuple(g["filters"]))),
             g["choose"])
            for g in groups
        )
        if not any(pool for pool, _ in resolved):
            return {"found": 0, "iids": [], "destination": node.destination}
        # pool_iids = 各组池并集，由 build_pending 的 choose_groups 直通分支计算
        # （该分支不经 resolve_pool，exclude_iids 在此无效，不传）
        need = NeedChoice(
            pool="own_deck", min_choose=0,
            max_choose=max(cap for _, cap in resolved),
            destination="hand",
        )
        need.choose_groups = resolved  # 组池按牌库序冻结，build_pending 直通
        return need
    picked = tuple(c for c in p.deck if c.iid in choice)
    ctx.set_player_state(p.model_copy(update={
        "hand": p.hand + picked,
        "deck": tuple(c for c in p.deck if c.iid not in choice),
    }))
    return {"found": len(picked), "iids": list(choice), "destination": "hand"}


def _search_deck_distinct_split(
    ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None,
) -> dict[str, object] | NeedChoice:
    """distinct+split 三段流（task 026 WP6 赤松，D-WP6-4）：段1 选 ≤choose 张属性
    互异能量（distinct=energy_type 分桶，桶数 < choose 自动收缩）→ 段2 从中选 1 张
    入手 → 段3 剩余附着到自己场上 1 只宝可梦。选 0 → no-op（重洗由后续节点）；
    选 1 → 直接入手，无段2/段3。

    段标记靠 carry（PendingChoice.payload 穿透）：carry 空 = 段1恢复；
    choice[0] ∈ carry = 段2恢复（选入手张）；否则 = 段3恢复（选附着目标）。
    """
    p = ctx.player_state
    carry = ctx.carry
    if choice is None:
        pool = tuple(c for c in p.deck if matches(c, node.filters))
        if not pool:
            return {"found": 0, "iids": [], "destination": node.destination}
        cap = min(node.choose, len({c.card.energy_type for c in pool}))  # 桶数收缩
        need = NeedChoice(pool="own_deck", filters=node.filters,
                          min_choose=0, max_choose=cap, destination="hand")
        need.distinct = "energy_type"  # build_pending 冻结分桶，枚举只产互异子集
        return need
    if carry and choice and choice[0] in carry:
        # 段2恢复：入手张从牌库移入手牌，剩余进入段3（附着目标选择）
        picked = next(c for c in p.deck if c.iid == choice[0])
        rest = tuple(i for i in carry if i != choice[0])
        ctx.set_player_state(p.model_copy(update={
            "hand": p.hand + (picked,),
            "deck": tuple(c for c in p.deck if c.iid != choice[0]),
        }))
        return NeedChoice(pool="own_pokemon_in_play", min_choose=1, max_choose=1,
                          carry=rest)
    if carry:
        # 段3恢复：剩余能量从牌库摘下，附着到所选自己场上宝可梦
        slot, idx, mon = ctx.engine._find_in_play(p, choice[0])
        attached = tuple(c for c in p.deck if c.iid in carry)
        ctx.set_player_state(
            ctx.engine._replace_in_play(p, slot, idx, mon.model_copy(update={
                "attached_energy": mon.attached_energy + attached,
            })).model_copy(update={
                "deck": tuple(c for c in p.deck if c.iid not in carry),
            })
        )
        return {"found": len(carry) + 1, "iids": [*carry],
                "destination": "hand_attach", "attached_to": choice[0]}
    # 段1恢复：选 0 → no-op；选 1 → 直接入手（无段2/段3）；≥2 → 段2 选入手张
    if not choice:
        return {"found": 0, "iids": [], "destination": node.destination}
    if len(choice) == 1:
        picked = next(c for c in p.deck if c.iid == choice[0])
        ctx.set_player_state(p.model_copy(update={
            "hand": p.hand + (picked,),
            "deck": tuple(c for c in p.deck if c.iid != choice[0]),
        }))
        return {"found": 1, "iids": list(choice), "destination": "hand"}
    return NeedChoice(
        pool="own_deck", filters=node.filters, min_choose=1, max_choose=1,
        carry=tuple(choice),
        exclude_iids=tuple(c.iid for c in p.deck if c.iid not in choice),
    )


@register("shuffle_deck")
def _shuffle_deck(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """重洗牌库（规则：检索牌库后必须洗牌）。"""
    _require_no_choose(node, "shuffle_deck")
    p = ctx.player_state
    ctx.set_player_state(p.model_copy(update={"deck": ctx.engine.rng.shuffle(p.deck)}))
    return {"shuffled": len(p.deck)}


@register("recover_from_discard")
def _recover_from_discard(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """弃牌区回收：过滤器 + 选择 + 去向（hand 入手 / deck 回牌库 / bench 直放备战区）。

    hand：至少 1 张（夜间担架）；args.up_to=true 改 up-to 语义（min_choose=0，
    水莲的照顾「最多3张」，task 026 WP3）。deck：up-to 语义（厉害钓竿，min_choose=0，
    洗牌由后续 shuffle_deck 节点表达）。bench（task 026 WP3，夜巡灵 渡魂）：up-to
    （min_choose=0），必须 choose=N 形式；直放备战区为 InPlayPokemon 并登记
    entered_play_this_turn；备战区 5 只容量上限在池解析即截断（超出经 exclude 剔除）。
    无合法目标 / 容量 0 时不挂起、效果 no-op。
    args.exclude_cost_discarded=true（task 026 WP4，超级能量回收「无法选择因为
    这张卡牌的效果而被放于弃牌区的能量」）：cost 段弃置的 iid（执行上下文
    cost_discarded_iids，挂起/恢复经 PendingChoice.cost_discarded 穿透）从池剔除；
    无 cost 段时为空集无影响。
    """
    if node.selector != "own_discard":
        raise DslError(f"recover_from_discard 暂仅支持 selector=own_discard（收到 {node.selector!r}）")
    if node.destination not in ("hand", "deck", "bench"):
        raise DslError(
            f"recover_from_discard 暂仅支持 destination=hand/deck/bench"
            f"（收到 {node.destination!r}）"
        )
    up_to = node.args.get("up_to", False)
    if not isinstance(up_to, bool):
        raise DslError(f"recover_from_discard 的 up_to 须为 bool（收到 {up_to!r}）")
    exclude_cost = node.args.get("exclude_cost_discarded", False)
    if not isinstance(exclude_cost, bool):
        raise DslError(
            f"recover_from_discard 的 exclude_cost_discarded 须为 bool"
            f"（收到 {exclude_cost!r}）"
        )
    if up_to and node.destination != "hand":
        raise DslError(
            f"recover_from_discard 的 up_to 仅 hand 去向可用（deck/bench 本即 up-to；"
            f"收到 destination={node.destination!r}）"
        )
    if node.destination == "bench" and node.choose is None:
        raise DslError("recover_from_discard 的 bench 去向需要 choose=N（不猜 count 形式）")
    choose = node.choose or (node.count if isinstance(node.count, int) else None)
    if choose is None:
        raise DslError("recover_from_discard 需要 choose=N 或 count=int")
    if choice is None:
        targets = tuple(c for c in ctx.player_state.discard if matches(c, node.filters))
        excluded: tuple[int, ...] = ()
        if exclude_cost and ctx.cost_discarded_iids:
            excluded += tuple(ctx.cost_discarded_iids)
            targets = tuple(c for c in targets if c.iid not in excluded)
        if node.destination == "bench":
            capacity = ctx.engine._bench_size(ctx.player) - len(ctx.player_state.bench)
            excluded = tuple(c.iid for c in targets[capacity:])
            targets = targets[:capacity]
        if not targets:
            return {"found": 0, "iids": [], "destination": node.destination}
        min_choose = 0 if (node.destination != "hand" or up_to) else 1
        max_choose = min(choose, len(targets)) if node.destination == "bench" else choose
        return NeedChoice(
            pool="own_discard", filters=node.filters,
            min_choose=min_choose, max_choose=max_choose, destination=node.destination,
            exclude_iids=excluded,
        )
    p = ctx.player_state
    picked = tuple(c for c in p.discard if c.iid in choice)
    update: dict[str, object] = {"discard": tuple(c for c in p.discard if c.iid not in choice)}
    if node.destination == "hand":
        update["hand"] = p.hand + picked
    elif node.destination == "deck":  # 回牌库上方（洗牌由后续节点执行）
        update["deck"] = p.deck + picked
    else:  # bench：直放备战区，当回合登场（不可进化联动）
        bench = p.bench
        entered = p.entered_play_this_turn
        for c in picked:
            bench = bench + (InPlayPokemon(stack=(c,)),)
            entered = entered | {c.iid}
        update["bench"] = bench
        update["entered_play_this_turn"] = entered
    ctx.set_player_state(p.model_copy(update=update))
    return {"found": len(picked), "iids": list(choice), "destination": node.destination}


def _attach_energy_from_deck(
    ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None,
) -> dict[str, object] | NeedChoice:
    """attach_energy selector=own_deck（task 026 WP7，D-WP7-8 喷火龙ex 烈炎支配）：牌库检索能量附着。

    段1 牌库池 up-to N（min 0；池空/选 0 → 仅重洗完成）；选 K>0 → 先重洗，
    再逐张挂起选目标（pool=own_pokemon_in_play，args.target_filters 过滤），
    每张从牌库按 iid 摘下附着（任意分配、可全给 1 只）；能量在选目标前不离
    牌库。multi_target/energy_up_to/damage_counters 与 own_deck 组合语义冲突
    → DslError（不猜）。
    """
    if node.args.get("multi_target") or node.args.get("energy_up_to"):
        raise DslError(
            "attach_energy selector=own_deck 不支持 multi_target/energy_up_to"
            "（语义冲突，不猜）"
        )
    if node.args.get("damage_counters"):
        raise DslError(
            "attach_energy selector=own_deck 不支持 damage_counters（不猜）"
        )
    engine = ctx.engine
    target_filters = tuple(node.args.get("target_filters", ()))
    if choice is None:
        # 段1：选能量（牌库池空 → 仅重洗，不挂起）
        if not resolve_pool(ctx.player_state, "own_deck", node.filters):
            p = ctx.player_state
            ctx.set_player_state(p.model_copy(update={
                "deck": engine.rng.shuffle(p.deck),
            }))
            return {"attached": 0, "iids": [], "destination": "attach",
                    "shuffled": True, "reason": "no_match"}
        return NeedChoice(
            pool="own_deck", filters=node.filters,
            min_choose=0, max_choose=node.choose, destination="attach",
        )
    if not ctx.carry:
        # 段1 恢复：先统一重洗；选 0 张 → 仅重洗完成，不进目标选择
        p = ctx.player_state
        ctx.set_player_state(p.model_copy(update={
            "deck": engine.rng.shuffle(p.deck),
        }))
        if not choice:
            return {"attached": 0, "iids": [], "destination": "attach",
                    "shuffled": True}
        # 逐张挂起选目标：carry = 待附着能量 iids（选择顺序 FIFO）
        return NeedChoice(
            pool="own_pokemon_in_play", filters=target_filters,
            min_choose=1, max_choose=1, destination="attach", carry=tuple(choice),
        )
    # 恢复完成：carry = 全部已选能量 iids（选择顺序 FIFO 全程保留，不逐张收缩
    # ——复核 m1：事件载荷报全量 iids）；附着进度 = carry 中仍在牌库的首个
    # （已附着者已按 iid 离库）
    p = ctx.player_state
    deck_iids = {c.iid for c in p.deck}
    remaining = tuple(i for i in ctx.carry if i in deck_iids)
    energy_iid = remaining[0]
    target_iid = choice[0]
    energy_card = next(c for c in p.deck if c.iid == energy_iid)
    p = p.model_copy(update={
        "deck": tuple(c for c in p.deck if c.iid != energy_iid),
    })
    slot, idx, mon = engine._find_in_play(p, target_iid)
    ctx.set_player_state(engine._replace_in_play(p, slot, idx, mon.model_copy(
        update={"attached_energy": mon.attached_energy + (energy_card,)},
    )))
    if len(remaining) > 1:
        return NeedChoice(
            pool="own_pokemon_in_play", filters=target_filters,
            min_choose=1, max_choose=1, destination="attach", carry=ctx.carry,
        )
    return {
        "attached": len(ctx.carry), "energy_iids": sorted(ctx.carry),
        "destination": "attach", "shuffled": True,
    }


@register("attach_energy")
def _attach_energy(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """效果附着能量（不受每回合 1 次限制）：selector 区域 → 自己场上宝可梦。

    两段式选择（chooser carry 协议，task 011）：第一段选能量卡（池 = selector），
    第二段选目标宝可梦（池 = own_pokemon_in_play，args.target_filters 过滤，
    如 would_survive_20 = 「对会被昏厥的宝可梦无法使用」精神拥抱守卫）；
    args.damage_counters 附着后在目标身上放伤害指示物（每个 10 伤害）。
    完成后统一 check_knockouts（守卫外的理论兜底）。

    args.multi_target=true（task 026 WP3，奥琳博士的气魄「最多2只各附着1张」）：
    段1 选能量 up-to N（min_choose=0）→ 段2 选等量目标（args.target_filters，
    min 收缩至 min(能量数, 目标池大小)，D-WP3-1）→ 按选择顺序 FIFO 一一配对，
    每只目标各附 1 张；未配对能量留弃牌区。任一侧为空 no-op 不挂起。

    args.target_pool=own_bench（task 026 WP4，怒鹦哥ex 鼓足干劲/飞天螳螂 辅助斩
    「附着于备战宝可梦」）：段2 目标池改备战区（战斗场不可选）；目标空（无备战）
    → no-op 不挂起。args.energy_up_to=true（「最多N张」，D-WP4-4）：段1
    min_choose=0，选 0 张 → 不进段2 直接完成。multi_target × target_pool=own_bench
    组合暂不支持（DslError 不猜，需要时再扩展）。
    """
    if node.destination != "attach":
        raise DslError(f"attach_energy 暂仅支持 destination=attach（收到 {node.destination!r}）")
    if node.selector not in ("own_discard", "own_deck"):
        raise DslError(f"attach_energy 暂仅支持 selector=own_discard/own_deck（收到 {node.selector!r}）")
    if node.selector == "own_deck":
        return _attach_energy_from_deck(ctx, node, choice)
    if node.choose is None:
        raise DslError("attach_energy 需要 choose=N（附着必须经 chooser 交互选择）")
    target_filters = tuple(node.args.get("target_filters", ()))
    counters = node.args.get("damage_counters", 0)
    if not isinstance(counters, int) or counters < 0:
        raise DslError(f"attach_energy 的 damage_counters 须为非负 int（收到 {counters!r}）")
    multi = node.args.get("multi_target", False)
    if not isinstance(multi, bool):
        raise DslError(f"attach_energy 的 multi_target 须为 bool（收到 {multi!r}）")
    target_pool = node.args.get("target_pool", "own_pokemon_in_play")
    if target_pool not in ("own_pokemon_in_play", "own_bench"):
        raise DslError(
            f"attach_energy 的 target_pool 暂仅支持 own_pokemon_in_play/own_bench"
            f"（收到 {target_pool!r}）"
        )
    if multi and target_pool != "own_pokemon_in_play":
        raise DslError(
            "attach_energy 的 multi_target × target_pool=own_bench 组合暂不支持"
            "（不猜，需要时再扩展）"
        )
    energy_up_to = node.args.get("energy_up_to", False)
    if not isinstance(energy_up_to, bool):
        raise DslError(f"attach_energy 的 energy_up_to 须为 bool（收到 {energy_up_to!r}）")

    if multi:
        return _attach_energy_multi(ctx, node, choice, target_filters, counters)

    if choice is None:
        # 第一段：选能量（池空不挂起，尽力而为空结算）；bench-only 形态目标空
        # （无备战）→ no-op 不挂起（task 026 WP4 清单 4）
        if not resolve_pool(ctx.player_state, node.selector, node.filters):
            return {"attached": 0, "iids": [], "destination": "attach"}
        if target_pool == "own_bench" and not resolve_pool(
            ctx.player_state, "own_bench", target_filters,
            hp_of=lambda m: ctx.engine._effective_hp(m, ctx.player),
        ):
            return {"attached": 0, "iids": [], "destination": "attach",
                    "reason": "no_targets"}
        return NeedChoice(
            pool=node.selector, filters=node.filters,
            min_choose=0 if energy_up_to else node.choose,
            max_choose=node.choose, destination="attach",
        )
    if not ctx.carry:
        # 段1 恢复：energy_up_to 选 0 张 → 直接完成，不进段2（D-WP4-4）
        if energy_up_to and not choice:
            return {"attached": 0, "iids": [], "destination": "attach"}
        # 第二段：选目标宝可梦（能量选择经 carry 冻结传递；target_pool=own_bench
        # 时目标池为备战区，战斗场不可选）
        return NeedChoice(
            pool=target_pool, filters=target_filters,
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


def _attach_energy_multi(
    ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None,
    target_filters: tuple[str, ...], counters: int,
) -> dict[str, object] | NeedChoice:
    """attach_energy 多目标各附1（task 026 WP3，D-WP3-1 配对口径，🔲 待核）。"""
    if choice is None:
        # 段1：选能量 up-to N（池空不挂起，尽力而为空结算）
        if not resolve_pool(ctx.player_state, node.selector, node.filters):
            return {"attached": 0, "iids": [], "destination": "attach"}
        return NeedChoice(
            pool=node.selector, filters=node.filters,
            min_choose=0, max_choose=node.choose, destination="attach",
        )
    if not ctx.carry:
        # 段1 恢复：选 0 张能量 → 直接完成（不进段2）
        if not choice:
            return {"attached": 0, "iids": [], "destination": "attach"}
        # 段2：选等量目标宝可梦（目标空 no-op 不挂起，已选能量留弃牌区不消耗）
        targets = resolve_in_play_pool(
            ctx.player_state, target_filters,
            hp_of=lambda m: ctx.engine._effective_hp(m, ctx.player),
        )
        if not targets:
            return {"attached": 0, "iids": [], "destination": "attach",
                    "reason": "no_targets"}
        return NeedChoice(
            pool="own_pokemon_in_play", filters=target_filters,
            min_choose=min(len(choice), len(targets)), max_choose=len(choice),
            destination="attach", carry=tuple(choice),
        )

    # 恢复完成：carry = 能量 iids（选择顺序），choice = 目标栈顶 iids（选择顺序）
    # FIFO 一一配对（D-WP3-1）：能量[i] → 目标[i]，未配对能量留弃牌区
    p = ctx.player_state
    pairs = tuple(zip(ctx.carry, choice))  # min 收缩时 len(choice) < len(carry)，弃多余能量
    energy_iids = {ei for ei, _ in pairs}
    energies = tuple(c for c in p.discard if c.iid in energy_iids)
    p = p.model_copy(update={
        "discard": tuple(c for c in p.discard if c.iid not in energy_iids),
    })

    def attach(mon: InPlayPokemon) -> InPlayPokemon:
        adds = tuple(c for ei, ti in pairs if ti == mon.current.iid
                     for c in energies if c.iid == ei)
        if not adds:
            return mon
        return mon.model_copy(update={
            "attached_energy": mon.attached_energy + adds,
            "damage": mon.damage + counters * 10,
        })

    ctx.set_player_state(p.model_copy(update={
        "active": attach(p.active) if p.active else None,
        "bench": tuple(attach(m) for m in p.bench),
    }))
    ctx.engine.check_knockouts()  # 兜底（同单目标口径；附能量本身不致昏厥）
    return {
        "attached": len(pairs),
        "pairs": [[ei, ti] for ei, ti in pairs],
        "damage_counters": counters,
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
    if word == "attached_energy_on_target":
        # task 026 WP5（猛雷鼓 落雷风暴）：目标宝可梦附着能量数量
        if target is None:
            raise DslError(
                "attached_energy_on_target 需要已选目标（choose 挂起后求值）"
            )
        return len(target.attached_energy)
    if word == "opponent_taken_prizes":
        # task 026 WP5（月月熊 老练招式）：对手已拿奖赏 = 6 − 对手剩余奖赏
        return 6 - len(opp.prizes)
    if word == "discarded_this_effect":
        # task 026 WP5（D-WP5-1 ×N 伤害族）：本效果内前序 discard 节点弃置张数
        return ctx.discarded_this_effect
    if word == "flip_heads_count":
        # task 026 WP5（until_tails 索财灵）：本效果内掷币正面次数
        if ctx.flip_heads_count is None:
            raise DslError(
                "flip_heads_count 需要本效果内前置 coin_flip（无掷币结果，不猜）"
            )
        return ctx.flip_heads_count
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


def _damage_self(ctx: ExecutionContext, node: ActionNode) -> dict[str, object]:
    """damage selector=self（task 026 WP7 爬地翅 烫伤怒涛，D-WP7-10②）：「这只宝可梦
    也受到 N 伤害」——固定值直接放置，不吃弱点/抗性/增伤修正（自身伤害非对
    对手战斗场落点，§6 修正链不接）；致昏厥走正常 check_knockouts（§8）。
    仅 args.amount 固定值；计数公式等形式 DslError（不猜）。
    """
    _require_no_choose(node, "damage")
    if "amount" not in node.args:
        raise DslError(
            "damage self 暂仅支持 args.amount 固定值（计数公式等形式不猜）"
        )
    amount = _resolve_damage_amount(ctx, node, None)
    engine = ctx.engine
    source_mon = _find_source_mon(ctx)
    if source_mon is None:
        raise DslError("damage self：来源宝可梦不在场上")
    p = engine.state.players[ctx.player]
    slot, idx, target = engine._find_in_play(p, source_mon.current.iid)
    engine._set_player(ctx.player, engine._replace_in_play(
        p, slot, idx, target.model_copy(update={"damage": target.damage + amount}),
    ))
    engine.check_knockouts()
    return {
        "amount": amount, "damage_mod": 0, "final": amount,
        "target_iid": target.current.iid,
        "target": target.current.card.name, "to_bench": slot == "bench",
        "protected": False,  # 自伤不经保护守卫（键位对齐 damage 对手分支）
    }


@register("damage")
def _damage(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """造成伤害：selector=opponent_active（自动目标）/ opponent_pokemon_any（choose=1 挂起选目标）。

    弱点 ×2 / 抗性 -30 由引擎规则骨架结算、仅对战斗场目标生效（rules-manual §6；
    备战区不计算是贯穿规则）。on_attack 触发的招式伤害落点为对手战斗场时，
    先加攻方持有者的声明式伤害修正（task 025 modify_damage，§6 顺序 2，
    在弱点抗性前）。伤害后统一 check_knockouts（rules-manual §8）。
    """
    from battlefrontier.engine.core import _weakness_resistance

    if node.selector not in ("opponent_active", "opponent_pokemon_any", "self"):
        raise DslError(f"damage 暂仅支持 opponent_active / opponent_pokemon_any / self（收到 {node.selector!r}）")
    engine = ctx.engine
    if node.selector == "self":
        return _damage_self(ctx, node)
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
            mod = engine._effective_damage_modifier(
                attacker, ctx.player,
                target_rule_box=target.current.card.rule_box)
    # 谢米（task 026 WP7，D-WP7-5）：招式伤害落点对手备战区且受 protection
    # scope=opponent_attack_damage_to_bench 保护 → 伤害归零（指示物不受此保护）
    protected = (
        slot == "bench" and ctx.trigger == "on_attack"
        and engine._protected_bench_from_attack_damage(target, defender_idx)
    )
    # 弱点/抗性仅对战斗场目标（rules-manual §6）
    if protected:
        final = 0
    elif slot == "active":
        final = _weakness_resistance(
            ctx.source.card, target, amount + mod,
            weakness=ctx.engine._effective_weakness(ctx.player, target))
    else:
        final = amount
    engine._set_player(defender_idx, engine._replace_in_play(
        d, slot, idx, target.model_copy(update={"damage": target.damage + final}),
    ))
    # 招式伤害瞬时记录（task 026 WP5 白蕾雅 D-WP5-2 / WP7 古玉鱼 D-WP7-7 + F1 归正）：
    # on_attack 伤害落点（战斗场或备战）且 final>0 → 置记录，check_knockouts 取走并
    # 清空；效果触发（非 on_attack）/指示物/0 伤害（含谢米保护归零）永不置位。
    # 白蕾雅奖赏加成与 own_ko_by_attack 触发器仍只在战斗场昏厥读取（_knockout_one
    # 的 active_ko 门）；古玉鱼精确标记战斗场/备战昏厥均置位（F1：卡面无战斗场限定）
    if ctx.trigger == "on_attack" and final > 0:
        attacker = _find_source_mon(ctx)  # 备战落点不经上方修正块，此处重新定位
        engine._attack_damage_active = (
            ctx.player, attacker is not None and attacker.current.card.is_tera,
            attacker.current.iid if attacker is not None else None,
        )
    engine.check_knockouts()
    return {
        "amount": amount, "damage_mod": mod, "final": final,
        "target_iid": target.current.iid,
        "target": target.current.card.name, "to_bench": slot == "bench",
        "protected": protected,
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
        # 麻痹施加标记随状态恢复清除（task 026 WP7，D-WP7-2）
        p, slot, idx, mon.model_copy(update={
            "conditions": frozenset(), "paralyzed_mark": None,
        }),
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
    if ctx.trigger == "on_attack" and engine._protected_from_attack_effects(
        d.active, defender_idx
    ):
        # 闪焰之幕（task 026 WP6，D-WP6-7）：对手招式施加的特殊状态不适用
        # （伤害本体不免疫——damage 节点不经本判定；训练家卡效果不受保护）
        return {"applied": None, "reason": "protected"}
    # 麻痹施加标记（task 026 WP7，D-WP7-2）=（施加时 turn, 施加方）：检查阶段
    # 据此判定「持有者下一个自己回合结束才恢复」（施加当回合不恢复）
    mark = (
        (engine.state.turn, engine.state.current_player)
        if status == SpecialCondition.PARALYZED else d.active.paralyzed_mark
    )
    engine._set_player(defender_idx, d.model_copy(update={
        "active": d.active.model_copy(update={
            "conditions": d.active.conditions | {status},
            "paralyzed_mark": mark,
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
    retreated = o.active.model_copy(update={
        "conditions": frozenset(),
        # 麻痹施加标记随状态恢复清除（task 026 WP7，D-WP7-2）
        "paralyzed_mark": None,
    })
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
    zone="hand"（神奇糖果跳阶等）时 own_evolve_from_hand 触发请求入队
    （pending_event_triggers，用户裁决 2026-09-07：「从手牌使出并进化」含 DSL 手牌路径；
    zone="deck" 学习器路径不经过手牌，不触发）。
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
        # 麻痹施加标记随状态恢复清除（task 026 WP7，D-WP7-2）
        "paralyzed_mark": None,
    })
    p = engine._replace_in_play(p, slot, idx, evolved)
    ctx.set_player_state(p.model_copy(update={
        "evolved_this_turn": p.evolved_this_turn | {card.iid},
    }))
    ctx.emit("evolve", iid=card.iid, name=card.card.name, onto=target.current.card.name)
    if zone == "hand":
        # 进化卡从手牌使出（神奇糖果跳阶等 DSL 路径）：own_evolve_from_hand 触发请求
        # 入队（用户裁决 2026-09-07），效果完成后由 _run_or_suspend 完成路径排水
        engine._queue_event_trigger(ctx.player, card.iid, "own_evolve_from_hand")
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
    # 局部 import 防循环（engine.core ← dsl ← primitives）
    from battlefrontier.engine.core import effect_doc

    opp_doc = effect_doc(engine.card_effects, opp_active.current.card)

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
            sub.inner = (opp_active.current.card.card_id, opp_active.current.card.name,
                         attack.name)
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
                             engine._effective_damage_modifier(
                                 attacker, ctx.player,
                                 target_rule_box=d.active.current.card.rule_box)
                             if attacker is not None else 0
                         ))
    engine._set_player(opp_idx, d.model_copy(update={
        "active": d.active.model_copy(update={"damage": d.active.damage + dmg}),
    }))
    # 白蕾雅奖赏瞬时记录（task 026 WP5，D-WP5-2）：复制招式也是我方宝可梦所使用
    # 的招式——招式伤害落点对手战斗场且 dmg>0 → 置位（攻方太晶读持有者栈顶）
    if dmg > 0:
        engine._attack_damage_active = (
            ctx.player, attacker is not None and attacker.current.card.is_tera,
            attacker.current.iid if attacker is not None else None,
        )
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
    if node.selector == "all_pokemon_both":
        # 野餐篮（task 026 WP7，D-WP7-10）：双方全场各恢复 N（无 choose；
        # 满血 no-op 照常，healed 按实际恢复量求和）
        _require_no_choose(node, "heal")
        total = 0
        for who in (ctx.player, 1 - ctx.player):
            p = ctx.engine.state.players[who]
            positions = ([("active", -1)] if p.active else []) + [
                ("bench", i) for i in range(len(p.bench))
            ]
            for slot, idx in positions:
                p = ctx.engine.state.players[who]
                mon = p.active if slot == "active" else p.bench[idx]
                healed = min(amount, mon.damage)
                total += healed
                if healed:
                    ctx.engine._set_player(who, ctx.engine._replace_in_play(
                        p, slot, idx,
                        mon.model_copy(update={"damage": mon.damage - healed}),
                    ))
        return {"healed": total}
    raise DslError(f"heal 暂仅支持 selector=own_active/own_pokemon_in_play/all_pokemon_both（收到 {node.selector!r}）")


@register("coin_flip")
def _coin_flip(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """掷币（task 025）：args.times 次（默认 1），走引擎单一随机源（RandomSource.flip_coin，
    与混乱判定同款，rules-manual §2 所需物品/§7 特殊状态掷币）。

    逐次结果存 ExecutionContext.last_flip（= 最后一次），节点级门控
    if_flip_heads / if_flip_tails 据此求值（interpreter）；明细落 effect_primitive 事件。
    args.until_tails=true（task 026 WP5 索财灵 连掷硬币「抛掷硬币直到出现反面」）：
    单次行动内连续掷到反面为止（逐次走同一随机源，种子确定性不变），
    正面次数存 ExecutionContext.flip_heads_count 供 damage 的 flip_heads_count
    计数词引用；与 times 互斥。常规路径同样写 flip_heads_count（times 次正面数）。
    """
    _require_no_choose(node, "coin_flip")
    until_tails = node.args.get("until_tails", False)
    if not isinstance(until_tails, bool):
        raise DslError(f"coin_flip 的 until_tails 须为 bool（收到 {until_tails!r}）")
    if until_tails and "times" in node.args:
        raise DslError("coin_flip 的 until_tails 与 times 互斥（不猜）")
    if until_tails:
        flips: list[bool] = []
        while True:
            heads = ctx.engine.rng.flip_coin()
            flips.append(heads)
            if not heads:
                break
    else:
        times = node.args.get("times", 1)
        if not isinstance(times, int) or isinstance(times, bool) or times < 1:
            raise DslError(f"coin_flip 的 times 须为正 int（收到 {times!r}）")
        flips = [ctx.engine.rng.flip_coin() for _ in range(times)]
    ctx.last_flip = flips[-1]
    ctx.flip_heads_count = sum(flips)
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
    有备战 → 换上流程（resume_after_promotes=(效果方, main)：主阶段内换上后继续
    当前回合，不推进/不抽牌；task 026 WP2 D-WP2-4 归并 promote_to_main）；
    无备战 → 场上无宝可梦判负（reason=no_pokemon，🔲 待核）。
    回手牌不触发昏厥/奖赏；特殊状态随离场消失（rules-manual §7.1 恢复途径）。
    """
    if node.selector != "own_pokemon_in_play":
        raise DslError(f"bounce 暂仅支持 selector=own_pokemon_in_play（收到 {node.selector!r}）")
    if node.choose != 1:
        raise DslError(f"bounce 需要 choose=1（收到 choose={node.choose}）")
    # task 026 WP5（牡丹「以及放于其身上的所有卡牌，放回手牌」）：attachments=hand
    # 时附着能量/道具随整叠回手牌；默认 discard 行为不变（弗图博士的剧本等回归）
    attachments_mode = node.args.get("attachments", "discard")
    if attachments_mode not in ("discard", "hand"):
        raise DslError(
            f"bounce 的 attachments 暂仅支持 discard/hand（收到 {attachments_mode!r}）"
        )
    engine = ctx.engine
    if choice is None:
        # filters（task 026 WP5 牡丹 basic_pokemon：进化体不可选）随池解析冻结
        return NeedChoice(pool="own_pokemon_in_play", filters=node.filters, min_choose=1, max_choose=1)
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
    if attachments_mode == "hand":
        p = p.model_copy(update={"hand": p.hand + returned + attachments})
    else:
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
                "resume_after_promotes": (ctx.player, "main"),
            })
        else:
            # 场上无宝可梦判负（附录 A 决议，🔲 待核）
            engine._game_over(winner=1 - ctx.player, reason="no_pokemon")
    return {
        "returned": [c.iid for c in returned],
        "discarded": [c.iid for c in attachments] if attachments_mode == "discard" else [],
        "attachments_to": attachments_mode,
        "from": slot,
        "name": mon.current.card.name,
    }


# ── task 026 WP2：ko_self（自我昏厥）+ place_damage_counters（放置伤害指示物）──


@register("ko_self")
def _ko_self(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """自我昏厥（task 026 WP2，彷徨夜灵 咒怨炸弹机制件）。

    【rules-manual §8】自己的宝可梦昏厥：整叠（进化链+能量+道具）进弃牌区、
    对手按规则盒拿奖赏；战斗场昏厥须换上——换上推迟到效果全部结算完毕后按
    promote_queue 统一进行（D-WP2-1，🔲 待核），本原语只入队不翻阶段
    （ko_self 恒在效果内，翻阶段由 _run_or_suspend 完成路径做）。
    """
    _require_no_choose(node, "ko_self")
    if node.selector != "self":
        raise DslError(f"ko_self 暂仅支持 selector=self（收到 {node.selector!r}）")
    engine = ctx.engine
    mon = _find_source_mon(ctx)
    if mon is None:
        raise DslError("ko_self：来源宝可梦不在场上")
    p = ctx.player_state
    was_active = p.active is not None and p.active.current.iid == mon.current.iid
    if was_active:
        ctx.set_player_state(p.model_copy(update={"active": None}))
    else:
        ctx.set_player_state(p.model_copy(update={
            "bench": tuple(b for b in p.bench if b.current.iid != mon.current.iid),
        }))
    if engine._knockout_one(ctx.player, mon):
        # 对手拿完奖赏立即获胜：终局，不入队不换上
        return {"ko_self": mon.current.card.name, "game_over": "prizes"}
    if was_active:
        d = ctx.player_state
        if not d.bench:
            # 与 check_knockouts 同口径（rules-manual §8 胜利条件②）：
            # 对手也无场上宝可梦 → 平局（§8 同时胜利口径，🔲 待核），否则判负
            opp = engine.state.players[1 - ctx.player]
            if opp.active is None and not opp.bench:
                engine._game_over(winner=None, reason="no_pokemon", is_draw=True)
            else:
                engine._game_over(winner=1 - ctx.player, reason="no_pokemon")
        elif ctx.player not in engine.state.promote_queue:
            engine.state = engine.state.model_copy(update={
                "promote_queue": engine.state.promote_queue + (ctx.player,),
            })
    return {"ko_self": mon.current.card.name, "was_active": was_active}


@register("place_damage_counters")
def _place_damage_counters(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """放置伤害指示物（task 026 WP2，咒怨炸弹/摔角鹰人机制件）：对手场上 choose 只
    各放 args.counters 个（每个 = 10 伤害）。

    【rules-manual §6】伤害指示物不是招式伤害：不结算弱点/抗性；放置后统一
    check_knockouts（§8）。「可使用」的放弃选项不建模、满足即自动发动
    （D-WP2-3）：池不足 min_choose 收缩至池大小，池空 no-op 不挂起。
    """
    if node.selector not in (
        "opponent_pokemon_any", "opponent_bench", "opponent_attacker",
        "own_active", "all_pokemon_both",
    ):
        raise DslError(
            f"place_damage_counters 暂仅支持 opponent_pokemon_any/opponent_bench/"
            f"opponent_attacker/own_active/all_pokemon_both（收到 {node.selector!r}）"
        )
    counters = node.args.get("counters")
    if not isinstance(counters, int) or isinstance(counters, bool) or counters <= 0:
        raise DslError(f"place_damage_counters 需要 args.counters 正 int（收到 {counters!r}）")
    engine = ctx.engine
    opp_idx = 1 - ctx.player
    if node.selector == "opponent_attacker":
        # 沙铃仙人掌 炸裂针刺（task 026 WP6，D-WP6-6）：目标 = 造成昏厥的攻击方
        # 宝可梦（ctx.attacker_iid，own_ko_by_attack 触发时由引擎穿透）——
        # choose 形态校验先于上下文校验（挂起纪律）；攻击方已离场 → no-op
        if node.choose is not None:
            raise DslError(
                f"place_damage_counters opponent_attacker 不支持 choose"
                f"（收到 choose={node.choose}；目标唯一 = 攻击方）"
            )
        if ctx.attacker_iid is None:
            raise DslError(
                "place_damage_counters opponent_attacker 需要昏厥事件上下文"
                "（own_ko_by_attack 触发时由引擎记录攻击方；无记录不猜）"
            )
        o = engine.state.players[opp_idx]
        try:
            slot, idx, mon = engine._find_in_play(o, ctx.attacker_iid)
        except IllegalActionError:
            return {"placed": 0, "reason": "attacker_gone"}  # 攻击方已离场 → no-op
        engine._set_player(opp_idx, engine._replace_in_play(
            o, slot, idx, mon.model_copy(update={"damage": mon.damage + counters * 10}),
        ))
        engine.check_knockouts()
        return {"placed": 1, "counters_each": counters,
                "target_iids": [ctx.attacker_iid]}
    if node.selector == "own_active":
        # 惊吓炸弹反面（task 026 WP7，D-WP7-10①）：自己战斗场放 N 个指示物，无 choose
        if node.choose is not None:
            raise DslError(
                "place_damage_counters own_active 不支持 choose"
                f"（收到 choose={node.choose}；目标唯一=自己战斗场）"
            )
        p = engine.state.players[ctx.player]
        if p.active is None:
            raise DslError("place_damage_counters own_active：自己战斗场为空")
        engine._set_player(ctx.player, p.model_copy(update={
            "active": p.active.model_copy(update={
                "damage": p.active.damage + counters * 10,
            }),
        }))
        engine.check_knockouts()
        return {"placed": 1, "counters_each": counters,
                "target_iids": [p.active.current.iid]}
    if node.selector == "all_pokemon_both":
        # 雪妖女 冻结帷幕（task 026 WP7，D-WP7-11）：双方全场逐只各放 N 个
        # （无 choose；filters 对双方场上逐只收敛，如 has_ability/not_name:X）；
        # on_attack 时逐目标过闪焰之幕效果免疫守卫（D-WP6-7 口径延伸）——
        # 守卫只判定防守方目标（复核 m4：「对手招式效果」不保护攻击方自己的宝可梦）
        if node.choose is not None:
            raise DslError(
                "place_damage_counters all_pokemon_both 不支持 choose"
                f"（收到 choose={node.choose}；双方全场逐只无选择）"
            )
        placed_all = 0
        skipped_all: list[int] = []
        target_iids_all: list[int] = []
        for who in (ctx.player, 1 - ctx.player):
            p = engine.state.players[who]
            positions = ([("active", -1)] if p.active else []) + [
                ("bench", i) for i in range(len(p.bench))
            ]
            for slot, idx in positions:
                p = engine.state.players[who]
                mon = p.active if slot == "active" else p.bench[idx]
                if node.filters and not matches_in_play(mon, node.filters):
                    continue
                if (
                    who == 1 - ctx.player
                    and ctx.trigger == "on_attack"
                    and engine._protected_from_attack_effects(mon, who)
                ):
                    skipped_all.append(mon.current.iid)
                    continue
                engine._set_player(who, engine._replace_in_play(
                    p, slot, idx, mon.model_copy(update={
                        "damage": mon.damage + counters * 10,
                    }),
                ))
                placed_all += 1
                target_iids_all.append(mon.current.iid)
        engine.check_knockouts()
        result_all: dict[str, object] = {
            "placed": placed_all, "counters_each": counters,
            "target_iids": target_iids_all,
        }
        if skipped_all:
            result_all["skipped_protected"] = skipped_all
        return result_all
    if node.choose is None:
        raise DslError("place_damage_counters 需要 choose=N（目标经 chooser 交互选择）")
    if node.selector == "opponent_pokemon_any" and node.choose != 1:
        raise DslError(
            f"place_damage_counters opponent_pokemon_any 暂仅支持 choose=1"
            f"（收到 choose={node.choose}）"
        )
    if choice is None:
        o = engine.state.players[opp_idx]
        if node.selector == "opponent_pokemon_any":
            pool = ([o.active] if o.active else []) + list(o.bench)
        else:
            pool = list(o.bench)
        if not pool:
            return {"placed": 0, "reason": "no_targets"}  # D-WP2-3：池空 no-op 不挂起
        return NeedChoice(pool=node.selector,
                          min_choose=min(node.choose, len(pool)),
                          max_choose=node.choose)
    placed = 0
    skipped: list[int] = []
    for iid in choice:
        o = engine.state.players[opp_idx]
        slot, idx, mon = engine._find_in_play(o, iid)
        # 闪焰之幕（task 026 WP6，D-WP6-7）：对手招式效果落点守卫——被保护目标
        # 跳过放置（仅招式路径 on_attack；训练家卡效果不受保护）
        if ctx.trigger == "on_attack" and engine._protected_from_attack_effects(
            mon, opp_idx
        ):
            skipped.append(iid)
            continue
        engine._set_player(opp_idx, engine._replace_in_play(
            o, slot, idx, mon.model_copy(update={"damage": mon.damage + counters * 10}),
        ))
        placed += 1
    engine.check_knockouts()
    result: dict[str, object] = {
        "placed": placed, "counters_each": counters, "target_iids": list(choice),
    }
    if skipped:
        result["skipped_protected"] = skipped
    return result


# ── task 026 WP3：reveal（给对手看过）────────────────────────────────────────


@register("reveal")
def _reveal(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """给对手看过（task 026 WP3，词表 actions 既有词本期实现）：selector 池 iids + 卡名
    落 reveal 事件，无状态变更（D-WP3-4 一期口径：仅结构化事件流，对手 Agent 可见视图
    不引入手牌内容泄露建模，PRD 观测范围纪律）。

    承接前序 search/recover 节点（猫头夜鹰 寻找宝石 / 水莲的照顾「给对手看过之后」）：
    池按 selector+filters 在执行时重新解析，DSL 编写纪律 = 紧跟移动节点之后、
    filters 与移动目标一致。
    """
    _require_no_choose(node, "reveal")
    if node.selector != "own_hand":
        raise DslError(f"reveal 暂仅支持 selector=own_hand（收到 {node.selector!r}）")
    pool = resolve_pool(ctx.player_state, node.selector, node.filters)
    ctx.emit("reveal", iids=[c.iid for c in pool],
             names=[c.card.name for c in pool])
    return {"revealed": len(pool), "iids": [c.iid for c in pool]}


@register("lock_attack")
def _lock_attack(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """招式冷却锁（task 026 WP4 裁决 2，2026-09-14 用户裁决；拉帝亚斯ex 无限之刃
    「在下一个自己的回合，这只宝可梦无法使用招式」）。

    在 on_attack 效果块内把本效果块绑定的招式名（effect.attack，经
    ExecutionContext.bound_attack 读取）锁到来源宝可梦（InPlayPokemon.attack_locks
    + attack_lock_turn = 当前 turn）。selector 非 self / 效果块无 attack 绑定 /
    来源已不在场上 → DslError（不猜）。
    解禁时点：core._begin_turn 清除距当前 turn ≥2 的锁（turn 仅在先攻方回合开始
    递增：攻击于 turn N → 下个自己回合 N+1 仍锁 → N+2 解禁）；撤退/离场/昏厥
    天然清除；进化继承锁（model_copy 字段保留——决议口径，待核）。
    """
    _require_no_choose(node, "lock_attack")
    if node.selector != "self":
        raise DslError(f"lock_attack 暂仅支持 selector=self（收到 {node.selector!r}）")
    attack_name = ctx.bound_attack
    if attack_name is None:
        raise DslError("lock_attack 需要效果块 attack 绑定（on_attack 招式效果；不猜）")
    p = ctx.player_state
    slot, idx, holder = ctx.engine._find_in_play(p, ctx.source.iid)
    locked = holder.model_copy(update={
        "attack_locks": (*holder.attack_locks, attack_name),
        "attack_lock_turn": ctx.engine.state.turn,
    })
    ctx.set_player_state(ctx.engine._replace_in_play(p, slot, idx, locked))
    return {"locked": attack_name, "turn": ctx.engine.state.turn}


# ── task 026 WP5：prize_bonus（白蕾雅奖赏加成标记）+ transform（百变怪变身替换）──


@register("prize_bonus")
def _prize_bonus(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """奖赏加成标记（task 026 WP5 白蕾雅，D-WP5-2 🔲 待核）：回合级标记
    （PlayerState.extra_prize_tera_ko，core._on_turn_end 清除）——本回合自己
    太晶宝可梦招式伤害致对手战斗场昏厥时多拿 1 张奖赏。

    触发面收窄（不猜）：仅「招式伤害 → 对手战斗场昏厥」路径（效果/指示物致昏厥、
    备战昏厥不触发）；结算触点 = core._knockout_one 的 take_prize（奖赏不足按
    剩余拿取、拿完即胜）。args.amount 暂仅支持 1、scope 暂仅支持 tera_attack_ko。
    """
    _require_no_choose(node, "prize_bonus")
    amount = node.args.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise DslError(f"prize_bonus 需要 args.amount 正 int（收到 {amount!r}）")
    if amount != 1:
        raise DslError(f"prize_bonus 的 amount 暂仅支持 1（收到 {amount!r}；多档需要时再扩展）")
    scope = node.args.get("scope")
    if scope != "tera_attack_ko":
        raise DslError(
            f"prize_bonus 的 scope 暂仅支持 tera_attack_ko（收到 {scope!r}；不猜）"
        )
    ctx.set_player_state(ctx.player_state.model_copy(update={
        "extra_prize_tera_ko": True,
    }))
    return {"prize_bonus": amount, "scope": scope}


@register("transform")
def _transform(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object] | NeedChoice:
    """变身替换（task 026 WP5 百变怪 变身启动，D-WP5-3 🔲 待核）：战斗场来源宝可梦
    整叠+附着物进弃牌区 → 牌库选 1 张匹配宝可梦（filters 如 basic_pokemon +
    not_name:百变怪）入原位置 → 重洗由后续 shuffle_deck 节点表达（DSL 编写纪律）。

    替换不触发昏厥/奖赏/换上（非昏厥离场）；伤害/特殊状态/效果不继承（全新
    InPlayPokemon）；新宝可梦登记 entered_play_this_turn。
    检索 up-to（牌库非公开区域，min_choose=0）：可以不找 → no-op（重洗仍执行）；
    牌库无合法目标 → 不挂起 no-op。战斗场/首回合门控由 effect.condition
    （self_is_active_and_first_own_turn）承担。
    """
    if node.selector != "self":
        raise DslError(f"transform 暂仅支持 selector=self（收到 {node.selector!r}）")
    if node.choose != 1:
        raise DslError(f"transform 需要 choose=1（收到 choose={node.choose}）")
    p = ctx.player_state
    if choice is None:
        if not resolve_pool(p, "own_deck", node.filters):
            return {"transformed": False, "reason": "no_legal_target"}
        return NeedChoice(pool="own_deck", filters=node.filters,
                          min_choose=0, max_choose=1)
    if not choice:
        return {"transformed": False, "reason": "declined"}  # 可以不找（重洗仍执行）
    if p.active is None or p.active.current.iid != ctx.source.iid:
        raise DslError(
            "transform：来源宝可梦不在战斗场（战斗场门控 = effect.condition self_is_active）"
        )
    card = next(c for c in p.deck if c.iid == choice[0])
    old = p.active
    pile = old.stack + old.attached_energy + (
        (old.attached_tool,) if old.attached_tool is not None else ()
    )
    ctx.set_player_state(p.model_copy(update={
        "deck": tuple(c for c in p.deck if c.iid != choice[0]),
        "active": InPlayPokemon(stack=(card,)),
        "discard": p.discard + pile,
        "entered_play_this_turn": p.entered_play_this_turn | {card.iid},
    }))
    ctx.emit("transform", into=card.card.name, out=old.current.card.name)
    return {"transformed": True, "into": card.card.name, "iid": card.iid}


# ── task 026 WP6：手牌扰乱 / 撤退锁 / 退化 ──────────────────────────────────


@register("hand_disrupt")
def _hand_disrupt(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """手牌扰乱（task 026 WP6 雪童子 惊吓，D-WP6-1）：「在不看正面的前提下选择
    对手1张手牌，查看该卡牌的正面后，放回对手牌库并重洗牌库」。

    「不看正面选择」= 均匀随机（engine.rng.randbelow，单一随机源，种子确定性）；
    「查看正面」= reveal 结构化事件（iids+卡名，一期口径同猫头夜鹰 reveal）；
    「放回牌库并重洗」= 该卡入对手牌库（尾）后整库 rng.shuffle。
    对手空手 → no-op（disrupted=0/empty_hand，无 reveal 事件），其他节点照算。
    """
    _require_no_choose(node, "hand_disrupt")
    if node.count is not None:
        raise DslError(
            f"hand_disrupt 不支持 count（收到 count={node.count!r}；随机 1 张语义固定）"
        )
    if node.selector != "opponent_hand":
        raise DslError(f"hand_disrupt 暂仅支持 selector=opponent_hand（收到 {node.selector!r}）")
    engine = ctx.engine
    opp_idx = 1 - ctx.player
    o = engine.state.players[opp_idx]
    if not o.hand:
        return {"disrupted": 0, "reason": "empty_hand"}
    i = engine.rng.randbelow(len(o.hand))
    picked = o.hand[i]
    ctx.emit("reveal", iids=[picked.iid], names=[picked.card.name])
    engine._set_player(opp_idx, o.model_copy(update={
        "hand": o.hand[:i] + o.hand[i + 1:],
        "deck": engine.rng.shuffle(o.deck + (picked,)),
    }))
    return {"disrupted": 1, "iids": [picked.iid], "names": [picked.card.name]}


@register("lock_retreat")
def _lock_retreat(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """撤退锁（task 026 WP6 沙铃仙人掌 穷追不舍，D-WP6-6）：「在下一个对手的回合，
    受到这个招式影响的宝可梦无法撤退」——目标战斗宝可梦置 retreat_lock，
    撤退行动枚举层拦截；目标自己回合结束解除（core._on_turn_end），进化亦清除
    （core._do_evolve 重置，rules-manual §7.1 进化恢复口径延伸，🔲 待核）。

    闪焰之幕守卫（D-WP6-7）：对手招式（on_attack）落点且目标持 protection 声明
    → 锁不适用（一期守卫落点清单见 core._protected_from_attack_effects docstring）。
    """
    _require_no_choose(node, "lock_retreat")
    if node.selector != "opponent_active":
        raise DslError(f"lock_retreat 暂仅支持 selector=opponent_active（收到 {node.selector!r}）")
    engine = ctx.engine
    opp_idx = 1 - ctx.player
    o = engine.state.players[opp_idx]
    if o.active is None:
        # 前序节点已致昏厥（等待换上）：目标不存在，锁空结算（同 apply_status 口径）
        return {"locked": False, "reason": "target_knocked_out"}
    if ctx.trigger == "on_attack" and engine._protected_from_attack_effects(
        o.active, opp_idx
    ):
        return {"locked": False, "reason": "protected"}
    engine._set_player(opp_idx, o.model_copy(update={
        "active": o.active.model_copy(update={"retreat_lock": True}),
    }))
    return {"locked": True, "target": o.active.current.card.name}


@register("devolve")
def _devolve(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """退化（task 026 WP6 招式学习器 退化，D-WP6-8 🔲 待核）：「对手的进化宝可梦
    全部退化」——对手全场（战斗场先、备战区后）各退栈顶 1 张回其手牌（保序）。

    退后：伤害指示物保留、特殊状态恢复（进化链变化，rules-manual §7.1 恢复途径
    口径延伸）、附着能量/道具不动；retreat_lock 保留（退化非进化/离场，
    「受到这个招式影响」的招式效果锁不随退化解除，🔲 待核）；
    退后 HP 超限的昏厥走既有 check_knockouts（§8，奖赏/换上正常结算）。
    未进化（栈长 1）不动；对手全场无已进化 → no-op。

    闪焰之幕守卫（D-WP6-7）：对手招式（on_attack）落点且目标持 protection 声明
    → 该目标不退化（记入 skipped_protected），其余目标照常。
    """
    _require_no_choose(node, "devolve")
    if node.selector != "opponent_pokemon_all":
        raise DslError(
            f"devolve 暂仅支持 selector=opponent_pokemon_all（收到 {node.selector!r}）"
        )
    engine = ctx.engine
    opp_idx = 1 - ctx.player
    o = engine.state.players[opp_idx]
    returned: list[CardInstance] = []
    skipped: list[int] = []

    def devolve_mon(mon: InPlayPokemon) -> InPlayPokemon:
        if len(mon.stack) < 2:
            return mon
        if ctx.trigger == "on_attack" and engine._protected_from_attack_effects(
            mon, opp_idx
        ):
            skipped.append(mon.current.iid)
            return mon
        returned.append(mon.stack[-1])
        return mon.model_copy(update={
            "stack": mon.stack[:-1], "conditions": frozenset(),
            # 麻痹施加标记随状态恢复清除（task 026 WP7，D-WP7-2）
            "paralyzed_mark": None,
        })

    active = devolve_mon(o.active) if o.active is not None else None
    bench = tuple(devolve_mon(b) for b in o.bench)
    engine._set_player(opp_idx, o.model_copy(update={
        "active": active, "bench": bench,
        "hand": o.hand + tuple(returned),
    }))
    if returned:
        ctx.emit("devolve", iids=[c.iid for c in returned],
                 names=[c.card.name for c in returned])
        engine.check_knockouts()  # 退化后 HP 超限昏厥（§8；效果内只入队不翻阶段）
    result: dict[str, object] = {"devolved": len(returned)}
    if skipped:
        result["skipped_protected"] = skipped
    return result



# ── task 026 WP7：小原语批（D-WP7-3/6/9/10④）──────────────────────────────────


@register("modify_damage")
def _modify_damage(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """回合级伤害修正标记（task 026 WP7 空手道王的修炼，D-WP7-3）：on_play 解释
    执行——写 PlayerState.turn_damage_mods（(增减值, 目标规则盒限定 | None)），
    持有方回合结束清除（core._on_turn_end / 检查阶段入口双清）；求和与
    target_rule_box 过滤在引擎 _effective_damage_modifier 求值点。
    passive_static 挂载（道具/竞技场/aura）是声明式，不经本原语。
    """
    _require_no_choose(node, "modify_damage")
    if ctx.trigger != "on_play":
        raise DslError(
            f"modify_damage 解释执行仅支持 on_play（收到 trigger={ctx.trigger!r}；"
            f"passive_static 为声明式挂载，引擎读声明）"
        )
    if "scope" in node.args:
        raise DslError(
            f"on_play modify_damage 不支持 args.scope（收到 {node.args['scope']!r}；"
            f"aura 是 passive_static 声明，不猜）"
        )
    amount = node.args.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise DslError(f"modify_damage 需要 args.amount int（收到 {amount!r}）")
    target_rule_box = node.args.get("target_rule_box")
    p = ctx.player_state
    ctx.set_player_state(p.model_copy(update={
        "turn_damage_mods": p.turn_damage_mods + ((amount, target_rule_box),),
    }))
    return {"amount": amount, "target_rule_box": target_rule_box}


@register("discard_stadium")
def _discard_stadium(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """弃置竞技场（task 026 WP7，D-WP7-6）：公共场进其放置方（stadium_owner）
    弃牌区 + 状态清理；无竞技场 no-op。备战区失效缩减由引擎完成路径
    _check_bench_shrink 复查承接（D-WP6-2 触点）。无 selector/choose/count
    参数（带则 DslError 不猜）。
    """
    _require_no_choose(node, "discard_stadium")
    if node.selector is not None:
        raise DslError(f"discard_stadium 不支持 selector（收到 {node.selector!r}）")
    if node.count is not None:
        raise DslError(f"discard_stadium 不支持 count（收到 {node.count!r}）")
    engine = ctx.engine
    stadium, owner = engine.state.stadium, engine.state.stadium_owner
    if stadium is None:
        return {"discarded": None}
    engine.state = engine.state.model_copy(update={
        "stadium": None, "stadium_owner": None,
    })
    if owner is not None:
        p = engine.state.players[owner]
        engine._set_player(owner, p.model_copy(update={
            "discard": p.discard + (stadium,),
        }))
    return {"discarded": stadium.card.name}


@register("shuffle_hand_into_deck")
def _shuffle_hand_into_deck(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """手牌洗回牌库（task 026 WP7 裁判，D-WP7-9）：selector=own_hand/
    opponent_hand——该方手牌全部回库后重洗（单一随机源 rng.shuffle，
    种子确定性硬规矩）；手牌空照常重洗（裁判语序：先洗回再抽牌）。
    """
    _require_no_choose(node, "shuffle_hand_into_deck")
    if node.selector not in ("own_hand", "opponent_hand"):
        raise DslError(
            f"shuffle_hand_into_deck 暂仅支持 own_hand/opponent_hand"
            f"（收到 {node.selector!r}）"
        )
    engine = ctx.engine
    who = ctx.player if node.selector == "own_hand" else 1 - ctx.player
    p = engine.state.players[who]
    engine._set_player(who, p.model_copy(update={
        "deck": engine.rng.shuffle(p.deck + p.hand), "hand": (),
    }))
    return {"shuffled": len(p.hand), "player": who}


@register("mill")
def _mill(ctx: ExecutionContext, node: ActionNode, choice: tuple[int, ...] | None) -> dict[str, object]:
    """磨牌（task 026 WP7，D-WP7-10④）：对手牌库顶 N 张 → 对手弃牌区（保序）；
    牌库不足收缩（全磨），空库 no-op；效果磨光牌库不判负——判负只在回合
    开始抽牌（rules-manual §8 胜利条件，core._begin_turn 单一判定点）。
    """
    _require_no_choose(node, "mill")
    if node.selector != "opponent_deck":
        raise DslError(f"mill 暂仅支持 selector=opponent_deck（收到 {node.selector!r}）")
    count = node.count
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise DslError(f"mill 需要 count 正 int（收到 {count!r}）")
    engine = ctx.engine
    opp_idx = 1 - ctx.player
    o = engine.state.players[opp_idx]
    milled = o.deck[:count]
    engine._set_player(opp_idx, o.model_copy(update={
        "deck": o.deck[len(milled):], "discard": o.discard + milled,
    }))
    return {"milled": len(milled), "iids": [c.iid for c in milled]}
