# task 158：CLI 端到端小样例——真实 CLI 入口 → 预检 → 模拟 → SQLite → 报告

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import yaml
from helpers import e2e_decklist, make_e2e_dist

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_e2e_exp(tmp_path: Path) -> Path:
    deck_a = tmp_path / "a.deck.txt"
    deck_b = tmp_path / "b.deck.txt"
    deck_a.write_text(e2e_decklist(), encoding="utf-8")
    deck_b.write_text(e2e_decklist(), encoding="utf-8")
    exp = {
        "name": "e2e-smoke",
        "games": 8,
        "seed_start": 900000,
        "decks": {"a": {"source": "file", "path": str(deck_a)},
                  "b": {"source": "file", "path": str(deck_b)}},
        "agents": {"a": {"type": "heuristic"}, "b": {"type": "heuristic"}},
    }
    p = tmp_path / "e2e.yml"
    p.write_text(yaml.safe_dump(exp, allow_unicode=True), encoding="utf-8")
    return p


def _cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "battlefrontier.cli", *argv],
        capture_output=True, text=True, encoding="utf-8", cwd=REPO_ROOT,
        timeout=300, check=False)


def _game_rows(db_path: Path) -> list[tuple]:
    con = sqlite3.connect(str(db_path))
    try:
        return con.execute(
            "SELECT seed, winner, is_draw, turns, events_hash, error "
            "FROM games ORDER BY seed").fetchall()
    finally:
        con.close()


def test_cli_run_端到端_预检模拟落库报告_与API逐局一致(tmp_path):
    """E2E 决策（task 158 spike 落档）：open_jsonl fixture 后端（jsonl dist
    目录，离线可跑、零真实上游依赖）——CLI run（含 strict 预检）8 局落库，
    与直接 API 调用逐局一致（seed/winner/draw/turns/events_hash）；再经
    report 子命令出报告。串行口径（小样例不重复测 workers 纪律）。"""
    dist = make_e2e_dist(tmp_path)
    (tmp_path / "cards").mkdir()                    # 空 DSL 库：全靠豁免
    exp_yml = _write_e2e_exp(tmp_path)
    results = tmp_path / "cli.db"

    r = _cli("run", str(exp_yml), "--db", str(dist),
             "--results", str(results), "--cards-dir", str(tmp_path / "cards"),
             "--strict-coverage")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[strict-coverage] 通过" in r.stdout       # 预检过闸（纯豁免口径）
    assert "数据版本" in r.stdout and "jsonl_schema=99" in r.stdout

    rows = _game_rows(results)
    assert len(rows) == 8
    assert all(row[5] is None for row in rows)        # 零失败局

    # API 对照（同定义、同种子域、另一结果库）→ 逐局一致
    from battlefrontier.runner.experiment import load_experiment, run_experiment
    defn = load_experiment(str(exp_yml))
    api_results = tmp_path / "api.db"
    run_experiment(defn, str(dist), api_results, cards_dir=tmp_path / "cards")
    assert _game_rows(api_results) == rows

    # 报告子命令：真实 CLI 出口可读结果库
    rep = _cli("report", "1", "--results", str(results))
    assert rep.returncode == 0, rep.stdout + rep.stderr
    assert "e2e-smoke" in rep.stdout
