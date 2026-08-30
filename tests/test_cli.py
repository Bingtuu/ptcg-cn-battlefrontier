"""task 019：bfsim CLI —— run 子命令端到端（PRD §8 / M3「CLI 实验 Runner」）。"""

from pathlib import Path

import pytest

from battlefrontier.cli import main
from battlefrontier.runner.results_db import ResultsDB

DB_PATH = Path(r"C:/Vibe Project/Pokearena/data/ptcg-cn.db")

CLI_YAML = """
name: cli-e2e
games: 2
seed_start: 300
decks:
  a: {source: db, deck_id: "mik_moe:644634"}
  b: {source: db, deck_id: "mik_moe:644634"}
agents:
  a: {type: heuristic}
  b: {type: random}
"""


def test_cli_no_args_placeholder(capsys):
    assert main([]) == 0
    assert "battlefrontier" in capsys.readouterr().out


@pytest.mark.skipif(not DB_PATH.exists(), reason="本机无 ptcg-cn.db")
def test_cli_run_end_to_end(tmp_path, capsys):
    exp = tmp_path / "exp.yml"
    exp.write_text(CLI_YAML, encoding="utf-8")
    results = tmp_path / "results.db"
    rc = main(["run", str(exp), "--results", str(results),
               "--db", str(DB_PATH), "--cards-dir", "cards"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "cli-e2e" in out and "实验" in out
    db = ResultsDB(results)
    try:
        exps = db._conn.execute(
            "SELECT status FROM experiments WHERE name='cli-e2e'").fetchall()
        assert exps == [("done",)]
        exp_id = db._conn.execute(
            "SELECT id FROM experiments WHERE name='cli-e2e'").fetchone()[0]
        assert len(db.games(exp_id)) == 2
    finally:
        db.close()


def _seed_pair(results: Path):
    """造 base/variant 两实验供 sensitivity 子命令冒烟。"""
    from battlefrontier.runner.play import GameResult

    db = ResultsDB(results)
    ids = []
    for variant, wins in (("", 3), ("v1", 1)):
        exp_id = db.start_experiment(name="grp", definition_yaml="y",
                                     code_version="c", data_version="d",
                                     group_name="grp", variant=variant)
        for seed in range(4):
            res = GameResult(winner=0 if seed < wins else 1, is_draw=False,
                             turns=8, phase="main", first_player=0)
            db.record_game(exp_id, seed=seed, first_player=0, result=res,
                           deck_a_id="a", deck_b_id="b")
        db.finish_experiment(exp_id)
        ids.append(exp_id)
    db.close()
    return ids


def test_cli_sensitivity(tmp_path, capsys):
    """task 023：bfsim sensitivity <base> <variant...> 并排 ΔWR 报告。"""
    results = tmp_path / "r.db"
    base_id, var_id = _seed_pair(results)
    rc = main(["sensitivity", str(base_id), str(var_id),
               "--results", str(results)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ΔWR" in out and "v1" in out


def test_cli_sensitivity_bad_id(tmp_path, capsys):
    results = tmp_path / "r.db"
    _seed_pair(results)
    rc = main(["sensitivity", "999", "1", "--results", str(results)])
    assert rc == 1
    assert "错误" in capsys.readouterr().out
