"""task 074：每局汇总、抽样 render_log、主阶段行动 × 胜率。"""

import json

from battlefrontier.cli import main
from battlefrontier.engine.events import GameEvent
from battlefrontier.report.battle_log import (
    battle_log_report,
    format_main_actions,
    write_battle_log_pack,
)
from battlefrontier.runner.play import GameResult
from battlefrontier.runner.results_db import ResultsDB


def _attack() -> GameEvent:
    return GameEvent(
        seq=0, turn=1, phase="main", player=0, kind="attack",
        detail={"name": "喷火龙", "attack": "火之玉", "damage": 10, "target": "甲"},
    )


def _seed(tmp_path) -> tuple[ResultsDB, int]:
    db = ResultsDB(tmp_path / "r.db")
    exp_id = db.start_experiment(
        name="log", definition_yaml="y", code_version="c", data_version="d",
    )
    choose = GameEvent(
        seq=1, turn=1, phase="main", player=0, kind="choose",
        detail={"card": "球", "pool": "hand", "chosen_names": ["甲"]},
    )
    end = GameEvent(seq=0, turn=2, phase="main", player=1, kind="end_turn", detail={})
    db.record_game(
        exp_id, seed=1, first_player=0, deck_a_id="a", deck_b_id="b",
        result=GameResult(
            winner=0, is_draw=False, turns=3, phase="main", first_player=0,
            events=[_attack(), choose],
        ),
    )
    db.record_game(
        exp_id, seed=2, first_player=0, deck_a_id="a", deck_b_id="b",
        result=GameResult(
            winner=1, is_draw=False, turns=4, phase="main", first_player=0,
            events=[_attack()],
        ),
    )
    db.record_game(
        exp_id, seed=3, first_player=1, deck_a_id="a", deck_b_id="b",
        result=GameResult(
            winner=None, is_draw=True, turns=5, phase="main", first_player=1,
            events=[end],
        ),
    )
    db.record_error(exp_id, seed=4, deck_a_id="a", deck_b_id="b", error="boom")
    db.finish_experiment(exp_id)
    return db, exp_id


def test_summary_actions_and_one_replay(tmp_path) -> None:
    db, exp_id = _seed(tmp_path)
    try:
        rep = battle_log_report(db, exp_id, sample_n=1)
    finally:
        db.close()
    assert [row.seed for row in rep.summaries] == [1, 2, 3, 4]
    assert rep.summaries[-1].error == "boom"
    attack = next(s for s in rep.actions if s.kind == "attack")
    assert attack.label == "喷火龙：火之玉"
    assert attack.occurrences == 2 and attack.wins == 1
    assert attack.winrate == 0.5
    end = next(s for s in rep.actions if s.kind == "end_turn")
    assert end.occurrences == 1 and end.games == 0
    assert all(s.kind != "choose" for s in rep.actions)
    assert len(rep.replays) == 1 and rep.replays[0].seed == 1
    assert "使用招式" in rep.replays[0].text
    text = format_main_actions(rep)
    assert "理由" not in text and "合法行动" not in text
    paths = write_battle_log_pack(tmp_path / "pack", rep)
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["actions"][0]["winrate"] == rep.actions[0].winrate
    assert "使用招式" in paths["md"].read_text(encoding="utf-8")
    assert "使用招式" in paths["html"].read_text(encoding="utf-8")


def test_cli_report_writes_log_pack(tmp_path, capsys) -> None:
    db, exp_id = _seed(tmp_path)
    path = tmp_path / "r.db"
    db.close()
    out = tmp_path / "pack"
    rc = main([
        "report", str(exp_id), "--results", str(path),
        "--out", str(out), "--replay-sample", "1",
    ])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "每局汇总" in printed and "主阶段行动" in printed
    assert "理由" not in printed
    assert "对局包：" in printed
    md = (out / "log.md").read_text(encoding="utf-8")
    assert "使用招式" in md
    payload = json.loads((out / "log.json").read_text(encoding="utf-8"))
    assert payload["actions"][0]["label"] == "喷火龙：火之玉"
    assert abs(payload["actions"][0]["winrate"] - 0.5) < 1e-9
