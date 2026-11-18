# task 150 过线探针（预注册：task 150 设计段）——t145 协议参数化版。
# 协议与 t145_eval_probe.py 完全一致（启发式自对局、第 3 回合起逐行动采样、
# p0 视角打分、终局胜方侧 AUC、平局局作废）：t145 冻结脚本不动，本脚本把
# 模型路径/对决做成参数，供 eval-linear-v2 过线判读与对照臂复用。
# 判据（跑数前钉死）：v2.x 对决（711854×676344, 20 局, seed 800000..800019）
# 新资产 AUC ≥ 0.90 → PASS。
# 用法: .venv/Scripts/python.exe -X utf8 .kimi-code/t150_eval_gate.py <model.json>
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
LIB = load_card_dir(ROOT / "cards")
N_GAMES = 20
SEED0 = 800000
GATE = 0.90

MATCHUPS = {
    "v2.x": ("mik_moe:711854", "mik_moe:676344"),
    "v1": ("mik_moe:644634", "mik_moe:650353"),
}


def sample_states(model, deck_a_id, deck_b_id, seeds):
    da = load_deck(DB, deck_a_id).cards
    db_ = load_deck(DB, deck_b_id).cards
    samples = []  # (score_for_p0, p0_won)
    for i, seed in enumerate(seeds):
        engine = GameEngine(RandomSource(seed), card_effects=LIB)
        engine.new_game(da, db_)
        agents = [HeuristicAgent(card_effects=LIB), HeuristicAgent(card_effects=LIB)]
        n_before = len(samples)
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
            if engine.state.phase != "game_over" and engine.state.turn >= 3:
                s = predict(model, engine.state.visible_state(0))
                samples.append((s, None))
        w = engine.state.winner
        if w is None:  # 平局：本轮采样作废
            del samples[n_before:]
            continue
        idx = len(samples) - 1
        while idx >= n_before and samples[idx][1] is None:
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


def main():
    model_path = Path(sys.argv[1])
    model = load_model(model_path)
    print(f"模型：{model_path.name}（format {model.meta.get('format', '?')}）")
    verdicts = {}
    for tag, (a_id, b_id) in MATCHUPS.items():
        samples = sample_states(model, a_id, b_id,
                                [SEED0 + i for i in range(N_GAMES)])
        scores = [s for s, _ in samples]
        finite = all(isinstance(s, float) and abs(s) < 1e9 for s in scores)
        var = max(scores) - min(scores) if scores else 0.0
        a = auc(samples)
        verdicts[tag] = a
        print(f"[{tag}] {a_id}×{b_id}：n={len(samples)} 有限={finite} "
              f"极差={var:.4f} AUC={a:.4f}")
    gate_auc = verdicts["v2.x"]
    passed = gate_auc is not None and gate_auc >= GATE
    print(f"过线判据（预注册）：v2.x AUC ≥ {GATE} → "
          f"{'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
