"""单卡 DSL 测试（task 025 批 1 wave 1）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批卡：
- 吉尼亚：检索牌库 ≤2 张进化宝可梦入手 + 洗牌（支援者 on_play）。
- 波波：招式「呼朋引伴」检索牌库 ≤2 张【基础】宝可梦直放备战区 + 洗牌；
  「撞击」为白板固定伤害，无需 DSL（附带回归确认互不干扰）。
规则出处：检索为 up-to 语义（可以不找）；检索后必须洗牌（官方规则·检索）。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state, stage1

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

GEETA_DOC = load_card_doc(CARDS_DIR / "吉尼亚.yml")
PIDGEY_DOC = load_card_doc(CARDS_DIR / "波波.yml")


def supporter(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="支援者")


# ── 吉尼亚 ────────────────────────────────────────────────────────────


def geeta_engine(deck: tuple):
    """main 阶段、p0 手牌含吉尼亚（iid 60）、牌库为指定构成的引擎。"""
    state = main_state(p0_extra_hand=(inst(60, supporter("吉尼亚")),))
    p0 = state.players[0].model_copy(update={"deck": deck})
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"吉尼亚": GEETA_DOC}
    return engine


def geeta_deck() -> tuple:
    """1 阶 + 2 阶（合法）+ 基础 + 能量（均应被过滤）。"""
    stage2 = CardDef(
        card_id="stub-妙蛙花", name="妙蛙花", supertype="pokemon",
        hp=140, stage=2, evolves_from="妙蛙草",
    )
    return (
        inst(100, stage1("妙蛙草", "妙蛙种子")),
        inst(101, stage2),
        inst(102, basic("小拉达")),
        inst(103, energy()),
    )


def test_吉尼亚_full_flow() -> None:
    """全链路：挂起检索 → 选 2 张进化宝可梦入手 → 洗牌 → 本体进弃牌区。"""
    e = geeta_engine(geeta_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    # 池 = {100, 101}，最多 2 张（up-to 语义含空集）
    assert sorted(a.choices for a in choices) == [(), (100,), (100, 101), (101,)]
    e.apply(0, next(a for a in choices if a.choices == (100, 101)))
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert [c.iid for c in p0.hand] == [50, 51, 100, 101]
    assert [c.iid for c in p0.discard] == [60]  # 本体收尾进弃牌区
    assert len(p0.deck) == 2  # 取走 2 张且已洗牌
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
    assert any(ev.kind == "effect_observe" and ev.detail["anchor"] == "key_search" for ev in e.events)


def test_吉尼亚_filters_non_evolved() -> None:
    """负例：【基础】宝可梦与能量均不进检索池（仅 1 阶及以上进化宝可梦）。"""
    e = geeta_engine(geeta_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {100, 101}  # 小拉达(基础)/能量被过滤


def test_吉尼亚_decline_search_still_shuffles() -> None:
    """选空集（不找）：效果空结算，但洗牌仍执行（检索后必洗）。"""
    e = geeta_engine(geeta_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == ()))
    p0 = e.state.players[0]
    assert [c.iid for c in p0.hand] == [50, 51] and len(p0.deck) == 4
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1


# ── 波波 ──────────────────────────────────────────────────────────────


def pidgey() -> CardDef:
    return CardDef(
        card_id="stub-波波", name="波波", supertype="pokemon",
        hp=50, stage=0,
        attacks=(
            AttackDef(name="呼朋引伴", cost=("无",), damage=None),
            AttackDef(name="撞击", cost=("无", "无"), damage=20),
        ),
    )


def pidgey_engine(deck: tuple, energies: int = 1):
    """main 阶段、p0 战斗场为波波（iid 1，能量数可调）、牌库为指定构成。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, pidgey(), energies),
        "deck": deck,
    })
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"波波": PIDGEY_DOC}
    return engine


def pidgey_deck() -> tuple:
    """基础 ×2（合法）+ 1 阶 + 能量（均应被过滤）。"""
    return (
        inst(100, basic("小拉达")),
        inst(101, basic("喵喵")),
        inst(102, stage1("妙蛙草", "妙蛙种子")),
        inst(103, energy()),
    )


def test_波波_呼朋引伴_full_flow() -> None:
    """全链路：攻击挂起检索 → 选 2 只基础直放备战区 → 洗牌 → 回合权移交对手。"""
    e = pidgey_engine(pidgey_deck())
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert sorted(a.choices for a in choices) == [(), (100,), (100, 101), (101,)]
    e.apply(0, next(a for a in choices if a.choices == (100, 101)))
    p0 = e.state.players[0]
    assert [m.current.iid for m in p0.bench] == [100, 101]
    assert {100, 101} <= p0.entered_play_this_turn  # 当回合登场 → 不可进化联动
    assert len(p0.deck) == 2  # 取走 2 张且已洗牌
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
    assert any(ev.kind == "effect_observe" and ev.detail["anchor"] == "key_search" for ev in e.events)
    # 招式结算完成 → 回合结束，对手开始回合
    assert e.state.current_player == 1 and e.state.phase == "main"
    assert e.state.players[1].active.damage == 0  # 呼朋引伴无伤害


def test_波波_呼朋引伴_filters_non_basic() -> None:
    """负例：1 阶进化与能量均不进检索池（仅【基础】宝可梦）。"""
    e = pidgey_engine(pidgey_deck())
    e.apply(0, Action(kind="attack", attack_index=0))
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {100, 101}  # 妙蛙草(1阶)/能量被过滤


def test_波波_呼朋引伴_decline_search_still_shuffles() -> None:
    """选空集（不找）：备战区不进宝可梦，洗牌仍执行，回合照常移交。"""
    e = pidgey_engine(pidgey_deck())
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == ()))
    p0 = e.state.players[0]
    assert len(p0.bench) == 0 and len(p0.deck) == 4
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
    assert e.state.current_player == 1


def test_波波_撞击_whiteboard_damage() -> None:
    """白板招式「撞击」：无 DSL 绑定，固定 20 伤害走引擎骨架，互不干扰。"""
    e = pidgey_engine((), energies=2)
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[1].active.damage == 20
    assert e.state.current_player == 1
