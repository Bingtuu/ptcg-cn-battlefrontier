# task 156：bfsim field-snap——场快照导出 + 就绪探针测试

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from battlefrontier.runner.field_snap import (
    STATS_USAGE_KW,
    export_field_snap,
    probe_field_freshness,
)


class _StubRow:
    def __init__(self, d: dict) -> None:
        self._d = d

    def model_dump(self, mode: str = "json") -> dict:
        return dict(self._d)


class _StubRes:
    def __init__(self, data: list[dict], meta: dict) -> None:
        self.data = [_StubRow(d) for d in data]
        self.meta = meta


class _StubDb:
    def __init__(self, res: _StubRes) -> None:
        self._res = res
        self.calls: dict = {}
        self.closed = False

    def stats_usage(self, **kw):
        self.calls = kw
        return self._res

    def close(self) -> None:
        self.closed = True


def _make_upstream(tmp_path: Path, rows: list[dict], meta: dict) -> tuple[str, _StubDb]:
    db_path = str(tmp_path / "upstream.db")
    stub = _StubDb(_StubRes(rows, meta))
    return db_path, stub


def test_export_结构与口径逐键锁定(tmp_path, monkeypatch):
    import battlefrontier.runner.field_snap as fs

    db_path, stub = _make_upstream(tmp_path, [{"group_key": "甲", "value": 0.5}],
                                   {"n_tournaments": 19, "date_from": "2026-11-01",
                                    "date_to": "2026-11-15"})
    monkeypatch.setattr(fs, "open_db", lambda p: stub)

    out = tmp_path / "snap.json"
    snap = export_field_snap(db_path, "2026-11-01", "2026-11-15", out,
                             as_of="2026-11-22")

    # 调用口径与 t152 探针逐键一致（除窗口参数外全部钉死）
    assert stub.calls["date_from"] == "2026-11-01"
    assert stub.calls["date_to"] == "2026-11-15"
    for k, v in STATS_USAGE_KW.items():
        assert stub.calls[k] == v, f"stats_usage 口径漂移: {k}"
    assert stub.closed

    written = json.loads(out.read_text(encoding="utf-8"))
    assert written == snap
    assert written["meta"]["n_tournaments"] == 19
    assert written["meta"]["as_of"] == "2026-11-22"  # 钉运行日
    assert written["data"] == [{"group_key": "甲", "value": 0.5}]


def test_export_as_of_缺省取当日(tmp_path, monkeypatch):
    import battlefrontier.runner.field_snap as fs

    db_path, stub = _make_upstream(tmp_path, [], {"n_tournaments": 0})
    monkeypatch.setattr(fs, "open_db", lambda p: stub)
    out = tmp_path / "snap.json"
    snap = export_field_snap(db_path, "2026-11-01", "2026-11-15", out)
    assert snap["meta"]["as_of"] == fs.today_iso()


def _write_weights_db(path: Path, dates: list[tuple[str, str, str]]) -> str:
    """造上游 v_tournament_weights 最小表：(date, basis, division) 行。"""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE v_tournament_weights (tournament_id INTEGER, date TEXT,"
                " basis TEXT, division TEXT, weight REAL)")
    for i, (d, b, div) in enumerate(dates):
        con.execute("INSERT INTO v_tournament_weights VALUES (?,?,?,?,?)",
                    (i, d, b, div, 1.0))
    con.commit()
    con.close()
    return str(path)


def test_probe_无基线(tmp_path):
    db = _write_weights_db(tmp_path / "up.db", [("2026-11-15", "cn", "master")])
    status, detail = probe_field_freshness(db, None)
    assert status == "no_baseline"
    assert "2026-11-15" in detail


def test_probe_fresh_上游不超出窗(tmp_path):
    db = _write_weights_db(tmp_path / "up.db", [("2026-11-15", "cn", "master")])
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"meta": {"date_to": "2026-11-15"}, "data": []}),
                    encoding="utf-8")
    status, detail = probe_field_freshness(db, snap)
    assert status == "fresh"
    assert "2026-11-15" in detail


def test_probe_stale_上游超出窗(tmp_path):
    db = _write_weights_db(tmp_path / "up.db", [
        ("2026-11-15", "cn", "master"),
        ("2026-11-20", "cn", "master"),   # 新数据
        ("2026-11-20", "intl_aligned", "master"),  # 其他 basis 不计
        ("2026-11-21", "cn", "junior"),   # 非 master 不计
    ])
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"meta": {"date_to": "2026-11-15"}, "data": []}),
                    encoding="utf-8")
    status, detail = probe_field_freshness(db, snap)
    assert status == "stale"
    assert "2026-11-20" in detail and "2026-11-15" in detail
