"""task 108 验证：事件序修复的行为等价抽查。

同实验定义（gard-zoro，种子 300000..300019）在新代码下重跑，与
results/m13-followup-gard-zoro.db（旧代码，500 局）逐局比对：
1. 事件多重集等价（Counter(kind 序列) 逐局相等）——零事件丢失/新增；
2. 终局状态等价（winner/reason）——零对局行为变更；
3. 新序生效（存在局 knockout 位置相对 effect_end 后移）；
4. 串行两次重跑 events_hash 一致——确定性保持。

用法：PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 .kimi-code/t108_replay_check.py
"""

import json
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD_DB = ROOT / "results/m13-followup-gard-zoro.db"
NEW_DB = ROOT / "results/t108-replay-check.db"
NEW_YML = ROOT / "results/t108-replay-check.yml"
N_GAMES = 20


def main() -> int:
    yml = (ROOT / "results/m13-followup-gard-zoro.yml").read_text(encoding="utf-8")
    yml = yml.replace("games: 500", f"games: {N_GAMES}")
    NEW_YML.write_text(yml, encoding="utf-8")
    for db in (NEW_DB,):
        db.unlink(missing_ok=True)

    py = sys.executable
    for run in (1, 2):  # 两次串行：确定性自查
        subprocess.run(
            [py, "-m", "battlefrontier.cli", "run", str(NEW_YML),
             "--results", str(NEW_DB)],
            cwd=ROOT, check=True,
            env={"PYTHONIOENCODING": "utf-8", "PATH": __import__("os").environ["PATH"],
                 "SystemRoot": __import__("os").environ.get("SystemRoot", "")},
        )
        if run == 1:
            hash1 = events_hashes(NEW_DB)
    hash2 = events_hashes(NEW_DB)
    det_ok = hash1 == hash2
    print(f"[1] 串行两次 events_hash 全等: {det_ok} ({N_GAMES} 局)")

    old = load_games(OLD_DB)
    new = load_games(NEW_DB)
    common = sorted(set(old) & set(new))
    assert len(common) == N_GAMES, f"种子交集 {len(common)} != {N_GAMES}"
    multiset_ok = outcomes_ok = 0
    reorder_seen = 0
    for seed in common:
        o, n = old[seed], new[seed]
        assert Counter(o["kinds"]) == Counter(n["kinds"]), f"seed {seed}: 事件多重集不等"
        multiset_ok += 1
        assert o["outcome"] == n["outcome"], f"seed {seed}: 终局不等 {o['outcome']} vs {n['outcome']}"
        outcomes_ok += 1
        if o["kinds"] != n["kinds"]:
            reorder_seen += 1
    print(f"[2] 事件多重集等价: {multiset_ok}/{N_GAMES}")
    print(f"[3] 终局状态等价: {outcomes_ok}/{N_GAMES}")
    print(f"[4] 事件序重排局数: {reorder_seen}/{N_GAMES}（0 = 修复未生效）")
    ok = det_ok and multiset_ok == N_GAMES and outcomes_ok == N_GAMES and reorder_seen > 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def load_games(db_path: Path) -> dict[int, dict]:
    db = sqlite3.connect(db_path)
    out = {}
    for seed, winner, is_draw in db.execute(
        "SELECT seed, winner, is_draw FROM games"
    ):
        rows = db.execute(
            "SELECT event_json FROM game_events WHERE game_id = "
            "(SELECT id FROM games WHERE seed = ?) ORDER BY seq", (seed,),
        ).fetchall()
        kinds = [json.loads(r[0])["kind"] for r in rows]
        out[seed] = {"kinds": kinds, "outcome": (winner, is_draw)}
    return out


def events_hashes(db_path: Path) -> dict[int, str]:
    db = sqlite3.connect(db_path)
    return {seed: h for seed, h in db.execute("SELECT seed, events_hash FROM games")}


if __name__ == "__main__":
    sys.exit(main())
