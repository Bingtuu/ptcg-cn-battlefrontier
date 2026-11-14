"""task 131：跑前 DSL 覆盖率门槛（run 子命令三态报告 + --strict-coverage）。

判定口径与 check-deck 同源（classify_dsl 共用）；真实 db 测试跟随
tests/test_deck_check.py 先例（本机 config 指向的 ptcg-cn.db）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from battlefrontier.dsl.loader import load_card_dir
from battlefrontier.engine.state import CardDef, Supertype
from battlefrontier.runner.coverage import (
    classify_dsl,
    format_coverage,
    run_coverages,
    side_coverage,
    strict_violations,
)

DB_PATH = Path(r"C:/Vibe Project/Pokearena/data/ptcg-cn.db")
GARDEVOIR_DECK = "mik_moe:644634"
HAS_DB = DB_PATH.exists()


def _lib(tmp_path, docs: dict[str, str]):
    for fname, text in docs.items():
        (tmp_path / fname).write_text(text, encoding="utf-8")
    return load_card_dir(tmp_path)


def _card(cid: str, name: str, *, basic_energy: bool = False,
          has_ability: bool = False, damage_modifier: str | None = None) -> CardDef:
    supertype = Supertype.ENERGY if basic_energy else Supertype.POKEMON
    attacks = ()
    if damage_modifier is not None:
        from battlefrontier.engine.state import AttackDef

        attacks = (AttackDef(name="招式", cost=(), damage=10,
                             damage_modifier=damage_modifier),)
    return CardDef(card_id=cid, name=name, supertype=supertype,
                   is_basic_energy=basic_energy, has_ability=has_ability,
                   attacks=attacks)


@pytest.fixture()
def lib(tmp_path):
    return _lib(tmp_path, {
        "甲.yml": "card:\n  name_group: 甲\n  card_ids: [A-1]\n",
    })


def test_classify_dsl_三态(lib):
    assert classify_dsl("A-1", "甲", lib) == "covered"      # card_id 精确挂载
    assert classify_dsl("A-2", "甲", lib) == "vanilla"      # 同名有文档、本印刷未覆盖
    assert classify_dsl("B-1", "乙", lib) == "no_doc"       # 同名也无文档


def test_side_coverage_三态归类与豁免拆分(lib):
    cards = ([_card("A-1", "甲")] * 2                       # covered
             + [_card("A-2", "甲")] * 1                     # vanilla（不触发 strict）
             + [_card("B-1", "乙", has_ability=True)] * 3   # no_doc（阻断）
             + [_card("D-1", "丙")] * 2                     # no_doc 纯白板（豁免）
             + [_card("E-1", "基础能量丙", basic_energy=True)] * 4)  # 豁免
    cov = side_coverage("卡组 a", cards, lib)
    assert cov.total == 12
    assert sum(e.count for e in cov.covered) == 2
    assert sum(e.count for e in cov.vanilla) == 1
    assert sum(e.count for e in cov.no_doc) == 3
    assert sum(e.count for e in cov.pure_vanilla) == 2
    assert sum(e.count for e in cov.basic_energy) == 4
    assert [e.name for e in cov.no_doc] == ["乙"]
    assert strict_violations([cov]) == ["卡组 a：3 张 乙（B-1）无 DSL 文档"]


def test_pure_vanilla_豁免边界(lib):
    # 纯白板判定仅限宝可梦：训练家无文档一律阻断（效果即文档本身）
    trainer = CardDef(card_id="T-1", name="道具丁", supertype=Supertype.TRAINER)
    # 招式带效果修饰（damage_modifier 非空）→ 语义无文档不可结算，阻断
    fx = _card("F-1", "戊", damage_modifier="coin_flip")
    cov = side_coverage("卡组 a", [trainer, fx], lib)
    assert {e.card_id for e in cov.no_doc} == {"T-1", "F-1"}
    assert cov.pure_vanilla == ()


def test_strict_violations_vanilla与豁免项不阻断(lib):
    cards = ([_card("A-2", "甲")] * 1
             + [_card("D-1", "丙")] * 2
             + [_card("E-1", "基础能量丙", basic_energy=True)] * 7)
    cov = side_coverage("卡组 b", cards, lib)
    assert strict_violations([cov]) == []


def test_format_coverage_含计数与卡名清单(lib):
    cards = ([_card("A-1", "甲")] * 2 + [_card("A-2", "甲")] * 1
             + [_card("B-1", "乙", has_ability=True)] * 3
             + [_card("D-1", "丙")] * 2
             + [_card("E-1", "基础能量丙", basic_energy=True)] * 4)
    text = format_coverage([side_coverage("卡组 a", cards, lib)])
    assert "卡组 a" in text and "12 张" in text
    assert "覆盖 2" in text and "vanilla 异文本 1" in text and "无文档 9" in text
    assert "基本能量豁免 4" in text and "纯白板豁免 2" in text and "阻断 3" in text
    assert "乙" in text and "B-1" in text and "无文档·阻断" in text


def test_run_coverages_单实验_ab两侧(tmp_path, monkeypatch):
    from battlefrontier.runner import experiment as exp_mod
    from battlefrontier.runner.experiment import (
        DeckSides,
        DeckSourceCfg,
        ExperimentDef,
        PreparedExperiment,
    )

    lib = _lib(tmp_path, {"甲.yml": "card:\n  name_group: 甲\n  card_ids: [A-1]\n"})
    decks_a = [_card("A-1", "甲")] * 60
    decks_b = [_card("B-1", "乙", has_ability=True)] * 60

    def fake_prepare_experiment(defn, db_path, cards_dir=exp_mod.DEFAULT_CARDS_DIR):
        return PreparedExperiment(
            deck_a=decks_a, deck_b=decks_b, card_effects=lib,
            deck_a_id="x", deck_b_id="y", data_version="d")

    monkeypatch.setattr(exp_mod, "prepare_experiment", fake_prepare_experiment)
    defn = ExperimentDef(name="t", games=1, seed_start=1,
                         decks=DeckSides(a=DeckSourceCfg(source="db", deck_id="x"),
                                         b=DeckSourceCfg(source="db", deck_id="y")))
    covers = run_coverages(defn, "unused-db", cards_dir=tmp_path)
    assert [c.label for c in covers] == ["卡组 a", "卡组 b"]
    assert covers[0].no_doc == () and covers[1].no_doc != ()


def test_run_coverages_matrix_按池去重(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from battlefrontier.runner.experiment import ExperimentDef, MatrixCfg

    _lib(tmp_path, {"甲.yml": "card:\n  name_group: 甲\n  card_ids: [A-1]\n"})
    entry = SimpleNamespace(archetype="甲组", deck_id="s:1")
    monkeypatch.setattr("battlefrontier.data.pool.load_target_pool",
                        lambda path: SimpleNamespace(decks=[entry]))
    monkeypatch.setattr(
        "battlefrontier.data.deck.load_deck",
        lambda db, deck_id: SimpleNamespace(cards=[_card("A-1", "甲")] * 60))
    defn = ExperimentDef(name="m", seed_start=1,
                         matrix=MatrixCfg(pool="pool.yml", games_per_pair=1))
    covers = run_coverages(defn, "unused-db", cards_dir=tmp_path)
    assert len(covers) == 1
    assert covers[0].label == "卡组 甲组（s:1）"
    assert covers[0].covered != ()


@pytest.mark.skipif(not HAS_DB, reason="本机无 ptcg-cn.db")
def test_cli_run_默认打印覆盖率报告(tmp_path, capsys):
    from battlefrontier.cli import main

    exp = tmp_path / "exp.yml"
    exp.write_text(f"""
name: cov-report
games: 1
seed_start: 700001
decks:
  a: {{source: db, deck_id: "{GARDEVOIR_DECK}"}}
  b: {{source: db, deck_id: "{GARDEVOIR_DECK}"}}
agents:
  a: {{type: heuristic}}
  b: {{type: random}}
""", encoding="utf-8")
    rc = main(["run", str(exp), "--results", str(tmp_path / "r.db"),
               "--db", str(DB_PATH), "--cards-dir", "cards"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DSL 覆盖率" in out and "卡组 a" in out and "卡组 b" in out


@pytest.mark.skipif(not HAS_DB, reason="本机无 ptcg-cn.db")
def test_cli_run_strict_全覆盖正常开跑(tmp_path, capsys):
    from battlefrontier.cli import main

    exp = tmp_path / "exp.yml"
    exp.write_text(f"""
name: cov-strict-pass
games: 1
seed_start: 700002
decks:
  a: {{source: db, deck_id: "{GARDEVOIR_DECK}"}}
  b: {{source: db, deck_id: "{GARDEVOIR_DECK}"}}
agents:
  a: {{type: heuristic}}
  b: {{type: random}}
""", encoding="utf-8")
    results = tmp_path / "r.db"
    rc = main(["run", str(exp), "--results", str(results),
               "--db", str(DB_PATH), "--cards-dir", "cards",
               "--strict-coverage"])
    out = capsys.readouterr().out
    assert rc == 0 and "通过" in out
    from battlefrontier.runner.results_db import ResultsDB

    db = ResultsDB(results)
    try:
        assert len(db.games(1)) == 1
    finally:
        db.close()


@pytest.mark.skipif(not HAS_DB, reason="本机无 ptcg-cn.db")
def test_cli_run_strict_无文档卡拒绝零局跑批(tmp_path, capsys):
    from battlefrontier.cli import main
    from battlefrontier.runner.results_db import ResultsDB

    empty_cards = tmp_path / "no-cards"
    empty_cards.mkdir()
    exp = tmp_path / "exp.yml"
    exp.write_text(f"""
name: cov-strict-reject
games: 2
seed_start: 700003
decks:
  a: {{source: db, deck_id: "{GARDEVOIR_DECK}"}}
  b: {{source: db, deck_id: "{GARDEVOIR_DECK}"}}
agents:
  a: {{type: heuristic}}
  b: {{type: random}}
""", encoding="utf-8")
    results = tmp_path / "r.db"
    rc = main(["run", str(exp), "--results", str(results),
               "--db", str(DB_PATH), "--cards-dir", str(empty_cards),
               "--strict-coverage"])
    out = capsys.readouterr().out
    assert rc != 0
    assert "拒绝" in out
    assert "卡组 a" in out and "沙奈朵" in out  # 指明卡组侧与卡名
    db = ResultsDB(results)
    try:
        assert db._conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0
    finally:
        db.close()


@pytest.mark.skipif(not HAS_DB, reason="本机无 ptcg-cn.db")
def test_v2池卡组_strict口径全覆盖():
    from battlefrontier.data.deck import load_deck
    from battlefrontier.data.pool import load_target_pool

    pool = load_target_pool("config/target-pool.v2.yml")
    lib = load_card_dir("cards")
    for entry in pool.decks:
        cov = side_coverage(entry.archetype,
                            load_deck(str(DB_PATH), entry.deck_id).cards, lib)
        assert cov.no_doc == (), (
            f"{entry.archetype} 存在无文档非豁免卡："
            f"{[(e.name, e.card_id) for e in cov.no_doc]}")
