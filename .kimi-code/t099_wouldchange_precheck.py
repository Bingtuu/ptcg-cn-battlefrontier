# task 092 菜单 A/E 频数预检（只读）：replay 500 局（hash 校验逐局可信），
# 在 B（N索）侧每个主线决策点检测两类 would-change 候选信号：
#   W1 = B 战斗场存在「估算可斩杀 A 战斗场」的招式，但 B 没能在本回合拿奖
#   W2 = A 备战区有可斩杀目标 ∧ B 手里有「老大的指令」且支援者槽可出
# 上界口径：不做招式可支付性检查（不可支付会高估；频数预检取上界——
# 上界 <15 ⇒ 方向死透；上界 ≥15 ⇒ 再收紧口径复核）。
# 判定门槛（092 dig 菜单 E 预注册）：触及负局（B 摸过暗夜但仍输）would-change
# 局数 ≥15 才立项。Q3 的 0/52 口径 = 局数。
# 用法：PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 .kimi-code/t099_wouldchange_precheck.py

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
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.runner.experiment import (
    load_db_path,
    load_experiment,
    prepare_experiment,
)
from battlefrontier.runner.play import OBSERVATION_KINDS

DB_FILE = ROOT / "results/t092-gard-zoro-500.db"
EXPERIMENT = ROOT / "experiments/t092-gard-zoro-500.yml"
BOSS = "老大的指令"
ACE = "暗夜王牌"


def events_hash(engine: GameEngine) -> str:
    payload = json.dumps(
        [ev.model_dump(mode="json") for ev in engine.events
         if ev.kind not in OBSERVATION_KINDS],
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    defn = load_experiment(EXPERIMENT)
    prep = prepare_experiment(defn, load_db_path())
    helper = HeuristicAgent(HeuristicParams(), card_effects=prep.card_effects)

    con = sqlite3.connect(DB_FILE)
    games = con.execute(
        "SELECT seed, winner, is_draw, events_hash FROM games "
        "WHERE experiment_id=1 ORDER BY seed").fetchall()
    con.close()

    hash_bad = 0
    samples: list[dict] = []  # 每局 B 主线决策点一条
    game_info: dict[int, dict] = {}
    for seed, winner, is_draw, want_hash in games:
        engine = GameEngine(RandomSource(seed), card_effects=prep.card_effects)
        agents = [
            HeuristicAgent(HeuristicParams(**defn.agents.a.params),
                           card_effects=prep.card_effects),
            HeuristicAgent(HeuristicParams(**defn.agents.b.params),
                           card_effects=prep.card_effects),
        ]
        engine.new_game(prep.deck_a, prep.deck_b)
        touched = False
        n_events = 0
        while engine.state.phase != "game_over":
            if engine.state.turn >= 1000:
                engine.force_draw(reason="turn_cap")
                break
            player = engine.state.current_player
            actions = engine.legal_actions(player)
            if not actions:
                engine.force_draw(reason="no_legal_actions")
                break
            sample = None
            if player == 1:
                kinds = {a.kind for a in actions}
                if "attack" in kinds or "end_turn" in kinds:  # 主线阶段
                    view = engine.state.visible_state(1)
                    opp = view.opponent.active
                    me = view.own.active
                    lethal_avail = boss_avail = False
                    lethal_payable = copy_ko = False
                    best = best_payable = 0
                    if opp is not None and me is not None:
                        remaining = helper._ko_remaining(view, opp)
                        own_type = me.current.card.energy_type

                        def _eff(dmg: int, _opp=opp, _t=own_type) -> int:
                            if dmg and _opp.current.card.weakness \
                                    and _t == _opp.current.card.weakness:
                                dmg *= 2
                            if dmg and _opp.current.card.resistance \
                                    and _t == _opp.current.card.resistance:
                                dmg = max(0, dmg - 30)
                            return dmg

                        atk_actions = [a for a in actions if a.kind == "attack"]
                        for atk in me.current.card.attacks:
                            est = estimate_attack_damage(
                                view, atk.name, atk.damage,
                                me.current.card, prep.card_effects)
                            dmg = est.amount if est is not None else (atk.damage or 0)
                            best = max(best, _eff(dmg))
                        for a in atk_actions:  # 合法 attack 行动 = 可支付
                            atk = me.current.card.attacks[a.attack_index]
                            est = estimate_attack_damage(
                                view, atk.name, atk.damage,
                                me.current.card, prep.card_effects)
                            dmg = est.amount if est is not None else (atk.damage or 0)
                            best_payable = max(best_payable, _eff(dmg))
                        # W3：复制招式（暗夜王牌）可斩杀 = 供体×招式枚举
                        ace_payable = any(
                            a.kind == "attack"
                            and me.current.card.attacks[a.attack_index].name == ACE
                            for a in actions)
                        if ace_payable:
                            for donor in view.own.bench:
                                for idx in range(len(donor.current.card.attacks)):
                                    if helper._copied_strike(view, donor, idx)[1]:
                                        copy_ko = True
                                        break
                                if copy_ko:
                                    break
                        if remaining is not None and remaining > 0:
                            lethal_avail = best >= remaining
                            lethal_payable = best_payable >= remaining
                        if (not lethal_payable
                                and any(c.card.name == BOSS for c in view.own.hand)
                                and any(a.kind == "play_trainer" for a in actions)):
                            for mon in view.opponent.bench:
                                rem = helper._ko_remaining(view, mon)
                                if rem is not None and 0 < rem <= best_payable:
                                    boss_avail = True
                                    break
                    sample = {
                        "seed": seed, "turn": engine.state.turn,
                        "lethal_avail": lethal_avail,
                        "lethal_payable": lethal_payable,
                        "copy_ko": copy_ko,
                        "boss_avail": boss_avail,
                        "before_touch": not touched,
                    }
            action = agents[player].observe(
                engine.state.visible_state(player), actions)
            before = n_events
            engine.apply(player, action)
            n_events = len(engine.events)
            new_evts = [engine.events[i] for i in range(before, n_events)]
            prize = any(e.kind == "knockout" and e.player == 0 for e in new_evts)
            ace_now = any(
                e.kind == "attack" and player == 1
                and (e.detail or {}).get("attack") == ACE for e in new_evts)
            if sample is not None:
                sample["prize_taken"] = prize
                samples.append(sample)
            if ace_now and not touched:
                touched = True
        game_info[seed] = {
            "a_win": bool(is_draw) is False and winner == 0,
            "b_win": (not is_draw) and winner == 1,
            "touched": touched,
        }
        if events_hash(engine) != want_hash:
            hash_bad += 1

    n_games = len(game_info)
    print(f"hash 校验：{n_games - hash_bad}/{n_games} 一致")
    touch_loss = {s for s, g in game_info.items() if g["touched"] and g["a_win"]}
    touch_win = {s for s, g in game_info.items() if g["touched"] and g["b_win"]}
    print(f"局级：触及负 {len(touch_loss)} / 触及胜 {len(touch_win)}（dig 参照 236/145）")

    def game_count(pred) -> int:
        return len({r["seed"] for r in samples if pred(r)
                    and r["seed"] in touch_loss})

    print("\n== 触及负局 would-change 局数（Q3 口径，门槛 ≥15）==")
    w1_pre = game_count(lambda r: r["lethal_avail"] and not r["prize_taken"]
                        and r["before_touch"])
    w1_post = game_count(lambda r: r["lethal_avail"] and not r["prize_taken"]
                         and not r["before_touch"])
    w1t_pre = game_count(lambda r: r["lethal_payable"] and not r["prize_taken"]
                         and r["before_touch"])
    w1t_post = game_count(lambda r: r["lethal_payable"] and not r["prize_taken"]
                          and not r["before_touch"])
    w3_pre = game_count(lambda r: r["copy_ko"] and not r["prize_taken"]
                        and r["before_touch"])
    w3_post = game_count(lambda r: r["copy_ko"] and not r["prize_taken"]
                         and not r["before_touch"])
    w2_any = game_count(lambda r: r["boss_avail"] and not r["prize_taken"])
    w2_pre = game_count(lambda r: r["boss_avail"] and not r["prize_taken"]
                        and r["before_touch"])
    print(f"W1  可斩未拿奖（上界·混不可支付）·首触前：{w1_pre} 局 ·首触后：{w1_post} 局")
    print(f"W1t 可支付可斩未拿奖（紧口径）·首触前：{w1t_pre} 局 ·首触后：{w1t_post} 局")
    print(f"W3  复制可斩未挥·首触前：{w3_pre} 局 ·首触后：{w3_post} 局")
    print(f"W2  老大+备战可斩未拿奖（紧口径）全部：{w2_any} 局（首触前 {w2_pre} 局）")

    print("\n== 对照：触及胜局同口径（方向 sanity）==")

    def game_count_win(pred) -> int:
        return len({r["seed"] for r in samples if pred(r)
                    and r["seed"] in touch_win})
    print(f"W1t·首触前：{game_count_win(lambda r: r['lethal_payable'] and not r['prize_taken'] and r['before_touch'])} 局")
    print(f"W3·首触前：{game_count_win(lambda r: r['copy_ko'] and not r['prize_taken'] and r['before_touch'])} 局")
    print(f"W2（全部）：{game_count_win(lambda r: r['boss_avail'] and not r['prize_taken'])} 局")

    print("\n== 决策点级总量 ==")
    print(f"B 主线决策点总数：{len(samples)}")
    for key in ("lethal_avail", "lethal_payable", "copy_ko", "boss_avail"):
        print(f"  {key} 且未拿奖："
              f"{sum(1 for r in samples if r[key] and not r['prize_taken'])} 点")
    verdict = "PASS（可进入识别器收紧 + 立项拍板）" if max(
        w1t_pre, w1t_post, w2_any, w3_pre, w3_post) >= 15 else \
        "FAIL（紧口径不足 15，方向死透）"
    print(f"\n频数门判定（紧口径）：{verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
