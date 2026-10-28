"""task 071 批 4c：宝可梦 7 张，从 cards/ 真实文件装载。"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import AttackDef, CardDef

CARDS = Path(__file__).parent.parent / "cards"


def load(name: str):
    return load_card_doc(CARDS / f"{name}.yml")


def poke(name: str, **kw) -> CardDef:
    attacks = kw.pop("attacks", (AttackDef(name="打击", cost=("无",), damage=20),))
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=kw.pop("hp", 200), stage=kw.pop("stage", 0), attacks=attacks, **kw,
    )


def test_N的索罗亚克ex_交易弃一抽二() -> None:
    doc = load("N的索罗亚克ex")
    fox = poke(
        "N的索罗亚克ex", stage=1, rule_box="ex", has_ability=True,
        attacks=(AttackDef(name="暗夜王牌", cost=("无",), damage=None),),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, fox)})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"N的索罗亚克ex": doc}
    deck_before = len(e.state.players[0].deck)
    e.apply(0, Action(kind="use_ability", iid=1))
    e.apply(0, Action(kind="choose", choices=(50,)))
    assert len(e.state.players[0].discard) == 1
    assert len(e.state.players[0].deck) == deck_before - 2


def test_N的索罗亚克ex_暗夜王牌复制备战N的招式() -> None:
    doc = load("N的索罗亚克ex")
    fox = poke(
        "N的索罗亚克ex", stage=1, rule_box="ex",
        attacks=(AttackDef(name="暗夜王牌", cost=("无",), damage=None),),
    )
    donor = poke("N莱", owner="N", attacks=(
        AttackDef(name="火焰", cost=("火",), damage=40),))
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, fox, energies=1),
        "bench": (in_play(70, donor),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"N的索罗亚克ex": doc}
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(70,)))
    e.apply(0, Action(kind="choose", choices=(0,)))
    assert e.state.players[1].active.damage == 40


def test_伊布_突进进化刚出场也能进化() -> None:
    doc = load("伊布")
    eevee = poke("伊布", has_ability=True)
    flare = poke("火伊布", stage=1, evolves_from="伊布")
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, eevee),
        "hand": (inst(60, flare),),
        "entered_play_this_turn": frozenset({1}),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"伊布": doc}
    assert any(a.kind == "evolve" and a.iid == 60 for a in e.legal_actions(0))


def test_伊布_突击自伤() -> None:
    doc = load("伊布")
    eevee = poke("伊布", attacks=(AttackDef(name="突击", cost=("无",), damage=None),))
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, eevee, energies=1)})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"伊布": doc}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 30
    assert e.state.players[0].active.damage == 10


def test_厄诡椪_水井面具ex_激流水泵选了才打备战() -> None:
    doc = load("厄诡椪 水井面具ex")
    og = poke(
        "厄诡椪 水井面具ex", rule_box="ex",
        attacks=(AttackDef(name="激流水泵", cost=("无",), damage=None),),
    )
    energies = tuple(inst(20 + i, energy()) for i in range(3))
    active = in_play(1, og).model_copy(update={"attached_energy": energies})
    state = main_state(p1_bench=(in_play(80, poke("敌备", hp=400)),))
    tough = in_play(2, poke("墙", hp=400))
    p0 = state.players[0].model_copy(update={"active": active})
    p1 = state.players[1].model_copy(update={"active": tough})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"厄诡椪 水井面具ex": doc}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 100
    e.apply(0, Action(kind="choose", choices=()))
    assert e.state.players[1].bench[0].damage == 0
    assert len(e.state.players[0].active.attached_energy) == 3

    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"厄诡椪 水井面具ex": doc}
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(20,)))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 120


def test_火伊布ex_红玉髓锁全部招式() -> None:
    doc = load("火伊布ex")
    flare = poke(
        "火伊布ex", stage=1, rule_box="ex", evolves_from="伊布",
        attacks=(
            AttackDef(name="燃烧充能", cost=("无",), damage=None),
            AttackDef(name="红玉髓", cost=("无",), damage=None),
        ),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, flare, energies=1)})
    p1 = state.players[1].model_copy(update={"active": in_play(2, poke("墙", hp=400))})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"火伊布ex": doc}
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[0].active.attack_lock_all
    assert e.state.players[1].active.damage == 280


def test_火伊布ex_燃烧充能两张附同一只() -> None:
    doc = load("火伊布ex")
    flare = poke(
        "火伊布ex", stage=1, rule_box="ex",
        attacks=(AttackDef(name="燃烧充能", cost=("无",), damage=None),),
    )
    state = main_state()
    deck = (inst(91, energy()), inst(92, energy())) + state.players[0].deck
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, flare, energies=1),
        "bench": (in_play(70, basic("备")),),
        "deck": deck,
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, poke("墙", hp=400))})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"火伊布ex": doc}
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(91, 92)))
    assert e.state.pending_choice.max_choose == 1
    e.apply(0, Action(kind="choose", choices=(70,)))
    assert {c.iid for c in e.state.players[0].bench[0].attached_energy} == {91, 92}
    assert e.state.phase != "choice"


def test_铁臂膀ex_多谢款待多拿一张奖赏() -> None:
    doc = load("铁臂膀ex")
    iron = poke(
        "铁臂膀ex", rule_box="ex", labels=("未来",),
        attacks=(AttackDef(name="多谢款待", cost=("无",), damage=None),),
    )
    foe = poke("靶", hp=50)
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, iron, energies=1)})
    p1 = state.players[1].model_copy(update={"active": in_play(2, foe)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"铁臂膀ex": doc}
    before = len(e.state.players[0].prizes)
    e.apply(0, Action(kind="attack", attack_index=0))
    assert len(e.state.players[0].prizes) == before - 2


def test_铁斑叶ex_快速游标换位后转附能量() -> None:
    doc = load("铁斑叶ex")
    leaves = poke(
        "铁斑叶ex", rule_box="ex", labels=("未来",),
        attacks=(AttackDef(name="棱镜利刃", cost=("无",), damage=30),),
    )
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "hand": state.players[0].hand + (inst(60, leaves),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"铁斑叶ex": doc}
    e.apply(0, Action(kind="place_bench", iid=60))
    assert e.state.players[0].active.current.card.name == "铁斑叶ex"
    assert e.state.phase == "choice"
    picked = e.state.pending_choice.pool_iids[0]
    e.apply(0, Action(kind="choose", choices=(picked,)))
    assert any(c.iid == picked for c in e.state.players[0].active.attached_energy)


def test_电蜘蛛_复眼与麻麻网只叠加一次() -> None:
    doc = load("电蜘蛛")
    spider = poke(
        "电蜘蛛", stage=1, energy_type="草", has_ability=True,
        attacks=(AttackDef(name="麻麻网", cost=("无",), damage=None),),
    )
    able = poke("有特", has_ability=True, hp=400)
    plain = poke("无特", has_ability=False, hp=400)
    state = main_state()

    def strike(defender: CardDef, lightning: bool) -> int:
        attached = (inst(9, energy("雷", "雷")),) if lightning else (inst(9, energy()),)
        active = in_play(1, spider).model_copy(update={"attached_energy": attached})
        p0 = state.players[0].model_copy(update={"active": active})
        p1 = state.players[1].model_copy(update={"active": in_play(2, defender)})
        e = engine_at(state.model_copy(update={"players": (p0, p1)}))
        e.card_effects = {"电蜘蛛": doc}
        e.apply(0, Action(kind="attack", attack_index=0))
        return e.state.players[1].active.damage

    assert strike(able, False) == 100   # 50 + 复眼 50
    assert strike(able, True) == 180    # 50+80 + 复眼 50
    assert strike(plain, True) == 130   # 无复眼
