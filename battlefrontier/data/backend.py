"""task 158：上游数据后端分派——sqlite db 文件 ∥ jsonl dist 目录。

E2E 决策（task 158 spike 实证落档）：ptcgdb `JsonlBackend` 覆盖
get_card / search_cards / snapshots / validate_deck / stats_usage 全接口，
jsonl dist fixture 后端可行——`--db` 传目录即开 jsonl（真实上游仍为
sqlite 文件，行为零变化）。探针的 v_tournament_weights 裸 SQL 维持
sqlite-only（场数据管道不走路径分派以外的口径）。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def open_backend(path: str | Path):
    """目录 = jsonl dist 导出；文件 = sqlite db（对齐 sdk 双后端契约）。"""
    from ptcgdb.sdk import open_db, open_jsonl

    return open_jsonl(path) if Path(path).is_dir() else open_db(path)


def backend_data_version(path: str | Path, snapshot_date: str | None = None) -> str:
    """数据版本锚点：sqlite = 快照日期 + user_version；jsonl = 快照日期 + schema_version。

    与 experiment._data_version 同口径族（其 sqlite 分支委托本函数）。
    """
    db = open_backend(path)
    try:
        snapshots = db.snapshots("standard")
        date = snapshot_date or (snapshots[-1].effective_from if snapshots
                                 else "unknown")
        schema = getattr(db, "schema_version", None)
    finally:
        db.close()
    if Path(path).is_dir():
        return f"{date} (jsonl_schema={schema})"
    try:
        # 主库只读（FR-10）：PRAGMA 走只读 URI 连接
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            uv = con.execute("PRAGMA user_version").fetchone()[0]
        finally:
            con.close()
        return f"{date} (user_version={uv})"
    except sqlite3.Error:
        return str(date)
