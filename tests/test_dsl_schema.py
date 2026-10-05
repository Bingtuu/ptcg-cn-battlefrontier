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
# task 038 F2（D-038-2）：args 键名白名单上线后，原示例里静默无效的 both_players
# 键已删除（hand_to_deck_bottom/draw 均不接受该键；真实 cards/奇树.yml 本就无 args）
IONO = """
card:
  name_group: 奇树
  card_ids: [CSV3C-123]
effects:
  - trigger: on_play
    actions:
      - {action: hand_to_deck_bottom, selector: own_hand, count: all}
      - {action: draw, count: own_remaining_prizes}
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


# ── task 026 WP2：trigger_on_event 的 event 字段（events 词表段）────────────

TRIGGER_ON_EVENT = """
card:
  name_group: 摔角鹰人
effects:
  - trigger: trigger_on_event
    event: own_play_from_hand_to_bench
    actions:
      - {action: place_damage_counters, selector: opponent_bench, choose: 2, args: {counters: 1}}
"""


def test_trigger_on_event_event_field_parses():
    """event 字段仅 trigger_on_event 使用，值查 events 词表段。"""
    doc = parse_card_doc(TRIGGER_ON_EVENT)
    effect = doc.effects[0]
    assert effect.trigger == "trigger_on_event"
    assert effect.event == "own_play_from_hand_to_bench"


def test_trigger_on_event_missing_event_rejected():
    bad = TRIGGER_ON_EVENT.replace("    event: own_play_from_hand_to_bench\n", "")
    with pytest.raises(DslError, match="event"):
        parse_card_doc(bad)


def test_event_on_other_trigger_rejected():
    bad = TRIGGER_ON_EVENT.replace("trigger: trigger_on_event", "trigger: on_play")
    with pytest.raises(DslError, match="event"):
        parse_card_doc(bad)


def test_unknown_event_word_rejected():
    bad = TRIGGER_ON_EVENT.replace("own_play_from_hand_to_bench", "on_vibes")
    with pytest.raises(DslError, match="on_vibes"):
        parse_card_doc(bad)


def test_own_evolve_from_hand_event_word_parses():
    """task 026 WP3：events 词表新词 own_evolve_from_hand（猫头夜鹰 寻找宝石）。"""
    doc = parse_card_doc(
        TRIGGER_ON_EVENT.replace("own_play_from_hand_to_bench", "own_evolve_from_hand")
    )
    assert doc.effects[0].event == "own_evolve_from_hand"


# ── task 038 F2（D-038-2）：args 键名白名单 ────────────────

ARGS_TYPO = """
card:
  name_group: 测试回收
effects:
  - trigger: on_play
    actions:
      - {action: recover_from_discard, selector: own_discard, choose: 1, destination: hand, args: {upto: true}}
"""


def test_unknown_args_key_rejected():
    """拼错键（upto 应为 up_to）装载即 DslError——不再静默取默认值。"""
    with pytest.raises(DslError, match="upto"):
        parse_card_doc(ARGS_TYPO)


def test_unknown_args_key_lists_primitive_and_known_keys():
    """报错含原语名与白名单（对齐「未知词不猜」提示风格）。"""
    with pytest.raises(DslError, match="recover_from_discard") as exc_info:
        parse_card_doc(ARGS_TYPO)
    assert "up_to" in str(exc_info.value)


def test_whitelisted_args_keys_parse():
    """白名单内键正常装载（recover_from_discard 双键 + search_deck 检视键组）。"""
    doc = parse_card_doc(ARGS_TYPO.replace("upto: true", "up_to: true"))
    assert doc.effects[0].actions[0].args == {"up_to": True}
    doc2 = parse_card_doc("""
card:
  name_group: 测试检索
effects:
  - trigger: on_play
    actions:
      - {action: search_deck, selector: own_deck, choose: 1, destination: hand, args: {top_n: 7, rest: deck_bottom}}
""")
    assert doc2.effects[0].actions[0].args == {"top_n": 7, "rest": "deck_bottom"}


def test_args_on_no_args_primitive_rejected():
    """无 args 原语（shuffle_deck）带任何键 → DslError。"""
    with pytest.raises(DslError, match="shuffle_deck"):
        parse_card_doc("""
card:
  name_group: 测试洗牌
effects:
  - trigger: on_play
    actions:
      - {action: shuffle_deck, args: {force: true}}
""")


# ── task 038 F3（D-038-3）：Effect.attack 装载校验 ─────────

ATTACK_ON_WRONG_TRIGGER = """
card:
  name_group: 测试绑定
effects:
  - trigger: on_play
    attack: 打击
    actions:
      - {action: draw, count: 1}
"""


def test_attack_field_on_non_on_attack_rejected():
    """attack 仅 on_attack 使用（schema docstring 承诺落为装载校验）。"""
    with pytest.raises(DslError, match="attack"):
        parse_card_doc(ATTACK_ON_WRONG_TRIGGER)


def test_attack_field_on_on_attack_parses():
    doc = parse_card_doc(
        ATTACK_ON_WRONG_TRIGGER.replace("trigger: on_play", "trigger: on_attack")
    )
    assert doc.effects[0].attack == "打击"
