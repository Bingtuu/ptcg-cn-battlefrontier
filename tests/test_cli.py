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
