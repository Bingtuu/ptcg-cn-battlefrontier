"""task 030 WP3：M6 校准偏差表 —— 模拟 matchup 矩阵 vs 真实赛事（EN 对齐段）。

真实侧全部注入 fixture（SimpleNamespace 形 MatchupStat），不打真库；
合成结果库用 record_game/record_error 落已知胜负，逐字段对拍（test_cli.py _seed_pair 先例）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from battlefrontier.data.pool import PoolEntry, TargetPool
from battlefrontier.report.calibration import (
    REAL_AS_OF,
    REAL_BASIS,
    REAL_DATE_FROM,
    REAL_DATE_TO,
    REAL_MIN_N,
    calibration_report,
    format_calibration,
)
from battlefrontier.report.winrate import wilson_ci
from battlefrontier.runner.experiment import ExperimentDef, MatrixCfg
from battlefrontier.runner.results_db import ResultsDB

QUERY = {k: "x" for k in ("window", "division", "basis", "min_n", "n_tournaments",
                          "snapshot", "name_group_rules_hash")}

REAL_META = {
    "as_of": REAL_AS_OF, "date_from": REAL_DATE_FROM, "date_to": REAL_DATE_TO,
    "basis": REAL_BASIS, "division": "master", "min_n": REAL_MIN_N,
    "n_tournaments": 409, "name_group_rules_hash": "c47538c37ca8",
    "tournament_tiers_hash": "3229fe16c2e2", "n_games_used": 99799,
}


def _entry(archetype: str, en: str, wur: float) -> PoolEntry:
    return PoolEntry(archetype=archetype, en_archetype=en, wur=wur, n=10,
                     deck_id=f"mik_moe:{wur * 1000:.0f}")


def _pool2() -> TargetPool:
    return TargetPool(version=1, locked_at="t", query=dict(QUERY), decks=[
        _entry("A宝", "Alpha", 0.6),
        _entry("B宝", "Beta", 0.5),
    ])


def _pool3() -> TargetPool:
    return TargetPool(version=1, locked_at="t", query=dict(QUERY), decks=[
        _entry("A宝", "Alpha", 0.6),
        _entry("B宝", "Beta", 0.5),
        _entry("C宝", "Gamma", 0.4),
    ])


def _defn() -> ExperimentDef:
    return ExperimentDef(name="m6t", seed_start=500,
                         matrix=MatrixCfg(pool="p.yml", games_per_pair=500))


def _real(en_a: str, en_b: str, n: int, wr: float) -> SimpleNamespace:
    return SimpleNamespace(archetype=en_a, opponent=en_b, n=n,
                           wins=round(n * wr), losses=n - round(n * wr), ties=0,
                           winrate=wr, low_confidence=False)


def _seed_pair_ab(db: ResultsDB) -> int:
    """m6t::A宝×B宝 子实验 500 局：A 胜 300 / B 胜 180 / 平 15 / 失败 5。"""
    from battlefrontier.runner.play import GameResult

    exp_id = db.start_experiment(name="m6t::A宝×B宝", definition_yaml="y",
                                 code_version="cv", data_version="dv",
                                 group_name="m6t")
    for i in range(500):
        seed = 500 + i
        if i < 300:
            res = GameResult(winner=0, is_draw=False, turns=8, phase="main",
                             first_player=0)
            db.record_game(exp_id, seed=seed, first_player=0, result=res,
                           deck_a_id="a", deck_b_id="b")
        elif i < 480:
            res = GameResult(winner=1, is_draw=False, turns=8, phase="main",
                             first_player=1)
            db.record_game(exp_id, seed=seed, first_player=1, result=res,
                           deck_a_id="a", deck_b_id="b")
        elif i < 495:
            res = GameResult(winner=None, is_draw=True, turns=30, phase="main",
                             first_player=0)
            db.record_game(exp_id, seed=seed, first_player=0, result=res,
                           deck_a_id="a", deck_b_id="b")
        else:
            db.record_error(exp_id, seed=seed, deck_a_id="a", deck_b_id="b",
                            error="DslError: 演示失败")
    db.finish_experiment(exp_id)
    return exp_id


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "r.db"
    db = ResultsDB(path)
    try:
        _seed_pair_ab(db)
    finally:
        db.close()
    return path


def _report(db_path, real_rows, pool=None):
    db = ResultsDB(db_path)
    try:
        return calibration_report(db, _defn(), pool or _pool2(), real_rows,
                                  dict(REAL_META))
    finally:
        db.close()


# ── 验收 1+2：逐格对拍（平局剔分母 / 失败局单列）──────────────

def test_逐格字段对拍(db_path):
    rep = _report(db_path, [_real("Alpha", "Beta", 100, 0.60),
                            _real("Beta", "Alpha", 100, 0.45)])
    assert rep.group_name == "m6t"
    assert len(rep.cells) == 2
    # |Δ|：b→a 0.075 > a→b 0.025，降序 b→a 在前
    ba, ab = rep.cells
    assert (ba.archetype, ba.opponent) == ("B宝", "A宝")
    assert (ba.en_archetype, ba.en_opponent) == ("Beta", "Alpha")
    assert (ab.archetype, ab.opponent) == ("A宝", "B宝")
    assert (ab.en_archetype, ab.en_opponent) == ("Alpha", "Beta")

    # 决定局 480（平 15 剔分母），失败 5 单列不进分母
    for cell in (ab, ba):
        assert cell.sim_decided == 480
        assert cell.sim_draws == 15
        assert cell.sim_failed == 5

    assert ab.sim_wins == 300 and ba.sim_wins == 180
    assert ab.sim_wr == pytest.approx(300 / 480)
    assert ba.sim_wr == pytest.approx(180 / 480)
    # CI 与 wilson_ci 对拍
    assert ab.sim_ci == wilson_ci(300, 480)
    assert ba.sim_ci == wilson_ci(180, 480)
    # 真实侧 + Δ
    assert ab.real_n == 100 and ab.real_wr == pytest.approx(0.60)
    assert ba.real_n == 100 and ba.real_wr == pytest.approx(0.45)
    assert ab.delta == pytest.approx(300 / 480 - 0.60)
    assert ba.delta == pytest.approx(180 / 480 - 0.45)


# ── 验收 3：真实侧缺格 → None 排尾 ─────────────────────────

def test_真实侧缺格_None_排尾(db_path):
    rep = _report(db_path, [_real("Alpha", "Beta", 100, 0.60)])
    ab, ba = rep.cells  # 有 Δ 的在前，缺格排尾
    assert ab.delta is not None
    assert (ba.archetype, ba.opponent) == ("B宝", "A宝")
    assert ba.real_n is None and ba.real_wr is None and ba.delta is None
    # 汇总只算有效格：单格 a→b，|Δ|=0.025，权重 100
    assert rep.weighted_mean_abs_delta == pytest.approx(abs(300 / 480 - 0.60))


def test_真实侧全缺_汇总_None(db_path):
    rep = _report(db_path, [])
    assert all(c.delta is None for c in rep.cells)
    assert rep.weighted_mean_abs_delta is None and rep.ci_coverage is None


# ── 验收 4：汇总手算对拍 ───────────────────────────────────

def test_汇总加权平均与CI覆盖率(db_path):
    rep = _report(db_path, [_real("Alpha", "Beta", 100, 0.60),
                            _real("Beta", "Alpha", 100, 0.45)])
    # 手算：(|0.025|·100 + |−0.075|·100) / 200 = 0.05
    assert rep.weighted_mean_abs_delta == pytest.approx(0.05)
    # CI：a→b 300/480 CI≈[0.581, 0.667] 覆盖 real 0.60；
    #     b→a 180/480 CI≈[0.333, 0.419] 不覆盖 real 0.45 → 1/2
    lo_a, hi_a = wilson_ci(300, 480)
    lo_b, hi_b = wilson_ci(180, 480)
    assert lo_a <= 0.60 <= hi_a
    assert not (lo_b <= 0.45 <= hi_b)
    assert rep.ci_coverage == pytest.approx(0.5)


def test_meta_要素(db_path):
    rep = _report(db_path, [_real("Alpha", "Beta", 100, 0.60)])
    m = rep.meta
    assert m["group_name"] == "m6t"
    assert (m["seed_min"], m["seed_max"]) == (500, 999)
    assert m["code_version"] == "cv" and m["data_version"] == "dv"
    assert m["real"]["n_games_used"] == 99799
    assert m["real"]["name_group_rules_hash"] == "c47538c37ca8"


# ── 验收 5：子实验缺失 → ValueError ───────────────────────

def test_子实验缺失_ValueError(db_path):
    with pytest.raises(ValueError, match="m6t::A宝×C宝"):
        _report(db_path, [], pool=_pool3())


# ── 验收 6：format_calibration 文本 ───────────────────────

def test_format_含meta全要素与逐格行汇总行(db_path):
    rep = _report(db_path, [_real("Alpha", "Beta", 100, 0.60)])
    out = format_calibration(rep)
    # meta：窗口 / basis / min_n / 数据版本 / 种子区间 / 口径哈希
    assert REAL_DATE_FROM in out and REAL_DATE_TO in out
    assert REAL_BASIS in out and str(REAL_MIN_N) in out
    assert "dv" in out and "500..999" in out
    assert "c47538c37ca8" in out and "99799" in out
    # 逐格行 + 缺格标注 + 汇总行 + 口径注明
    assert "A宝 vs B宝" in out and "B宝 vs A宝" in out
    assert "真实侧缺数据" in out
    assert "加权平均" in out and "CI 覆盖率" in out and "最大偏差" in out
    assert "决定局" in out and "失败" in out


# ── 验收 7：CLI e2e ───────────────────────────────────────

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
  - {archetype: A宝, en_archetype: Alpha, wur: 0.6, n: 10, deck_id: "mik_moe:1"}
  - {archetype: B宝, en_archetype: Beta, wur: 0.5, n: 10, deck_id: "mik_moe:2"}
"""


def _write_defs(tmp_path, *, matrix: bool = True) -> tuple:
    pool_path = tmp_path / "pool.yml"
    pool_path.write_text(POOL_YAML, encoding="utf-8")
    exp = tmp_path / "exp.yml"
    if matrix:
        exp.write_text(
            "name: m6t\nseed_start: 500\n"
            "matrix:\n"
            f"  pool: {pool_path.as_posix()}\n"
            "  games_per_pair: 500\n",
            encoding="utf-8")
    else:
        exp.write_text(
            "name: solo\ngames: 1\nseed_start: 0\n"
            "decks:\n"
            '  a: {source: db, deck_id: "mik_moe:1"}\n'
            '  b: {source: db, deck_id: "mik_moe:2"}\n',
            encoding="utf-8")
    return pool_path, exp


class _FakeSdk:
    """stats_matchup 记录查询参数并返回固定 MatchupResult 形数据。"""

    def __init__(self):
        self.kwargs = None
        self.closed = False

    def stats_matchup(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(meta=dict(REAL_META),
                               data=[_real("Alpha", "Beta", 100, 0.60),
                                     _real("Beta", "Alpha", 100, 0.45)])

    def close(self):
        self.closed = True


def test_cli_calibration_出表_rc0(db_path, tmp_path, capsys, monkeypatch):
    from battlefrontier.cli import main

    _, exp = _write_defs(tmp_path)
    fake = _FakeSdk()
    monkeypatch.setattr("ptcgdb.sdk.open_db", lambda path: fake)
    rc = main(["calibration", str(exp), "--results", str(db_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "A宝 vs B宝" in out and "加权平均" in out
    # D-030-1 口径参数原样传给 SDK
    assert fake.kwargs == {
        "date_from": REAL_DATE_FROM, "date_to": REAL_DATE_TO,
        "as_of": REAL_AS_OF, "basis": REAL_BASIS,
        "division": "master", "min_n": REAL_MIN_N,
    }
    assert fake.closed


def test_cli_calibration_非matrix定义_rc1(tmp_path, capsys):
    from battlefrontier.cli import main

    _, exp = _write_defs(tmp_path, matrix=False)
    rc = main(["calibration", str(exp), "--results", str(tmp_path / "r.db")])
    assert rc == 1
    assert "matrix" in capsys.readouterr().out
