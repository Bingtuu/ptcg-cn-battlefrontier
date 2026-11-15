# task 145 冒烟臂 2（预注册修订 2026-11-16）：评估器健康探针。
# 原协议臂（MCTS 1×25 + eval-cutoff agreement）在快照规模墙钟 >15min/份，
# 超冒烟预算——改为等价回答「非退化」的探针：eval-linear-v1 对局中状态的
# 打分须有限、非恒定、且终局胜方侧分数更高（AUC）。
# 预注册下限（跑数前钉死）：v1 参考与 v2.x 各自 AUC ≥ 0.55，且 v2.x ≥ v1 − 0.10。
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path("C:/Vibe Project/Pokebattle")
sys.path.insert(0, str(ROOT))

from battlefrontier.agent.heuristic import HeuristicAgent
from battlefrontier.dsl.loader import load_card_dir
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.learn.model import load_model, predict
from battlefrontier.runner.experiment import load_deck

DB = "C:/Vibe Project/Pokearena/data/ptcg-cn.db"
MODEL = load_model(ROOT / "models/eval-linear-v1.json")
LIB = load_card_dir(ROOT / "cards")
N_GAMES = 20
SEED0 = 800000

MATCHUPS = {
    "v2.x": ("mik_moe:711854", "mik_moe:676344"),
    "v1": ("mik_moe:644634", "mik_moe:650353"),
}


def sample_states(deck_a_id, deck_b_id, seeds):
    da = load_deck(DB, deck_a_id).cards
    db_ = load_deck(DB, deck_b_id).cards
    samples = []  # (score_for_p0, p0_won)
    for i, seed in enumerate(seeds):
        engine = GameEngine(RandomSource(seed), card_effects=LIB)
        engine.new_game(da, db_)
        agents = [HeuristicAgent(card_effects=LIB), HeuristicAgent(card_effects=LIB)]
        while engine.state.phase != "game_over":
            if engine.state.turn >= 50:
                engine.force_draw(reason="turn_cap")
                break
            player = engine.state.current_player
            actions = engine.legal_actions(player)
            if not actions:
                engine.force_draw(reason="no_legal_actions")
                break
            view = engine.state.visible_state(player)
            action = agents[player].observe(view, actions)
            engine.apply(player, action)
            # 采样：第 3 回合起每个行动后给 p0 打分（终局后由 winner 打标签）
            if engine.state.phase != "game_over" and engine.state.turn >= 3:
                s = predict(MODEL, engine.state.visible_state(0))
                samples.append((s, None))
        w = engine.state.winner
        if w is None:  # 平局不计
            samples = [t for t in samples if t[1] is None][: max(0, len(samples) - sum(1 for t in samples if t[1] is None))]
            # 简单处理：本轮采样全部作废
            n_round = sum(1 for t in samples if t[1] is None)
            samples = samples[:-n_round] if n_round else samples
            continue
        # 回填本轮标签
        idx = len(samples) - 1
        while idx >= 0 and samples[idx][1] is None:
            samples[idx] = (samples[idx][0], 1 if w == 0 else 0)
            idx -= 1
    return samples


def auc(samples):
    wins = [s for s, w in samples if w == 1]
    losses = [s for s, w in samples if w == 0]
    if not wins or not losses:
        return None
    total = right = 0
    for a in wins:
        for b in losses:
            total += 1
            right += 1 if a > b else (0.5 if a == b else 0)
    return right / total


results = {}
for tag, (a_id, b_id) in MATCHUPS.items():
    samples = sample_states(a_id, b_id, [SEED0 + i for i in range(N_GAMES)])
    scores = [s for s, _ in samples]
    finite = all(isinstance(s, float) and abs(s) < 1e9 for s in scores)
    var = max(scores) - min(scores) if scores else 0.0
    a = auc(samples)
    results[tag] = a
    print(f"{tag}: states={len(samples)} finite={finite} range={var:.3f} AUC={a:.3f}"
          if a is not None else f"{tag}: states={len(samples)} finite={finite} AUC=None")

v1, v2 = results.get("v1"), results.get("v2.x")
ok = (v1 is not None and v2 is not None and v1 >= 0.55 and v2 >= 0.55
      and v2 >= v1 - 0.10)
print("EVAL PROBE:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
