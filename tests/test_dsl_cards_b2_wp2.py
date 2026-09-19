"""单卡 DSL 测试（task 026 WP2）：从 cards/ 真实文件装载，stub 引擎驱动全链路。

本批卡（trigger_on_event 分发 + place_damage_counters + ko_self 随之解锁）：
- 彷徨夜灵（H 标 CSV8C-082 等价类）：咒怨炸弹——自我昏厥（ko_self）+ 对手 1 只放 5 个
  伤害指示物（place_damage_counters），once_per_turn；战斗位发动的换上走 promote_queue。
- 摔角鹰人（G 标 CSV1C-079 等价类）：飞身入场——trigger_on_event
  own_play_from_hand_to_bench，对手 2 只备战各放 1 个伤害指示物。
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef, GameState, PlayerState

CARDS_DIR = Path(__file__).parent.parent / "cards"

DUSCLOPS_DOC = load_card_doc(CARDS_DIR / "彷徨夜灵.yml")
HAWLUCHA_DOC = load_card_doc(CARDS_DIR / "摔角鹰人.yml")


def dusclops() -> CardDef:
    return CardDef(
        card_id="stub-彷徨夜灵", name="彷徨夜灵", supertype="pokemon",
        hp=90, stage=1, evolves_from="夜巡灵",
        attacks=(AttackDef(name="磷火", cost=("超", "超"), damage=50),),
        retreat_cost=2,
    )


def hawlucha() -> CardDef:
    return CardDef(
        card_id="stub-摔角鹰人", name="摔角鹰人", supertype="pokemon",
        hp=70, stage=0,
        attacks=(AttackDef(name="翅膀攻击", cost=("斗", "无", "无"), damage=70),),
        retreat_cost=1,
    )


# ── 彷徨夜灵（咒怨炸弹）────────────────────────────────────────────────────


def test_彷徨夜灵_备战位发动_自爆放5指示物() -> None:
    """备战位发动：整叠进弃牌区、对手立即拿 1 张奖赏（语序保真：先昏厥后放指示物），
    挂起选对手 1 只 +50 伤害，备战位昏厥无换上、回我方主阶段。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "bench": (in_play(70, dusclops()),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"彷徨夜灵": DUSCLOPS_DOC}
    abilities = [a for a in e.legal_actions(0) if a.kind == "use_ability"]
    assert [a.iid for a in abilities] == [70]
    e.apply(0, abilities[0])
    assert e.state.phase == "choice"
    assert e.state.players[0].bench == ()  # 已昏厥离场
    assert [c.card.name for c in e.state.players[0].discard] == ["彷徨夜灵"]
    assert len(e.state.players[1].hand) == 1  # 对手已拿 1 张奖赏
    ko = next(ev for ev in e.events if ev.kind == "knockout")
    assert ko.detail["name"] == "彷徨夜灵"
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert sorted(a.choices for a in choices) == [(2,)]  # 对手场上仅战斗场 1 只
    e.apply(0, choices[0])
    assert e.state.players[1].active.damage == 50  # 5 个指示物
    assert e.state.phase == "main" and e.state.current_player == 0  # 我方回合继续
    assert e.state.promote_queue == ()


def test_彷徨夜灵_战斗位发动_换上后回我方主阶段() -> None:
    """战斗位发动：自我昏厥入 promote_queue（效果内不翻阶段），指示物结算完成后
    换上，回我方主阶段（D-WP2-1；turn 不推进）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, dusclops()),
        "bench": (in_play(70, basic("小拉达")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"彷徨夜灵": DUSCLOPS_DOC}
    e.apply(0, Action(kind="use_ability", iid=1))
    assert e.state.phase == "choice"  # 效果继续：选指示物目标
    assert e.state.players[0].active is None
    assert e.state.promote_queue == (0,)
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.players[1].active.damage == 50
    assert e.state.phase == "promote" and e.state.current_player == 0
    assert e.state.resume_after_promotes == (0, "main")
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert e.state.turn == 2  # 未推进回合
    assert e.state.players[0].active.current.card.name == "小拉达"


def test_彷徨夜灵_指示物昏厥对手战斗场_双换上队列() -> None:
    """指示物昏厥对手战斗场（30+50≥70）：队列 (0, 1) 按入队序先后换上，
    全部完成后回我方主阶段；奖赏顺序 = 先对手拿（自爆）后我方拿（指示物）。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, dusclops()),
        "bench": (in_play(70, basic("小拉达")),),
    })
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, basic("小火龙")).model_copy(update={"damage": 30}),
        "bench": (in_play(80, basic("喵喵")),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"彷徨夜灵": DUSCLOPS_DOC}
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(2,)))
    assert e.state.promote_queue == (0, 1)
    assert e.state.phase == "promote" and e.state.current_player == 0
    prizes = [ev.player for ev in e.events if ev.kind == "take_prize"]
    assert prizes == [1, 0]  # 语序保真：先自爆（对手拿）后指示物（我方拿）
    e.apply(0, Action(kind="promote", bench_index=0))
    assert e.state.phase == "promote" and e.state.current_player == 1
    e.apply(1, Action(kind="promote", bench_index=0))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert [c.card.name for c in e.state.players[1].discard] == ["小火龙"]


# ── 摔角鹰人（飞身入场）────────────────────────────────────────────────────


def hawlucha_engine(p1_bench: tuple) -> object:
    """main 阶段、p0 手牌含摔角鹰人（iid 60）、对手备战区可调。"""
    state = main_state(p0_extra_hand=(inst(60, hawlucha()),), p1_bench=p1_bench)
    engine = engine_at(state)
    engine.card_effects = {"摔角鹰人": HAWLUCHA_DOC}
    return engine


def test_摔角鹰人_主阶段手牌放备战触发() -> None:
    """trigger_on_event：place_bench 事件后自动发动（放弃选项不建模，D-WP2-3），
    挂起选对手 2 只备战各 +10，完成后回主阶段；本体不弃置。"""
    e = hawlucha_engine((in_play(80, basic("小拉达")), in_play(81, basic("喵喵"))))
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "choice" and e.state.pending_choice is not None
    kinds = [ev.kind for ev in e.events]
    assert kinds.index("place_bench") < kinds.index("trigger_on_event")
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert [a.choices for a in choices] == [(80, 81)]  # 恰好 2 只，必选 2
    e.apply(0, choices[0])
    p1 = e.state.players[1]
    assert [m.damage for m in p1.bench] == [10, 10]  # 各 1 个指示物
    assert e.state.phase == "main" and e.state.current_player == 0
    assert p1.discard == ()
    # 摔角鹰人本体在备战区（特性不弃置）
    assert e.state.players[0].bench[-1].current.card.name == "摔角鹰人"


def test_摔角鹰人_对手备战1只_min收缩() -> None:
    """对手备战仅 1 只：min_choose 收缩至池大小（尽力而为），只能选那 1 只。"""
    e = hawlucha_engine((in_play(80, basic("小拉达")),))
    e.apply(0, Action(kind="place_bench", iid=60))
    choices = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert [a.choices for a in choices] == [(80,)]
    e.apply(0, choices[0])
    assert e.state.players[1].bench[0].damage == 10


def test_摔角鹰人_对手备战空_noop() -> None:
    """对手备战空：效果发动但无落点，no-op 不挂起（D-WP2-3），回主阶段。"""
    e = hawlucha_engine(())
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert any(ev.kind == "trigger_on_event" for ev in e.events)  # 发动过
    assert [m.current.card.name for m in e.state.players[0].bench] == ["摔角鹰人"]


def test_摔角鹰人_setup阶段放置不触发() -> None:
    """setup 布阵阶段的 place_bench 不是「自己的回合使出」，不触发特性。"""
    p0 = PlayerState(hand=(inst(60, hawlucha()),))
    p1 = PlayerState(hand=(inst(61, basic("小火龙")),))
    state = GameState(players=(p0, p1), phase="setup_bench", current_player=0)
    e = engine_at(state)
    e.card_effects = {"摔角鹰人": HAWLUCHA_DOC}
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "setup_bench" and e.state.pending_choice is None
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]
