"""task 119：bfsim check-deck 卡表预检（跑前体检，零跑批）。

真实 db 测试跟随 tests/test_deckload.py 先例（本机 config 指向的 ptcg-cn.db）。
"""

from __future__ import annotations

import pytest

from battlefrontier.runner.deck_check import (
    DeckCheckReport,
    check_decklist,
    format_deck_check,
)

DB_PATH = r"C:/Vibe Project/Pokearena/data/ptcg-cn.db"
GARDEVOIR_DECK = "mik_moe:644634"


@pytest.fixture(scope="module")
def gard_list(tmp_path_factory):
    """真实 db：从 Gardevoir 赛事卡组生成印刷级 decklist txt。"""
    from battlefrontier.data import load_deck

    loaded = load_deck(DB_PATH, GARDEVOIR_DECK)
    counts: dict[str, tuple[str, int]] = {}
    for c in loaded.cards:
        key = c.card_id
        name, n = counts.get(key, (c.name, 0))
        counts[key] = (name, n + 1)
    lines = [f"{n} {name} [{cid}]" for cid, (name, n) in counts.items()]
    p = tmp_path_factory.mktemp("deck") / "gard.txt"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_check_decklist_合法卡表_体检通过(gard_list):
    rep = check_decklist(DB_PATH, gard_list)
    assert isinstance(rep, DeckCheckReport)
    assert rep.total_cards == 60
    text = format_deck_check(rep)
    assert "60" in text and "宝可梦" in text and "DSL" in text


def test_check_decklist_张数不足_显式报错(tmp_path):
    p = tmp_path / "bad.txt"
    p.write_text("4 沙奈朵ex\n", encoding="utf-8")
    with pytest.raises(ValueError, match="60"):
        check_decklist(DB_PATH, p)


def test_check_decklist_卡名未命中_显式报错(tmp_path):
    p = tmp_path / "bad.txt"
    p.write_text("60 不存在的卡名xyz\n", encoding="utf-8")
    with pytest.raises(ValueError, match="未命中"):
        check_decklist(DB_PATH, p)


def test_check_decklist_格式错误_带行号(tmp_path):
    p = tmp_path / "bad.txt"
    p.write_text("4 沙奈朵ex\nx 博士的研究\n", encoding="utf-8")
    with pytest.raises(ValueError, match="第 2 行"):
        check_decklist(DB_PATH, p)


def test_format_deck_check_含构成与DSL状态(gard_list):
    rep = check_decklist(DB_PATH, gard_list)
    text = format_deck_check(rep)
    for entry in rep.entries:
        assert entry.name in text
    assert "覆盖" in text  # 池内卡组应全 DSL 覆盖（v2 池零缺口口径）


def test_cli_check_deck_退出码(gard_list, capsys):
    from battlefrontier.cli import main

    assert main(["check-deck", str(gard_list), "--db", DB_PATH]) == 0
    assert "卡表体检" in capsys.readouterr().out
    assert main(["check-deck", str(gard_list) + ".missing", "--db", DB_PATH]) == 1
