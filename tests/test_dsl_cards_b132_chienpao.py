"""单卡 DSL 测试（task 132 批次 3/3）：古剑豹——从 cards/ 真实文件装载，stub 引擎驱动全链路。

古剑豹（CSV9C-053 等价类 3 印刷，H 标，基础，水，HP120，非 ex）：
- 特性 埋入雪中：trigger_on_event own_play_from_hand_to_bench + discard_stadium
  （摔角鹰人/大比鸟ex 先例：「可使用」放弃不建模，无竞技场 no-op）。
- 招式 冰柱环（【水】【水】【无】 120）：伤害 120 + 自身附着能量 1 个回手牌
  （move_energy destination=hand，task 132 新形态：scope=self + choose=1 必选；
  池空无事发生）。
"""

from pathlib import Path

from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import (
    AttackDef,
    CardDef,
    GameState,
    InPlayPokemon,
    PlayerState,
)

CARDS_DIR = Path(__file__).parent.parent / "cards"

CHIENPAO_DOC = load_card_doc(CARDS_DIR / "古剑豹.yml")


def chienpao() -> CardDef:
    return CardDef(
        card_id="stub-古剑豹", name="古剑豹", supertype="pokemon", hp=120, stage=0,
        energy_type="水", has_ability=True,
        attacks=(AttackDef(name="冰柱环", cost=("水", "水", "无"), damage=120),),
        retreat_cost=1,
    )


def stadium_card(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="竞技场")


def water_energy(iid: int) -> CardDef:
    return CardDef(card_id=f"stub-水{iid}", name="基本水能量", supertype="energy",
                   energy_type="水", is_basic_energy=True)


def bench_engine(*, stadium_owner: int | None) -> object:
    """main 阶段：p0 手牌含古剑豹（iid 60），场上可选有竞技场（iid 399）。"""
    state = main_state(p0_extra_hand=(inst(60, chienpao()),))
    e = engine_at(state)
    if stadium_owner is not None:
        e.state = e.state.model_copy(update={
            "stadium": inst(399, stadium_card("老竞技场")), "stadium_owner": stadium_owner})
    e.card_effects = {"古剑豹": CHIENPAO_DOC}
    return e


def attack_engine(p0_bench: tuple = ()) -> object:
    """main 阶段：p0 战斗场古剑豹（iid 1，附 水水无 3 能），p1 战斗场 hp200。"""
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": InPlayPokemon(
            stack=(inst(1, chienpao()),),
            attached_energy=(inst(9001, water_energy(1)), inst(9002, water_energy(2)),
                             inst(9003, water_energy(3))),
        ),
        "bench": p0_bench,
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, basic("厚皮兽", hp=200))})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"古剑豹": CHIENPAO_DOC}
    return e


def prim_results(e, action: str) -> list[dict]:
    return [ev.detail["result"] for ev in e.events
            if ev.kind == "effect_primitive" and ev.detail.get("action") == action
            and not ev.detail.get("result", {}).get("skipped")]


# ── 特性：埋入雪中（own_play_from_hand_to_bench + discard_stadium）─────────


def test_古剑豹_埋入雪中_放备战弃竞技场() -> None:
    """主阶段手牌放备战区：自动发动，场上竞技场入其持有者（p1）弃牌区，
    回主阶段；本体留在备战区（特性不弃置）。"""
    e = bench_engine(stadium_owner=1)
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "main" and e.state.current_player == 0
    assert e.state.stadium is None
    assert 399 in [c.iid for c in e.state.players[1].discard]
    assert prim_results(e, "discard_stadium")[0]["discarded"] == "老竞技场"
    assert e.state.players[0].bench[-1].current.card.name == "古剑豹"


def test_古剑豹_埋入雪中_无竞技场noop() -> None:
    """无竞技场：特性发动（trigger_on_event 事件落）但 no-op，回主阶段。"""
    e = bench_engine(stadium_owner=None)
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "main" and e.state.pending_choice is None
    assert any(ev.kind == "trigger_on_event" for ev in e.events)
    assert prim_results(e, "discard_stadium")[0]["discarded"] is None
    assert e.state.players[0].bench[-1].current.card.name == "古剑豹"


def test_古剑豹_埋入雪中_setup阶段放置不触发() -> None:
    """setup 布阵阶段的 place_bench 不是「自己的回合使出」，不触发特性。"""
    p0 = PlayerState(hand=(inst(60, chienpao()),))
    p1 = PlayerState(hand=(inst(61, basic("小火龙")),))
    state = GameState(players=(p0, p1), phase="setup_bench", current_player=0)
    e = engine_at(state)
    e.card_effects = {"古剑豹": CHIENPAO_DOC}
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.phase == "setup_bench" and e.state.pending_choice is None
    assert not [ev for ev in e.events if ev.kind == "trigger_on_event"]


# ── 招式：冰柱环（120 + 自身附着能量 1 个回手牌）────────────────────────────


def test_古剑豹_冰柱环_120伤害并能量回手() -> None:
    """冰柱环：对手战斗场 120 伤害；chooser 挂起选自身附着能量 1 个，
    所选能量进自己手牌，选完即结束回合。"""
    e = attack_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.phase == "choice"
    choices = sorted(a.choices for a in e.legal_actions(0) if a.kind == "choose")
    assert choices == [(9001,), (9002,), (9003,)]  # 自身 3 能任选 1
    e.apply(0, Action(kind="choose", choices=(9002,)))
    p0 = e.state.players[0]
    assert e.state.players[1].active.damage == 120
    assert 9002 in [c.iid for c in p0.hand]
    assert [c.iid for c in p0.active.attached_energy] == [9001, 9003]
    assert e.state.phase == "main" and e.state.current_player == 1


def test_古剑豹_冰柱环_chooser池只含自身能量() -> None:
    """scope=self：chooser 池只含攻击者自身附着能量，备战宝可梦附着能量不进池。"""
    bench_mon = in_play(70, basic("小拉达"), 1)  # 附着能量 iid 9000+70*10=9700
    e = attack_engine(p0_bench=(bench_mon,))
    e.apply(0, Action(kind="attack", attack_index=0))
    pc = e.state.pending_choice
    assert set(pc.pool_iids) == {9001, 9002, 9003}
    e.apply(0, Action(kind="choose", choices=(9001,)))
    assert [c.iid for c in e.state.players[0].bench[0].attached_energy] == [9700]
    assert 9001 in [c.iid for c in e.state.players[0].hand]
    assert e.state.phase == "main" and e.state.current_player == 1
