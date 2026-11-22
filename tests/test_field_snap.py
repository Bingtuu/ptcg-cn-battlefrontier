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
    # task 158：签名 n_qualified 走真实 qualified_count SQL——造最小
    # v_tournament_weights 表（0 合格赛事），user_version=3 锚数据版本
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE v_tournament_weights (tournament_id INTEGER,"
                " date TEXT, basis TEXT, division TEXT, weight REAL,"
                " is_qual INTEGER, is_team INTEGER, static_weight REAL)")
    con.execute("PRAGMA user_version=3")
    con.commit()
    con.close()
    stub = _StubDb(_StubRes(rows, meta))
    return db_path, stub


def test_export_结构与口径逐键锁定(tmp_path, monkeypatch):
    import battlefrontier.runner.field_snap as fs

    db_path, stub = _make_upstream(tmp_path, [{"group_key": "甲", "value": 0.5}],
                                   {"n_tournaments": 19, "date_from": "2026-11-01",
                                    "date_to": "2026-11-15"})
    monkeypatch.setattr(fs, "open_backend", lambda p: stub)

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
    # task 158：签名三键；task 161：+ 内容签名
    sig = written["meta"]["sig"]
    assert sig["window"] == ["2026-11-01", "2026-11-15"]
    assert sig["n_qualified"] == 0
    assert sig["data_version"] == "user_version=3"
    assert len(sig["content_sha256"]) == 64


def test_export_as_of_缺省取当日(tmp_path, monkeypatch):
    import battlefrontier.runner.field_snap as fs

    db_path, stub = _make_upstream(tmp_path, [], {"n_tournaments": 0})
    monkeypatch.setattr(fs, "open_backend", lambda p: stub)
    out = tmp_path / "snap.json"
    snap = export_field_snap(db_path, "2026-11-01", "2026-11-15", out)
    assert snap["meta"]["as_of"] == fs.today_iso()


def _write_weights_db(path: Path, dates: list[tuple[str, str, str]],
                      *, user_version: int = 3) -> str:
    """造上游 v_tournament_weights 最小表：(date, basis, division) 行——
    is_qual/is_team=0、static_weight=1.0（默认行均合格，对齐 _base_meta 口径）。"""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE v_tournament_weights (tournament_id INTEGER, date TEXT,"
                " basis TEXT, division TEXT, weight REAL,"
                " is_qual INTEGER, is_team INTEGER, static_weight REAL)")
    for i, (d, b, div) in enumerate(dates):
        con.execute("INSERT INTO v_tournament_weights VALUES (?,?,?,?,?,?,?,?)",
                    (i, d, b, div, 1.0, 0, 0, 1.0))
    con.execute(f"PRAGMA user_version={user_version}")
    con.commit()
    con.close()
    return str(path)


def _write_sig_snap(path: Path, *, n_qualified: int = 2,
                    user_version: int = 3) -> Path:
    """带 task 158 签名的快照（窗 11-01..11-15，签名与 _write_weights_db
    的默认 fixture 同源：前两行合格）。"""
    snap = {"meta": {"date_to": "2026-11-15",
                     "sig": {"window": ["2026-11-01", "2026-11-15"],
                             "n_qualified": n_qualified,
                             "data_version": f"user_version={user_version}"}},
            "data": []}
    path.write_text(json.dumps(snap), encoding="utf-8")
    return path


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
    assert "newer" in detail


# ── task 158：签名双判（newer / backfill）──────────────────────────

def test_probe_签名一致_fresh(tmp_path):
    """同窗同数据：n_qualified 与 data_version 全等 → fresh。"""
    db = _write_weights_db(tmp_path / "up.db", [
        ("2026-11-10", "cn", "master"),
        ("2026-11-15", "cn", "master"),
    ])
    status, detail = probe_field_freshness(db, _write_sig_snap(tmp_path / "snap.json"))
    assert status == "fresh"
    assert "签名一致" in detail


def test_probe_同窗回填合格赛事_stale_backfill(tmp_path):
    """同窗补入合格赛事（MAX(date) 不动）→ stale 且注明 backfill。"""
    db = _write_weights_db(tmp_path / "up.db", [
        ("2026-11-10", "cn", "master"),
        ("2026-11-15", "cn", "master"),
        ("2026-11-12", "cn", "master"),   # 同窗回填（tournament_id 不同 → DISTINCT +1）
    ])
    status, detail = probe_field_freshness(db, _write_sig_snap(tmp_path / "snap.json"))
    assert status == "stale"
    assert "backfill" in detail and "2→3" in detail


def test_probe_同窗仅新增被筛除赛事_still_fresh(tmp_path):
    """同窗新增 junior/其他 basis（口径外）→ 计数不变 → 仍 fresh 不误报。"""
    db = _write_weights_db(tmp_path / "up.db", [
        ("2026-11-10", "cn", "master"),
        ("2026-11-15", "cn", "master"),
        ("2026-11-12", "cn", "junior"),          # 被筛除
        ("2026-11-13", "intl_aligned", "master"),  # 其他 basis
    ])
    status, _detail = probe_field_freshness(db, _write_sig_snap(tmp_path / "snap.json"))
    assert status == "fresh"


def test_probe_同窗新增未加权赛事_still_fresh(tmp_path):
    """static_weight IS NULL（数据未完备）的赛事不计入签名口径——独立复验
    实证该过滤是真库 41 vs meta 19 的差异源；同窗新增未加权赛事不误报。"""
    db = _write_weights_db(tmp_path / "up.db", [
        ("2026-11-10", "cn", "master"),
        ("2026-11-15", "cn", "master"),
    ])
    con = sqlite3.connect(db)
    con.execute("INSERT INTO v_tournament_weights "
                "VALUES (99, '2026-11-12', 'cn', 'master', 1.0, 0, 0, NULL)")
    con.commit()
    con.close()
    status, _detail = probe_field_freshness(db, _write_sig_snap(tmp_path / "snap.json"))
    assert status == "fresh"


def test_probe_数据版本变更_stale_backfill(tmp_path):
    """上游 user_version 变（同窗数据修订）→ stale backfill。"""
    db = _write_weights_db(tmp_path / "up.db", [
        ("2026-11-10", "cn", "master"),
        ("2026-11-15", "cn", "master"),
    ], user_version=9)  # 签名锚的是 3
    status, detail = probe_field_freshness(db, _write_sig_snap(tmp_path / "snap.json"))
    assert status == "stale"
    assert "backfill" in detail and "user_version=3→user_version=9" in detail


def test_probe_无签名旧快照_降级日期比对(tmp_path):
    db = _write_weights_db(tmp_path / "up.db", [("2026-11-15", "cn", "master")])
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"meta": {"date_to": "2026-11-15"}, "data": []}),
                    encoding="utf-8")
    status, detail = probe_field_freshness(db, snap)
    assert status == "fresh"
    assert "降级" in detail


# ── task 161：内容签名（同窗纯内容修订检测 + 能力边界明示）──────────

def test_export_sig_含内容签名(tmp_path, monkeypatch):
    """sig 增 content_sha256（合格行内容哈希，best-effort 检测
    「计数与日期不变、仅修订内容」的修订路径）。"""
    import battlefrontier.runner.field_snap as fs

    db_path, stub = _make_upstream(tmp_path, [{"group_key": "甲", "value": 0.5}],
                                   {"n_tournaments": 0})
    monkeypatch.setattr(fs, "open_backend", lambda p: stub)
    out = tmp_path / "snap.json"
    export_field_snap(db_path, "2026-11-01", "2026-11-15", out)

    sig = json.loads(out.read_text(encoding="utf-8"))["meta"]["sig"]
    assert sig["window"] == ["2026-11-01", "2026-11-15"]
    assert sig["n_qualified"] == 0
    assert sig["data_version"] == "user_version=3"
    assert len(sig["content_sha256"]) == 64


def test_probe_同窗纯内容修订_stale_backfill(tmp_path):
    """日期与合格赛事数全不变，仅修订同窗一行 static_weight
    （牌表更正/权重修订路径）→ 内容签名判出 backfill。"""
    from battlefrontier.runner.field_snap import qualified_content_sha256

    db = _write_weights_db(tmp_path / "up.db", [
        ("2026-11-10", "cn", "master"),
        ("2026-11-15", "cn", "master"),
    ])
    snap = tmp_path / "snap.json"
    snap_obj = {"meta": {"date_to": "2026-11-15",
                         "sig": {"window": ["2026-11-01", "2026-11-15"],
                                 "n_qualified": 2,
                                 "data_version": "user_version=3",
                                 "content_sha256": qualified_content_sha256(
                                     db, "2026-11-01", "2026-11-15")}},
                "data": []}
    snap.write_text(json.dumps(snap_obj), encoding="utf-8")
    status, detail = probe_field_freshness(db, snap)
    assert status == "fresh"

    # 同窗纯内容修订： tournament_id=0 的 static_weight 1.0 → 2.0
    con = sqlite3.connect(db)
    con.execute("UPDATE v_tournament_weights SET static_weight=2.0 "
                "WHERE tournament_id=0")
    con.commit()
    con.close()
    status, detail = probe_field_freshness(db, snap)
    assert status == "stale"
    assert "backfill" in detail and "内容签名" in detail


def test_probe_旧快照无内容签名_能力边界注记(tmp_path):
    """旧签名（无 content_sha256）fresh 时明示检测能力边界。"""
    db = _write_weights_db(tmp_path / "up.db", [
        ("2026-11-10", "cn", "master"),
        ("2026-11-15", "cn", "master"),
    ])
    status, detail = probe_field_freshness(db, _write_sig_snap(tmp_path / "snap.json"))
    assert status == "fresh"
    assert "签名一致" in detail
    assert "不保证内容未变" in detail
