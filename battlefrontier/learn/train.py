"""M11 学得评估器训练器（task 051 WP2，D-M11-3）：岭回归闭式解，位级确定。

- **闭式解** w = (XᵀX + λI)⁻¹Xᵀy：纯 Python 高斯消元（部分主元，31×31 小矩阵；
  特征 30 维 + 截距列，截距不正则化）——无迭代随机源，同数据同代码位级确定。
  （环境无 numpy 且约束不引新依赖；矩阵规模小，纯 Python 足够。）
- **特征标准化**：z-score，均值/方差从训练集算并存入模型资产；常数维度
  方差为 0 时 std 置 1 防除零。
- **按局划分**：(pair_index, seed) 为局 id，random.Random(split_seed) 洗牌后
  80/20 训练/验证划分——同局样本不跨集（防泄漏）；split_seed 钉死进 meta。
- **λ 选定**：候选 {0.1, 1, 10, 100} 按验证集 MSE 选定，并列取小 λ（确定）。
- **死维度警戒**（设计文档 §5 风险口径）：验证集 MSE 不优于常数基线（训练集
  均值预测器）MSE → meta["warning"] 落账；模型仍照常产出（不强行失败），
  CLI 退出码区分（2）。
- **按局行数上限**（task 051 增量：正式数据 744 万行远超 D-M11-1 的 150–200 万
  估算）：``max_rows_per_game`` 按局确定性抽样（每局 ≤ N 行，保文件内原顺序，
  抽样种子 pair_index×10⁶+seed+subsample_seed）；缺省 None = 全量行为不变。
- **load 瘦身**：只保留训练所需字段（pair_index/seed/features/label），
  action/turn/player 丢弃（schema 校验口径不变，仍校验原始行）。
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.learn.model import LinearModel

__all__ = [
    "DEFAULT_SPLIT_SEED",
    "DEFAULT_SUBSAMPLE_SEED",
    "LAMBDAS",
    "TRAIN_RATIO",
    "load_dataset",
    "split_by_game",
    "subsample_rows",
    "train_model",
]

LAMBDAS: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0)
TRAIN_RATIO = 0.8
DEFAULT_SPLIT_SEED = 20261016
DEFAULT_SUBSAMPLE_SEED = 20261017

_REQUIRED_KEYS = {"pair_index", "seed", "features", "label"}


def _validate_row(row: dict, source: str) -> None:
    missing = _REQUIRED_KEYS - row.keys()
    if missing:
        raise ValueError(f"{source}：数据行缺字段 {sorted(missing)}（不猜）")
    feat_keys = set(row["features"])
    if feat_keys != set(FEATURE_NAMES):
        raise ValueError(
            f"{source}：数据行特征键与 FEATURE_NAMES 不符（不猜）——"
            f"多出 {sorted(feat_keys - set(FEATURE_NAMES))} / "
            f"缺 {sorted(set(FEATURE_NAMES) - feat_keys)}")
    label = row["label"]
    if not isinstance(label, int | float) or not 0.0 <= label <= 1.0:
        raise ValueError(f"{source}：label {label!r} 不在 [0,1]（不猜）")


def load_dataset(data_dir: str | Path) -> list[dict]:
    """读目录下全部 pair-*.jsonl（文件名排序保确定序），逐行校验 schema。

    瘦身：只保留训练所需字段（pair_index/seed/features/label），action/turn/
    player 丢弃——744 万行级正式数据的内存口径（校验仍对原始行，口径不变）。
    """
    files = sorted(Path(data_dir).glob("pair-*.jsonl"))
    if not files:
        raise ValueError(f"{data_dir} 下无 pair-*.jsonl 数据文件")
    rows: list[dict] = []
    for f in files:
        for ln, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            _validate_row(row, f"{f.name}:{ln}")
            rows.append({"pair_index": row["pair_index"], "seed": row["seed"],
                         "features": row["features"], "label": row["label"]})
    return rows


def split_by_game(rows: list[dict], split_seed: int = DEFAULT_SPLIT_SEED,
                  train_ratio: float = TRAIN_RATIO) -> tuple[list[dict], list[dict]]:
    """按局 (pair_index, seed) 80/20 划分；同局样本不跨集。返回 (训练, 验证)。"""
    game_ids = sorted({(r["pair_index"], r["seed"]) for r in rows})
    if len(game_ids) < 2:
        raise ValueError(f"局数不足（{len(game_ids)} < 2）无法划分训练/验证集")
    shuffled = list(game_ids)
    random.Random(split_seed).shuffle(shuffled)
    n_train = max(1, min(len(game_ids) - 1, int(len(game_ids) * train_ratio)))
    train_ids = set(shuffled[:n_train])
    train = [r for r in rows if (r["pair_index"], r["seed"]) in train_ids]
    val = [r for r in rows if (r["pair_index"], r["seed"]) not in train_ids]
    return train, val


def subsample_rows(rows: list[dict], max_rows_per_game: int,
                   subsample_seed: int = DEFAULT_SUBSAMPLE_SEED) -> list[dict]:
    """按局行数上限确定性抽样：每局至多 N 行，选取后保文件内原顺序。

    行数 ≤ N 的局全留；否则 ``random.Random(pair_index×1_000_000 + seed +
    subsample_seed)`` 对行索引 ``sorted(rng.sample(range(n), N))`` 选取。
    局集合不丢（每局至少抽到 min(n, N) ≥ 1 行）。
    """
    if max_rows_per_game < 1:
        raise ValueError(f"max_rows_per_game 须 ≥ 1：{max_rows_per_game}（不猜）")
    groups: dict[tuple[int, int], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["pair_index"], r["seed"]), []).append(r)
    out: list[dict] = []
    for (pair_index, seed), game_rows in groups.items():
        n = len(game_rows)
        if n <= max_rows_per_game:
            out.extend(game_rows)
            continue
        rng = random.Random(pair_index * 1_000_000 + seed + subsample_seed)
        picked = sorted(rng.sample(range(n), max_rows_per_game))
        out.extend(game_rows[i] for i in picked)
    return out


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """高斯消元（部分主元）解 Ax=b；固定运算次序 → 位级确定。奇异矩阵显式报错。"""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if m[piv][col] == 0.0:
            raise ValueError(f"设计矩阵奇异（列 {col}；不猜）")
        m[col], m[piv] = m[piv], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / m[i][i]
    return x


def _ridge_fit(xs: list[list[float]], ys: list[float], lam: float) -> list[float]:
    """岭回归闭式解；末维为截距列（恒 1，不正则化）。

    正规方程只累加上三角（j≥i）再镜像拷贝到下三角：每元素求和次序不变、
    镜像是精确拷贝（非重算）→ 与全量累计逐位一致（测试对拍锚定），运算量减半。
    """
    d = len(xs[0]) + 1
    a = [[0.0] * d for _ in range(d)]
    b = [0.0] * d
    for x, y in zip(xs, ys, strict=True):
        v = x + [1.0]
        for i in range(d):
            b[i] += v[i] * y
            ai, vi = a[i], v[i]
            for j in range(i, d):
                ai[j] += vi * v[j]
    for i in range(d):
        for j in range(i):
            a[i][j] = a[j][i]
    for i in range(d - 1):
        a[i][i] += lam
    return _solve(a, b)


def _mse(weights: list[float], xs: list[list[float]], ys: list[float]) -> float:
    """末维截距的点积 MSE。"""
    total = 0.0
    for x, y in zip(xs, ys, strict=True):
        pred = weights[-1] + sum(w * v for w, v in zip(weights[:-1], x, strict=True))
        total += (pred - y) ** 2
    return total / len(ys)


def _select_lambda(results: list[tuple[float, float]]) -> float:
    """(λ, 验证集 MSE) 候选列表 → 选定 λ：MSE 最小，并列取小 λ（候选升序传入）。"""
    best_lam, best_mse = results[0]
    for lam, mse in results[1:]:
        if mse < best_mse:
            best_lam, best_mse = lam, mse
    return best_lam


def train_model(rows: list[dict], *, split_seed: int = DEFAULT_SPLIT_SEED,
                lambdas: tuple[float, ...] = LAMBDAS, code_version: str = "",
                pool: str | None = None,
                max_rows_per_game: int | None = None,
                subsample_seed: int = DEFAULT_SUBSAMPLE_SEED) -> LinearModel:
    """数据行 → 训练完成的 LinearModel（meta 全量落账，含死维度警戒 warning）。

    ``max_rows_per_game`` 非 None 时先按局确定性抽样（subsample_rows），
    meta 落 rows_total（抽样前）/ rows（实际训练用）双口径。
    """
    rows_total = len(rows)
    if max_rows_per_game is not None:
        rows = subsample_rows(rows, max_rows_per_game, subsample_seed)
    train_rows, val_rows = split_by_game(rows, split_seed=split_seed)
    d = len(FEATURE_NAMES)
    x_train = [[float(r["features"][name]) for name in FEATURE_NAMES] for r in train_rows]
    y_train = [float(r["label"]) for r in train_rows]
    x_val = [[float(r["features"][name]) for name in FEATURE_NAMES] for r in val_rows]
    y_val = [float(r["label"]) for r in val_rows]

    n = len(x_train)
    mean = [sum(x[i] for x in x_train) / n for i in range(d)]
    std = []
    for i in range(d):
        var = sum((x[i] - mean[i]) ** 2 for x in x_train) / n
        std.append(math.sqrt(var) if var > 0.0 else 1.0)  # 常数维度置 1 防除零

    def z(xs: list[list[float]]) -> list[list[float]]:
        return [[(x[i] - mean[i]) / std[i] for i in range(d)] for x in xs]

    z_train, z_val = z(x_train), z(x_val)
    results = [(lam, _mse(_ridge_fit(z_train, y_train, lam), z_val, y_val))
               for lam in lambdas]
    lam = _select_lambda(results)
    weights = _ridge_fit(z_train, y_train, lam)
    train_mse = _mse(weights, z_train, y_train)
    val_mse = _mse(weights, z_val, y_val)

    # 常数基线：训练集均值预测器在验证集上的 MSE
    baseline = sum(y_train) / len(y_train)
    baseline_mse = sum((y - baseline) ** 2 for y in y_val) / len(y_val)
    warning = None
    if val_mse >= baseline_mse:
        warning = (f"死维度警戒：验证集 MSE {val_mse} 不优于常数基线 {baseline_mse}"
                   f"（特征对结局无可解释方差——如实落账，模型照常产出）")

    game_ids = {(r["pair_index"], r["seed"]) for r in rows}
    meta = {
        "baseline_mse": baseline_mse,
        "code_version": code_version,
        "games": len(game_ids),
        "lambda": lam,
        "max_rows_per_game": max_rows_per_game,
        "pairs": len({r["pair_index"] for r in rows}),
        "pool": pool,
        "rows": len(rows),
        "rows_total": rows_total,
        "seed_max": max(s for _, s in game_ids),
        "seed_min": min(s for _, s in game_ids),
        "split_seed": split_seed,
        "subsample_seed": subsample_seed,
        "train_games": len({(r["pair_index"], r["seed"]) for r in train_rows}),
        "train_mse": train_mse,
        "val_games": len({(r["pair_index"], r["seed"]) for r in val_rows}),
        "val_mse": val_mse,
        "warning": warning,
    }
    return LinearModel(feature_names=FEATURE_NAMES, weights=tuple(weights),
                       mean=tuple(mean), std=tuple(std), meta=meta)
