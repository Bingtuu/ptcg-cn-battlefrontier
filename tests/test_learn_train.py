"""task 051 · M11 WP2：岭回归训练器 + 按局划分 + λ 选定 + 死维度警戒（D-M11-3）。

验收口径见 `tasks/task 051.md`：训练确定性（同数据两跑模型资产逐字节一致）/
按局 80/20 划分（(pair_index, seed) 为局 id，同局样本不跨集）/ λ ∈ {0.1,1,10,100}
按验证集 MSE 确定性选定（并列取小）/ 死维度警戒（验证集 MSE 不优于常数基线 →
warning 字段 + CLI 退出码 2，模型仍照常产出）。
"""

import json
from pathlib import Path

from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.cli import main as cli_main
from battlefrontier.learn import (
    DEFAULT_SPLIT_SEED,
    DEFAULT_SUBSAMPLE_SEED,
    LAMBDAS,
    LinearModel,
    load_dataset,
    load_model,
    save_model,
    split_by_game,
    subsample_rows,
    train_model,
)
from battlefrontier.learn.train import _ridge_fit, _select_lambda


def _feats(**over: float) -> dict[str, float]:
    return {name: float(over.get(name, 0.0)) for name in FEATURE_NAMES}


def _row(pair: int, seed: int, turn: int, label: float, **feat_over: float) -> dict:
    return {"pair_index": pair, "seed": seed, "turn": turn, "player": turn % 2,
            "features": _feats(**feat_over), "action": {"kind": "end_turn"},
            "label": label}


def _good_rows(n_games: int = 20, per_game: int = 4) -> list[dict]:
    """有信号合成数据：label 由 prize_diff 决定（线性可学），3 个配对。"""
    rows = []
    for g in range(n_games):
        pair, seed = g % 3, 1000 + g
        diff = float((g % 7) - 3)  # -3..3
        label = 1.0 if diff > 0 else (0.0 if diff < 0 else 0.5)
        for t in range(per_game):
            rows.append(_row(pair, seed, t + 1, label, prize_diff=diff,
                             turn_norm=(t + 1) / 50))
    return rows


def _noise_rows(n_games: int = 10, per_game: int = 4) -> list[dict]:
    """纯噪声合成数据：特征全常数（不可学），标签按局交替 0/1。"""
    rows = []
    for g in range(n_games):
        label = 1.0 if g % 2 else 0.0
        for t in range(per_game):
            rows.append(_row(0, 2000 + g, t + 1, label))
    return rows


def _write_jsonl(data_dir: Path, rows: list[dict]) -> None:
    """按配对分文件落 JSONL（对齐产线 pair-<index>-<名A>x<名B>.jsonl 命名）。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    by_pair: dict[int, list[dict]] = {}
    for r in rows:
        by_pair.setdefault(r["pair_index"], []).append(r)
    for pair, pair_rows in sorted(by_pair.items()):
        path = data_dir / f"pair-{pair}-测试A{pair}x测试B{pair}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for r in pair_rows:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


# ── 按局划分 ──────────────────────────────────────────────

def test_按局划分_训练验证局id无交集():
    rows = _good_rows(20)
    train, val = split_by_game(rows, split_seed=123)
    train_ids = {(r["pair_index"], r["seed"]) for r in train}
    val_ids = {(r["pair_index"], r["seed"]) for r in val}
    assert train_ids.isdisjoint(val_ids)
    assert train_ids | val_ids == {(r["pair_index"], r["seed"]) for r in rows}
    # 80/20：20 局 → 16 训练 / 4 验证；每局样本整体归属一侧（不跨集）
    assert len(train_ids) == 16 and len(val_ids) == 4
    assert len(train) == 16 * 4 and len(val) == 4 * 4


def test_按局划分_确定性_同split_seed同划分():
    rows = _good_rows(20)
    assert split_by_game(rows, split_seed=7) == split_by_game(rows, split_seed=7)


def test_按局划分_局数不足_显式报错():
    import pytest

    with pytest.raises(ValueError, match="局数不足"):
        split_by_game(_good_rows(1))


# ── λ 选定 ────────────────────────────────────────────────

def test_λ选定_确定性且在候选集内():
    rows = _good_rows()
    m1 = train_model(rows, code_version="test")
    m2 = train_model(rows, code_version="test")
    assert m1.meta["lambda"] == m2.meta["lambda"]
    assert m1.meta["lambda"] in LAMBDAS
    assert LAMBDAS == (0.1, 1.0, 10.0, 100.0)


def test_λ选定_并列取小():
    assert _select_lambda([(0.1, 0.5), (1.0, 0.5), (10.0, 0.4), (100.0, 0.4)]) == 10.0
    assert _select_lambda([(0.1, 0.3), (1.0, 0.3), (10.0, 0.3)]) == 0.1


# ── 训练质量与标准化 ──────────────────────────────────────

def test_训练_有信号数据_验证MSE优于常数基线():
    model = train_model(_good_rows(), code_version="test")
    assert model.meta["warning"] is None
    assert model.meta["val_mse"] < model.meta["baseline_mse"]
    # 信号方向正确：prize_diff 权重为正
    idx = model.feature_names.index("prize_diff")
    assert model.weights[idx] > 0.0


def test_常数维度_std置1防除零():
    """_good_rows 中 hand_diff 等维度恒为 0（方差 0）→ std 落 1.0 防除零。"""
    model = train_model(_good_rows(), code_version="test")
    idx = model.feature_names.index("hand_diff")
    assert model.mean[idx] == 0.0 and model.std[idx] == 1.0


# ── 训练确定性 ────────────────────────────────────────────

def test_训练确定性_同数据两跑模型资产逐字节一致(tmp_path):
    rows = _good_rows()
    m1 = train_model(rows, split_seed=99, code_version="test")
    m2 = train_model(list(rows), split_seed=99, code_version="test")
    p1, p2 = tmp_path / "m1.json", tmp_path / "m2.json"
    save_model(m1, p1)
    save_model(m2, p2)
    assert p1.read_bytes() == p2.read_bytes()


# ── 死维度警戒 ────────────────────────────────────────────

def test_死维度警戒_纯噪声标签_warning落meta():
    """特征无可解释方差：模型退化为均值预测器，val MSE 不优于常数基线 → warning。"""
    model = train_model(_noise_rows(), code_version="test")
    assert model.meta["warning"]
    assert model.meta["val_mse"] >= model.meta["baseline_mse"]


def test_meta_字段齐全():
    model = train_model(_good_rows(), split_seed=77, code_version="test",
                        pool="config/target-pool.v1.yml")
    meta = model.meta
    assert meta["split_seed"] == 77
    assert meta["code_version"] == "test"
    assert meta["pool"] == "config/target-pool.v1.yml"
    assert meta["games"] == 20 and meta["pairs"] == 3
    assert meta["rows"] == 80
    assert meta["seed_min"] == 1000 and meta["seed_max"] == 1019
    assert meta["train_games"] + meta["val_games"] == 20
    for k in ("lambda", "train_mse", "val_mse", "baseline_mse"):
        assert isinstance(meta[k], float)
    assert meta["warning"] is None


# ── 数据装载 ──────────────────────────────────────────────

def test_load_dataset_特征键不符_显式报错(tmp_path):
    rows = _good_rows(4)
    rows[0]["features"]["坏特征"] = rows[0]["features"].pop("prize_diff")
    _write_jsonl(tmp_path / "data", rows)
    import pytest

    with pytest.raises(ValueError, match="特征"):
        load_dataset(tmp_path / "data")


def test_load_dataset_空目录_显式报错(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="pair-"):
        load_dataset(tmp_path / "不存在")


# ── CLI ───────────────────────────────────────────────────

def test_cli_train_eval_冒烟(tmp_path):
    data, out = tmp_path / "data", tmp_path / "models" / "eval-linear-v1.json"
    _write_jsonl(data, _good_rows())
    rc = cli_main(["train-eval", "--data", str(data), "--out", str(out),
                   "--code-version", "test"])
    assert rc == 0
    assert out.exists()
    model = load_model(out)
    assert isinstance(model, LinearModel)
    assert model.meta["games"] == 20 and model.meta["warning"] is None
    assert model.meta["code_version"] == "test"
    assert model.meta["split_seed"] == DEFAULT_SPLIT_SEED


def test_cli_train_eval_死维度警戒_退出码2且模型照常产出(tmp_path):
    data, out = tmp_path / "data", tmp_path / "m.json"
    _write_jsonl(data, _noise_rows())
    rc = cli_main(["train-eval", "--data", str(data), "--out", str(out),
                   "--code-version", "test"])
    assert rc == 2
    assert out.exists()  # 不强行失败——模型照常产出，如实落账
    assert load_model(out).meta["warning"]


def test_cli_train_eval_无数据_退出码1(tmp_path, capsys):
    rc = cli_main(["train-eval", "--data", str(tmp_path / "空"),
                   "--out", str(tmp_path / "m.json")])
    assert rc == 1
    assert "错误" in capsys.readouterr().out


# ── 按局行数上限（子采样，D-M11-1 样本量口径：150–200 万对线性族充足）──

def _game_ids(rows: list[dict]) -> set[tuple[int, int]]:
    return {(r["pair_index"], r["seed"]) for r in rows}


def test_子采样_cap生效_每局至多N行():
    rows = _good_rows(20, per_game=10)
    out = subsample_rows(rows, max_rows_per_game=3, subsample_seed=5)
    counts: dict[tuple[int, int], int] = {}
    for r in out:
        gid = (r["pair_index"], r["seed"])
        counts[gid] = counts.get(gid, 0) + 1
    assert len(out) == 20 * 3
    assert set(counts) == _game_ids(rows)          # 局集合不丢
    assert all(c == 3 for c in counts.values())    # 每局恰为 cap（原 10 > 3）


def test_子采样_行数不超cap的局全留():
    rows = _good_rows(10, per_game=4)
    assert subsample_rows(rows, max_rows_per_game=4, subsample_seed=5) == rows
    assert subsample_rows(rows, max_rows_per_game=9, subsample_seed=5) == rows


def test_子采样_确定性_同参两跑一致():
    rows = _good_rows(10, per_game=8)
    a = subsample_rows(rows, max_rows_per_game=3, subsample_seed=7)
    b = subsample_rows(list(rows), max_rows_per_game=3, subsample_seed=7)
    assert a == b


def test_子采样_保原序_不同subsample_seed选取不同():
    rows = _good_rows(5, per_game=10)
    out = subsample_rows(rows, max_rows_per_game=4, subsample_seed=1)
    for gid in _game_ids(rows):
        orig = [r for r in rows if (r["pair_index"], r["seed"]) == gid]
        got = [r for r in out if (r["pair_index"], r["seed"]) == gid]
        idxs = [orig.index(r) for r in got]  # 同局行 turn 各异，dict 等值可定位
        assert idxs == sorted(idxs)          # 选取后保原序
    assert subsample_rows(rows, 4, 1) != subsample_rows(rows, 4, 2)


def test_子采样_非法cap_显式报错():
    import pytest

    with pytest.raises(ValueError, match="max_rows_per_game"):
        subsample_rows(_good_rows(4), max_rows_per_game=0)


def test_train_model_子采样_meta落账():
    rows = _good_rows(20, per_game=10)  # 200 行
    m = train_model(rows, code_version="t", max_rows_per_game=4, subsample_seed=9)
    assert m.meta["rows_total"] == 200
    assert m.meta["rows"] == 80           # 实际用于训练的行数
    assert m.meta["max_rows_per_game"] == 4
    assert m.meta["subsample_seed"] == 9
    assert m.meta["games"] == 20          # 局数不因采样缩水


def test_train_model_默认None_不采样行为不变():
    rows = _good_rows()
    m_default = train_model(rows, code_version="t")
    m_none = train_model(rows, code_version="t", max_rows_per_game=None)
    assert m_default.meta["rows_total"] == m_default.meta["rows"] == 80
    assert m_default.meta["max_rows_per_game"] is None
    assert m_default.meta["subsample_seed"] == DEFAULT_SUBSAMPLE_SEED
    assert m_default == m_none


def test_训练确定性_带子采样两跑模型逐字节一致(tmp_path):
    rows = _good_rows(20, per_game=10)
    m1 = train_model(rows, code_version="t", max_rows_per_game=4, subsample_seed=3)
    m2 = train_model(list(rows), code_version="t", max_rows_per_game=4,
                     subsample_seed=3)
    p1, p2 = tmp_path / "s1.json", tmp_path / "s2.json"
    save_model(m1, p1)
    save_model(m2, p2)
    assert p1.read_bytes() == p2.read_bytes()


# ── load 瘦身 ─────────────────────────────────────────────

def test_load_dataset_只保留训练所需字段(tmp_path):
    data = tmp_path / "data"
    _write_jsonl(data, _good_rows(4))
    rows = load_dataset(data)
    assert len(rows) == 16
    assert all(set(r) == {"pair_index", "seed", "features", "label"} for r in rows)


# ── _ridge_fit 上三角优化对拍 ─────────────────────────────

def _ridge_fit_ref(xs: list[list[float]], ys: list[float], lam: float) -> list[float]:
    """优化前全量累计参考实现（逐行复刻旧版：i/j 全维双重循环）。"""
    from battlefrontier.learn.train import _solve

    d = len(xs[0]) + 1
    a = [[0.0] * d for _ in range(d)]
    b = [0.0] * d
    for x, y in zip(xs, ys, strict=True):
        v = x + [1.0]
        for i in range(d):
            b[i] += v[i] * y
            ai, vi = a[i], v[i]
            for j in range(d):
                ai[j] += vi * v[j]
    for i in range(d - 1):
        a[i][i] += lam
    return _solve(a, b)


def test_ridge_fit_上三角优化_与参考实现逐位一致():
    rows = _good_rows(10)
    xs = [[r["features"][n] for n in FEATURE_NAMES] for r in rows]
    ys = [r["label"] for r in rows]
    for lam in LAMBDAS:
        assert _ridge_fit(xs, ys, lam) == _ridge_fit_ref(xs, ys, lam)


# ── CLI 子采样参数 ─────────────────────────────────────────

def test_cli_train_eval_max_rows_per_game(tmp_path):
    data, out = tmp_path / "data", tmp_path / "m.json"
    _write_jsonl(data, _good_rows(20, per_game=10))
    rc = cli_main(["train-eval", "--data", str(data), "--out", str(out),
                   "--code-version", "test",
                   "--max-rows-per-game", "5", "--subsample-seed", "11"])
    assert rc == 0
    meta = load_model(out).meta
    assert meta["rows_total"] == 200 and meta["rows"] == 100
    assert meta["max_rows_per_game"] == 5 and meta["subsample_seed"] == 11
