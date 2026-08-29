"""task 006：DSL schema + YAML loader 验收测试（PRD §5.1/§5.2）。"""

from pathlib import Path

import pytest

from battlefrontier.dsl import (
    DslError,
    load_card_doc,
    load_vocabularies,
    parse_card_doc,
)

# PRD §5.2 示意例（「博士的研究」风格），YAML 化
PROFESSORS_RESEARCH = """
card:
  name_group: 博士的研究
  card_ids: [CSV1C-121]
effects:
  - trigger: on_play
    cost:
      - {action: discard, selector: own_hand, count: all}
    actions:
      - {action: draw, count: 7}
"""

# 奇树：双方手牌洗回牌库下方，各抽剩余奖赏卡数（计数表达式 + 多 action + observe）
IONO = """
card:
  name_group: 奇树
  card_ids: [CSV3C-123]
effects:
  - trigger: on_play
    actions:
      - {action: hand_to_deck_bottom, selector: own_hand, count: all, args: {both_players: true}}
      - {action: draw, count: own_remaining_prizes, args: {both_players: true}}
    observe: [hand_size_before]
"""


def test_parse_professors_research_example():
    doc = parse_card_doc(PROFESSORS_RESEARCH)
    assert doc.card.name_group == "博士的研究"
    assert doc.card.card_ids == ("CSV1C-121",)
    (effect,) = doc.effects
    assert effect.trigger == "on_play"
    (cost,) = effect.cost
    assert (cost.action, cost.selector, cost.count) == ("discard", "own_hand", "all")
    (action,) = effect.actions
    assert (action.action, action.count) == ("draw", 7)


def test_parse_complex_doc_with_counter_expr_and_observe():
    doc = parse_card_doc(IONO)
    (effect,) = doc.effects
    assert effect.actions[0].action == "hand_to_deck_bottom"
    assert effect.actions[0].args == {"both_players": True}
    assert effect.actions[1].count == "own_remaining_prizes"
    assert effect.observe == ("hand_size_before",)


def test_unknown_field_rejected_with_field_name():
    bad = PROFESSORS_RESEARCH.replace("trigger:", "triger:")
    with pytest.raises(DslError, match="triger"):
        parse_card_doc(bad)


def test_unknown_action_rejected_with_vocab_hint():
    bad = PROFESSORS_RESEARCH.replace("action: draw", "action: fly")
    with pytest.raises(DslError, match="fly"):
        parse_card_doc(bad)


def test_unknown_selector_rejected():
    bad = PROFESSORS_RESEARCH.replace("selector: own_hand", "selector: mars")
    with pytest.raises(DslError, match="mars"):
        parse_card_doc(bad)


def test_unknown_trigger_rejected():
    bad = PROFESSORS_RESEARCH.replace("trigger: on_play", "trigger: on_vibes")
    with pytest.raises(DslError, match="on_vibes"):
        parse_card_doc(bad)


def test_count_accepts_int_all_and_counter_expr():
    for count in ("7", "all", "own_remaining_prizes"):
        doc = parse_card_doc(PROFESSORS_RESEARCH.replace("count: 7", f"count: {count}"))
        assert doc.effects[0].actions[0].count in (7, "all", "own_remaining_prizes")


def test_count_rejects_negative_and_free_text():
    for count in ("-1", "seven"):
        with pytest.raises(DslError, match="count"):
            parse_card_doc(PROFESSORS_RESEARCH.replace("count: 7", f"count: {count}"))


def test_missing_name_group_rejected():
    bad = PROFESSORS_RESEARCH.replace("  name_group: 博士的研究\n", "")
    with pytest.raises(DslError, match="name_group"):
        parse_card_doc(bad)


def test_condition_and_limit_parse():
    text = """
card:
  name_group: 化危为吉测试
effects:
  - trigger: ability_manual
    condition: own_pokemon_knocked_out_last_opponent_turn
    limit: once_per_turn_shared
    actions:
      - {action: draw, count: 3}
"""
    doc = parse_card_doc(text)
    effect = doc.effects[0]
    assert effect.condition == "own_pokemon_knocked_out_last_opponent_turn"
    assert effect.limit == "once_per_turn_shared"


def test_yaml_syntax_error_has_source_context():
    with pytest.raises(DslError, match="bad.yml"):
        parse_card_doc("card: [unclosed", source="bad.yml")


def test_vocabularies_load_nonempty_unique():
    vocab = load_vocabularies()
    for section in ("actions", "selectors", "triggers", "counters"):
        words = getattr(vocab, section)
        assert len(words) > 0, section
        assert len(words) == len(set(words)), f"{section} 有重复条目"


def test_load_card_doc_from_file(tmp_path: Path):
    p = tmp_path / "professors_research.yml"
    p.write_text(PROFESSORS_RESEARCH, encoding="utf-8")
    doc = load_card_doc(p)
    assert doc.card.name_group == "博士的研究"


def test_error_reports_source_file(tmp_path: Path):
    p = tmp_path / "bad_card.yml"
    p.write_text(PROFESSORS_RESEARCH.replace("action: draw", "action: fly"), encoding="utf-8")
    with pytest.raises(DslError, match="bad_card.yml"):
        load_card_doc(p)
