"""task 151 WP1：混编种群快照产线验收测试（预注册 2026-11-20 冻结）。

混编规则确定性（offset%2 交替指派 {MCTS, 启发式}）/ 行级 agent 标签与
行动方一致 / 教师参数（evaluator_path / eval_cutoff_turns）透传到 MCTSAgent /
混编产物经 task 052 loader + agreement 消费路径兼容 / Pool maxtasksperchild
存在性锚 / 缺省零变化（无新 flags = 现状 payload/header/行格式）。
"""

import json
from types import SimpleNamespace

from helpers import deck60

from battlefrontier.cli import main as cli_main
from battlefrontier.runner import snapshot as snapshot_mod
from battlefrontier.runner.agreement import run_agreement_file
from battlefrontier.runner.collect import MAXTASKS_PER_CHILD
from battlefrontier.runner.snapshot import (
    SNAPSHOT_FORMAT,
    _run_one_snapshot,
    load_snapshot_file,
    run_collect_snapshots,
    run_collect_snapshots_pool,  # noqa: F401
)
from battlefrontier.tune.fitness import PairAssignment, PreparedPair

_TINY_TEACHER = {"worlds": 1, "iterations": 2, "rollout_turn_cap": 50}
_SEED_START = 430000


def _stub_pair(index: int) -> PreparedPair:
    return PreparedPair(
        assignment=PairAssignment(index=index, archetype_a=f"种群A{index}",
                                  archetype_b=f"种群B{index}",
                                  deck_id_a="stub:a", deck_id_b="stub:b"),
        deck_a=deck60(), deck_b=deck60(), card_effects={}, warnings=())


def _mix_payload(seed: int, pair_index: int = 0, games_per_pair: int = 2,
                 teacher: dict | None = None) -> dict:
    pair = _stub_pair(pair_index)
    return {
        "deck_a": [c.model_dump(mode="json") for c in pair.deck_a],
        "deck_b": [c.model_dump(mode="json") for c in pair.deck_b],
        "card_effects": [],
        "seed": seed,
        "pair_index": pair_index,
        "teacher": dict(teacher or _TINY_TEACHER),
        "mix": True,
        "games_per_pair": games_per_pair,
        "seed_start": _SEED_START,
    }


# ── 混编规则确定性 ──────────────────────────────────────────


def test_混编_offset偶_MCTS在side0_奇_翻转():
    """offset%2 交替指派：偶 offset → side0=MCTS；奇 offset → side1=MCTS。"""
    _even_seed, _i, even_rows, even_err = _run_one_snapshot(
        _mix_payload(_SEED_START))  # offset 0（偶）
    _odd_seed, _i, odd_rows, odd_err = _run_one_snapshot(
        _mix_payload(_SEED_START + 1))  # offset 1（奇）
    assert even_err is None and odd_err is None
    assert even_rows and odd_rows
    for row in even_rows:
        assert (row["agent"] == "mcts") == (row["player"] == 0)
    for row in odd_rows:
        assert (row["agent"] == "mcts") == (row["player"] == 1)
    # 两局各自双标签都出现（启发式侧决策点经 record_players 入流）
    assert {r["agent"] for r in even_rows} == {"mcts", "heuristic"}
    assert {r["agent"] for r in odd_rows} == {"mcts", "heuristic"}


def test_混编同seed同指派_产物逐字节一致():
    payload = _mix_payload(_SEED_START + 2)  # offset 2（偶，同 offset 0 指派）
    _s1, _i1, rows1, err1 = _run_one_snapshot(dict(payload))
    _s2, _i2, rows2, err2 = _run_one_snapshot(dict(payload))
    assert err1 is None and err2 is None
    assert json.dumps(rows1, ensure_ascii=False, sort_keys=True) == \
        json.dumps(rows2, ensure_ascii=False, sort_keys=True)
    # offset 2 与 offset 0 同指派（偶）：side0 行均为 mcts
    assert all((r["agent"] == "mcts") == (r["player"] == 0) for r in rows1)


def test_混编payload缺键_显式报错():
    payload = _mix_payload(_SEED_START)
    del payload["games_per_pair"]
    _seed, _i, rows, error = _run_one_snapshot(payload)
    assert rows is None and error is not None and "games_per_pair" in error


# ── 教师参数透传 ────────────────────────────────────────────


def test_教师evaluator与cutoff透传_到达MCTSAgent构造(monkeypatch):
    """teacher dict 全量键经 **t 到 MCTSAgent（构造签名含 eval_cutoff_turns/
    evaluator_path，mcts.py:110）；spy 包装真实构造，断言路径真实打通。"""
    captured: list[dict] = []
    real_ctor = snapshot_mod.MCTSAgent

    def spy(rng, **kwargs):
        captured.append(kwargs)
        return real_ctor(rng, **kwargs)

    monkeypatch.setattr(snapshot_mod, "MCTSAgent", spy)
    payload = _mix_payload(_SEED_START + 3, teacher={
        "worlds": 1, "iterations": 2, "rollout_turn_cap": 50,
        "eval_cutoff_turns": 10, "evaluator_path": "models/eval-linear-v1.json"})
    _seed, _i, rows, error = _run_one_snapshot(payload)
    assert error is None and rows
    assert captured, "MCTSAgent 未被构造（混编局内必有 MCTS 侧）"
    for kwargs in captured:
        assert kwargs["eval_cutoff_turns"] == 10
        assert kwargs["evaluator_path"] == "models/eval-linear-v1.json"


def test_cli_新flags接线_注入teacher与mix(monkeypatch, tmp_path, capsys):
    """--evaluator-path/--eval-cutoff-turns 注入 teacher dict；--mix-population
    透传 mix=True——与 --mix-population 相互独立，缺省 None = 不注入。"""
    captured: list[dict] = []

    def fake_pool(pool_path, db_path, games_per_pair, seed_start, out_dir, **kw):
        captured.append(kw)
        return [], []

    monkeypatch.setattr(snapshot_mod, "run_collect_snapshots_pool", fake_pool)
    base = ["collect-snapshots", "--pool", "x.yml", "--games-per-pair", "1",
            "--seed-start", str(_SEED_START), "--out", str(tmp_path)]
    rc = cli_main(base + ["--mix-population", "--evaluator-path", "models/e.json",
                          "--eval-cutoff-turns", "10"])
    assert rc == 0
    assert captured[0]["mix"] is True
    assert captured[0]["teacher"]["evaluator_path"] == "models/e.json"
    assert captured[0]["teacher"]["eval_cutoff_turns"] == 10
    # 缺省：无注入、mix False（现状零变化）
    captured.clear()
    rc = cli_main(base)
    assert rc == 0
    assert captured[0]["mix"] is False
    assert set(captured[0]["teacher"]) == {"worlds", "iterations",
                                           "rollout_turn_cap"}


# ── 格式兼容（task 052 loader + agreement 消费路径）────────────


def test_混编产物_loader与agreement兼容(tmp_path):
    """1 对 × 2 局混编产物：load_snapshot_file 通过、format 不变、header 含
    mix:true、行含 agent 键；task 052 agreement 消费路径不报错。"""
    (s,) = run_collect_snapshots([_stub_pair(0)], games_per_pair=2,
                                 seed_start=_SEED_START, out_dir=tmp_path,
                                 workers=1, teacher=_TINY_TEACHER, mix=True)
    snap = load_snapshot_file(tmp_path / s.filename)
    assert snap.header["format"] == SNAPSHOT_FORMAT
    assert snap.header["mix"] is True
    assert snap.rows and all(r["record"] == "snapshot" for r in snap.rows)
    agents = {r["agent"] for r in snap.rows}
    assert agents == {"mcts", "heuristic"}
    # 行其余键与 v1 逐字兼容（仅多 agent 一键）
    for row in snap.rows:
        assert set(row) == {"record", "seed", "turn", "phase", "player",
                            "action_kind", "n_legal", "action", "state",
                            "agent"}
    report = run_agreement_file(tmp_path / s.filename, dict(_TINY_TEACHER))
    assert report["snapshots_total"] == len(snap.rows)
    assert report["denominator"] >= 1


def test_混编串并一致_字节全等(tmp_path):
    prepared = [_stub_pair(0)]
    kw = {"games_per_pair": 2, "seed_start": _SEED_START,
          "teacher": _TINY_TEACHER, "mix": True}
    run_collect_snapshots(prepared, out_dir=tmp_path / "s", workers=1, **kw)
    run_collect_snapshots(prepared, out_dir=tmp_path / "p", workers=2, **kw)
    name = "pair-0-种群A0x种群B0.jsonl"
    assert (tmp_path / "s" / name).read_bytes() == \
        (tmp_path / "p" / name).read_bytes()


# ── maxtasksperchild 存在性锚 ───────────────────────────────


def test_Pool构造带maxtasksperchild(monkeypatch, tmp_path):
    """spawn Pool 构造带 maxtasksperchild=MAXTASKS_PER_CHILD（task 155 内存
    棘轮修复锚）；fake ctx 拦截构造参数，imap 退化为串行执行（真 worker）。"""
    pool_kwargs: dict = {}

    class FakePool:
        def __init__(self, processes, **kwargs):
            pool_kwargs.update(kwargs)
            pool_kwargs["processes"] = processes

        def imap(self, func, payloads):
            return (func(p) for p in payloads)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake_mp = SimpleNamespace(
        get_context=lambda _name: SimpleNamespace(
            Pool=lambda processes, **kw: FakePool(processes, **kw)))
    monkeypatch.setattr(snapshot_mod, "mp", fake_mp)
    run_collect_snapshots([_stub_pair(0)], games_per_pair=1,
                          seed_start=_SEED_START, out_dir=tmp_path / "o",
                          workers=2, teacher=_TINY_TEACHER, mix=True)
    assert pool_kwargs["maxtasksperchild"] == MAXTASKS_PER_CHILD
    assert pool_kwargs["processes"] == 2


# ── 缺省零变化回归 ──────────────────────────────────────────


def test_缺省无mix_payload与header无新键(tmp_path, monkeypatch):
    """不带混编参数：payload 无 mix/games_per_pair/seed_start，teacher 缺省
    2×50；header 无 mix 键。"""
    payloads: list[dict] = []

    def fake_worker(payload):
        payloads.append(dict(payload))
        return (payload["seed"], payload["pair_index"],
                [{"seed": payload["seed"], "turn": 1, "phase": "main",
                  "player": 0, "action_kind": "end_turn", "n_legal": 2,
                  "action": {"kind": "end_turn", "attack_index": None,
                             "card_hand_index": None, "bench_index": None,
                             "choices": [], "tool_bench_index": None},
                  "state": {}}], None)

    monkeypatch.setattr(snapshot_mod, "_run_one_snapshot", fake_worker)
    (s,) = run_collect_snapshots([_stub_pair(0)], games_per_pair=1,
                                 seed_start=_SEED_START, out_dir=tmp_path / "o",
                                 workers=1)
    assert len(payloads) == 1
    assert payloads[0]["teacher"] == {"worlds": 2, "iterations": 50}
    assert "mix" not in payloads[0]
    assert "games_per_pair" not in payloads[0]
    assert "seed_start" not in payloads[0]
    header = json.loads(
        (tmp_path / "o" / s.filename).read_text(encoding="utf-8").splitlines()[0])
    assert "mix" not in header
    assert header["teacher"] == {"worlds": 2, "iterations": 50}


def test_非混编产物行无agent键(tmp_path):
    (s,) = run_collect_snapshots([_stub_pair(0)], games_per_pair=1,
                                 seed_start=_SEED_START, out_dir=tmp_path / "o",
                                 workers=1, teacher=_TINY_TEACHER)
    lines = [json.loads(x) for x in
             (tmp_path / "o" / s.filename).read_text(encoding="utf-8").splitlines()
             if x.strip()]
    assert "mix" not in lines[0]
    assert all("agent" not in row for row in lines[1:])
    assert set(lines[1]) == {"record", "seed", "turn", "phase", "player",
                             "action_kind", "n_legal", "action", "state"}
