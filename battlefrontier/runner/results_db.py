"""结果库（PRD §8.3，FR-10 契约）：独立 SQLite WAL，三层表。

- experiments：实验定义快照 + 代码/数据版本 + 状态
- games：每局元数据（胜负/回合数/先后手/种子/双方卡组 id）
- game_events：单局完整事件流（回放与 M4 决策聚合共用一份数据）

主库（ptcg-cn.db）只读，关联经 card_id / name_group / 快照 id——本库不复制卡牌数据。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from battlefrontier.runner.play import GameResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  definition_yaml TEXT NOT NULL,
  code_version TEXT NOT NULL,
  data_version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS games (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  experiment_id INTEGER NOT NULL REFERENCES experiments(id),
  seed INTEGER NOT NULL,
  first_player INTEGER NOT NULL,
  winner INTEGER,
  is_draw INTEGER NOT NULL,
  turns INTEGER NOT NULL,
  events_hash TEXT NOT NULL,
  deck_a_id TEXT NOT NULL,
  deck_b_id TEXT NOT NULL,
  error TEXT
);
CREATE TABLE IF NOT EXISTS game_events (
  game_id INTEGER NOT NULL REFERENCES games(id),
  seq INTEGER NOT NULL,
  event_json TEXT NOT NULL,
  PRIMARY KEY (game_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_games_experiment ON games(experiment_id);
"""


class ResultsDB:
    """结果库连接（WAL；每局增量落库）。"""

    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    def start_experiment(self, *, name: str, definition_yaml: str,
                         code_version: str, data_version: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO experiments (name, definition_yaml, code_version, data_version)"
            " VALUES (?, ?, ?, ?)",
            (name, definition_yaml, code_version, data_version))
        self._conn.commit()
        return int(cur.lastrowid)

    def record_game(self, experiment_id: int, *, seed: int, first_player: int,
                    result: GameResult, deck_a_id: str, deck_b_id: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO games (experiment_id, seed, first_player, winner, is_draw,"
            " turns, events_hash, deck_a_id, deck_b_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (experiment_id, seed, first_player, result.winner, int(result.is_draw),
             result.turns, result.events_hash, deck_a_id, deck_b_id))
        game_id = int(cur.lastrowid)
        self._conn.executemany(
            "INSERT INTO game_events (game_id, seq, event_json) VALUES (?, ?, ?)",
            [(game_id, seq, json.dumps(ev.model_dump(mode="json"), ensure_ascii=False,
                                       sort_keys=True))
             for seq, ev in enumerate(result.events)])
        self._conn.commit()
        return game_id

    def record_error(self, experiment_id: int, *, seed: int, deck_a_id: str,
                     deck_b_id: str, error: str) -> int:
        """失败局落库（不猜纪律：DSL 显式 DslError 等异常不掩盖，记 error 列继续实验）。"""
        cur = self._conn.execute(
            "INSERT INTO games (experiment_id, seed, first_player, winner, is_draw,"
            " turns, events_hash, deck_a_id, deck_b_id, error)"
            " VALUES (?, ?, -1, NULL, 0, 0, '', ?, ?, ?)",
            (experiment_id, seed, deck_a_id, deck_b_id, error))
        self._conn.commit()
        return int(cur.lastrowid)

    def finish_experiment(self, experiment_id: int, status: str = "done") -> None:
        self._conn.execute(
            "UPDATE experiments SET status=? WHERE id=?", (status, experiment_id))
        self._conn.commit()

    def games(self, experiment_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM games WHERE experiment_id=? ORDER BY seed", (experiment_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    def game_events(self, game_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM game_events WHERE game_id=? ORDER BY seq", (game_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()
