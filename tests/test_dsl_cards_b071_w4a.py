"""task 071 批 4a：训练家 7 张，从 cards/ 真实文件装载。"""

from pathlib import Path

from helpers import basic, energy, engine_at, in_play, inst, main_state

from battlefrontier.dsl.loader import load_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import AttackDef, CardDef

CARDS = Path(__file__).parent.parent / "cards"


def load(name: str):
    return load_card_doc(CARDS / f"{name}.yml")


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="物品")


def supporter(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="支援者")


def stadium(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="竞技场")


def poke(name: str, **kw) -> CardDef:
    return CardDef(
        card_id=f"stub-{name}", name=name, supertype="pokemon",
        hp=kw.pop("hp", 120), stage=kw.pop("stage", 0),
        attacks=(AttackDef(name="打击", cost=("无",), damage=10),),
        **kw,
    )


def engine(doc, hand_card: CardDef, **p0):
    state = main_state(p0_extra_hand=(inst(60, hand_card),))
    base = state.players[0]
    if p0:
        base = base.model_copy(update=p0)
    e = engine_at(state.model_copy(update={"players": (base, state.players[1])}))
    e.card_effects = {hand_card.name: doc}
    return e


def test_宝可平板_检索无规则宝可梦() -> None:
    doc = load("宝可平板")
    plain = poke("普通", stage=1)
    ex = poke("规则ex", rule_box="ex")
    deck = (inst(90, plain), inst(91, ex)) + tuple(
        inst(100 + i, energy()) for i in range(8)
    )
    e = engine(doc, item("宝可平板"), deck=deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.pending_choice.pool_iids == (90,)
    e.apply(0, Action(kind="choose", choices=(90,)))
    assert any(c.iid == 90 for c in e.state.players[0].hand)
    assert any(ev.kind == "reveal" and "普通" in ev.detail["names"] for ev in e.events)


def test_莉莉艾的决心_奖赏六张改抽八张() -> None:
    doc = load("莉莉艾的决心")
    e = engine(doc, supporter("莉莉艾的决心"))
    before = len(e.state.players[0].deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    # 手牌 2 张回库 + 抽 8；支援者本身已离手
    assert len(e.state.players[0].deck) == before + 2 - 8

    state = main_state(p0_extra_hand=(inst(60, supporter("莉莉艾的决心")),))
    p0 = state.players[0].model_copy(update={"prizes": state.players[0].prizes[:5]})
    e = engine_at(state.model_copy(update={"players": (p0, state.players[1])}))
    e.card_effects = {"莉莉艾的决心": doc}
    before = len(e.state.players[0].deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert len(e.state.players[0].deck) == before + 2 - 6


def test_席蓝_检索ex() -> None:
    doc = load("席蓝")
    ex = poke("席ex", rule_box="ex")
    plain = poke("普通")
    deck = (inst(90, ex), inst(91, plain), inst(92, ex))
    e = engine(doc, supporter("席蓝"), deck=deck)
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert set(e.state.pending_choice.pool_iids) == {90, 92}


def test_玻璃喇叭_太晶门槛与无色备战() -> None:
    doc = load("玻璃喇叭")
    tera = poke("太晶无", is_tera=True, energy_type="无")
    colored = poke("草备", energy_type="草")
    disc = (inst(80, energy("草", "草")), inst(81, energy("火", "火")))
    e = engine(
        doc, item("玻璃喇叭"),
        active=in_play(1, tera),
        bench=(in_play(70, tera), in_play(71, colored)),
        discard=disc,
    )
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(80,)))
    assert e.state.pending_choice.pool_iids == (70,)

    no_tera = engine(
        doc, item("玻璃喇叭"),
        bench=(in_play(70, poke("无", energy_type="无")),),
        discard=disc,
    )
    assert not any(a.kind == "play_trainer" for a in no_tera.legal_actions(0))


def test_太晶珠_检索太晶() -> None:
    doc = load("太晶珠")
    tera = poke("珠", is_tera=True)
    plain = poke("普通")
    e = engine(doc, item("太晶珠"), deck=(inst(90, plain), inst(91, tera)))
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert e.state.pending_choice.pool_iids == (91,)


def test_粉碎之锤_正面弃对手能量() -> None:
    doc = load("粉碎之锤")
    heads = next(s for s in range(30) if RandomSource(s).flip_coin())
    state = main_state(
        p0_extra_hand=(inst(60, item("粉碎之锤")),),
        p1_active_energies=1,
    )
    e = engine_at(state)
    e.card_effects = {"粉碎之锤": doc}
    e.rng = RandomSource(heads)
    e.apply(0, Action(kind="play_trainer", iid=60))
    iid = e.state.pending_choice.pool_iids[0]
    e.apply(0, Action(kind="choose", choices=(iid,)))
    assert any(c.iid == iid for c in e.state.players[1].discard)


def test_N的城堡_N的宝可梦撤退归零() -> None:
    doc = load("N的城堡")
    nmon = poke("N兽", owner="N", retreat_cost=3)
    other = poke("路人", owner="玛俐", retreat_cost=3)
    state = main_state()
    p0 = state.players[0].model_copy(update={
        "active": in_play(1, nmon),
        "bench": (in_play(70, basic("换")),),
    })
    p1 = state.players[1].model_copy(update={"active": in_play(2, other)})
    e = engine_at(state.model_copy(update={
        "players": (p0, p1),
        "stadium": inst(8, stadium("N的城堡")),
    }))
    e.card_effects = {"N的城堡": doc}
    assert e._effective_retreat_cost(e.state.players[0].active, 0) == 0
    assert e._effective_retreat_cost(e.state.players[1].active, 1) == 3
    assert any(a.kind == "retreat" for a in e.legal_actions(0))
