"""task 075：换卡报告双轨导出与抽样回放。不扫描卡池。"""

import json

from battlefrontier.cli import main
from battlefrontier.engine.events import GameEvent
from battlefrontier.report.sensitivity import sensitivity_report
from battlefrontier.report.swap_pack import swap_replays, write_swap_pack
from battlefrontier.runner.experiment import load_experiment
from battlefrontier.runner.play import GameResult
from battlefrontier.runner.results_db import ResultsDB


def _attack(seq: int = 0) -> GameEvent:
    return GameEvent(
        seq=seq, turn=1, phase="main", player=0, kind="attack",
        detail={"name": "沙奈朵", "attack": "奇迹力", "damage": 30, "target": "甲"},
    )


def _seed(tmp_path) -> tuple[ResultsDB, int, int]:
    db = ResultsDB(tmp_path / "r.db")
    ids = []
    for variant, wins in (("", 6), ("v1", 8)):
        exp_id = db.start_experiment(
            name="grp", definition_yaml="y", code_version="c", data_version="d",
            group_name="grp", variant=variant,
        )
        for seed in range(10):
            events = [_attack()] if seed == 0 else []
            res = GameResult(
                winner=0 if seed < wins else 1, is_draw=False, turns=8,
                phase="main", first_player=0, events=events,
            )
            db.record_game(
                exp_id, seed=seed, first_player=0, result=res,
                deck_a_id="a", deck_b_id="b",
            )
        db.finish_experiment(exp_id)
        ids.append(exp_id)
    return db, ids[0], ids[1]


def test_pack_shares_delta_and_samples_one_each(tmp_path) -> None:
    db, base_id, var_id = _seed(tmp_path)
    try:
        rep = sensitivity_report(db, base_id, [var_id])
        replays = swap_replays(db, rep, 1)
        paths = write_swap_pack(tmp_path / "pack", rep, replays)
    finally:
        db.close()
    assert rep.variants[0].d_wr == pytest_delta(rep)
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    variant = next(row for row in payload["rows"] if row["role"] == "variant")
    assert variant["d_wr"] == rep.variants[0].d_wr
    assert variant["wr_a"] == rep.variants[0].wr_a
    baseline = next(row for row in payload["rows"] if row["role"] == "baseline")
    assert baseline["d_wr"] is None
    md = paths["md"].read_text(encoding="utf-8")
    assert "ΔWR" in md and "使用招式" in md
    assert "使用招式" in paths["html"].read_text(encoding="utf-8")
    labels = [r.label for r in replays]
    assert labels == ["baseline", "v1"]
    assert all("使用招式" in r.text for r in replays)


def pytest_delta(rep) -> float:
    return rep.variants[0].report.wr_a - rep.base.wr_a


def test_card_swap_template_is_one_declared_swap() -> None:
    defn = load_experiment("experiments/templates/card-swap.example.yml")
    assert len(defn.variants) == 1
    assert defn.variants[0].swaps[0].out == "反击捕捉器"
    assert defn.variants[0].swaps[0].in_ == "巢穴球"
    assert defn.games == 1


def test_cli_sensitivity_writes_swap_pack(tmp_path, capsys) -> None:
    db, base_id, var_id = _seed(tmp_path)
    path = tmp_path / "r.db"
    db.close()
    out = tmp_path / "pack"
    rc = main([
        "sensitivity", str(base_id), str(var_id),
        "--results", str(path), "--out", str(out), "--replay-sample", "1",
    ])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "ΔWR" in printed and "换卡包：" in printed
    payload = json.loads((out / "swap.json").read_text(encoding="utf-8"))
    variant = next(row for row in payload["rows"] if row["role"] == "variant")
    assert abs(variant["d_wr"] - 0.2) < 1e-9
    assert "使用招式" in (out / "swap.md").read_text(encoding="utf-8")
