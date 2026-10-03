"""task 030 WP1：M6 校准基线 matrix 跑批骨架。

池映射（en_archetype）+ matrix 实验定义双模式 + runner 展开 + 结果库分组访问器
+ CLI run matrix 分支；偏差表报告归 WP3。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from battlefrontier.data.pool import PoolEntry, TargetPool, load_target_pool
from battlefrontier.runner.experiment import (
    DeckSides,
    DeckSourceCfg,
    ExperimentDef,
    MatrixCfg,
    expand_matrix,
)
from battlefrontier.runner.results_db import ResultsDB

DB_PATH = Path(r"C:/Vibe Project/Pokearena/data/ptcg-cn.db")
needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="本机无 ptcg-cn.db")

QUERY = {k: "x" for k in ("window", "division", "basis", "min_n", "n_tournaments",
                          "snapshot", "name_group_rules_hash")}

DECKS = DeckSides(a=DeckSourceCfg(source="db", deck_id="mik_moe:1"),
                  b=DeckSourceCfg(source="db", deck_id="mik_moe:2"))


def _entry(archetype: str, wur: float, deck_id: str, en: str = "EN") -> PoolEntry:
    return PoolEntry(archetype=archetype, en_archetype=en, wur=wur, n=10,
                     deck_id=deck_id)


def _pool3() -> TargetPool:
    return TargetPool(version=1, locked_at="t", query=dict(QUERY), decks=[
        _entry("沙奈朵", 0.3, "mik_moe:644634", en="Gardevoir"),
        _entry("喷火龙 大比鸟", 0.2, "mik_moe:650353", en="Charizard Pidgeot"),
        _entry("猛雷鼓 厄诡椪", 0.1, "mik_moe:652967", en="Raging Bolt Ogerpon"),
    ])


def _matrix_def(**kw) -> ExperimentDef:
    return ExperimentDef(name="m6", seed_start=100,
                         matrix=MatrixCfg(pool="p.yml", games_per_pair=2), **kw)


# ── expand_matrix：配对数 / 顺序 / 名称 / 种子区间 ──────────

def test_expand_matrix_配对顺序与种子区间():
    subs = expand_matrix(_matrix_def(), _pool3())
    assert len(subs) == 3
    assert [s.name for s in subs] == [
        "m6::沙奈朵×喷火龙 大比鸟",
        "m6::沙奈朵×猛雷鼓 厄诡椪",
        "m6::喷火龙 大比鸟×猛雷鼓 厄诡椪",
    ]
    assert [(s.decks.a.deck_id, s.decks.b.deck_id) for s in subs] == [
        ("mik_moe:644634", "mik_moe:650353"),
        ("mik_moe:644634", "mik_moe:652967"),
        ("mik_moe:650353", "mik_moe:652967"),
    ]
    # games_per_pair=2、seed_start=100：[100,102)/[102,104)/[104,106) 连续不重叠
    assert [(s.seed_start, s.games) for s in subs] == [(100, 2), (102, 2), (104, 2)]


def test_expand_matrix_确定性_两次展开逐字段相等():
    assert expand_matrix(_matrix_def(), _pool3()) == expand_matrix(_matrix_def(), _pool3())


def test_expand_matrix_非matrix模式报错():
    defn = ExperimentDef(name="x", games=1, decks=DECKS)
    with pytest.raises(ValueError, match="matrix"):
        expand_matrix(defn, _pool3())


# ── ExperimentDef 双模式互斥校验 ──────────────────────────

def test_matrix_与_decks_并存报错():
    with pytest.raises(ValidationError, match="互斥"):
        ExperimentDef(name="x", games=1, decks=DECKS,
                      matrix=MatrixCfg(pool="p.yml", games_per_pair=1))


def test_matrix_与_variants_并存报错():
    variants = [{"name": "v1",
                 "swaps": [{"out": "a", "out_count": 1, "in": "b", "in_count": 1}]}]
    with pytest.raises(ValidationError, match="互斥"):
        ExperimentDef.model_validate(
            {"name": "x", "matrix": {"pool": "p.yml", "games_per_pair": 1},
             "variants": variants})


def test_单实验缺_decks_报错():
    with pytest.raises(ValidationError, match="decks"):
        ExperimentDef(name="x", games=1)


def test_单实验缺_games_报错():
    with pytest.raises(ValidationError, match="games"):
        ExperimentDef(name="x", decks=DECKS)


def test_单实验模式照常可用():
    defn = ExperimentDef(name="x", games=2, decks=DECKS)
    assert defn.matrix is None and defn.games == 2


# ── 池映射：en_archetype 必填 / 去重 / matchup_pairs ──────

def test_pool_entry_en_archetype_必填():
    with pytest.raises(ValidationError):
        PoolEntry(archetype="A", wur=0.1, n=1, deck_id="mik_moe:1")


def test_target_pool_en_archetype_重复报错():
    with pytest.raises(ValidationError, match="en_archetype"):
        TargetPool(version=1, locked_at="t", query=dict(QUERY), decks=[
            _entry("A", 0.2, "mik_moe:1", en="X"),
            _entry("B", 0.1, "mik_moe:2", en="X"),
        ])


def test_matchup_pairs_顺序为文件序无向对():
    pool = _pool3()
    pairs = pool.matchup_pairs()
    assert [(a.archetype, b.archetype) for a, b in pairs] == [
        ("沙奈朵", "喷火龙 大比鸟"),
        ("沙奈朵", "猛雷鼓 厄诡椪"),
        ("喷火龙 大比鸟", "猛雷鼓 厄诡椪"),
    ]
    assert pairs[0][0] is pool.decks[0] and pairs[0][1] is pool.decks[1]


# ── 结果库访问器：experiments_by_group ────────────────────

def test_experiments_by_group(tmp_path):
    db = ResultsDB(tmp_path / "r.db")
    try:
        ids = {}
        for name, group in (("m6::A×B", "m6"), ("m6::A×C", "m6"), ("solo", "other")):
            ids[name] = db.start_experiment(
                name=name, definition_yaml="y", code_version="c",
                data_version="d", group_name=group)
        rows = db.experiments_by_group("m6")
        assert [r["id"] for r in rows] == sorted(r["id"] for r in rows)
        assert [r["id"] for r in rows] == [ids["m6::A×B"], ids["m6::A×C"]]
        assert [r["name"] for r in rows] == ["m6::A×B", "m6::A×C"]
        assert db.experiments_by_group("无此组") == []
    finally:
        db.close()


# ── 真实池回归：9 条 en_archetype == 既定名表 ─────────────

def test_真实池_en_archetype_回归():
    pool = load_target_pool("config/target-pool.v1.yml")
    assert len(pool.decks) == 9
    assert [(d.archetype, d.en_archetype) for d in pool.decks] == [
        ("沙奈朵", "Gardevoir"),
        ("喷火龙 大比鸟", "Charizard Pidgeot"),
        ("猛雷鼓 厄诡椪", "Raging Bolt Ogerpon"),
        ("多龙巴鲁托 黑夜魔灵", "Dragapult Dusknoir"),
        ("多龙巴鲁托 喷火龙", "Dragapult Charizard"),
        ("玛俐的长毛巨魔 雪妖女", "Grimmsnarl Froslass"),
        ("赛富豪", "Gholdengo"),
        ("多龙巴鲁托", "Dragapult"),
        ("赫普的苍响", "Hop's Zacian"),
    ]
    assert len(pool.matchup_pairs()) == 36


# ── CLI e2e：matrix run 分支 ──────────────────────────────

POOL_YAML = """\
version: 1
locked_at: "2026-10-03"
query:
  window: "2026-05-30..2026-08-28"
  division: master
  basis: cn
  min_n: 5
  n_tournaments: 6
  snapshot: standard-2026-07-16
  name_group_rules_hash: abc
decks:
  - {archetype: 沙奈朵, en_archetype: Gardevoir, wur: 0.3, n: 10,
     deck_id: "mik_moe:644634"}
  - {archetype: 喷火龙 大比鸟, en_archetype: Charizard Pidgeot, wur: 0.2, n: 10,
     deck_id: "mik_moe:650353"}
  - {archetype: 猛雷鼓 厄诡椪, en_archetype: Raging Bolt Ogerpon, wur: 0.1, n: 10,
     deck_id: "mik_moe:652967"}
"""


@needs_db
def test_cli_matrix_run_end_to_end(tmp_path, capsys):
    from battlefrontier.cli import main

    pool_path = tmp_path / "pool.yml"
    pool_path.write_text(POOL_YAML, encoding="utf-8")
    exp = tmp_path / "m.yml"
    exp.write_text(
        "name: m6-test\n"
        "seed_start: 900\n"
        "matrix:\n"
        f"  pool: {pool_path.as_posix()}\n"
        "  games_per_pair: 2\n"
        "agents:\n"
        "  a: {type: heuristic}\n"
        "  b: {type: heuristic}\n",
        encoding="utf-8")
    results = tmp_path / "results.db"
    rc = main(["run", str(exp), "--results", str(results),
               "--db", str(DB_PATH), "--cards-dir", "cards"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "矩阵完成" in out and "3 个配对" in out
    db = ResultsDB(results)
    try:
        rows = db.experiments_by_group("m6-test")
        assert len(rows) == 3
        for row in rows:
            assert row["status"] == "done"
            assert "::" in row["name"] and "×" in row["name"]
            assert row["group_name"] == "m6-test"
            assert len(db.games(row["id"])) == 2
    finally:
        db.close()
