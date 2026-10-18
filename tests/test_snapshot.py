"""task 052 WP3：决策点快照采集验收测试（D-M11-5）。

快照采集（序列化 GameState + 教师结构化 Action 往返 / 只落教师实际搜索的
决策点）/ 开关默认关 = 行为零变化（events_hash 纪律）/ 产线落盘（header +
snapshot 行，种子区间 matrix 惯例，串并一致）/ 载入校验（不猜）。
"""

import json
from pathlib import Path

import pytest
import yaml
from helpers import deck60, energy, engine_at, main_state

from battlefrontier.agent.mcts import Consideration, MCTSAgent
from battlefrontier.agent.snapshot import SnapshotCollector
from battlefrontier.cli import main as cli_main
from battlefrontier.engine.actions import Action
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import GameState
from battlefrontier.runner import snapshot as snapshot_mod
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


# ── 增量落盘与断点续采（pair_start）───────────────────────────


def test_增量落盘_对完成即写_串行(tmp_path, monkeypatch):
    """对收满 games_per_pair 局立即写盘：第二对首局被请求时，第一对文件已完整落盘。"""
    prepared = [_stub_pair(0), _stub_pair(1)]
    out = tmp_path / "out"
    checked = []

    def fake_worker(payload):
        pair_index = payload["pair_index"]
        if pair_index == 1 and not checked:
            f0 = out / "pair-0-测试A0x测试B0.jsonl"
            assert f0.exists()  # 第一对完成即写，不等到全部局结束
            lines = [json.loads(x) for x in
                     f0.read_text(encoding="utf-8").splitlines() if x.strip()]
            assert lines[0]["record"] == "header"
            assert [r["seed"] for r in lines[1:]] == [410000, 410001]
            assert not (out / "pair-1-测试A1x测试B1.jsonl").exists()
            checked.append(True)
        return payload["seed"], pair_index, [{"seed": payload["seed"]}], None

    monkeypatch.setattr(snapshot_mod, "_run_one_snapshot", fake_worker)
    summaries = run_collect_snapshots(
        prepared, games_per_pair=2, seed_start=410000, out_dir=out, workers=1,
        teacher={"worlds": 1, "iterations": 2})
    assert checked == [True]  # 第二对确实被处理过（断言分支真实执行）
    assert [(s.pair_index, s.games, s.rows, s.failed) for s in summaries] == \
        [(0, 2, 2, 0), (1, 2, 2, 0)]


def test_pair_start_种子映射不变(tmp_path, monkeypatch):
    """pair_start=1：首对首种子 = seed_start + 1×games_per_pair（assignment.index 锚定）。"""
    prepared = [_stub_pair(0), _stub_pair(1), _stub_pair(2)]
    payloads_seen = []

    def fake_worker(payload):
        payloads_seen.append((payload["pair_index"], payload["seed"]))
        return payload["seed"], payload["pair_index"], [], None

    monkeypatch.setattr(snapshot_mod, "_run_one_snapshot", fake_worker)
    summaries = run_collect_snapshots(
        prepared, games_per_pair=2, seed_start=410000, out_dir=tmp_path / "out",
        workers=1, teacher={"worlds": 1, "iterations": 2}, pair_start=1)
    assert payloads_seen == [(1, 410002), (1, 410003), (2, 410004), (2, 410005)]
    assert [s.pair_index for s in summaries] == [1, 2]


def test_pair_start_断点续采_拼接字节全等(tmp_path):
    """pair_start=1 续采的 pair-1 文件与全量跑同文件逐字节全等；pair-0 不重复产出。"""
    prepared = [_stub_pair(0), _stub_pair(1)]
    kw = {"games_per_pair": 2, "seed_start": 410000, "workers": 1,
          "teacher": {"worlds": 1, "iterations": 2, "rollout_turn_cap": 50}}
    run_collect_snapshots(prepared, out_dir=tmp_path / "full", pair_start=0, **kw)
    summaries = run_collect_snapshots(prepared, out_dir=tmp_path / "resume",
                                      pair_start=1, **kw)
    assert [s.pair_index for s in summaries] == [1]
    assert not (tmp_path / "resume" / "pair-0-测试A0x测试B0.jsonl").exists()
    f1 = tmp_path / "resume" / "pair-1-测试A1x测试B1.jsonl"
    assert f1.read_bytes() == \
        (tmp_path / "full" / "pair-1-测试A1x测试B1.jsonl").read_bytes()
    header = json.loads(f1.read_text(encoding="utf-8").splitlines()[0])
    assert (header["seed_start"], header["seed_end"]) == (410002, 410003)


def test_pair_start_越界负数_显式报错(tmp_path):
    """pair_start 合法区间 [0, len(prepared))，越界/负数显式报错（不猜）。"""
    prepared = [_stub_pair(0)]
    kw = {"games_per_pair": 1, "seed_start": 410000, "out_dir": tmp_path / "out",
          "workers": 1, "teacher": {"worlds": 1, "iterations": 2}}
    with pytest.raises(ValueError, match="pair_start"):
        run_collect_snapshots(prepared, pair_start=-1, **kw)
    with pytest.raises(ValueError, match="pair_start"):
        run_collect_snapshots(prepared, pair_start=1, **kw)


# ── CLI（pair_start）──────────────────────────────────────────

_DB_PATH = Path("C:/Vibe Project/Pokearena/data/ptcg-cn.db")


def test_cli_pair_start_负数_退出码1(tmp_path):
    """--pair-start 负数：CLI 层显式报错退出码 1（不装载卡池，不猜）。"""
    rc = cli_main(["collect-snapshots", "--pool", "x.yml",
                   "--games-per-pair", "1", "--seed-start", "410000",
                   "--out", str(tmp_path), "--pair-start", "-1"])
    assert rc == 1


def _mini_pool(tmp_path, n_decks: int = 3) -> Path:
    full = yaml.safe_load(Path("config/target-pool.v1.yml").read_text(encoding="utf-8"))
    mini = dict(full, decks=full["decks"][:n_decks])
    pool_path = tmp_path / "pool.yml"
    pool_path.write_text(yaml.safe_dump(mini, allow_unicode=True), encoding="utf-8")
    return pool_path


@pytest.mark.skipif(not _DB_PATH.exists(), reason="本机无 ptcg-cn.db")
def test_cli_pair_start_越界_退出码1(tmp_path):
    """3 配对迷你池 --pair-start 3（== len(prepared)）：越界显式报错退出码 1。"""
    pool_path = _mini_pool(tmp_path)
    rc = cli_main(["collect-snapshots", "--pool", str(pool_path),
                   "--games-per-pair", "1", "--seed-start", "420000",
                   "--out", str(tmp_path / "out"), "--workers", "1",
                   "--worlds", "1", "--iterations", "2",
                   "--db", str(_DB_PATH), "--pair-start", "3"])
    assert rc == 1
    out = tmp_path / "out"
    assert not out.exists() or not list(out.glob("pair-*.jsonl"))


@pytest.mark.skipif(not _DB_PATH.exists(), reason="本机无 ptcg-cn.db")
def test_cli_pair_start_续采_真实池(tmp_path):
    """3 配对迷你池 --pair-start 2：只产 pair-2 文件，header 种子区间 = [S+2, S+2]。"""
    pool_path = _mini_pool(tmp_path)
    out = tmp_path / "out"
    rc = cli_main(["collect-snapshots", "--pool", str(pool_path),
                   "--games-per-pair", "1", "--seed-start", "420000",
                   "--out", str(out), "--workers", "1",
                   "--worlds", "1", "--iterations", "2",
                   "--db", str(_DB_PATH), "--pair-start", "2"])
    assert rc == 0
    files = list(out.glob("pair-*.jsonl"))
    assert len(files) == 1 and files[0].name.startswith("pair-2-")
    header = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert (header["pair_index"], header["seed_start"], header["seed_end"]) == \
        (2, 420002, 420002)
