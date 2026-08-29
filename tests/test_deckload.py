"""task 010：卡组装载层（db → CardDef）+ DSL 定义库落盘验收测试。

数据源：ptcgdb SDK（只读，config/battlefrontier.local.yml 的 sqlite_path）。
口径：2026-08-29 接入约定（prize_cards 校验 / provides 能量属性 / 弱点抗性值校验）。
"""

import pytest

from battlefrontier.data import load_deck
from battlefrontier.dsl import load_card_dir
from battlefrontier.engine.state import Supertype

DB_PATH = r"C:/Vibe Project/Pokearena/data/ptcg-cn.db"
GARDEVOIR_DECK = "mik_moe:644634"


@pytest.fixture(scope="module")
def loaded():
    return load_deck(DB_PATH, GARDEVOIR_DECK)


def by_name(loaded, name: str):
    return next(c for c in loaded.cards if c.name == name)


def test_deck_loads_60_cards_and_validates(loaded) -> None:
    assert len(loaded.cards) == 60
    assert loaded.warnings == []  # 目标卡组零告警（跨源 38 待核销无交集，task 010 前置已核）


def test_gardevoir_ex_field_mapping(loaded) -> None:
    g = by_name(loaded, "沙奈朵ex")
    assert g.hp == 310 and g.energy_type == "超" and g.retreat_cost == 2
    assert g.weakness == "恶" and g.resistance == "斗"
    assert g.rule_box == "ex" and g.stage == 2 and g.evolves_from == "奇鲁莉安"
    assert len(g.attacks) == 1
    atk = g.attacks[0]
    assert atk.name == "奇迹之力" and atk.cost == ("超", "超", "无") and atk.damage == 190


def test_stage_and_evolution_chain(loaded) -> None:
    assert by_name(loaded, "拉鲁拉丝").stage == 0
    k = by_name(loaded, "奇鲁莉安")
    assert k.stage == 1 and k.evolves_from == "拉鲁拉丝"


def test_energy_provides_mapping(loaded) -> None:
    psy = by_name(loaded, "基本超能量")
    assert psy.supertype == Supertype.ENERGY
    assert psy.energy_type == "超" and psy.is_basic_energy


def test_variable_damage_modifier_preserved(loaded) -> None:
    """变量伤害：基准值装载 + 修饰符保留（白板结算忽略，DSL 落地时用）。"""
    drifloon = by_name(loaded, "飘飘球")
    balloon = next(a for a in drifloon.attacks if a.name == "气球炸弹")
    assert balloon.damage == 30 and balloon.damage_modifier == "×"
    mew = by_name(loaded, "梦幻ex")
    gene = next(a for a in mew.attacks if a.name == "基因侵入")
    assert gene.damage is None  # 复制招式：无基准伤害


def test_trainer_and_ace_spec_fields(loaded) -> None:
    assert by_name(loaded, "博士的研究").trainer_subtype == "支援者"
    box = by_name(loaded, "秘密箱")
    assert box.trainer_subtype == "物品" and box.is_ace_spec


def test_loaded_deck_plays_game(loaded) -> None:
    """装载卡组 + 定义库四卡效果：play_game 端到端跑通且同种子一致。"""
    from battlefrontier.runner.play import play_game

    effects = load_card_dir("cards")
    r1 = play_game(loaded.cards, loaded.cards, seed=11, card_effects=effects)
    r2 = play_game(loaded.cards, loaded.cards, seed=11, card_effects=effects)
    assert r1.events_hash == r2.events_hash


# ── 校验告警口径（不猜）─────────────────────────────────────────────────

def test_prize_mismatch_warns_not_guesses() -> None:
    """db prize_cards 与引擎 PRIZE_BY_RULE_BOX 不符 → warning，不静默不猜测。"""
    from battlefrontier.data.cards import carddef_from_db

    class FakeWeak:
        type = "恶"
        value = "×2"

    class FakeCard:
        card_id = "FAKE-001"
        name_full = "假面兽ex"
        card_type = "pokemon"
        hp = 200
        stage = "基础"
        types = ("恶",)
        weakness = FakeWeak()
        resistance = None
        retreat_cost = 1
        attacks = ()
        rule_box_type = "ex"
        prize_cards = 1  # 与映射表 ex=2 不符
        trainer_subtype = None
        is_ace_spec = False
        provides = None
        evolves_from_text = None

    card, warnings = carddef_from_db(FakeCard())
    assert card.rule_box == "ex"
    assert any("prize" in w.lower() or "奖赏" in w for w in warnings)


def test_unknown_stage_raises() -> None:
    from battlefrontier.data.cards import carddef_from_db

    class FakeCard:
        card_id = "FAKE-002"
        name_full = "谜之兽"
        card_type = "pokemon"
        hp = 100
        stage = "3阶"  # 词表外
        types = ("超",)
        weakness = None
        resistance = None
        retreat_cost = 0
        attacks = ()
        rule_box_type = None
        prize_cards = 1
        trainer_subtype = None
        is_ace_spec = False
        provides = None
        evolves_from_text = None

    with pytest.raises(ValueError, match="stage"):
        carddef_from_db(FakeCard())


# ── DSL 定义库（cards/）─────────────────────────────────────────────────

def test_card_library_loads_and_covers_four_cards() -> None:
    docs = load_card_dir("cards")
    assert {"博士的研究", "高级球", "巢穴球", "夜间担架"} <= set(docs)
    for name, doc in docs.items():
        assert doc.card.name_group == name  # 文件名/键 = name_group


def test_library_docs_semantics() -> None:
    """定义库四卡与任务验收语义一致（抽查结构）。"""
    docs = load_card_dir("cards")
    ub = docs["高级球"].effects[0]
    assert ub.cost[0].action == "discard" and ub.cost[0].choose == 2
    assert ub.actions[0].action == "search_deck" and ub.actions[0].destination == "hand"
    assert ub.actions[1].action == "shuffle_deck"
    nb = docs["巢穴球"].effects[0]
    assert nb.actions[0].destination == "bench"
    assert "basic_pokemon" in nb.actions[0].filters
