"""task 156：bfsim field-snap——场快照导出 + 就绪探针。

导出 = 上游 stats_usage 钉口径调用的产品化（t152_field_refresh.py 同款，
调用参数逐键锁定，改口径须改测试）；探针 = 上游最新赛事日期 vs 既有快照
窗口终点的就绪检查（Owner 规划 ③：回答「现在刷新能不能拿到新场」）。

task 158：导出 meta 落签名 sig = {window, n_qualified, data_version}
（n_qualified 与合格赛事计数共享同一 SQL——探针据此双判：newer = 上游
超出窗终点；backfill = 同窗补入合格赛事/数据版本变更，MAX(date) 不动也
判出；仅新增被筛除赛事（junior/团队/qual）不误报）；无 sig 旧快照降级
为原日期比对并注明。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from battlefrontier.data.backend import open_backend


def today_iso() -> str:
    """本地时区当日 ISO 日期（DTZ 合规，替代 date.today()）。"""
    return datetime.now(tz=UTC).astimezone().date().isoformat()

# 与 t152 场刷新探针逐键一致的调用口径（scope/division/tiers/qual/team/
# basis/min_n/granularity/usage_basis 全部钉死；窗参数由调用方给）
STATS_USAGE_KW: dict = {
    "scope": ["pokemon", "supporter", "stadium"],
    "division": "master",
    "tiers": None,
    "include_qual": False,
    "include_team": False,
    "basis": "cn",
    "min_n": 5,
    "granularity": "archetype",
    "usage_basis": "decks",
}

# 合格赛事口径：与 stats_engine._base_meta 的 n_tournaments 逐条件对齐
# （FR-9.6「该指标实际参与的赛事数」）——division master-or-NULL、qual/team
# 剔除、basis=cn、static_weight IS NOT NULL（task 158 独立复验实证：缺
# static_weight 过滤时真库 41 vs meta 19，漏计过滤的 22 场）。
QUALIFIED_WHERE = ("(division = ? OR division IS NULL) "
                   "AND is_qual = 0 AND is_team = 0 "
                   "AND basis = ? "
                   "AND static_weight IS NOT NULL")
_LATEST_TOURNAMENT_SQL = (
    "SELECT MAX(date) FROM v_tournament_weights "
    "WHERE basis='cn' AND (division='master' OR division IS NULL)")


def qualified_count(db_path: str | Path, date_from: str, date_to: str) -> int:
    """该窗合格赛事数（与导出 meta.n_tournaments 同口径——_base_meta
    where 族逐条件对齐，导出签名与探针共享本函数，不抄两份 SQL）。"""
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute(
            f"SELECT count(*) FROM v_tournament_weights "
            f"WHERE date BETWEEN ? AND ? AND {QUALIFIED_WHERE}",
            (date_from, date_to, "master", "cn")).fetchone()
    finally:
        con.close()
    return int(row[0] or 0)


def _sig_data_version(db_path: str | Path) -> str:
    """签名数据版本锚点：sqlite = user_version（只读）；jsonl dist = schema_version。"""
    if Path(db_path).is_dir():
        db = open_backend(db_path)
        try:
            return f"jsonl_schema={db.schema_version}"
        finally:
            db.close()
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)  # 主库只读（FR-10）
    try:
        uv = con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()
    return f"user_version={uv}"


def export_field_snap(db_path: str | Path, date_from: str, date_to: str,
                      out: str | Path, *, as_of: str | None = None) -> dict:
    """上游 stats_usage（钉口径）→ 场快照 JSON（{"meta":…, "data":[…]}）。

    meta 继承上游出口 meta 并钉 as_of（缺省 = 运行日）+ 签名 sig（task 158）；
    返回写入的 dict。
    """
    db = open_backend(str(db_path))
    try:
        res = db.stats_usage(date_from=date_from, date_to=date_to,
                             **STATS_USAGE_KW)
    finally:
        db.close()
    meta = dict(res.meta)
    meta["as_of"] = as_of or today_iso()
    meta["sig"] = {
        "window": [date_from, date_to],
        "n_qualified": qualified_count(db_path, date_from, date_to),
        "data_version": _sig_data_version(db_path),
    }
    snap = {"meta": meta,
            "data": [r.model_dump(mode="json") for r in res.data]}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(snap, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    return snap


def probe_field_freshness(db_path: str | Path,
                          snap_path: str | Path | None
                          ) -> tuple[str, str]:
    """就绪探针：返回 (status, detail)。

    status ∈ {"no_baseline", "fresh", "stale"}：
    no_baseline = 无既有快照（上游最新日期照报，供首次建窗参考）；
    fresh = 上游最新赛事日期 ≤ 快照窗终点且签名一致（现在刷新拿不到新场）；
    stale = 上游已超出窗终点（newer）∥ 同窗回填/数据版本变更（backfill，
    签名双判——MAX(date) 不动也判出）；无 sig 旧快照降级为纯日期比对并注明。
    """
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute(_LATEST_TOURNAMENT_SQL).fetchone()
    finally:
        con.close()
    latest = row[0] if row else None
    if latest is None:
        return ("no_baseline", "上游 v_tournament_weights 无 cn/master 赛事记录")

    if snap_path is None or not Path(snap_path).exists():
        return ("no_baseline", f"上游最新赛事 {latest}；无既有快照基线")

    snap = json.loads(Path(snap_path).read_text(encoding="utf-8"))
    meta = snap.get("meta") or {}
    win_to = meta.get("date_to")
    if not win_to:
        return ("no_baseline", f"上游最新赛事 {latest}；快照缺 meta.date_to 无法比对")
    if latest > win_to:
        return ("stale", (f"上游最新赛事 {latest} 已超出快照窗终点 {win_to}"
                          f"——刷新可拿到新数据（newer）"))

    sig = meta.get("sig")
    window = (sig or {}).get("window")
    if not (isinstance(window, list) and len(window) == 2
            and "n_qualified" in (sig or {}) and "data_version" in (sig or {})):
        return ("fresh", (f"上游最新赛事 {latest} ≤ 快照窗终点 {win_to}"
                          f"——现在刷新拿不到新场（旧快照无签名，仅日期比对降级）"))

    reasons: list[str] = []
    n_now = qualified_count(db_path, window[0], window[1])
    if n_now != sig["n_qualified"]:
        reasons.append(f"同窗合格赛事数 {sig['n_qualified']}→{n_now}（回填）")
    dv_now = _sig_data_version(db_path)
    if dv_now != sig["data_version"]:
        reasons.append(f"数据版本 {sig['data_version']}→{dv_now}（变更）")
    if reasons:
        return ("stale", (f"上游最新赛事 {latest} 未超窗终点 {win_to}，"
                          f"但签名不符：{'；'.join(reasons)}"
                          f"——刷新可取回修订数据（backfill）"))
    return ("fresh", (f"上游最新赛事 {latest} ≤ 快照窗终点 {win_to}，签名一致"
                      f"（n_qualified={n_now}）——现在刷新拿不到新场"))
