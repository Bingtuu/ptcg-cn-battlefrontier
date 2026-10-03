"""DSL 变量伤害估算与效果模式检测（task 032 WP2，D-032-3 ~ D-032-6）。

启发式 Agent 的 DSL 读取层：全部纯函数、零随机、只读 VisibleGameState（可见视图
纪律不破——DSL 文档 = 公开卡面信息），不 import 引擎运行态。任何未知结构
（未知计数词 / 无 DSL 文档 / 无 damage 节点 / 嵌套 copy / 掷币门控）一律返回
None / False，由调用方回退静态基值或现状行为（不猜）。

口径要点（D-032-3）：
- discarded_this_effect 回读同效果前序 discard 节点池：own_hand → 手牌中匹配
  该 discard 节点 filters 的卡数；own_attached_energy → 攻击方宝可梦附着能量数；
- 效果级 condition 仅求值奖赏类词 opponent_prizes_eq:N / opponent_prizes_in:[...]
  （可见状态可判）；不满足 → 不参与斩杀（lethal_ok=False，amount=0——招式失败
  无伤害）；其他未知 condition → 基值仍入表但不参与斩杀（lethal_ok=False）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from battlefrontier.dsl.chooser import matches
from battlefrontier.dsl.interpreter import flatten_steps
from battlefrontier.dsl.loader import CardLibrary, DslError
from battlefrontier.dsl.schema import ActionNode, CardEffectDoc, Effect
from battlefrontier.engine.state import CardDef, PendingChoice, VisibleGameState

__all__ = [
    "DamageEstimate",
    "attack_has_draw",
    "card_has_draw",
    "damage_formula",
    "doc_for",
    "estimate_attack_damage",
    "find_attack_effect",
    "has_hand_ammo_pattern",
    "pending_damage_link",
]


@dataclass(frozen=True)
class DamageEstimate:
    """一招的估算伤害（未含弱点/抗性，修正由调用方后处理）+ 斩杀资格。"""

    amount: int
    lethal_ok: bool


def doc_for(
    card_effects: Mapping[str, CardEffectDoc], card: CardDef
) -> CardEffectDoc | None:
    """按卡身份解析 DSL 文档（引擎 effect_doc 同口径，防同名异文本静默错挂）。

    CardLibrary（装载键 = card_id 精确挂载）：仅按 card_id 取，无名字兜底；
    朴素 dict = 存量测试兼容路径，按卡名取。
    """
    if isinstance(card_effects, CardLibrary):
        return card_effects.get(card.card_id)
    return card_effects.get(card.name)


def find_attack_effect(doc: CardEffectDoc, attack_name: str) -> Effect | None:
    """trigger=on_attack 且绑定该招式名的效果块。"""
    return next(
        (e for e in doc.effects if e.trigger == "on_attack" and e.attack == attack_name),
        None,
    )


def damage_formula(node: ActionNode, n: int) -> int | None:
    """damage 节点公式求值：args.amount 固定 / {per, op:"×"|"+", base}（n = 计数值）。

    结构畸形（per/op/base 非法）→ None（不猜，调用方回退）。
    """
    if "amount" in node.args:
        amount = node.args["amount"]
        return amount if isinstance(amount, int) and amount >= 0 else None
    per, op = node.args.get("per"), node.args.get("op")
    if not isinstance(per, int) or per <= 0:
        return None
    if op == "×":
        return n * per
    if op == "+":
        base = node.args.get("base", 0)
        return base + n * per if isinstance(base, int) and base >= 0 else None
    return None


def _prize_condition_met(condition: str, opponent_prizes_count: int) -> bool | None:
    """奖赏类 effect 级 condition 求值（可见状态可判）；非奖赏词 / 畸形参数 → None。"""
    if condition.startswith("opponent_prizes_eq:"):
        try:
            return opponent_prizes_count == int(condition.split(":", 1)[1])
        except ValueError:
            return None
    if condition.startswith("opponent_prizes_in:"):
        body = condition.split(":", 1)[1]
        if not (body.startswith("[") and body.endswith("]")):
            return None
        try:
            values = [int(v) for v in body[1:-1].split(",")]
        except ValueError:
            return None
        return opponent_prizes_count in values
    return None


def _visible_counter(
    word: str, view: VisibleGameState, steps: list[tuple[str, ActionNode]], damage_idx: int
) -> int | None:
    """计数词 → 可见状态量。未知 / 依赖隐藏信息（掷币、已选目标）→ None。"""
    own, opp = view.own, view.opponent
    if word == "discarded_this_effect":
        # 回读同效果前序（damage 节点之前）最近的 discard 节点池
        for _, node in reversed(steps[:damage_idx]):
            if node.action != "discard":
                continue
            if node.selector == "own_hand":
                try:
                    return sum(1 for c in own.hand if matches(c, node.filters))
                except DslError:
                    return None
            if node.selector == "own_attached_energy":
                return len(own.active.attached_energy) if own.active else 0
        return None
    if word == "attached_energy_on_both_actives":
        return (
            (len(own.active.attached_energy) if own.active else 0)
            + (len(opp.active.attached_energy) if opp.active else 0)
        )
    if word == "attached_energy_on_opponent_active":
        return len(opp.active.attached_energy) if opp.active else 0
    if word == "bench_count_both":
        return len(own.bench) + len(opp.bench)
    if word == "opponent_taken_prizes":
        return 6 - opp.prizes_count
    if word == "opponent_remaining_prizes":
        return opp.prizes_count
    if word == "own_remaining_prizes":
        return own.prizes_count
    if word == "opponent_ability_pokemon_count":
        return sum(
            1
            for m in ([opp.active] if opp.active else []) + list(opp.bench)
            if m.current.card.has_ability
        )
    if word == "damage_counters_on_self":
        return (own.active.damage // 10) if own.active else 0
    return None


def estimate_attack_damage(
    view: VisibleGameState,
    attack_name: str,
    base_damage: int | None,
    source_card: CardDef,
    card_effects: Mapping[str, CardEffectDoc] | None,
) -> DamageEstimate | None:
    """on_attack 效果的 damage 节点（selector=opponent_active）→ 估算伤害。

    返回 None = 调用方回退静态基值（无 card_effects / 无文档 / 无绑定效果 /
    无 damage 节点 / 未知计数词 / 掷币门控节点）。condition 可判时回
    DamageEstimate（lethal_ok 标记斩杀资格），不消耗任何随机源。
    """
    if card_effects is None:
        return None
    doc = doc_for(card_effects, source_card)
    if doc is None:
        return None
    effect = find_attack_effect(doc, attack_name)
    if effect is None:
        return None
    if effect.condition is not None:
        met = _prize_condition_met(effect.condition, view.opponent.prizes_count)
        if met is None:
            # 未知 condition：基值仍入表但不参与斩杀判定（D-032-3）
            return DamageEstimate(amount=base_damage or 0, lethal_ok=False)
        if not met:
            # 奖赏条件不满足 → 招式失败（古月鸟型）：无伤害、不参与斩杀
            return DamageEstimate(amount=0, lethal_ok=False)
    steps = flatten_steps(effect)
    for i, (_, node) in enumerate(steps):
        if node.action != "damage" or node.selector != "opponent_active":
            continue
        if node.condition is not None:
            return None  # 掷币门控等节点级条件 → 估算不可判定，回退基值
        if "amount" in node.args:
            amount = node.args["amount"]
            if isinstance(amount, int) and amount >= 0:
                return DamageEstimate(amount=amount, lethal_ok=True)
            return None
        if not isinstance(node.count, str):
            return None
        n = _visible_counter(node.count, view, steps, i)
        if n is None:
            return None
        value = damage_formula(node, n)
        return DamageEstimate(amount=value, lethal_ok=True) if value is not None else None
    return None


def pending_damage_link(
    pc: PendingChoice, card_effects: Mapping[str, CardEffectDoc] | None
) -> ActionNode | None:
    """D-032-4：pending choose 为伤害关联的 any_count discard → 返回该 damage 节点。

    判定链：pool ∈ {own_hand, own_attached_energy} 且 min_choose=0、max>1；
    来源卡 + effect_index 取文档，cursor 指向的扁平步骤为 discard，同效果后续
    步骤含 damage selector=opponent_active count=discarded_this_effect。
    嵌套 copy（inner 非空）/ 无文档 / 结构不符 → None（调用方回退评分方向）。
    """
    if card_effects is None or pc.inner is not None:
        return None
    if pc.pool not in ("own_hand", "own_attached_energy"):
        return None
    if not (pc.min_choose == 0 and pc.max_choose > 1):
        return None
    doc = doc_for(card_effects, pc.source.card)
    if doc is None or not (0 <= pc.effect_index < len(doc.effects)):
        return None
    steps = flatten_steps(doc.effects[pc.effect_index])
    if not (0 <= pc.cursor < len(steps)) or steps[pc.cursor][1].action != "discard":
        return None
    for _, node in steps[pc.cursor + 1:]:
        if (
            node.action == "damage"
            and node.selector == "opponent_active"
            and node.count == "discarded_this_effect"
        ):
            return node
    return None


def has_hand_ammo_pattern(
    source_card: CardDef, card_effects: Mapping[str, CardEffectDoc] | None
) -> bool:
    """D-032-5 手牌弹药型：任一 on_attack 效果含 discard own_hand + 后续
    damage count=discarded_this_effect（淘金潮型——能量留手牌作弹药）。"""
    if card_effects is None:
        return False
    doc = doc_for(card_effects, source_card)
    if doc is None:
        return False
    for effect in doc.effects:
        if effect.trigger != "on_attack":
            continue
        steps = flatten_steps(effect)
        for i, (_, node) in enumerate(steps):
            if node.action == "discard" and node.selector == "own_hand" and any(
                later.action == "damage" and later.count == "discarded_this_effect"
                for _, later in steps[i + 1:]
            ):
                return True
    return False


def _effect_has_draw(effect: Effect) -> bool:
    return any(node.action == "draw" for node in effect.actions)


def card_has_draw(
    card: CardDef, card_effects: Mapping[str, CardEffectDoc] | None
) -> bool:
    """D-032-6：卡文档任一效果 actions 含 draw 节点（不过度细分「纯过牌」）。"""
    if card_effects is None:
        return False
    doc = doc_for(card_effects, card)
    return doc is not None and any(_effect_has_draw(e) for e in doc.effects)


def attack_has_draw(
    source_card: CardDef, attack_name: str,
    card_effects: Mapping[str, CardEffectDoc] | None,
) -> bool:
    """D-032-6 攻击侧：招式绑定的 on_attack 效果 actions 含 draw 节点。"""
    if card_effects is None:
        return False
    doc = doc_for(card_effects, source_card)
    if doc is None:
        return False
    effect = find_attack_effect(doc, attack_name)
    return effect is not None and _effect_has_draw(effect)
