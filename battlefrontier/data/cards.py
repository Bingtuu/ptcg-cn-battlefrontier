"""SDK Card → CardDef 字段映射（2026-08-29 接入约定）。

口径：不猜——supertype/stage 词表外直接抛错；prize 张数、弱点/抗性值与
引擎规则常数不符时记 warning 返回（不静默、不改值），由上层汇集呈现。
挂载键 = card_id 精确挂载（task 026，2026-09-06 决议；同名异文本印刷不共用文档）。
"""

from battlefrontier.engine.core import PRIZE_BY_RULE_BOX
from battlefrontier.engine.state import AttackDef, CardDef, Supertype

SUPERTYPE_MAP = {
    "pokemon": Supertype.POKEMON,
    "trainer": Supertype.TRAINER,
    "energy": Supertype.ENERGY,
}
STAGE_MAP = {"基础": 0, "1阶": 1, "2阶": 2}  # 对齐 db stage 中文词表


def carddef_from_db(card) -> tuple[CardDef, list[str]]:
    """单卡映射；返回 (CardDef, warnings)。词表外字段抛 ValueError。"""
    warnings: list[str] = []

    supertype = SUPERTYPE_MAP.get(card.card_type)
    if supertype is None:
        raise ValueError(f"{card.card_id} 未知 card_type: {card.card_type!r}")

    stage = 0
    if supertype == Supertype.POKEMON:
        if card.stage not in STAGE_MAP:
            raise ValueError(f"{card.card_id} 未知 stage: {card.stage!r}")
        stage = STAGE_MAP[card.stage]

    # 弱点/抗性值校验（规则固定 ×2 / -30，rules-manual §6；异常值不猜）
    if card.weakness is not None and card.weakness.value != "×2":
        warnings.append(f"{card.card_id} {card.name_full} 弱点值 {card.weakness.value!r} 非 ×2")
    if card.resistance is not None and card.resistance.value != "-30":
        warnings.append(f"{card.card_id} {card.name_full} 抗性值 {card.resistance.value!r} 非 -30")

    # 奖赏张数校验：db prize_cards vs 引擎 PRIZE_BY_RULE_BOX（rules-manual §7）
    if supertype == Supertype.POKEMON:
        expected = PRIZE_BY_RULE_BOX.get(card.rule_box_type or "", 1)
        if card.prize_cards != expected:
            warnings.append(
                f"{card.card_id} {card.name_full} 奖赏张数不符："
                f"db prize_cards={card.prize_cards}，引擎 prize={expected}"
            )

    attacks = tuple(
        AttackDef(
            name=a.name,
            cost=tuple(c.type for c in a.cost for _ in range(c.count)),
            damage=a.damage_base,
            damage_modifier=a.damage_modifier,
        )
        for a in (card.attacks or ())
    )

    if supertype == Supertype.POKEMON:
        energy_type = card.types[0] if card.types else None
    elif supertype == Supertype.ENERGY:
        energy_type = card.provides[0] if card.provides else None
    else:
        energy_type = None

    card_def = CardDef(
        card_id=card.card_id,
        name=card.name_full,
        supertype=supertype,
        hp=card.hp,
        stage=stage,
        evolves_from=card.evolves_from_text,
        evolution_chain=card.evolution_chain_id,
        energy_type=energy_type,
        is_basic_energy=bool(getattr(card, "is_basic_energy", False)),
        attacks=attacks,
        retreat_cost=card.retreat_cost or 0,
        weakness=card.weakness.type if card.weakness else None,
        resistance=card.resistance.type if card.resistance else None,
        rule_box=card.rule_box_type,
        trainer_subtype=card.trainer_subtype,
        is_ace_spec=bool(card.is_ace_spec),
        is_tera=bool(getattr(card, "is_tera", False)),
        owner=getattr(card, "owner", None),
        # 特质标签（task 026 WP1）：effect_tags.labels = mik 机制标签（古代/未来等，
        # db PRD v1.23 契约键）；db 无独立特质列，缺 effect_tags 即空组（不猜）
        labels=tuple(getattr(getattr(card, "effect_tags", None), "labels", None) or ()),
        # 特性存在标记（task 026 WP7）：db abilities 非空即 True（列表/None 两形态都吃）
        has_ability=bool(getattr(card, "abilities", None)),
    )
    return card_def, warnings
