"""task 124：败局解剖分节 —— 终局类型 × 死亡回合分桶 + 每桶抽样回放（红测先行）。

预注册判据（task 124 验收 2）：测试从 game_events 独立重算终局类型/死亡回合
分布，与 --autopsy 分节输出逐项一致。分桶口径写死：≤6 / 7–9 / 10–12 / 13–15 / >15。
"""

from __future__ import annotations

import json

from battlefrontier.cli import main
from battlefrontier.engine.events import GameEvent
from battlefrontier.report import SIM_INTERPRETATION_NOTE
from battlefrontier.report.autopsy import (
    DEATH_BUCKETS,
    REASON_ROWS,
    autopsy_report,
    format_autopsy,
    write_autopsy_packs,
)
from battlefrontier.runner.play import GameResult
from battlefrontier.runner.results_db import ResultsDB


def _ko(seq: int, turn: int, player: int, name: str = "甲") -> GameEvent:
    return GameEvent(seq=seq, turn=turn, phase="main", player=player,
                     kind="knockout", detail={"name": name})


def _over(seq: int, turn: int, reason: str) -> GameEvent:
    return GameEvent(seq=seq, turn=turn, phase="game_over", player=None,
                     kind="game_over", detail={"reason": reason})


def _game(db: ResultsDB, exp_id: int, seed: int, winner: int, turns: int,
          reason: str, loser_ko_turns: tuple[int, ...] = ()) -> None:
    events: list[GameEvent] = []
    seq = 0
    for t in loser_ko_turns:
        events.append(_ko(seq, t, 1 - winner))
        seq += 1
    events.append(_over(seq, turns, reason))
    db.record_game(
        exp_id, seed=seed, first_player=0, deck_a_id="a", deck_b_id="b",
        result=GameResult(winner=winner, is_draw=False, turns=turns,
                          phase="game_over", first_player=0, events=events),
    )


def _seed(tmp_path) -> tuple[ResultsDB, int]:
    """8 局合成实验：覆盖 A 负/B 负、四种终局类型、五个死亡回合分桶、平局/失败排除。"""
    db = ResultsDB(tmp_path / "r.db")
    exp_id = db.start_experiment(name="autopsy", definition_yaml="y",
                                 code_version="c", data_version="d")
    _game(db, exp_id, seed=100, winner=1, turns=6, reason="prizes", loser_ko_turns=(4,))
    _game(db, exp_id, seed=101, winner=1, turns=7, reason="prizes", loser_ko_turns=(5,))
    _game(db, exp_id, seed=102, winner=1, turns=8, reason="deck_out",
          loser_ko_turns=(3,))
    _game(db, exp_id, seed=103, winner=1, turns=12, reason="prizes",
          loser_ko_turns=(8, 11))
    _game(db, exp_id, seed=104, winner=0, turns=14, reason="no_pokemon")
    _game(db, exp_id, seed=105, winner=0, turns=21, reason="prizes",
          loser_ko_turns=(20,))
    _game(db, exp_id, seed=106, winner=0, turns=4, reason="timeout")
    db.record_game(
        exp_id, seed=107, first_player=0, deck_a_id="a", deck_b_id="b",
        result=GameResult(winner=None, is_draw=True, turns=9,
                          phase="game_over", first_player=0,
                          events=[_over(0, 9, "turn_cap")]),
    )
    db.record_error(exp_id, seed=108, deck_a_id="a", deck_b_id="b", error="boom")
    db.finish_experiment(exp_id)
    return db, exp_id


def _recalc(db: ResultsDB, exp_id: int) -> dict[tuple[int, str, int], int]:
    """独立重算：直接从 games + game_events 原始 JSON 重推 (败方, 终局类型, 桶) 计数。"""
    expected: dict[tuple[int, str, int], int] = {}
    for g in db.games(exp_id):
        if g["error"] or g["is_draw"] or g["winner"] is None:
            continue
        loser = 1 - int(g["winner"])
        over_turn = None
        reason = "其他"
        ko_turns = []
        for row in db.game_events(int(g["id"])):
            ev = json.loads(row["event_json"])
            if ev["kind"] == "knockout" and ev["player"] == loser:
                ko_turns.append(int(ev["turn"]))
            elif ev["kind"] == "game_over":
                r = str(ev["detail"].get("reason") or "")
                reason = r if r in ("prizes", "no_pokemon", "deck_out") else "其他"
                over_turn = int(ev["turn"])
        if over_turn is None:
            continue
        death = over_turn if reason == "deck_out" else (max(ko_turns) if ko_turns else over_turn)
        if death <= 6:
            bucket = 0
        elif death <= 9:
            bucket = 1
        elif death <= 12:
            bucket = 2
        elif death <= 15:
            bucket = 3
        else:
            bucket = 4
        key = (loser, reason, bucket)
        expected[key] = expected.get(key, 0) + 1
    return expected


def test_分桶与终局类型_与game_events独立重算逐项一致(tmp_path) -> None:
    db, exp_id = _seed(tmp_path)
    try:
        rep = autopsy_report(db, exp_id)
        expected = _recalc(db, exp_id)
    finally:
        db.close()
    assert rep.decided == 7 and rep.wins_a == 3 and rep.wins_b == 4
    assert len(DEATH_BUCKETS) == 5 and DEATH_BUCKETS == ("≤6", "7–9", "10–12", "13–15", ">15")
    assert REASON_ROWS == ("prizes", "no_pokemon", "deck_out", "其他")
    for loser in (0, 1):
        for reason in REASON_ROWS:
            for bucket in range(len(DEATH_BUCKETS)):
                assert rep.count(loser, reason, bucket) == expected.get(
                    (loser, reason, bucket), 0), (loser, reason, bucket)
    assert rep.count(0, "prizes", 0) == 2   # A 负 prizes 死亡回合 4/5
    assert rep.count(0, "deck_out", 1) == 1  # deck_out 取 game_over turn 8
    assert rep.count(0, "prizes", 2) == 1   # 最后昏厥 turn 11（非最大 knockout 数）
    assert rep.count(1, "no_pokemon", 3) == 1  # 无 knockout 回退 game_over turn 14
    assert rep.count(1, "prizes", 4) == 1
    assert rep.count(1, "其他", 0) == 1     # 未知 reason 归「其他」


def test_分节文本含矩阵头注限定语与样本路径(tmp_path) -> None:
    db, exp_id = _seed(tmp_path)
    try:
        rep = autopsy_report(db, exp_id, sample_n=1)
        paths = write_autopsy_packs(tmp_path / "pack", rep, db)
    finally:
        db.close()
    text = format_autopsy(rep, paths)
    assert "败局解剖" in text
    assert "knockout" in text and "deck_out 类取 game_over 事件 turn" in text
    assert "A 负：4 局" in text and "B 负：3 局" in text
    assert "≤6 | 7–9 | 10–12 | 13–15 | >15" in text
    for reason in REASON_ROWS:
        assert reason in text
    assert SIM_INTERPRETATION_NOTE in text
    bodies = [p["md"].read_text(encoding="utf-8") for p in paths.values()]
    assert any("昏厥" in body for body in bodies)
    assert all("对局包" in body for body in bodies)
    assert any("game-" in line and "log.md" in line for line in text.splitlines())


def test_每桶抽样按种子升序且可调(tmp_path) -> None:
    db, exp_id = _seed(tmp_path)
    try:
        rep1 = autopsy_report(db, exp_id, sample_n=1)
        rep2 = autopsy_report(db, exp_id, sample_n=2)
    finally:
        db.close()
    cell1 = rep1.cell(0, "prizes", 0)
    cell2 = rep2.cell(0, "prizes", 0)
    assert cell1.count == 2 and len(cell1.samples) == 1
    assert [s.seed for s in cell1.samples] == [100]
    assert len(cell2.samples) == 2 and [s.seed for s in cell2.samples] == [100, 101]
    deck = rep1.cell(0, "deck_out", 1)
    assert len(deck.samples) == 1 and deck.samples[0].death_turn == 8


def test_cli_report_autopsy_输出分节并写对局包(tmp_path, capsys) -> None:
    db, exp_id = _seed(tmp_path)
    path = tmp_path / "r.db"
    db.close()
    out = tmp_path / "pack"
    rc = main([
        "report", str(exp_id), "--results", str(path),
        "--autopsy", "--autopsy-sample", "1", "--out", str(out),
    ])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "败局解剖" in printed
    assert "A 负：4 局" in printed and "B 负：3 局" in printed
    assert "prizes" in printed and "deck_out" in printed and "其他" in printed
    assert SIM_INTERPRETATION_NOTE in printed
    sample_md = out / "autopsy" / "game-1" / "log.md"
    assert sample_md.exists()
    assert "昏厥" in sample_md.read_text(encoding="utf-8")
    assert str(sample_md) in printed
