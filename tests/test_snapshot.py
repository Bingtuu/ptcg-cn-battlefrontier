"""task 052 WP3：决策点快照采集验收测试（D-M11-5）。

快照采集（序列化 GameState + 教师结构化 Action 往返 / 只落教师实际搜索的
决策点）/ 开关默认关 = 行为零变化（events_hash 纪律）/ 产线落盘（header +
snapshot 行，种子区间 matrix 惯例，串并一致）/ 载入校验（不猜）。
"""

import json

import pytest
from helpers import deck60, energy, engine_at, main_state

from battlefrontier.agent.mcts import Consideration, MCTSAgent
from battlefrontier.agent.snapshot import SnapshotCollector
from battlefrontier.engine.actions import Action
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import GameState
from battlefrontier.runner.experiment import _unique_docs
from battlefrontier.runner.play import play_game
from battlefrontier.runner.snapshot import (
    SNAPSHOT_FORMAT,
    _run_one_snapshot,
    load_snapshot_file,
    run_collect_snapshots,
    snapshot_state,
    teacher_action,
)
from battlefrontier.tune.fitness import PairAssignment, PreparedPair


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"测试A{index}",
                                  archetype_b=f"测试B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


def _mcts_mirror(seed: int, snapshot_collector=None):
    agents = [MCTSAgent(RandomSource(seed), worlds=1, iterations=2),
              MCTSAgent(RandomSource(seed + 999), worlds=1, iterations=2)]
    return play_game(deck60(), deck60(), seed=seed, agents=agents,
                     snapshot_collector=snapshot_collector)


_FAKE_CONSIDERATION = Consideration(
    turn=2, phase="main", player=0, total_visits=2,
    considered=((Action(kind="end_turn"), 2),), chosen=Action(kind="end_turn"))


# ── collector 钩子 ──────────────────────────────────────────


def test_collector_仅落教师实际搜索的决策点():
    """consideration=None（早退 / 非搜索 agent）不记录；非 None 才落快照。"""
    engine = engine_at(main_state())
    c = SnapshotCollector()
    c.on_decision(engine=engine, player=0, action=Action(kind="end_turn"),
                  consideration=None, n_legal=1)
    assert c.rows == []
    c.on_decision(engine=engine, player=0, action=Action(kind="end_turn"),
                  consideration=_FAKE_CONSIDERATION, n_legal=5)
    assert len(c.rows) == 1
    row = c.rows[0]
    assert set(row) == {"turn", "phase", "player", "action_kind", "n_legal",
                        "action", "state"}
    assert (row["turn"], row["phase"], row["player"]) == (2, "main", 0)
    assert row["action_kind"] == "end_turn" and row["n_legal"] == 5


def test_collector_不消费随机源_同种子hash全等():
    """同种子有无 snapshot_collector 两跑：events_hash 逐值全等（行为零变化）。"""
    plain = _mcts_mirror(21)
    snapped = _mcts_mirror(21, snapshot_collector=SnapshotCollector())
    assert plain.events_hash == snapped.events_hash
    assert (plain.winner, plain.is_draw, plain.turns) == \
        (snapped.winner, snapped.is_draw, snapped.turns)
    assert plain.snapshot_rows is None
    assert snapped.snapshot_rows is not None and snapped.snapshot_rows


def test_snapshot_默认关_行为零变化():
    """不传 snapshot_collector（默认）→ snapshot_rows 为 None。"""
    assert _mcts_mirror(23).snapshot_rows is None


def test_snapshot行_决策点结构与唯一合法行动剔除():
    """每行 n_legal > 1（mcts 早退口径）；state / action 可往返重建。"""
    result = _mcts_mirror(25, snapshot_collector=SnapshotCollector())
    rows = result.snapshot_rows
    assert rows
    for row in rows:
        assert row["n_legal"] > 1
        state = snapshot_state(row)
        assert isinstance(state, GameState)
        assert state.turn == row["turn"] and state.phase == row["phase"]
        action = teacher_action(row)
        assert isinstance(action, Action) and action.kind == row["action_kind"]
        # 序列化往返全等（test_state / test_chooser 先例口径）
        assert GameState.model_validate(
            json.loads(json.dumps(row["state"]))) == state
        assert action == teacher_action(
            json.loads(json.dumps(row)))


# ── worker ──────────────────────────────────────────────────


def _snapshot_payload(seed: int, pair_index: int = 0, deck_a=None) -> dict:
    pair = _stub_pair(pair_index)
    return {
        "deck_a": [c.model_dump(mode="json") for c in (deck_a or pair.deck_a)],
        "deck_b": [c.model_dump(mode="json") for c in pair.deck_b],
        "card_effects": [d.model_dump(mode="json")
                         for d in _unique_docs(pair.card_effects.values())],
        "seed": seed,
        "pair_index": pair_index,
        "teacher": {"worlds": 1, "iterations": 2, "rollout_turn_cap": 50},
    }


def test_worker_正常局_返回快照与种子():
    seed, pair_index, rows, error = _run_one_snapshot(_snapshot_payload(410000))
    assert error is None and rows is not None and rows
    assert seed == 410000 and pair_index == 0
    assert all(r["seed"] == 410000 for r in rows)


def test_worker_失败局_剔除并上报():
    """非法卡组（无基础宝可梦）→ rows=None + 错误文本（不抛出、不猜）。"""
    _seed, _idx, rows, error = _run_one_snapshot(
        _snapshot_payload(410001, deck_a=[energy()] * 60))
    assert rows is None and error is not None
    assert "基础宝可梦" in error


# ── 批量驱动与落盘 ───────────────────────────────────────────


def test_run_collect_snapshots_落盘结构与种子区间(tmp_path):
    prepared = [_stub_pair(0), _stub_pair(1)]
    out = tmp_path / "out"
    summaries = run_collect_snapshots(
        prepared, games_per_pair=2, seed_start=410000, out_dir=out, workers=1,
        teacher={"worlds": 1, "iterations": 2, "rollout_turn_cap": 50})
    assert [s.filename for s in summaries] == [
        "pair-0-测试A0x测试B0.jsonl", "pair-1-测试A1x测试B1.jsonl"]
    for s in summaries:
        lines = [json.loads(line)
                 for line in (out / s.filename).read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        header, rows = lines[0], lines[1:]
        assert header["record"] == "header" and header["format"] == SNAPSHOT_FORMAT
        assert header["pair_index"] == s.pair_index
        assert header["teacher"] == {"worlds": 1, "iterations": 2,
                                     "rollout_turn_cap": 50}
        assert len(header["deck_a"]) == 60 and len(header["deck_b"]) == 60
        lo = 410000 + s.pair_index * 2
        assert (header["seed_start"], header["seed_end"]) == (lo, lo + 1)
        assert len(rows) == s.rows and s.rows > 0
        for row in rows:
            assert row["record"] == "snapshot"
            assert lo <= row["seed"] < lo + 2
            assert set(row) == {"record", "seed", "turn", "phase", "player",
                                "action_kind", "n_legal", "action", "state"}
            # 行内禁止非确定量（无墙钟/时间戳字段）
            assert not any("time" in k or "wall" in k for k in row)


def test_run_collect_snapshots_串并一致_字节全等(tmp_path):
    prepared = [_stub_pair(0)]
    kw = {"games_per_pair": 2, "seed_start": 410000,
          "teacher": {"worlds": 1, "iterations": 2, "rollout_turn_cap": 50}}
    run_collect_snapshots(prepared, out_dir=tmp_path / "s", workers=1, **kw)
    run_collect_snapshots(prepared, out_dir=tmp_path / "p", workers=2, **kw)
    assert (tmp_path / "s" / "pair-0-测试A0x测试B0.jsonl").read_bytes() == \
        (tmp_path / "p" / "pair-0-测试A0x测试B0.jsonl").read_bytes()


def test_load_snapshot_file_校验不猜(tmp_path):
    prepared = [_stub_pair(0)]
    out = tmp_path / "out"
    (s,) = run_collect_snapshots(prepared, games_per_pair=1, seed_start=410000,
                                 out_dir=out, workers=1,
                                 teacher={"worlds": 1, "iterations": 2,
                                          "rollout_turn_cap": 50})
    snap = load_snapshot_file(out / s.filename)
    assert snap.header["pair_index"] == 0
    assert all(r["record"] == "snapshot" for r in snap.rows)

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="为空"):
        load_snapshot_file(empty)
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"record": "snapshot"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        load_snapshot_file(bad)
