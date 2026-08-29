"""task 017（1/2）：竞技场骨架 + 深钵镇 stadium_grant。

规则出处：rules-manual §5（竞技场：每回合限 1 张、同名不可覆盖、旧场进原主人
弃牌区）；深钵镇 text_raw「双方玩家，每次在自己的回合有1次机会，可选择自己牌库中
的1张【基础】宝可梦（除「拥有规则的宝可梦」外），放于备战区。并重洗牌库。」。
"""

import pytest
from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.dsl import parse_card_doc
from battlefrontier.engine.actions import Action, IllegalActionError
from battlefrontier.engine.state import CardDef

STADIUM_DOC = parse_card_doc("""
card:
  name_group: 深钵镇
effects:
  - trigger: stadium_grant
    actions:
      - {action: search_deck, selector: own_deck, filters: [basic_pokemon_no_rule], choose: 1, destination: bench}
      - {action: shuffle_deck}
""")


def stadium(name: str = "深钵镇") -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer",
                   trainer_subtype="竞技场")


def stadium_engine(*, hand_extra=(), stadium_card=None, stadium_owner=None,
                   p0_over=None):
    """main 局面：可自带场上竞技场与 p0 覆盖。"""
    state = main_state(p0_extra_hand=hand_extra)
    if p0_over:
        p0 = state.players[0].model_copy(update=p0_over)
        state = state.model_copy(update={"players": (p0, state.players[1])})
    if stadium_card is not None:
        state = state.model_copy(update={"stadium": stadium_card,
                                         "stadium_owner": stadium_owner})
    e = engine_at(state)
    e.card_effects = {"深钵镇": STADIUM_DOC}
    return e


def play_stadium_actions(e, player=0):
    return [a for a in e.legal_actions(player) if a.kind == "play_stadium"]


def use_stadium_actions(e, player=0):
    return [a for a in e.legal_actions(player) if a.kind == "use_stadium"]


# ── play_stadium：打出规则 ───────────────────────────────────────────────

def test_play_stadium_enumerated_and_flow() -> None:
    e = stadium_engine(hand_extra=(inst(60, stadium()),))
    acts = play_stadium_actions(e)
    assert acts == [Action(kind="play_stadium", iid=60)]
    e.apply(0, acts[0])
    assert e.state.stadium is not None and e.state.stadium.card.name == "深钵镇"
    assert 60 not in [c.iid for c in e.state.players[0].hand]
    assert e.state.players[0].stadium_played_this_turn
    assert any(ev.kind == "play_stadium" for ev in e.events)


def test_play_stadium_once_per_turn() -> None:
    """每回合限 1 张竞技场；次回合重置。"""
    e = stadium_engine(hand_extra=(inst(60, stadium()), inst(61, stadium("别的镇"))))
    e.apply(0, Action(kind="play_stadium", iid=60))
    assert play_stadium_actions(e) == []
    e.apply(0, Action(kind="end_turn"))  # p1
    e.apply(1, Action(kind="end_turn"))  # 回 p0
    assert play_stadium_actions(e) == [Action(kind="play_stadium", iid=61)]


def test_play_stadium_same_name_banned() -> None:
    """与场上同名的竞技场不可打出（规则书·训练家卡）。"""
    e = stadium_engine(hand_extra=(inst(60, stadium()), inst(61, stadium("别的镇"))),
                       stadium_card=inst(80, stadium()))
    assert play_stadium_actions(e) == [Action(kind="play_stadium", iid=61)]


def test_play_stadium_replaces_old_to_owner_discard() -> None:
    """旧竞技场进其放置方（stadium_owner）的弃牌区（规则书·训练家卡）。"""
    e = stadium_engine(hand_extra=(inst(60, stadium()),),
                       stadium_card=inst(80, stadium("旧镇")), stadium_owner=1)
    e.apply(0, Action(kind="play_stadium", iid=60))
    assert e.state.stadium.card.name == "深钵镇"
    assert e.state.stadium_owner == 0
    assert 80 in [c.iid for c in e.state.players[1].discard]


# ── use_stadium：stadium_grant 每方每回合 1 次 ───────────────────────────

def test_use_stadium_flow() -> None:
    """深钵镇：检索基础（除规则盒）放备战区 + 洗牌；双方各 1 次/回合。"""
    e = stadium_engine(stadium_card=inst(80, stadium()))
    acts = use_stadium_actions(e)
    assert acts == [Action(kind="use_stadium")]
    e.apply(0, acts[0])
    # 检索池 = p0 牌库基础宝可梦（妙蛙种子 10 只）：选 1 放备战区
    picks = [a for a in e.legal_actions(0) if a.kind == "choose"]
    assert picks  # min 0 max 1
    e.apply(0, next(a for a in picks if len(a.choices) == 1))
    p0 = e.state.players[0]
    assert len(p0.bench) == 1 and p0.bench[0].current.card.name == "妙蛙种子"
    assert p0.stadium_used_this_turn
    assert use_stadium_actions(e) == []  # 本回合已用
    assert any(ev.kind == "use_stadium" for ev in e.events)
    # 对手回合也可用 1 次
    e.apply(0, Action(kind="end_turn"))
    assert use_stadium_actions(e, player=1) == [Action(kind="use_stadium")]


def test_use_stadium_bench_full_not_enumerated() -> None:
    """备战区满 → 无合法落点不枚举（无效果不可使用纪律）。"""
    full = tuple(in_play(70 + i, basic("小火龙")) for i in range(5))
    e = stadium_engine(stadium_card=inst(80, stadium()), p0_over={"bench": full})
    assert use_stadium_actions(e) == []


def test_use_stadium_illegal_without_stadium() -> None:
    e = stadium_engine()
    assert use_stadium_actions(e) == []
    with pytest.raises(IllegalActionError):
        e.apply(0, Action(kind="use_stadium"))
