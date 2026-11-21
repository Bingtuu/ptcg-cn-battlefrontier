"""task 156：bfsim field-snap——场快照导出 + 就绪探针。

导出 = 上游 stats_usage 钉口径调用的产品化（t152_field_refresh.py 同款，
调用参数逐键锁定，改口径须改测试）；探针 = 上游最新赛事日期 vs 既有快照
窗口终点的就绪检查（Owner 规划 ③：回答「现在刷新能不能拿到新场」）。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ptcgdb.sdk import open_db


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

# 就绪探针查询口径：与导出同赛区（cn / master），不猜
_LATEST_TOURNAMENT_SQL = (
    "SELECT MAX(date) FROM v_tournament_weights "
    "WHERE basis='cn' AND (division='master' OR division IS NULL)"
)


def export_field_snap(db_path: str | Path, date_from: str, date_to: str,
                      out: str | Path, *, as_of: str | None = None) -> dict:
    """上游 stats_usage（钉口径）→ 场快照 JSON（{"meta":…, "data":[…]}）。

    meta 继承上游出口 meta 并钉 as_of（缺省 = 运行日）；返回写入的 dict。
    """
    db = open_db(str(db_path))
    try:
        res = db.stats_usage(date_from=date_from, date_to=date_to,
                             **STATS_USAGE_KW)
    finally:
        db.close()
    meta = dict(res.meta)
    meta["as_of"] = as_of or today_iso()
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
    fresh = 上游最新赛事日期 ≤ 快照窗终点（现在刷新拿不到新场）；
    stale = 上游已超出窗终点（刷新可拿到新数据，detail 含两端日期）。
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
    win_to = (snap.get("meta") or {}).get("date_to")
    if not win_to:
        return ("no_baseline", f"上游最新赛事 {latest}；快照缺 meta.date_to 无法比对")
    if latest <= win_to:
        return ("fresh", f"上游最新赛事 {latest} ≤ 快照窗终点 {win_to}——现在刷新拿不到新场")
    return ("stale", f"上游最新赛事 {latest} 已超出快照窗终点 {win_to}——刷新可拿到新数据")
