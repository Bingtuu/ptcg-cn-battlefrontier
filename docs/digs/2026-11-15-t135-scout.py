# task 135 侦察脚本：近窗候选表选取 + 合法性校验 + 新旧 diff（上游 db 只读）
# 口径：窗 2026-11-01~14、division=master、rank>0、mapping_status=full、
# 同构筑最高名次（并列取日期近/出战多）、limit=500；合法性 = SDK validate_deck
# （standard，最新快照 = standard-2026-09-16）。
import json
import sqlite3
from datetime import UTC, datetime

DB = "C:/Vibe Project/Pokearena/data/ptcg-cn.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

TARGETS = [
    "沙奈朵",
    "玛俐的长毛巨魔 雪妖女",
    "猛雷鼓 厄诡椪",
    "N的索罗亚克",
    "火伊布 猫头夜鹰",
    "喷火龙 大比鸟",
    "赛富豪 土龙节节",
]

CAND_SQL = """
WITH nap AS (
  SELECT da2.deck_id AS did, COUNT(*) AS n_app
  FROM deck_appearances da2
  JOIN tournaments t2 ON da2.tournament_id = t2.tournament_id
  WHERE t2.date BETWEEN '2026-11-01' AND '2026-11-14'
    AND t2.division='master' AND da2.rank > 0
  GROUP BY da2.deck_id
)
SELECT da.deck_id, t.date, t.name, t.tournament_id, da.rank,
       COALESCE(nap.n_app, 0) AS n_app
FROM deck_appearances da
JOIN tournaments t ON da.tournament_id = t.tournament_id
JOIN decks d ON da.deck_id = d.deck_id
LEFT JOIN nap ON nap.did = da.deck_id
WHERE t.date BETWEEN '2026-11-01' AND '2026-11-14'
  AND t.division='master' AND da.rank > 0
  AND d.mapping_status='full'
  AND d.archetype_name = ?
ORDER BY da.rank ASC, t.date DESC, n_app DESC, da.deck_id
LIMIT 500
"""

CARDS_SQL = """
SELECT dc.card_id, dc.count, dc.raw_name, c.name
FROM deck_cards dc LEFT JOIN cards c ON c.card_id = dc.card_id
WHERE dc.deck_id = ?
ORDER BY dc.stat_scope, dc.raw_name
"""

out = {"as_of": datetime.now(UTC).date().isoformat(), "targets": {}}
for arch in TARGETS:
    cands = cur.execute(CAND_SQL, (arch,)).fetchall()
    best = cands[0]
    out["targets"][arch] = {
        "n_candidates": len(cands),
        "picked": {
            "deck_id": best[0], "date": best[1], "tournament": best[2],
            "tournament_id": best[3], "rank": best[4], "n_app_window": best[5],
        },
        "top5": [
            {"deck_id": r[0], "date": r[1], "tournament": r[2], "rank": r[4],
             "n_app_window": r[5]} for r in cands[:5]
        ],
    }

# 卡表 + 合法性校验（SDK，只读）
from ptcgdb.sdk import open_db

sdk = open_db(DB)
snap = sdk.snapshots("standard")[-1]
out["snapshot"] = {"snapshot_id": snap.snapshot_id,
                   "effective_from": str(snap.effective_from)}
print(f"snapshot: {snap.snapshot_id} effective_from={snap.effective_from}")
for arch, info in out["targets"].items():
    did = info["picked"]["deck_id"]
    deck = sdk.get_deck(did)
    ids = [e.card_id for e in deck.cards for _ in range(e.count)]
    n_none = sum(1 for e in deck.cards if e.card_id is None)
    rep = sdk.validate_deck(ids, snap.effective_from, "standard")
    cards = [{"card_id": e.card_id, "count": e.count, "raw_name": e.raw_name}
             for e in deck.cards]
    info["legality"] = {"ok": rep.ok, "violations": rep.violations,
                        "n_cards": len(ids), "n_unmapped_entries": n_none}
    info["cards"] = cards
    print(f"{arch}: picked {did} rank={info['picked']['rank']} "
          f"date={info['picked']['date']} legal={rep.ok} viol={rep.violations} "
          f"unmapped={n_none}")
sdk.close()
con.close()

with open("docs/digs/2026-11-15-t135-scout.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("saved docs/digs/2026-11-15-t135-scout.json")
