"""task 019：实验定义 YAML + 正式 Runner（PRD §8.1/§8.2/§8.4）。

确定性硬验收（§8.4）：同实验定义 + 同种子区间，串行 vs 并行、两次独立重跑，
games 层 (seed, winner, is_draw, turns, events_hash) 逐局一致。
"""

import json
from pathlib import Path

import pytest
from helpers import deck60, energy

from battlefrontier.agent.heuristic import HeuristicAgent
from battlefrontier.agent.random_agent import RandomAgent
from battlefrontier.dsl.loader import CardLibrary, load_card_doc
from battlefrontier.engine.state import AttackDef, CardDef
from battlefrontier.runner.experiment import (
    PreparedExperiment,
    build_agents,
    execute_experiment,
    load_experiment,
    parse_decklist,
)
from battlefrontier.runner.results_db import ResultsDB

VALID_YAML = """
name: mirror-test
games: 4
seed_start: 100
decks:
  a: {source: db, deck_id: "mik_moe:644634"}
  b: {source: file, path: "decklists/x.txt"}
agents:
  a: {type: heuristic, params: {w_damage: 0.1}}
  b: {type: random}
snapshot_date: "2026-08-09"
"""


def _write(tmp_path, text: str = VALID_YAML):
    p = tmp_path / "exp.yml"
    p.write_text(text, encoding="utf-8")
    return p


# ── 实验定义 schema ──────────────────────────────────────

def test_load_valid(tmp_path):
    defn = load_experiment(_write(tmp_path))
    assert defn.name == "mirror-test"
    assert defn.games == 4 and defn.seed_start == 100
    assert defn.decks.a.source == "db" and defn.decks.a.deck_id == "mik_moe:644634"
    assert defn.decks.b.source == "file" and defn.decks.b.path == "decklists/x.txt"
    assert defn.agents.a.type == "heuristic" and defn.agents.a.params == {"w_damage": 0.1}
    assert defn.agents.b.type == "random"
    assert defn.snapshot_date == "2026-08-09"


@pytest.mark.parametrize("bad", [
    "name: t\ngames: 4\ndecks:\n  a: {source: db, deck_id: x}\n",  # 缺 decks.b
    "name: t\ngames: 0\ndecks:\n  a: {source: db, deck_id: x}\n  b: {source: db, deck_id: y}\n",
    ("name: t\ngames: 1\ndecks:\n  a: {source: db, deck_id: x}\n  b: {source: db, deck_id: y}\n"
     "agents:\n  a: {type: minimax}\n"),                              # 未知 agent type
    ("name: t\ngames: 1\ndecks:\n  a: {source: db, deck_id: x}\n  b: {source: db, deck_id: y}\n"
     "agents:\n  a: {type: heuristic, params: {w_hindsight: 1}}\n"),   # 未知参数名（不猜）
    ("name: t\ngames: 1\ndecks:\n  a: {source: db, deck_id: x}\n  b: {source: db, deck_id: y}\n"
     "agents:\n  a: {type: mcts, params: {time_limit: 5}}\n"),         # mcts 未知参数（禁墙钟，不猜）
    "name: t\ngames: 1\ndecks:\n  a: {source: http, url: x}\n  b: {source: db, deck_id: y}\n",
    "name: t\ngames: 1\ndecks:\n  a: {source: db}\n  b: {source: db, deck_id: y}\n",  # db 缺 deck_id
])
def test_load_invalid(tmp_path, bad):
    with pytest.raises((ValueError, TypeError)):
        load_experiment(_write(tmp_path, bad))


# ── 本地 decklist 解析 ───────────────────────────────────

def test_parse_decklist():
    assert parse_decklist("4 沙奈朵ex\n2 博士的研究\n# 注释行\n\n1 基本超能量\n") == [
        (4, "沙奈朵ex"), (2, "博士的研究"), (1, "基本超能量")]


@pytest.mark.parametrize("bad", ["4\n", "0 沙奈朵ex\n", "x 沙奈朵ex\n"])
def test_parse_decklist_invalid(bad):
    with pytest.raises(ValueError):
        parse_decklist(bad)


# ── Agent 构建 ───────────────────────────────────────────

def test_build_agents(tmp_path):
    defn = load_experiment(_write(tmp_path))
    a, b = build_agents(defn, seed=42)
    assert isinstance(a, HeuristicAgent) and a.params.w_damage == 0.1
    assert isinstance(b, RandomAgent)


# ── 执行与确定性 ─────────────────────────────────────────

def _prepared() -> PreparedExperiment:
    return PreparedExperiment(
        deck_a=deck60(), deck_b=deck60(), card_effects={},
        deck_a_id="stub", deck_b_id="stub", data_version="test")


def _defn(tmp_path) -> object:
    return load_experiment(_write(tmp_path))


def _games_snapshot(db_path, exp_id):
    db = ResultsDB(db_path)
    try:
        return [
            (g["seed"], g["winner"], g["is_draw"], g["turns"], g["events_hash"])
            for g in db.games(exp_id)
        ]
    finally:
        db.close()


def test_execute_serial_then_rerun_identical(tmp_path):
    """§8.4 硬验收：同定义同种子区间，两次独立重跑 games 层逐局一致。"""
    defn = _defn(tmp_path)
    snap_a = _games_snapshot(
        tmp_path / "a.db", execute_experiment(_prepared(), defn, tmp_path / "a.db",
                                              definition_yaml=VALID_YAML))
    snap_b = _games_snapshot(
        tmp_path / "b.db", execute_experiment(_prepared(), defn, tmp_path / "b.db",
                                              definition_yaml=VALID_YAML))
    assert len(snap_a) == 4 and snap_a == snap_b


def test_execute_parallel_matches_serial(tmp_path):
    """多进程并行与串行结果逐局一致（硬验收）。"""
    defn = _defn(tmp_path)
    serial = _games_snapshot(
        tmp_path / "s.db", execute_experiment(_prepared(), defn, tmp_path / "s.db",
                                              workers=1, definition_yaml=VALID_YAML))
    parallel = _games_snapshot(
        tmp_path / "p.db", execute_experiment(_prepared(), defn, tmp_path / "p.db",
                                              workers=2, definition_yaml=VALID_YAML))
    assert serial == parallel


# ── task 040 F2（D-040-2）：DSL 路径串并一致性对拍 ─────────

_CARDS_DIR = Path(__file__).parent.parent / "cards"


def _dsl_prepared() -> PreparedExperiment:
    """真实 DSL 库对拍卡组：检索（能量输送PRO chooser 挂起/恢复）+ 掷币
    （咕咕 times:3 / 索财灵 until_tails）+ flip_heads_count 计数伤害。
    CardDef 手工构造，card_id 与 DSL 文档 card_ids 对齐（精确挂载路径，非白板）。"""
    docs = [load_card_doc(_CARDS_DIR / name) for name in
            ("能量输送PRO.yml", "咕咕-三刺击.yml", "索财灵-连掷硬币.yml")]
    effects = CardLibrary.from_docs((d.card.name_group, d) for d in docs)
    deck = (
        [CardDef(card_id="CSV9C-154", name="咕咕", supertype="pokemon", hp=70,
                 stage=0, energy_type="无", retreat_cost=1,
                 attacks=(AttackDef(name="三刺击", cost=("无",), damage=None),))] * 14
        + [CardDef(card_id="CSV4C-063", name="索财灵", supertype="pokemon", hp=70,
                   stage=0, energy_type="超", retreat_cost=1,
                   attacks=(AttackDef(name="连掷硬币", cost=("无",), damage=None),))] * 14
        + [CardDef(card_id="CSV9C-176", name="能量输送PRO", supertype="trainer",
                   trainer_subtype="物品", is_ace_spec=True)] * 4
        + [energy("基本超能量", "超")] * 28
    )
    assert len(deck) == 60
    return PreparedExperiment(
        deck_a=deck, deck_b=deck, card_effects=effects,
        deck_a_id="dsl-stub", deck_b_id="dsl-stub", data_version="test")


def test_execute_parallel_matches_serial_dsl_path(tmp_path):
    """DSL 解释器参与路径的串并对拍（D-040-2；既有白板护栏 card_effects={} 的补盲）：
    workers=1 vs workers=2 逐局比对 (seed, winner, is_draw, turns, events_hash)。
    事件流 hash 覆盖 effect_primitive 明细（pool_iids/chosen/掷币结果等），
    dict 序依赖等串并分叉会立刻体现在 hash 上。"""
    defn = _defn(tmp_path)
    serial_db, parallel_db = tmp_path / "ds.db", tmp_path / "dp.db"
    serial_id = execute_experiment(_dsl_prepared(), defn, serial_db,
                                   workers=1, definition_yaml=VALID_YAML)
    parallel_id = execute_experiment(_dsl_prepared(), defn, parallel_db,
                                     workers=2, definition_yaml=VALID_YAML)
    serial = _games_snapshot(serial_db, serial_id)
    parallel = _games_snapshot(parallel_db, parallel_id)
    assert serial == parallel

    # 有效性自查（D-040-2 验收 2）：无失败局（error 行 winner=None/hash=''，
    # 放任不管会让对拍假绿），且事件流确含 DSL 解释器产出（effect_primitive
    # 检索 + 掷币），否则对拍没走 DSL 路径、测试无效
    db = ResultsDB(serial_db)
    try:
        games = db.games(serial_id)
        assert all(g["error"] is None for g in games)
        dsl_actions = {
            json.loads(ev["event_json"])["detail"].get("action")
            for g in games for ev in db.game_events(g["id"])
            if json.loads(ev["event_json"])["kind"] == "effect_primitive"
        }
    finally:
        db.close()
    assert {"search_deck", "coin_flip"} <= dsl_actions


def test_execute_interrupted_marks_aborted(tmp_path, monkeypatch):
    """task 038 F4（D-038-4）：KeyboardInterrupt/SystemExit 不永挂 running——
    兜底落 status=aborted 后原样重抛。"""
    import battlefrontier.runner.experiment as exp_mod

    def boom(deck_a, deck_b, seed, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(exp_mod, "play_game", boom)
    defn = _defn(tmp_path)
    db_path = tmp_path / "i.db"
    with pytest.raises(KeyboardInterrupt):
        execute_experiment(_prepared(), defn, db_path, definition_yaml=VALID_YAML)
    db = ResultsDB(db_path)
    try:
        status = db._conn.execute(
            "SELECT status FROM experiments").fetchone()[0]
        assert status == "aborted"
    finally:
        db.close()


def test_execute_records_failed_games(tmp_path, monkeypatch):
    """单局抛错（如 DSL 显式 DslError）不拖垮实验：记 error 行，实验照常 done。"""
    import battlefrontier.runner.experiment as exp_mod

    real_play_game = exp_mod.play_game

    def flaky(deck_a, deck_b, seed, **kw):
        if seed == 101:
            raise ValueError("模拟 DSL 未支持")
        return real_play_game(deck_a, deck_b, seed, **kw)

    monkeypatch.setattr(exp_mod, "play_game", flaky)
    defn = _defn(tmp_path)
    db_path = tmp_path / "f.db"
    exp_id = execute_experiment(_prepared(), defn, db_path, definition_yaml=VALID_YAML)
    db = ResultsDB(db_path)
    try:
        games = db.games(exp_id)
        assert len(games) == 4
        failed = [g for g in games if g["error"]]
        assert len(failed) == 1 and failed[0]["seed"] == 101
        assert "模拟 DSL 未支持" in failed[0]["error"]
        status = db._conn.execute(
            "SELECT status FROM experiments WHERE id=?", (exp_id,)).fetchone()[0]
        assert status == "done"
    finally:
        db.close()


def test_execute_experiment_row_meta(tmp_path):
    defn = _defn(tmp_path)
    db_path = tmp_path / "r.db"
    exp_id = execute_experiment(_prepared(), defn, db_path, definition_yaml=VALID_YAML)
    db = ResultsDB(db_path)
    try:
        row = db._conn.execute(
            "SELECT name, definition_yaml, code_version, data_version, status "
            "FROM experiments WHERE id=?", (exp_id,)).fetchone()
    finally:
        db.close()
    name, yaml_text, code_version, data_version, status = row
    assert name == "mirror-test" and yaml_text == VALID_YAML
    assert code_version and data_version == "test" and status == "done"
    # 事件流落库：每局事件流可重取
    db = ResultsDB(db_path)
    try:
        games = db.games(exp_id)
        assert all(len(db.game_events(g["id"])) > 0 for g in games)
    finally:
        db.close()
