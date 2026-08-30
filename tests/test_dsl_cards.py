"""单卡 DSL 测试：从 cards/ 真实文件装载（load_card_doc），stub 引擎驱动全链路。

按批次分节注释（task 024 起）。

═══ 批次：task 024 harness 自验卡 ═══
友好宝芬：检索牌库 ≤2 张 HP≤70【基础】宝可梦直放备战区 + 洗牌。
规则出处：检索为 up-to 语义（可以不找）；检索后必须洗牌（官方规则·检索）。
"""

from pathlib import Path

from helpers import basic, energy, engine_at, inst, main_state, stage1

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import CardDef

CARDS_DIR = Path(__file__).parent.parent / "cards"

POFFIN_DOC = load_card_doc(CARDS_DIR / "友好宝芬.yml")


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品")


def poffin_engine(deck: tuple, **kwargs):
    """main 阶段、p0 手牌含友好宝芬（iid 60）、牌库为指定构成的引擎。"""
    state = main_state(p0_extra_hand=(inst(60, item("友好宝芬")),), **kwargs)
    p0 = state.players[0].model_copy(update={"deck": deck})
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"友好宝芬": POFFIN_DOC}
    return engine


def mixed_deck() -> tuple:
    """5 张牌：HP≤70 基础 ×2（合法）+ HP>70 基础 + 1 阶 + 能量（均应被过滤）。"""
    return (
        inst(100, basic("妙蛙种子", hp=70)),
        inst(101, basic("小拉达", hp=30)),
        inst(102, basic("卡比兽", hp=150)),
        inst(103, stage1("妙蛙草", "妙蛙种子", hp=90)),
        inst(104, energy()),
    )


def test_友好宝芬_full_flow() -> None:
    """全链路：挂起检索 → 选 2 只 HP≤70 基础 → 直放备战区 → 洗牌 → 本体进弃牌区。"""
    e = poffin_engine(mixed_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    # 池 = {100, 101}，最多 2 张（up-to 语义含空集）
    assert sorted(a.choices for a in choices) == [(), (100,), (100, 101), (101,)]
    e.apply(0, next(a for a in choices if a.choices == (100, 101)))
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert [m.current.iid for m in p0.bench] == [100, 101]
    assert {100, 101} <= p0.entered_play_this_turn  # 当回合登场 → 不可进化联动
    assert [c.iid for c in p0.discard] == [60]  # 本体收尾进弃牌区
    assert len(p0.deck) == 3  # 取走 2 张且已洗牌
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1


def test_友好宝芬_hp_and_stage_filtering() -> None:
    """负例：HP>70 的基础、1 阶进化、能量均不进检索池。"""
    e = poffin_engine(mixed_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {100, 101}  # 卡比兽(HP150)/妙蛙草(stage1)/能量被过滤


def test_友好宝芬_decline_search_still_shuffles() -> None:
    """选空集（不找）：效果空结算，但洗牌仍执行（检索后必洗）。"""
    e = poffin_engine(mixed_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == ()))
    p0 = e.state.players[0]
    assert len(p0.bench) == 0 and len(p0.deck) == 5
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1


def test_友好宝芬_no_eligible_target_noop() -> None:
    """牌库无 HP≤70 基础：池空不挂起（尽力而为），效果空结算但仍洗牌。"""
    deck = (inst(100, basic("卡比兽", hp=150)), inst(101, energy()))
    e = poffin_engine(deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert len(e.state.players[0].bench) == 0
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1


# ═══ 批次：task 025 小原语代表卡 ═══
# 捕获香氛（coin_flip + 节点级门控）/ 交替推车（heal + switch own_bench）/
# 弗图博士的剧本（bounce）/ 不服输头带（modify_damage 声明式结算接入）。
# 规则出处：掷币与恢复（rules-manual §7.1）；互换清状态（§7.1 恢复途径「撤退或效果」）；
# bounce 结算（卡面 rule_reference 句 + rules-reference 附录 A·2026-08-30 决议）；
# 伤害修饰顺序（rules-manual §6：基准 → 攻方修饰 → 弱点 → 抗性）。

from helpers import in_play

from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import InPlayPokemon, SpecialCondition

AROMA_DOC = load_card_doc(CARDS_DIR / "捕获香氛.yml")
CART_DOC = load_card_doc(CARDS_DIR / "交替推车.yml")
FUTURE_DOC = load_card_doc(CARDS_DIR / "弗图博士的剧本.yml")
BAND_DOC = load_card_doc(CARDS_DIR / "不服输头带.yml")


def supporter(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="支援者")


def tool(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="宝可梦道具")


def aroma_engine(seed: int, deck: tuple):
    """main 阶段、p0 手牌含捕获香氛（iid 60）、牌库指定构成、随机源种子可注入。"""
    state = main_state(p0_extra_hand=(inst(60, item("捕获香氛")),))
    p0 = state.players[0].model_copy(update={"deck": deck})
    engine = GameEngine(RandomSource(seed))
    engine.state = state.model_copy(update={"players": (p0, state.players[1])})
    engine.card_effects = {"捕获香氛": AROMA_DOC}
    return engine


def aroma_deck() -> tuple:
    return (
        inst(100, basic("妙蛙种子")), inst(101, basic("小火龙")),
        inst(102, stage1("妙蛙草", "妙蛙种子")),
    )


def test_捕获香氛_heads_searches_evolved_pokemon():
    """正面（seed 0）：检索池仅进化宝可梦；反面分支落 skipped 事件；洗牌照常。"""
    e = aroma_engine(0, aroma_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {102}
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (102,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert [c.iid for c in p0.hand] == [50, 51, 102]
    assert [c.iid for c in p0.discard] == [60]
    skips = [
        ev for ev in e.events
        if ev.kind == "effect_primitive" and ev.detail["result"].get("skipped")
    ]
    assert len(skips) == 1 and skips[0].detail["result"]["condition"] == "if_flip_tails"
    shuffles = [ev for ev in e.events if ev.kind == "effect_primitive" and ev.detail["action"] == "shuffle_deck"]
    assert len(shuffles) == 1
    assert any(ev.kind == "effect_observe" and ev.detail["anchor"] == "key_search" for ev in e.events)


def test_捕获香氛_tails_searches_basic_pokemon():
    """反面（seed 1）：检索池仅【基础】宝可梦；正面分支先跳过。"""
    e = aroma_engine(1, aroma_deck())
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    skips = [
        ev for ev in e.events
        if ev.kind == "effect_primitive" and ev.detail["result"].get("skipped")
    ]
    assert len(skips) == 1 and skips[0].detail["result"]["condition"] == "if_flip_heads"
    pooled = {iid for a in e.legal_actions(0) if a.kind == "choose" for iid in a.choices}
    assert pooled == {100, 101}
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (100,)))
    assert [c.iid for c in e.state.players[0].hand] == [50, 51, 100]


def cart_engine(*, active_card=None, active_damage: int = 0,
                paralyzed: bool = False, bench: tuple = ()):
    """p0 战斗场（可带伤害/麻痹）+ 备战区，手牌含交替推车（iid 60）。"""
    state = main_state(p0_extra_hand=(inst(60, item("交替推车")),))
    p0 = state.players[0]
    active = p0.active if active_card is None else in_play(1, active_card, 1)
    active = active.model_copy(update={
        "damage": active_damage,
        "conditions": frozenset({SpecialCondition.PARALYZED}) if paralyzed else frozenset(),
    })
    p0 = p0.model_copy(update={"active": active, "bench": bench})
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"交替推车": CART_DOC}
    return engine


def test_交替推车_full_flow_heal_then_switch():
    """全链路：战斗场（50 伤害 + 麻痹）先回复 30 再与备战互换；回备战清状态、伤害随动。"""
    e = cart_engine(active_damage=50, paralyzed=True, bench=(in_play(70, basic("小拉达")),))
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (70,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert p0.active.current.iid == 70  # 备战换入战斗场
    out = p0.bench[0]
    assert out.current.iid == 1  # 原战斗宝可梦换入备战区
    assert out.damage == 20  # 50 - 恢复 30（机制取舍：先 heal 再互换，与原文终态等价）
    assert out.conditions == frozenset()  # 回备战区特殊状态恢复
    assert [c.iid for c in p0.discard] == [60]
    assert not p0.retreated_this_turn  # 效果互换不占撤退次数


def test_交替推车_requires_basic_active():
    """战斗场非【基础】（1 阶进化）：条件门拦截，不枚举。"""
    e = cart_engine(active_card=stage1("妙蛙草", "妙蛙种子"),
                    bench=(in_play(70, basic("小拉达")),))
    assert Action(kind="play_trainer", iid=60) not in e.legal_actions(0)


def test_交替推车_unavailable_without_bench():
    """无备战宝可梦：可行性门拦截，不枚举。"""
    e = cart_engine(active_damage=50)
    assert Action(kind="play_trainer", iid=60) not in e.legal_actions(0)


def future_engine(*, bench: tuple = ()):
    state = main_state(p0_extra_hand=(inst(60, supporter("弗图博士的剧本")),))
    p0 = state.players[0].model_copy(update={"bench": bench})
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"弗图博士的剧本": FUTURE_DOC}
    return engine


def test_弗图博士的剧本_bounce_bench_stack():
    """备战进化链（带能量+道具）：整叠回手牌，能量/道具进弃牌区，本体收尾弃置。"""
    mon = InPlayPokemon(
        stack=(inst(70, basic("妙蛙种子")), inst(71, stage1("妙蛙草", "妙蛙种子"))),
        attached_energy=(inst(72, energy()),),
        attached_tool=inst(73, tool("测试道具")),
    )
    e = future_engine(bench=(mon,))
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice"
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (71,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main"
    assert p0.bench == ()
    assert [c.iid for c in p0.hand[-2:]] == [70, 71]
    assert [c.iid for c in p0.discard] == [72, 73, 60]
    assert p0.supporter_played_this_turn  # 支援者标记


def test_弗图博士的剧本_bounce_active_promotes_and_continues_main():
    """战斗场目标：换上后继续当前主阶段（附录 A 决议），不推进回合。"""
    e = future_engine(bench=(in_play(70, basic("小拉达")),))
    turn_before = e.state.turn
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "choose" and a.choices == (1,)))
    assert e.state.phase == "promote" and e.state.current_player == 0
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.turn == turn_before
    p0 = e.state.players[0]
    assert p0.active.current.iid == 70
    assert 1 in [c.iid for c in p0.hand]


def band_engine(*, p1_prizes: int = 5):
    """p0 战斗场挂不服输头带（iid 80），p1 奖赏数可调。"""
    state = main_state()
    p0 = state.players[0]
    p0 = p0.model_copy(update={
        "active": p0.active.model_copy(update={"attached_tool": inst(80, tool("不服输头带"))}),
    })
    p1 = state.players[1].model_copy(update={"prizes": state.players[1].prizes[:p1_prizes]})
    engine = engine_at(state.model_copy(update={"players": (p0, p1)}))
    engine.card_effects = {"不服输头带": BAND_DOC}
    return engine


def test_不服输头带_boosts_when_behind_on_prizes():
    """自己奖赏多于对手：白板招式 +30（20→50，对对手战斗宝可梦）。"""
    e = band_engine(p1_prizes=5)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 50


def test_不服输头带_no_boost_when_not_behind():
    """奖赏不比对手多：原伤害 20；道具挂在身上但条件不满足即不生效。"""
    e = band_engine(p1_prizes=6)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20


def test_不服输头带_inert_without_dsl_doc():
    """引擎零硬编码防御：无 DSL 文档的同名道具不提供任何修正。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": state.players[0].active.model_copy(
            update={"attached_tool": inst(80, tool("不服输头带"))}),
    })
    p1 = state.players[1].model_copy(update={"prizes": state.players[1].prizes[:5]})
    engine = engine_at(state.model_copy(update={"players": (p0, p1)}))
    engine.apply(0, Action(kind="attack", attack_index=0))
    assert engine.state.players[1].active.damage == 20
