"""单卡 DSL 测试分片：task 025 批 1 wave 4（w4）。

从 cards/ 真实文件装载（load_card_doc），stub 引擎驱动全链路。

═══ 本 wave 卡单 ═══
宝可梦交替：自己战斗宝可梦与备战宝可梦互换（switch own_bench，task 025 原语）。
皮宝宝：招式「握握抽取」抽至手牌 7 张（draw args.until_hand）。
规则出处：互换回备战清特殊状态、伤害指示物与附着保留（rules-manual §7.1/§5）；
效果抽空牌库不判负（rules-manual·胜负判定，draw 原语注记）。

其余 4 卡（夜巡灵 / 猫头夜鹰 / 牡丹 / 摔角鹰人）因缺原语/缺机制标 blocked，
未写 DSL，详见批 1 wave 4 交付报告。
"""

from pathlib import Path

from helpers import basic, engine_at, inst, main_state
from test_attack import battle, mon

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef, InPlayPokemon

CARDS_DIR = Path(__file__).parent.parent / "cards"

SWITCH_DOC = load_card_doc(CARDS_DIR / "宝可梦交替.yml")
CLEFFA_DOC = load_card_doc(CARDS_DIR / "皮宝宝.yml")


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品")


# ── 宝可梦交替 ────────────────────────────────────────────────


def switch_engine(*, with_bench: bool = True):
    """main 阶段、p0 手牌含宝可梦交替（iid 60）、战斗场 iid 1、备战可选的引擎。"""
    state = main_state(p0_extra_hand=(inst(60, item("宝可梦交替")),))
    p0 = state.players[0]
    if with_bench:
        p0 = p0.model_copy(update={
            "bench": (
                InPlayPokemon(stack=(inst(10, basic("小火龙")),)),
                InPlayPokemon(stack=(inst(11, basic("妙蛙草")),)),
            ),
        })
    engine = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    engine.card_effects = {"宝可梦交替": SWITCH_DOC}
    return engine


def test_宝可梦交替_full_flow() -> None:
    """全链路：打出 → 挂起选备战 → 战斗场与所选备战互换 → 本体进弃牌区。"""
    e = switch_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert sorted(a.choices for a in choices) == [(10,), (11,)]  # 必换（min_choose=1）
    e.apply(0, next(a for a in choices if a.choices == (11,)))
    p0 = e.state.players[0]
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert p0.active.current.iid == 11  # 所选备战上战斗场
    assert [m.current.iid for m in p0.bench] == [10, 1]  # 原战斗场回备战区（原位）
    assert [c.iid for c in p0.discard] == [60]  # 本体收尾进弃牌区


def test_宝可梦交替_no_bench_unplayable() -> None:
    """无备战宝可梦：可行性门拦截，不枚举打出（「互换」无对象）。 """
    e = switch_engine(with_bench=False)
    plays = [a for a in e.legal_actions(0) if a.kind == "play_trainer"]
    assert all(a.iid != 60 for a in plays)


# ── 皮宝宝 ────────────────────────────────────────────────────


def cleffa_engine(hand_cards: tuple = ()):
    """p0 战斗场 = 皮宝宝（握握抽取，cost 0，伤害 None，DSL 绑定），手牌可指定。"""
    card = mon("皮宝宝", attacks=(AttackDef(name="握握抽取", cost=(), damage=None),), hp=30)
    state = battle(
        InPlayPokemon(stack=(inst(1, card),)),
        InPlayPokemon(stack=(inst(2, mon("厚皮兽", hp=200)),)),
    )
    p0 = state.players[0].model_copy(update={"hand": hand_cards})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"皮宝宝": CLEFFA_DOC}
    return e


def test_皮宝宝_握握抽取_draws_to_seven() -> None:
    """手牌 2 张时攻击：抽 5 张补至 7 张，牌库减 5。"""
    e = cleffa_engine(hand_cards=(inst(50, basic("小火龙")), inst(51, basic("妙蛙种子"))))
    e.apply(0, Action(kind="attack", attack_index=0))
    p0 = e.state.players[0]
    assert len(p0.hand) == 7
    assert len(p0.deck) == 5
    draws = [ev for ev in e.events
             if ev.kind == "effect_primitive" and ev.detail["action"] == "draw"]
    assert len(draws) == 1 and draws[0].detail["result"]["until_hand"] == 7
    assert draws[0].detail["result"]["drawn"] == 5


def test_皮宝宝_握握抽取_hand_full_noop() -> None:
    """手牌已 ≥7 张：空结算合法（不抽牌、不报错）。"""
    hand = tuple(inst(50 + i, basic("小火龙")) for i in range(8))
    e = cleffa_engine(hand_cards=hand)
    e.apply(0, Action(kind="attack", attack_index=0))
    p0 = e.state.players[0]
    assert len(p0.hand) == 8
    assert len(p0.deck) == 10
    draws = [ev for ev in e.events
             if ev.kind == "effect_primitive" and ev.detail["action"] == "draw"]
    assert draws[0].detail["result"]["drawn"] == 0
