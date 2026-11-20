# task 155a 非线性评估器天花板 spike（预注册：docs/digs/2026-11-20-t155a-nl-eval-spike.md）
# 判别「0.90 门不可达」= 模型类（线性天花板）还是度量尺（v2.x 不可约随机性）。
# 探索性探针：不落 models/ 版本控制、不改引擎/DSL 代码；判决 JSON 落 results/。
# 用法: .venv/Scripts/python.exe -X utf8 .kimi-code/t155a_nl_spike.py
import json
import random
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path("C:/Vibe Project/Pokebattle")
sys.path.insert(0, str(ROOT))

import numpy as np
import torch

from battlefrontier.agent.heuristic import HeuristicAgent
from battlefrontier.dsl.loader import load_card_dir
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.learn.model import load_model, predict
from battlefrontier.runner.experiment import load_deck

DATA = ROOT / "results/m11-v2x-v3data"
DB = "C:/Vibe Project/Pokearena/data/ptcg-cn.db"
LIB = load_card_dir(ROOT / "cards")
OUT = ROOT / "results/t155a-spike-verdict.json"

SEED_SPLIT = 20261016
SEED_TORCH = 20261120
EPOCHS = 3
BATCH = 4096
LR = 1e-3
N_GAMES = 60
SEED0 = 800000
MATCHUP = ("mik_moe:711854", "mik_moe:676344")  # 沙奈朵 × 多龙巴鲁托黑夜魔灵
THRESHOLD = 0.85


def load_xy():
    """分块流式读 v3 数据 → (X float32 n×560, y float32, game_ids list)。"""
    files = sorted(DATA.glob("pair-*.jsonl"))
    x_chunks, y_chunks, g_chunks = [], [], []
    t0 = time.time()
    for fi, f in enumerate(files):
        buf_x, buf_y, buf_g = [], [], []
        with f.open(encoding="utf-8") as fh:
            header = json.loads(fh.readline())
            n_feat = len(header["feature_names"])
            for ln, line in enumerate(fh, 2):
                if not line.strip():
                    continue
                row = json.loads(line)
                buf_x.append(row["features"])
                buf_y.append(row["label"])
                buf_g.append((row["pair_index"], row["seed"]))
        x_chunks.append(np.asarray(buf_x, dtype=np.float32))
        y_chunks.append(np.asarray(buf_y, dtype=np.float32))
        g_chunks.extend(buf_g)
        print(f"[load] {fi+1}/{len(files)} {f.name} 累计 {sum(c.shape[0] for c in x_chunks)} 行 "
              f"({time.time()-t0:.0f}s)", flush=True)
    X = np.concatenate(x_chunks)
    y = np.concatenate(y_chunks)
    assert X.shape[1] == n_feat
    return X, y, g_chunks


def split_mask(game_ids):
    """按局 80/20（split_by_game 同口径：sorted + Random(split_seed).shuffle）。"""
    uniq = sorted(set(game_ids))
    shuffled = list(uniq)
    random.Random(SEED_SPLIT).shuffle(shuffled)
    n_train = max(1, min(len(uniq) - 1, int(len(uniq) * 0.8)))
    train_ids = set(shuffled[:n_train])
    return np.array([g in train_ids for g in game_ids])


class MLP(torch.nn.Module):
    def __init__(self, d_in):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(d_in, 128), torch.nn.ReLU(),
            torch.nn.Linear(128, 64), torch.nn.ReLU(),
            torch.nn.Linear(64, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


def train_mlp(X, y, mask):
    mean = X[mask].mean(0)
    std = X[mask].std(0)
    std[std == 0] = 1.0
    X -= mean  # 原地标准化（省 9GB 副本；mean/std 已留存供探针复用）
    X /= std
    xt, yt = torch.from_numpy(X[mask]), torch.from_numpy(y[mask])
    xv, yv = torch.from_numpy(X[~mask]), torch.from_numpy(y[~mask])
    torch.manual_seed(SEED_TORCH)
    model = MLP(X.shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    lossf = torch.nn.MSELoss()
    n = xt.shape[0]
    per_epoch = []
    for ep in range(EPOCHS):
        model.train()
        t0 = time.time()
        for i in range(0, n - BATCH + 1, BATCH):
            opt.zero_grad()
            loss = lossf(model(xt[i:i + BATCH]), yt[i:i + BATCH])
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            val_mse = lossf(model(xv), yv).item()
        per_epoch.append(val_mse)
        print(f"[train] epoch {ep+1}/{EPOCHS} val_mse={val_mse:.6f} ({time.time()-t0:.0f}s)",
              flush=True)
    return model, mean, std, per_epoch


def sample_states(score_fn, deck_a_id, deck_b_id, seeds):
    """t150 gate 采样协议复制（启发式自对局、turn>=3 逐决策、p0 视角、平局局作废）。"""
    da = load_deck(DB, deck_a_id).cards
    db_ = load_deck(DB, deck_b_id).cards
    samples = []
    for seed in seeds:
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
                samples.append((score_fn(engine.state.visible_state(0)), None))
        w = engine.state.winner
        if w is None:
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
    X, y, game_ids = load_xy()
    print(f"[load] X={X.shape} y={y.shape} 局数={len(set(game_ids))}", flush=True)
    mask = split_mask(game_ids)
    print(f"[split] train={mask.sum()} val={(~mask).sum()}（按局 80/20, seed={SEED_SPLIT}）",
          flush=True)

    model, mean, std, per_epoch = train_mlp(X, y, mask)
    model.eval()

    def mlp_score(view):
        with torch.no_grad():
            feats = feature_list(view, mean, std)
            v = model(torch.from_numpy(feats[None, :])).item()
        return min(1.0, max(0.0, v))

    seeds = [SEED0 + i for i in range(N_GAMES)]
    print(f"[probe] MLP v2.x {MATCHUP} × {N_GAMES} 局…", flush=True)
    mlp_samples = sample_states(mlp_score, *MATCHUP, seeds)
    mlp_auc = auc(mlp_samples)
    print(f"[probe] MLP n={len(mlp_samples)} AUC={mlp_auc:.4f}", flush=True)

    ridge = load_model(ROOT / "models/eval-linear-v3.json")
    print("[probe] ridge v3 同 60 局…", flush=True)
    ridge_samples = sample_states(lambda v: predict(ridge, v), *MATCHUP, seeds)
    ridge_auc = auc(ridge_samples)
    print(f"[probe] ridge v3 n={len(ridge_samples)} AUC={ridge_auc:.4f}", flush=True)

    verdict = "A_prime_full" if mlp_auc >= THRESHOLD else "gate_recalibration"
    out = {
        "auc_mlp": mlp_auc, "auc_ridge_v3_same_probe": ridge_auc,
        "threshold": THRESHOLD, "verdict": verdict,
        "n_games": N_GAMES, "n_samples_mlp": len(mlp_samples),
        "per_epoch_val_mse": per_epoch,
        "matchup": MATCHUP, "seed_split": SEED_SPLIT, "seed_torch": SEED_TORCH,
        "epochs": EPOCHS, "batch": BATCH, "lr": LR,
        "pre_registration": "docs/digs/2026-11-20-t155a-nl-eval-spike.md",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[verdict] MLP AUC {mlp_auc:.4f} vs 阈值 {THRESHOLD} → {verdict}", flush=True)
    print(f"[verdict] JSON: {OUT}", flush=True)
    return 0


def feature_list(view, mean, std):
    """v3 特征 → 标准化 float32 向量（与训练同序 = eval_v3_names 序）。"""
    from battlefrontier.agent.eval_features import EVAL_V3_ZONES, feature_vector_v3
    feats = feature_vector_v3(view, _vocab(), zones=EVAL_V3_ZONES)
    names = _names()
    return ((np.array([feats[n] for n in names], dtype=np.float32) - mean) / std)


_VOCAB_CACHE = None
_NAMES_CACHE = None


def _vocab():
    global _VOCAB_CACHE
    if _VOCAB_CACHE is None:
        from battlefrontier.agent.policy_features import build_card_vocab
        _VOCAB_CACHE = build_card_vocab(ROOT / "config/target-pool.v2.yml", DB)
    return _VOCAB_CACHE


def _names():
    global _NAMES_CACHE
    if _NAMES_CACHE is None:
        from battlefrontier.agent.eval_features import eval_v3_names
        _NAMES_CACHE = eval_v3_names(_vocab())
    return _NAMES_CACHE


if __name__ == "__main__":
    sys.exit(main())
