"""M13：显式 split calibration 端到端。"""

from __future__ import annotations

import json
import sqlite3

import yaml

from battlefrontier.cli import main
from battlefrontier.runner.play import GameResult
from battlefrontier.runner.results_db import ResultsDB


def _real_db(tmp_path):
    path = tmp_path / "real.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE v_tournament_weights (
          tournament_id TEXT, date TEXT, division TEXT, basis TEXT
        );
        CREATE TABLE v_pairing_players (
          tournament_id TEXT, phase INT, round INT, table_no INT,
          archetype_name_1 TEXT, archetype_name_2 TEXT, winner_side INT
        );
        """
    )
    for i in range(1, 6):
        conn.execute(
            "INSERT INTO v_tournament_weights VALUES (?, ?, ?, ?)",
            (f"t{i}", f"2025-01-0{i}", "master", "intl_aligned"),
        )
        conn.execute(
            "INSERT INTO v_pairing_players VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"t{i}", 1, 1, 1, "Alpha", "Beta", 0 if i == 3 else (1 if i % 2 else 2)),
        )
    conn.commit()
    conn.close()
    return path


def _results_db(tmp_path):
    path = tmp_path / "results.db"
    db = ResultsDB(path)
    try:
        exp_id = db.start_experiment(
            name="m13::甲×乙", definition_yaml="y", code_version="cv",
            data_version="dv", group_name="m13",
        )
        for seed in range(10):
            db.record_game(
                exp_id, seed=seed, first_player=0,
                result=GameResult(winner=seed % 2, is_draw=False, turns=8, phase="main"),
                deck_a_id="a", deck_b_id="b",
            )
        db.finish_experiment(exp_id)
    finally:
        db.close()
    return path


def _definitions(tmp_path):
    pool = tmp_path / "pool.yml"
    pool.write_text(
        "version: 1\nlocked_at: t\nquery:\n"
        "  window: x\n  division: master\n  basis: cn\n  min_n: 1\n"
        "  n_tournaments: 1\n  snapshot: x\n  name_group_rules_hash: x\ndecks:\n"
        "  - {archetype: 甲, en_archetype: Alpha, wur: 0.6, n: 10, deck_id: 'mik_moe:1'}\n"
        "  - {archetype: 乙, en_archetype: Beta, wur: 0.4, n: 10, deck_id: 'mik_moe:2'}\n",
        encoding="utf-8",
    )
    exp = tmp_path / "exp.yml"
    exp.write_text(
        f"name: m13\nseed_start: 0\nmatrix:\n  pool: {pool.as_posix()}\n  games_per_pair: 10\n",
        encoding="utf-8",
    )
    protocol = tmp_path / "protocol.yml"
    protocol.write_text(
        "version: 1\nmethod: time-70-30\ndevelopment_fraction: 0.7\n"
        "tournament_count: 5\ndevelopment_count: 3\nvalidation_count: 2\n"
        "development_last: t3\nvalidation_first: t4\n"
        "real:\n"
        "  date_from: '2025-01-01'\n  date_to: '2025-01-31'\n"
        "  basis: intl_aligned\n  division: master\n",
        encoding="utf-8",
    )
    return exp, protocol


def test_cli_split_writes_three_packs_and_manifest(tmp_path, capsys):
    exp, protocol = _definitions(tmp_path)
    out = tmp_path / "out"
    rc = main([
        "calibration", str(exp), "--results", str(_results_db(tmp_path)),
        "--db", str(_real_db(tmp_path)), "--tournament-split", "time-70-30",
        "--validation-protocol", str(protocol), "--out", str(out),
    ])
    assert rc == 0
    assert "偏差包：" in capsys.readouterr().out
    for name in ("full", "development", "validation"):
        payload = json.loads((out / name / "deviation.json").read_text(encoding="utf-8"))
        assert payload["meta"]["validation_split"] == "time-70-30"
        assert payload["summary"]["unweighted_mean_abs_delta"] == 0.0
        assert payload["cells"][0]["sim_failed"] == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["protocol"]["development_count"] == 3
    assert manifest["reports"]["development"]["meta"]["real"]["n_tournaments"] == 3
    assert manifest["reports"]["validation"]["meta"]["real"]["n_tournaments"] == 2
    assert set(manifest["artifacts"]) == {"experiment", "results", "real_db"}
    assert manifest["protocol"]["report_code_version"]
    assert "前瞻验证" in manifest["reports"]["validation"]["meta"]["validation_limitation"]
    assert manifest["report_paths"]["full"]["json"].replace("\\", "/").endswith("full/deviation.json")


def test_cli_split_rejects_method_or_fraction_mismatch(tmp_path, capsys):
    exp, protocol = _definitions(tmp_path)
    original = yaml.safe_load(protocol.read_text())
    cases = (
        {"method": "time-50-50"},
        {
            "development_fraction": 0.5, "development_count": 2,
            "validation_count": 3, "development_last": "t2", "validation_first": "t3",
        },
    )
    results_db = _results_db(tmp_path)
    real_db = _real_db(tmp_path)
    for updates in cases:
        protocol.write_text(yaml.safe_dump({**original, **updates}), encoding="utf-8")
        rc = main([
            "calibration", str(exp), "--results", str(results_db),
            "--db", str(real_db), "--tournament-split", "time-70-30",
            "--validation-protocol", str(protocol), "--out", str(tmp_path / "out"),
        ])
        assert rc == 1
        assert "协议" in capsys.readouterr().out


def test_cli_split_rejects_protocol_mismatch(tmp_path, capsys):
    exp, protocol = _definitions(tmp_path)
    protocol.write_text(
        yaml.safe_dump({**yaml.safe_load(protocol.read_text()), "development_count": 2}),
        encoding="utf-8",
    )
    rc = main([
        "calibration", str(exp), "--results", str(_results_db(tmp_path)),
        "--db", str(_real_db(tmp_path)), "--tournament-split", "time-70-30",
        "--validation-protocol", str(protocol), "--out", str(tmp_path / "out"),
    ])
    assert rc == 1
    assert "协议" in capsys.readouterr().out
