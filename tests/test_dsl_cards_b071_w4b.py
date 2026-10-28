"""task 071 批 4b：驱劲能量 / 能量涡轮 / 可达鸭 / 咕咕 / N的达摩狒狒。"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
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


def tool(name: str) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="trainer",
        trainer_subtype="宝可梦道具",
    )


def test_驱劲能量_未来_撤退归零且伤害加二十() -> None:
    doc = load("驱劲能量 未来")
    holder = poke("未来兽", labels=("未来",), retreat_cost=2)
    plain = poke("普通兽", retreat_cost=2)
    capsule = tool("驱劲能量 未来")
    future = in_play(1, holder, energies=1).model_copy(update={
        "attached_tool": inst(90, capsule),
    })
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": future})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"驱劲能量 未来": doc}
    assert e._effective_retreat_cost(e.state.players[0].active, 0) == 0
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 40

    bare = in_play(1, plain, energies=1).model_copy(update={
        "attached_tool": inst(90, capsule),
    })
    p0 = state.players[0].model_copy(update={"active": bare})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"驱劲能量 未来": doc}
    assert e._effective_retreat_cost(e.state.players[0].active, 0) == 2
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 20


def test_招式学习器_能量涡轮_合成招式附到备战() -> None:
    doc = load("招式学习器 能量涡轮")
    learner = tool("招式学习器 能量涡轮")
    holder = in_play(1, poke("持"), energies=1).model_copy(update={
        "attached_tool": inst(90, learner),
    })
    state = main_state()
    deck = (inst(91, energy("雷", "雷")), inst(92, energy("草", "草"))) + state.players[0].deck
    p0 = state.players[0].model_copy(update={
        "active": holder,
        "bench": (in_play(70, basic("备")),),
        "deck": deck,
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"招式学习器 能量涡轮": doc}
    assert 1 in [a.attack_index for a in e.legal_actions(0) if a.kind == "attack"]
    e.apply(0, Action(kind="attack", attack_index=1))
    e.apply(0, Action(kind="choose", choices=(91, 92)))
    assert e.state.pending_choice.pool == "own_bench"
    e.apply(0, Action(kind="choose", choices=(70,)))
    e.apply(0, Action(kind="choose", choices=(70,)))
    assert {c.iid for c in e.state.players[0].bench[0].attached_energy} == {91, 92}


def test_可达鸭_湿气消除自昏厥特性() -> None:
    doc = load("可达鸭")
    bomb = parse_card_doc("""
card:
  name_group: 自爆兽
effects:
  - trigger: ability_manual
    limit: once_per_turn
    actions:
      - {action: ko_self}
""")
    duck = poke("可达鸭", has_ability=True)
    bomber = poke("自爆兽", energy_type="火", has_ability=True)
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, bomber),
        "bench": (in_play(70, duck),),
    })
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"可达鸭": doc, "自爆兽": bomb}
    assert not any(a.kind == "use_ability" for a in e.legal_actions(0))


def test_咕咕_寂静之翼查看对手手牌() -> None:
    doc = load("咕咕")
    bird = poke("咕咕", attacks=(AttackDef(name="寂静之翼", cost=("无",), damage=None),))
    state = main_state()
    p0 = state.players[0].model_copy(update={"active": in_play(1, bird, energies=1)})
    p1 = state.players[1].model_copy(update={"hand": (inst(77, basic("秘密")),)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"咕咕": doc}
    e.apply(0, Action(kind="attack", attack_index=0))
    revealed = [ev for ev in e.events if ev.kind == "reveal"]
    assert revealed[-1].detail["names"] == ["秘密"]
    assert e.state.players[1].active.damage == 20
    assert "秘密" not in str(e.state.visible_state(0).opponent)


def test_N的达摩狒狒_复燃与焚身加农炮() -> None:
    doc = load("N的达摩狒狒")
    dar = poke(
        "N的达摩狒狒", stage=1, owner="N",
        attacks=(
            AttackDef(name="复燃", cost=("无",), damage=None),
            AttackDef(name="焚身加农炮", cost=("无",), damage=None),
        ),
    )
    state = main_state()
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, poke("墙", hp=400)),
        "discard": (inst(10, energy()), inst(11, energy())),
        "bench": (in_play(80, poke("备", hp=400)),),
    })
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, dar, energies=2),
    })
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"N的达摩狒狒": doc}
    e.apply(0, Action(kind="attack", attack_index=0))
    assert e.state.players[1].active.damage == 60

    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"N的达摩狒狒": doc}
    e.apply(0, Action(kind="attack", attack_index=1))
    assert e.state.players[0].active.attached_energy == ()
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.players[1].bench[0].damage == 90
    assert e.state.players[1].active.damage == 90
