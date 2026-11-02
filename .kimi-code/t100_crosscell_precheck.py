# task 100 跨格 would-change 频数预检（只读；预注册见 tasks/task 100.md）。
# 对两个未归因高残差格在既有矩阵库上 replay（hash 逐局校验），
# 输家侧（玩家 0）主线决策点计数紧口径 would-change：
#   W1t = 可支付可斩（战斗场）未拿奖
#   W2  = not W1t ∧ 手里有老大 ∧ 支援者可出 ∧ 对方备战可斩（沿用 task 099 近似）未拿奖
# 判定：按 配对×识别器 独立，败局 ≥15 局 且 f_loss ≥ 1.5×f_win（f_win=0 视为满足）。
# 用法：PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 .kimi-code/t100_crosscell_precheck.py

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battlefrontier.agent.dsl_estimate import estimate_attack_damage
from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams
from battlefrontier.data.deck import load_deck
from battlefrontier.dsl.loader import load_card_dir
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.runner.experiment import (
    assemble_card_effects,
    load_db_path,
)
from battlefrontier.runner.play import DEFAULT_MAX_TURNS, OBSERVATION_KINDS

DB_FILE = ROOT / "results/v2-calibration-post086.db"
BOSS = "老大的指令"
ME = 0          # 输家侧 = 玩家 0（deck a = 猛雷鼓 / 火伊布）
OPP = 1         # 多龙侧
PAIRS = [
    ("ragingbolt-drag", "mik_moe:676249", "mik_moe:677868"),
    ("flareon-drag", "mik_moe:689871", "mik_moe:677868"),
]


def events_hash(engine) -> str:
    payload = json.dumps(
        [ev.model_dump(mode="json") for ev in engine.events
         if ev.kind not in OBSERVATION_KINDS],
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_pair(label: str, deck_a_id: str, deck_b_id: str, db_path: Path) -> None:
    db_path_str = load_db_path()
    deck_a = load_deck(db_path_str, deck_a_id).cards
    deck_b = load_deck(db_path_str, deck_b_id).cards
    card_effects, _ = assemble_card_effects(
        [deck_a, deck_b], load_card_dir(ROOT / "cards"))
    helper = HeuristicAgent(HeuristicParams(), card_effects=card_effects)

    con = sqlite3.connect(db_path)
    games = con.execute(
        "SELECT seed, winner, is_draw, events_hash FROM games "
        "WHERE deck_a_id=? AND deck_b_id=? ORDER BY seed",
        (deck_a_id, deck_b_id)).fetchall()
    con.close()

    hash_bad = 0
    samples: list[dict] = []
    for seed, winner, is_draw, want_hash in games:
        engine = GameEngine(RandomSource(seed), card_effects=card_effects)
        agents = [HeuristicAgent(HeuristicParams(), card_effects=card_effects)
                  for _ in range(2)]
        engine.new_game(deck_a, deck_b)
        n_events = 0
        while engine.state.phase != "game_over":
            if engine.state.turn >= DEFAULT_MAX_TURNS:
                engine.force_draw(reason="turn_cap")
                break
            player = engine.state.current_player
            actions = engine.legal_actions(player)
            if not actions:
                engine.force_draw(reason="no_legal_actions")
                break
            sample = None
            if player == ME:
                kinds = {a.kind for a in actions}
                if "attack" in kinds or "end_turn" in kinds:  # 主线（预注册采样门）
                    view = engine.state.visible_state(ME)
                    opp = view.opponent.active
                    me = view.own.active
                    w1t = w2 = False
                    best_payable = 0
                    if opp is not None and me is not None:
                        remaining = helper._ko_remaining(view, opp)
                        own_type = me.current.card.energy_type

                        def _eff(dmg, _opp=opp, _t=own_type):
                            if dmg and _opp.current.card.weakness \
                                    and _t == _opp.current.card.weakness:
                                dmg *= 2
                            if dmg and _opp.current.card.resistance \
                                    and _t == _opp.current.card.resistance:
                                dmg = max(0, dmg - 30)
                            return dmg

                        for a in [x for x in actions if x.kind == "attack"]:
                            atk = me.current.card.attacks[a.attack_index]
                            est = estimate_attack_damage(
                                view, atk.name, atk.damage,
                                me.current.card, card_effects)
                            dmg = est.amount if est is not None else (atk.damage or 0)
                            best_payable = max(best_payable, _eff(dmg))
                        if remaining is not None and 0 < remaining <= best_payable:
                            w1t = True
                        if (not w1t
                                and any(c.card.name == BOSS for c in view.own.hand)
                                and any(a.kind == "play_trainer" for a in actions)):
                            for mon in view.opponent.bench:
                                rem = helper._ko_remaining(view, mon)
                                if rem is not None and 0 < rem <= best_payable:
                                    w2 = True
                                    break
                    sample = {"seed": seed, "w1t": w1t, "w2": w2}
            action = agents[player].observe(
                engine.state.visible_state(player), actions)
            if sample is not None:
                sample["chose"] = action.kind
            before = n_events
            engine.apply(player, action)
            n_events = len(engine.events)
            new_evts = [engine.events[i] for i in range(before, n_events)]
            # 拿奖 = 对方（多龙侧）的宝可梦被击倒（player==OPP）
            prize = any(e.kind == "knockout" and e.player == OPP for e in new_evts)
            if sample is not None:
                sample["prize"] = prize
                sample["won"] = (not is_draw) and winner == ME
                samples.append(sample)
        if events_hash(engine) != want_hash:
            hash_bad += 1

    n = len(games)
    print(f"\n== {label}（{deck_a_id} vs {deck_b_id}）==")
    print(f"hash 校验：{n - hash_bad}/{n} 一致")
    loss = {r["seed"] for r in samples if not r["won"]}
    win = {r["seed"] for r in samples if r["won"]}
    print(f"局级：败 {len(loss)} / 胜 {len(win)}")
    for key in ("w1t", "w2"):
        ql = {r["seed"] for r in samples
              if r[key] and not r["prize"] and r["seed"] in loss}
        qw = {r["seed"] for r in samples
              if r[key] and not r["prize"] and r["seed"] in win}
        f_loss = len(ql) / max(len(loss), 1)
        f_win = len(qw) / max(len(win), 1)
        sep = f_loss >= 1.5 * f_win or f_win == 0
        verdict = "立项候选" if (len(ql) >= 15 and sep) else "关闭"
        print(f"  {key.upper()}: 败局 {len(ql)} 局（f={f_loss:.1%}）/ 胜局 {len(qw)} 局"
              f"（f={f_win:.1%}）→ 判定：{verdict}")
    # 诊断（不进判定）：W2 败局点的实际选择分布
    from collections import Counter
    for key in ("w2",):
        cnt = Counter(r["chose"] for r in samples
                      if r[key] and not r["prize"] and r["seed"] in loss)
        print(f"  [诊断] {key.upper()} 败局点选择分布：{dict(cnt.most_common())}")


def main() -> int:
    for label, a, b in PAIRS:
        run_pair(label, a, b, DB_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
