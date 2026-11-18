"""task 127：`bfsim league` CLI——跑+报一体与 --report 纯报告模式。"""

import pytest
from helpers import deck60

from battlefrontier.cli import main
from battlefrontier.runner.experiment import PreparedExperiment

_SMALL = """
name: lg-cli
seed_start: 820000
seed_stride: 100
games_per_cell: 4
decks:
  - {source: db, deck_id: "mik_moe:1"}
agents:
  - {id: ra, type: random}
  - {id: rb, type: random}
"""


@pytest.fixture()
def _stub_prep(monkeypatch):
    from battlefrontier.runner import league as league_mod

    def _fake_prep(defn, db_path, cards_dir=None):
        return PreparedExperiment(
            deck_a=deck60(), deck_b=deck60(), card_effects={},
            deck_a_id="stub", deck_b_id="stub", data_version="test")

    monkeypatch.setattr(league_mod, "prepare_experiment", _fake_prep)


def test_league_run_and_report_cli(tmp_path, capsys, _stub_prep):
    yml = tmp_path / "lg.yml"
    yml.write_text(_SMALL, encoding="utf-8")
    db = tmp_path / "x.db"
    rc = main(["league", str(yml), "--results", str(db), "--db", "fake.db"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "BT-MLE" in out and "ra" in out and "rb" in out
    assert "lg-cli" in out


def test_league_report_only_mode(tmp_path, capsys, _stub_prep):
    yml = tmp_path / "lg.yml"
    yml.write_text(_SMALL, encoding="utf-8")
    db = tmp_path / "x.db"
    main(["league", str(yml), "--results", str(db), "--db", "fake.db"])
    capsys.readouterr()
    rc = main(["league", "--report", "lg-cli", "--results", str(db)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "BT-MLE" in out


def test_league_report_only_unknown_errors(tmp_path, capsys):
    from battlefrontier.runner.results_db import ResultsDB
    ResultsDB(tmp_path / "x.db").close()
    with pytest.raises((ValueError, SystemExit)):
        main(["league", "--report", "nope", "--results", str(tmp_path / "x.db")])
