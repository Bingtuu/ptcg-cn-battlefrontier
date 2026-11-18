"""task 155 WP3：训练 v3——分块两遍流式岭回归（λ 六档，D3-4 非复算面延续）。

验收口径（tasks/task 155.md 验收 3）：分块两遍流式与全量矩阵参考实现
（同 λ）对拍 np.allclose 紧容差 / λ 候选扩展后选择规则（最小验证 MSE、
并列小 λ）/ meta 必含 card_vocab/zones/rows/rows_total/games/pairs/λ/
train+val MSE/baseline_mse/split_seed / 死维度警戒沿用（meta["warning"] +
CLI 退出码 2）/ 按局划分与同局抽样语义沿用 v1（同局不跨集；subsample_rows
流式等价）/ v1 dict 行喂 v3 训练显式 ValueError、v3 数据喂 v1 load_dataset
显式报错。测试数据为合成小数据（3 对 × 20 局 × 4 行，vocab 4 词 = 52 维），
参考实现全量物化（测试侧允许；训练侧 train_v3 禁止整读——见模块 docstring）。
"""

import json
from pathlib import Path

import numpy as np
import pytest

from battlefrontier.agent.eval_features import EVAL_V3_ZONES, eval_v3_names
from battlefrontier.cli import main as cli_main
from battlefrontier.learn import load_dataset, split_by_game, subsample_rows, train_v3
from battlefrontier.learn.model import MODEL_FORMAT_V3, save_model
from battlefrontier.learn.train import (
    DEFAULT_SPLIT_SEED,
    DEFAULT_SUBSAMPLE_SEED,
    _select_lambda,
)

VOCAB = ("卡甲", "卡乙", "卡丙", "卡丁")
NAMES = eval_v3_names(VOCAB)          # 36 基座 + 4 区 × 4 词 = 52 维
D = len(NAMES)


def _sig_rows(n_games: int = 20, n_pairs: int = 3, per_game: int = 4,
              seed0: int = 5000) -> list[dict]:
    """有信号合成 v3 行：label 由 diff 决定；特征非恒常、无精确共线。"""
    rows = []
    for g in range(n_games):
        pair, seed = g % n_pairs, seed0 + g
        diff = float((g % 7) - 3)                     # -3..3
        label = 1.0 if diff > 0 else (0.0 if diff < 0 else 0.5)
        for t in range(per_game):
            feats = [0.0] * D
            feats[0] = diff
            feats[1] = 0.5 * diff + 0.13 * (t + 1)
            feats[36] = float((g + t) % 2)            # cid_own_hand_卡甲
            feats[40] = float((g * 3 + t) % 5)        # cid_own_board_卡甲
            rows.append({"pair_index": pair, "seed": seed, "turn": t + 1,
                         "player": t % 2, "features": feats,
                         "action": {"kind": "end_turn"}, "label": label})
    return rows


def _const_rows(n_games: int = 20, n_pairs: int = 3, per_game: int = 4,
                seed0: int = 7000) -> list[dict]:
    """纯噪声合成 v3 行：特征全常数（不可学），标签按局交替 0/1。"""
    rows = []
    for g in range(n_games):
        label = 1.0 if g % 2 else 0.0
        for t in range(per_game):
            rows.append({"pair_index": g % n_pairs, "seed": seed0 + g,
                         "turn": t + 1, "player": t % 2,
                         "features": [1.0] * D,
                         "action": {"kind": "end_turn"}, "label": label})
    return rows


def _write_v3(data_dir: Path, rows: list[dict], names: tuple[str, ...] = NAMES) -> None:
    """按配对分文件落 v3 JSONL：首行 bf-collect-v3 header，数据行位置 list。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    by_pair: dict[int, list[dict]] = {}
    for r in rows:
        by_pair.setdefault(r["pair_index"], []).append(r)
    for pair, pair_rows in sorted(by_pair.items()):
        path = data_dir / f"pair-{pair}-测试A{pair}x测试B{pair}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "header", "format": "bf-collect-v3",
                                 "feature_names": list(names)},
                                ensure_ascii=False, sort_keys=True) + "\n")
            for r in pair_rows:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def _reference(rows: list[dict], *, split_seed: int = DEFAULT_SPLIT_SEED,
               lambdas: tuple[float, ...] = train_v3.LAMBDAS_V3,
               max_rows_per_game: int | None = None,
               subsample_seed: int = DEFAULT_SUBSAMPLE_SEED) -> dict:
    """全量 numpy 参考实现（测试侧）：与 train_v3 同口径——先按局抽样 →
    split_by_game 按局 80/20 → 训练集 mean/std（常数维置 1）→ 逐 λ
    闭式解（截距不正则化）→ 验证 MSE 最小并列取小 λ。
    """
    if max_rows_per_game is not None:
        rows = subsample_rows(rows, max_rows_per_game, subsample_seed)
    train_rows, val_rows = split_by_game(rows, split_seed=split_seed)
    x_tr = np.asarray([r["features"] for r in train_rows], dtype=np.float64)
    y_tr = np.asarray([r["label"] for r in train_rows], dtype=np.float64)
    x_va = np.asarray([r["features"] for r in val_rows], dtype=np.float64)
    y_va = np.asarray([r["label"] for r in val_rows], dtype=np.float64)
    mean = x_tr.mean(axis=0)
    std = x_tr.std(axis=0)
    std[std == 0.0] = 1.0
    z_tr = np.column_stack([(x_tr - mean) / std, np.ones(len(x_tr))])
    z_va = np.column_stack([(x_va - mean) / std, np.ones(len(x_va))])

    def fit(lam: float) -> np.ndarray:
        a = z_tr.T @ z_tr
        for i in range(len(mean)):
            a[i, i] += lam
        return np.linalg.solve(a, z_tr.T @ y_tr)

    val_mses = []
    weights = []
    for lam in lambdas:
        w = fit(lam)
        weights.append(w)
        val_mses.append(float(((z_va @ w - y_va) ** 2).mean()))
    lam = _select_lambda(list(zip(lambdas, val_mses)))
    w = weights[lambdas.index(lam)]
    return {
        "baseline_mse": float(((y_va - y_tr.mean()) ** 2).mean()),
        "lambda": lam,
        "mean": mean,
        "std": std,
        "train_mse": float(((z_tr @ w - y_tr) ** 2).mean()),
        "val_mse": float(((z_va @ w - y_va) ** 2).mean()),
        "weights": w,
    }


# ── 分块两遍流式 vs 全量矩阵参考实现 ──────────────────────────

def test_分块两遍对拍_全量参考实现(tmp_path, monkeypatch):
    """3 对 × 20 局合成数据：weights/mean/std/λ/MSE 与全量参考逐位一致
    （紧容差）；CHUNK_ROWS 压到 3 强制多 chunk 路径。"""
    rows = _sig_rows()
    _write_v3(tmp_path, rows)
    monkeypatch.setattr(train_v3, "CHUNK_ROWS", 3)
    model = train_v3.train_model_v3(tmp_path, code_version="test")
    ref = _reference(rows)
    assert np.allclose(model.weights[:-1], ref["weights"][:-1], atol=1e-10)
    assert abs(model.weights[-1] - ref["weights"][-1]) < 1e-10
    assert np.allclose(model.mean, ref["mean"], atol=1e-10)
    assert np.allclose(model.std, ref["std"], atol=1e-10)
    assert model.meta["lambda"] == ref["lambda"]
    assert model.meta["train_mse"] == pytest.approx(ref["train_mse"], abs=1e-12)
    assert model.meta["val_mse"] == pytest.approx(ref["val_mse"], abs=1e-12)
    assert model.meta["baseline_mse"] == pytest.approx(ref["baseline_mse"],
                                                       abs=1e-12)


# ── λ 候选六档与选择规则 ────────────────────────────────────

def test_λ候选六档():
    assert train_v3.LAMBDAS_V3 == (0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0)


def test_λ选定_全并列取最小(tmp_path):
    """特征全常数 → 标准化后全零，所有 λ 的解与验证 MSE 相同 → 并列取 0.1。"""
    rows = _const_rows()
    _write_v3(tmp_path, rows)
    model = train_v3.train_model_v3(tmp_path, code_version="test")
    assert model.meta["lambda"] == 0.1


def test_λ选定_与全量参考同选择(tmp_path):
    rows = _sig_rows()
    _write_v3(tmp_path, rows)
    model = train_v3.train_model_v3(tmp_path, code_version="test")
    assert model.meta["lambda"] == _reference(rows)["lambda"]
    assert model.meta["lambda"] in train_v3.LAMBDAS_V3


# ── meta 落账与资产 format ─────────────────────────────────

def test_meta必含字段_资产format_v3(tmp_path):
    rows = _sig_rows()
    _write_v3(tmp_path, rows)
    model = train_v3.train_model_v3(tmp_path, code_version="test",
                                    pool="config/target-pool.v2.yml")
    m = model.meta
    for key in ("card_vocab", "zones", "rows", "rows_total", "games", "pairs",
                "lambda", "train_mse", "val_mse", "baseline_mse", "split_seed",
                "feature_set", "code_version", "pool", "max_rows_per_game",
                "subsample_seed", "train_games", "val_games", "seed_min",
                "seed_max", "warning"):
        assert key in m, f"meta 缺字段 {key}"
    assert m["feature_set"] == "v3"
    assert m["card_vocab"] == list(VOCAB)
    assert m["zones"] == list(EVAL_V3_ZONES)
    assert m["rows"] == len(rows)
    assert m["rows_total"] == len(rows)
    assert m["games"] == 20 and m["pairs"] == 3
    assert m["train_games"] + m["val_games"] == 20
    assert model.feature_names == NAMES
    assert len(model.weights) == D + 1
    out = tmp_path / "model.json"
    save_model(model, out, model_format=MODEL_FORMAT_V3)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["format"] == "bf-linear-eval-v3"
    assert payload["feature_names"] == list(NAMES)
    assert payload["meta"]["feature_set"] == "v3"


def test_训练确定性_两跑资产逐字节一致(tmp_path):
    rows = _sig_rows()
    _write_v3(tmp_path, rows)
    m1 = train_v3.train_model_v3(tmp_path, code_version="test")
    m2 = train_v3.train_model_v3(tmp_path, code_version="test")
    assert m1.weights == m2.weights and m1.mean == m2.mean and m1.std == m2.std
    o1, o2 = tmp_path / "m1.json", tmp_path / "m2.json"
    save_model(m1, o1, model_format=MODEL_FORMAT_V3)
    save_model(m2, o2, model_format=MODEL_FORMAT_V3)
    assert o1.read_bytes() == o2.read_bytes()


# ── 死维度警戒沿用 ─────────────────────────────────────────

def test_死维度警戒_meta_warning且CLI退出码2(tmp_path):
    rows = _const_rows()
    _write_v3(tmp_path, rows)
    out = tmp_path / "model.json"
    rc = cli_main(["train-eval", "--data", str(tmp_path), "--out", str(out),
                   "--feature-set", "v3", "--code-version", "test"])
    assert rc == 2
    assert out.exists()  # 模型照常产出，如实落账不强行失败
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["meta"]["warning"] is not None


def test_有信号数据_无警戒_CLI退出码0(tmp_path):
    rows = _sig_rows()
    _write_v3(tmp_path, rows)
    out = tmp_path / "model.json"
    rc = cli_main(["train-eval", "--data", str(tmp_path), "--out", str(out),
                   "--feature-set", "v3", "--code-version", "test"])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["meta"]["warning"] is None
    assert payload["meta"]["val_mse"] < payload["meta"]["baseline_mse"]


# ── 按局划分 / 按局抽样语义沿用 ─────────────────────────────

def test_抽样流式与subsample_rows全量等价(tmp_path):
    """max_rows_per_game=3：分块流式产物与「物化行 + subsample_rows +
    split_by_game」全量参考一致；meta rows/rows_total 双口径正确。"""
    rows = _sig_rows(n_games=12, per_game=10)
    _write_v3(tmp_path, rows)
    model = train_v3.train_model_v3(tmp_path, code_version="test",
                                    max_rows_per_game=3)
    ref = _reference(rows, max_rows_per_game=3)
    assert np.allclose(model.weights[:-1], ref["weights"][:-1], atol=1e-10)
    assert model.meta["lambda"] == ref["lambda"]
    assert model.meta["rows_total"] == 12 * 10
    assert model.meta["rows"] == 12 * 3


def test_按局划分_同局不跨集且与v1一致(tmp_path):
    rows = _sig_rows()
    _write_v3(tmp_path, rows)
    model = train_v3.train_model_v3(tmp_path, code_version="test")
    _, val_rows = split_by_game(rows, split_seed=DEFAULT_SPLIT_SEED)
    assert model.meta["val_games"] == len({(r["pair_index"], r["seed"])
                                           for r in val_rows})
    assert model.meta["train_games"] == 20 - model.meta["val_games"]


# ── 数据形态互斥（不猜纪律）────────────────────────────────

def test_v1数据喂v3训练_显式ValueError(tmp_path):
    """v1 dict 行（无 header）目录 → train_model_v3 显式报错。"""
    from tests.test_learn_train import _write_jsonl

    data = tmp_path / "v1data"
    _write_jsonl(data, [
        {"pair_index": 0, "seed": 1, "turn": 1, "player": 0,
         "features": {"hand_count": 1.0}, "action": {"kind": "end_turn"},
         "label": 1.0}])
    with pytest.raises(ValueError, match="header"):
        train_v3.train_model_v3(data, code_version="test")


def test_v3数据喂v1训练_显式ValueError(tmp_path):
    """v3 目录喂 v1 load_dataset（--feature-set 缺省 v1 的 CLI 路径）显式报错。"""
    rows = _sig_rows()
    _write_v3(tmp_path, rows)
    with pytest.raises(ValueError):
        load_dataset(tmp_path)
    out = tmp_path / "model.json"
    rc = cli_main(["train-eval", "--data", str(tmp_path), "--out", str(out),
                   "--code-version", "test"])  # 缺省 --feature-set v1
    assert rc == 1


def test_文件头与行宽校验_显式ValueError(tmp_path):
    rows = _sig_rows()
    _write_v3(tmp_path, rows)
    # 数据行宽度与 header 名数不符
    bad = tmp_path / "pair-9-坏x坏.jsonl"
    bad.write_text(
        json.dumps({"type": "header", "format": "bf-collect-v3",
                    "feature_names": list(NAMES)}, ensure_ascii=False) + "\n"
        + json.dumps({"pair_index": 9, "seed": 1, "features": [1.0, 2.0],
                      "label": 1.0}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="宽度"):
        train_v3.train_model_v3(tmp_path, code_version="test")
    # header format 错误
    bad.write_text(
        json.dumps({"type": "header", "format": "bf-collect-v1",
                    "feature_names": list(NAMES)}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="bf-collect-v3"):
        train_v3.train_model_v3(tmp_path, code_version="test")


def test_空目录_显式ValueError(tmp_path):
    with pytest.raises(ValueError, match="pair-"):
        train_v3.train_model_v3(tmp_path, code_version="test")
