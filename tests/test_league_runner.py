"""task 127：plan_cells 纯规划 + run_league 执行编排（确定性硬验收）。

plan_cells：无序对（注册表序）× decks × 双向 ab/ba；同无序对共享种子区间
（CRN 双向配对）；卡组 mirror；名字/元数据确定性。
run_league：真引擎跑局（monkeypatch prepare_experiment 为 stub 卡组边界），
两次独立重跑评级一致 + 并串逐局一致（§8.4 纪律）。
"""

import yaml
from helpers import deck60

from battlefrontier.runner.experiment import PreparedExperiment
from battlefrontier.runner.league import load_league, plan_cells, run_league
from battlefrontier.runner.results_db import ResultsDB

VALID = """
name: lg
seed_start: 800000
seed_stride: 1000
games_per_cell: 10
decks:
  - {source: db, deck_id: "mik_moe:1"}
  - {source: db, deck_id: "mik_moe:2"}
agents:
  - {id: ra, type: random}
  - {id: rb, type: random}
  - {id: rc, type: random}
"""


def _league(tmp_path, text: str = VALID):
    p = tmp_path / "lg.yml"
    p.write_text(text, encoding="utf-8")
    return load_league(p)


# ── plan_cells ───────────────────────────────────────────

def test_plan_cell_count(tmp_path):
    lg = _league(tmp_path)
    cells = plan_cells(lg)
    assert len(cells) == 3 * 2 * 2  # C(3,2) 无序对 × 2 decks × 双向


def test_plan_crn_shared_seed_range_per_pair(tmp_path):
    lg = _league(tmp_path)
    cells = plan_cells(lg)
    # 每个无序对的 ab/ba（跨 deck）共享同一基础种子区间
    for k in range(3):
        pair_cells = [c for c in cells if c.pair_index == k]
        assert len(pair_cells) == 4  # 2 decks × ab/ba
        assert len({c.defn.seed_start for c in pair_cells}) == 1
        assert pair_cells[0].defn.seed_start == 800000 + k * 1000
        assert all(c.defn.games == 10 for c in pair_cells)


def test_plan_mirror_deck_and_swapped_agents(tmp_path):
    lg = _league(tmp_path)
    cells = plan_cells(lg)
    for c in cells:
        assert c.defn.decks.a == c.defn.decks.b  # mirror
        a_id, b_id = c.agent_a_id, c.agent_b_id
        assert {a_id, b_id} == {lg.agents[c.i].id, lg.agents[c.j].id}
    # ab/ba 互为换边
    for k in range(3):
        for d in range(2):
            ab = next(c for c in cells
                      if c.pair_index == k and c.deck_index == d
                      and c.direction == "ab")
            ba = next(c for c in cells
                      if c.pair_index == k and c.deck_index == d
                      and c.direction == "ba")
            assert (ab.agent_a_id, ab.agent_b_id) == (ba.agent_b_id, ba.agent_a_id)


def test_plan_names_deterministic(tmp_path):
    lg = _league(tmp_path)
    names1 = [c.name for c in plan_cells(lg)]
    names2 = [c.name for c in plan_cells(_league(tmp_path))]
    assert names1 == names2
    assert len(set(names1)) == len(names1)  # 全唯一


def test_plan_definition_yaml_carries_league_meta(tmp_path):
    lg = _league(tmp_path)
    cell = plan_cells(lg)[0]
    meta = yaml.safe_load(cell.definition_yaml)
    assert meta["league"]["agents"]["a"] == cell.agent_a_id
    assert meta["league"]["agents"]["b"] == cell.agent_b_id
    assert meta["league"]["deck_index"] == cell.deck_index
    assert "registry_sha256" in meta["league"]
    assert meta["experiment"]["games"] == 10


# ── run_league 执行与确定性 ──────────────────────────────

_SMALL = """
name: lg-small
seed_start: 810000
seed_stride: 100
games_per_cell: 4
decks:
  - {source: db, deck_id: "mik_moe:1"}
agents:
  - {id: ra, type: random}
  - {id: rb, type: random}
"""


def _stub_prep_factory(monkeypatch):
    """prepare_experiment 边界打桩（stub 卡组），底下真引擎真随机源。"""
    from battlefrontier.runner import league as league_mod

    def _fake_prep(defn, db_path, cards_dir=None):
        return PreparedExperiment(
            deck_a=deck60(), deck_b=deck60(), card_effects={},
            deck_a_id="stub", deck_b_id="stub", data_version="test")

    monkeypatch.setattr(league_mod, "prepare_experiment", _fake_prep)


def _games_snapshot(db_path):
    db = ResultsDB(db_path)
    try:
        return [
            (e["name"], g["seed"], g["winner"], g["is_draw"], g["turns"],
             g["events_hash"], g["error"])
            for e in db.experiments_by_group("lg-small")
            for g in db.games(e["id"])
        ]
    finally:
        db.close()


def test_run_league_serial_rerun_identical(tmp_path, monkeypatch):
    _stub_prep_factory(monkeypatch)
    lg = _league(tmp_path, _SMALL)
    id1 = run_league(lg, "fake.db", tmp_path / "a.db", workers=1,
                     registry_path=tmp_path / "lg.yml")
    id2 = run_league(lg, "fake.db", tmp_path / "b.db", workers=1,
                     registry_path=tmp_path / "lg.yml")
    assert id1 and id1 == id2  # 细胞数稳定
    snap_a, snap_b = _games_snapshot(tmp_path / "a.db"), _games_snapshot(tmp_path / "b.db")
    assert len(snap_a) == 8  # 1 无序对 × 1 deck × ab/ba × 4 局
    assert snap_a == snap_b


def test_run_league_parallel_matches_serial(tmp_path, monkeypatch):
    _stub_prep_factory(monkeypatch)
    lg = _league(tmp_path, _SMALL)
    run_league(lg, "fake.db", tmp_path / "s.db", workers=1,
               registry_path=tmp_path / "lg.yml")
    run_league(lg, "fake.db", tmp_path / "p.db", workers=2,
               registry_path=tmp_path / "lg.yml")
    assert _games_snapshot(tmp_path / "s.db") == _games_snapshot(tmp_path / "p.db")
