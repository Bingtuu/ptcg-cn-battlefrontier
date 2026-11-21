"""场数据刷新探针（Owner 2026-11-21 指令第 2 件）。

上游 mik 源 10-31 起停摆、11-15 轮询为在库最新态——库内 11-15 新增 4 场
合格城市赛（3771/3778/3788/3793，master 非组队各 64 出战）。本探针按
field-snap-2026-11.json 同款口径（meta 逐键复刻）导 2026-11-01..15 窗
新快照 field-snap-2026-11-21.json，并与旧窗对比场头变化。
"""

import json
from pathlib import Path

from ptcgdb.sdk import open_db

DB = "C:/Vibe Project/Pokearena/data/ptcg-cn.db"
OLD = Path("results/field-snap-2026-11.json")
OUT = Path("results/field-snap-2026-11-21.json")

db = open_db(DB)
res = db.stats_usage(
    date_from="2026-11-01", date_to="2026-11-15",
    scope=["pokemon", "supporter", "stadium"],
    division="master", tiers=None, include_qual=False, include_team=False,
    basis="cn", min_n=5, granularity="archetype", usage_basis="decks",
)
db.close()

rows = [r.model_dump(mode="json") for r in res.data]

old = json.loads(OLD.read_text(encoding="utf-8"))
meta = dict(res.meta)
meta["as_of"] = "2026-11-21"

snap = {"meta": meta, "data": rows}
OUT.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

old_v = {x["group_key"]: x["value"] for x in old["data"]}
new_v = {x["group_key"]: x["value"] for x in rows}
print(f"rows: old {len(old_v)} -> new {len(new_v)} | n_tournaments meta "
      f"{old['meta']['n_tournaments']} -> {meta.get('n_tournaments')}")
print(f"{'group':22s} {'old':>7s} {'new':>7s} {'delta':>8s}")
for k in list(new_v)[:14]:
    o = old_v.get(k, 0.0)
    print(f"{k:22s} {o:7.2%} {new_v[k]:7.2%} {new_v[k]-o:+8.2%}")
pool10 = ["多龙巴鲁托 黑夜魔灵", "电电虫Box", "玛俐的长毛巨魔 雪妖女",
          "赛富豪 土龙节节", "沙奈朵", "猛雷鼓 厄诡椪", "喷火龙 大比鸟",
          "N的索罗亚克", "多龙巴鲁托", "火伊布 猫头夜鹰"]
cov = sum(new_v.get(k, 0) for k in pool10)
old_cov = sum(old_v.get(k, 0) for k in pool10)
print(f"pool10 coverage: old {old_cov:.2%} -> new {cov:.2%}")
