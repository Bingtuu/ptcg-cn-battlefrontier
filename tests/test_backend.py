# task 158：上游数据后端分派（sqlite db 文件 ∥ jsonl dist 目录）

from __future__ import annotations

from helpers import make_e2e_dist

from battlefrontier.data.backend import backend_data_version, open_backend


def test_open_backend_目录走jsonl_文件走sqlite(tmp_path):
    from ptcgdb.sdk import DbBackend, JsonlBackend

    dist = make_e2e_dist(tmp_path)
    db = open_backend(dist)
    try:
        assert isinstance(db, JsonlBackend)
        assert db.get_card("TST-001").name_full == "测试苗蛙"
    finally:
        db.close()

    sqlite_path = tmp_path / "up.db"
    import sqlite3
    con = sqlite3.connect(sqlite_path)
    con.close()
    db = open_backend(sqlite_path)
    try:
        assert isinstance(db, DbBackend)
    finally:
        db.close()


def test_backend_data_version_jsonl_锚schema版本(tmp_path):
    dist = make_e2e_dist(tmp_path)
    v = backend_data_version(dist)
    assert "2020-01-01" in v and "99" in v


def test_backend_data_version_sqlite_锚user_version(tmp_path, monkeypatch):
    import sqlite3

    import battlefrontier.data.backend as backend_mod

    p = tmp_path / "up.db"
    con = sqlite3.connect(p)
    con.execute("PRAGMA user_version=7")
    con.close()

    class _Stub:
        def snapshots(self, fmt):
            return []

        schema_version = None

        def close(self):
            pass

    monkeypatch.setattr(backend_mod, "open_backend", lambda path: _Stub())
    v = backend_mod.backend_data_version(str(p))
    assert "user_version=7" in v
