"""task 022：choose 决策事件 + observe 锚点 + 决策聚合报告（PRD §5.4/§9）。"""

import pytest
from helpers import basic, engine_at, in_play, inst, main_state

from battlefrontier.cli import main as cli_main
from battlefrontier.dsl import load_card_dir, parse_card_doc
from battlefrontier.engine.actions import Action
from battlefrontier.engine.events import GameEvent
from battlefrontier.engine.state import AttackDef, CardDef
from battlefrontier.report.decisions import decision_report, format_decisions
from battlefrontier.runner.play import GameResult
from battlefrontier.runner.results_db import ResultsDB

ULTRA_BALL_DOC = parse_card_doc("""
card:
  name_group: 高级球
effects:
  - trigger: on_play
    cost:
      - {action: discard, selector: own_hand, choose: 2}
    actions:
      - {action: search_deck, selector: own_deck, filters: [pokemon], choose: 1, destination: hand}
      - {action: shuffle_deck}
""")

MEW_DOC = parse_card_doc("""
card:
  name_group: 梦幻ex
effects:
  - trigger: on_attack
    attack: 基因侵入
    actions:
      - {action: copy_attack, selector: opponent_active_attack, choose: 1}
""")

SNIPER_DOC = parse_card_doc("""
card:
  name_group: 狙手兽
effects:
  - trigger: on_attack
    attack: 狙击
    actions:
      - {action: damage, selector: opponent_pokemon_any, choose: 1, args: {amount: 100}}
""")


def item(name: str) -> CardDef:
    return CardDef(card_id=f"stub-{name}", name=name, supertype="trainer", trainer_subtype="物品")


def _ultra_engine():
    state = main_state(p0_extra_hand=(inst(60, item("高级球")),))
    e = engine_at(state)
    e.card_effects = {"高级球": ULTRA_BALL_DOC}
    return e


def _choose_events(e):
    return [ev for ev in e.events if ev.kind == "choose"]


# ── choose 决策事件 ──────────────────────────────────────

def test_choose_event_on_cost_and_search():
    e = _ultra_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    assert not _choose_events(e)  # 挂起尚未选择，无事件
    e.apply(0, Action(kind="choose", choices=(50, 51)))  # 成本弃牌
    cost_ev = _choose_events(e)
    assert len(cost_ev) == 1
    d = cost_ev[0].detail
    assert d["card"] == "高级球" and d["pool"] == "own_hand"
    assert d["chosen"] == [50, 51] and set(d["chosen_names"]) == {"小火龙", "基本能量"}
    assert "高级球" in d["effect_id"]
    e.apply(0, Action(kind="choose", choices=(100,)))  # 检索妙蛙种子
    search_ev = _choose_events(e)[1]
    assert search_ev.detail["pool"] == "own_deck"
    assert search_ev.detail["chosen_names"] == ["妙蛙种子"]


def test_choose_event_empty_choice_label():
    e = _ultra_engine()
    e.apply(0, Action(kind="play_trainer", iid=60))
    e.apply(0, Action(kind="choose", choices=(50, 51)))
    e.apply(0, Action(kind="choose", choices=()))  # 可以不找
    assert _choose_events(e)[1].detail["chosen_names"] == []


def _nested_engine():
    mew_card = CardDef(card_id="stub-梦幻ex", name="梦幻ex", supertype="pokemon",
                       hp=180, stage=0, rule_box="ex", energy_type="超",
                       attacks=(AttackDef(name="基因侵入", cost=("无",), damage=None),))
    sniper = CardDef(card_id="stub-狙手兽", name="狙手兽", supertype="pokemon",
                     hp=200, stage=0,
                     attacks=(AttackDef(name="狙击", cost=("无",), damage=None),))
    state = main_state(p0_active_energies=1)
    p0 = state.players[0].model_copy(update={"active": in_play(1, mew_card, 1)})
    p1 = state.players[1].model_copy(update={
        "active": in_play(2, sniper), "bench": (in_play(3, basic("备战靶")),)})
    e = engine_at(state.model_copy(update={"players": (p0, p1)}))
    e.card_effects = {"梦幻ex": MEW_DOC, "狙手兽": SNIPER_DOC}
    return e


def test_choose_events_in_nested_copy():
    e = _nested_engine()
    e.apply(0, Action(kind="attack", attack_index=0))
    e.apply(0, Action(kind="choose", choices=(0,)))  # 选招式（opponent_active_attack 池）
    e.apply(0, Action(kind="choose", choices=(2,)))  # 内层：选目标
    events = _choose_events(e)
    assert len(events) == 2
    assert events[0].detail["pool"] == "opponent_active_attack"
    assert events[0].detail["chosen_names"] == ["狙击"]  # 招式索引解析为招式名
    assert events[1].detail["pool"] == "opponent_pokemon_any"
    assert "copy>" in events[1].detail["effect_id"]


# ── 决策聚合 ─────────────────────────────────────────────

def _choose_ev(seq, card, chosen_names, effect_id=None, player=0, pool="own_deck"):
    return GameEvent(seq=seq, turn=1, phase="choice", player=player, kind="choose",
                     detail={"card": card, "pool": pool,
                             "effect_id": effect_id or f"{card}[10]:on_play",
                             "chosen": [], "chosen_names": chosen_names})


def _observe_ev(seq, effect_id, anchor):
    return GameEvent(seq=seq, turn=1, phase="main", player=0, kind="effect_observe",
                     detail={"effect_id": effect_id, "anchor": anchor})


@pytest.fixture()
def synth_db(tmp_path):
    """6 局：4 决定局（A胜 g1/g3，B胜 g2/g4）+ 1 平 + 1 失败。"""
    db = ResultsDB(tmp_path / "r.db")
    exp_id = db.start_experiment(name="agg", definition_yaml="x",
                                 code_version="v", data_version="d")
    games = [
        (100, 0, [_observe_ev(0, "高级球[10]:on_play", "key_search"),
                  _choose_ev(1, "高级球", ["沙奈朵ex"])]),                       # A 胜
        (101, 1, [_choose_ev(0, "高级球", ["奇鲁莉安"])]),                       # A 负
        (102, 0, [_choose_ev(0, "高级球", ["沙奈朵ex"]),
                  _choose_ev(1, "高级球", ["沙奈朵ex"])]),                       # A 胜（同选两次）
        (103, 1, [_choose_ev(0, "巢穴球", [])]),                                 # A 负（放弃）
        (104, None, [_choose_ev(0, "高级球", ["奇鲁莉安"])]),                    # 平局（不进分母）
    ]
    for seed, winner, events in games:
        db.record_game(exp_id, seed=seed, first_player=0,
                       result=GameResult(winner=winner, is_draw=winner is None,
                                         turns=10, phase="game_over", events=events),
                       deck_a_id="a", deck_b_id="b")
    db.record_error(exp_id, seed=105, deck_a_id="a", deck_b_id="b", error="x")
    db.finish_experiment(exp_id)
    yield db, exp_id
    db.close()


def test_decision_report_distribution(synth_db):
    db, exp_id = synth_db
    r = decision_report(db, exp_id)
    ultra = next(p for p in r.points if p.card == "高级球" and p.side == 0)
    by_label = {c.label: c for c in ultra.choices}
    garde = by_label["沙奈朵ex"]
    assert garde.occurrences == 3 and garde.games == 2  # 同局重复选择只计一局
    assert garde.wins == 2 and garde.winrate == 1.0
    kirlia = by_label["奇鲁莉安"]
    assert kirlia.occurrences == 2 and kirlia.games == 1  # 平局局不进
    assert kirlia.wins == 0 and kirlia.winrate == 0.0
    nest = next(p for p in r.points if p.card == "巢穴球")
    assert nest.choices[0].label == "（放弃）" and nest.choices[0].winrate == 0.0


def test_decision_report_anchor_join(synth_db):
    db, exp_id = synth_db
    r = decision_report(db, exp_id)
    ultra = next(p for p in r.points if p.card == "高级球" and p.side == 0)
    assert ultra.anchor == "key_search"
    nest = next(p for p in r.points if p.card == "巢穴球")
    assert nest.anchor is None


def test_format_decisions_renders(synth_db):
    db, exp_id = synth_db
    text = format_decisions(decision_report(db, exp_id))
    assert "高级球" in text and "沙奈朵ex" in text and "key_search" in text


# ── cards/ 锚点入库 ──────────────────────────────────────

@pytest.mark.parametrize("name", ["高级球", "巢穴球", "大地容器", "厉害钓竿",
                                  "夜间担架", "秘密箱", "派帕"])
def test_cards_observe_anchors(name):
    docs = load_card_dir("cards")
    assert any(e.observe for e in docs[name].effects), f"{name} 缺 observe 锚点"


# ── CLI ──────────────────────────────────────────────────

def test_cli_report_decisions(synth_db, capsys):
    db, exp_id = synth_db
    path = db._conn.execute("PRAGMA database_list").fetchone()[2]
    db.close()
    rc = cli_main(["report", str(exp_id), "--results", path, "--decisions"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "决策" in out and "高级球" in out
