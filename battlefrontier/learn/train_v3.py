"""task 155 WP3：训练 v3——numpy 分块两遍流式岭回归（λ 六档，D3-4 非复算面延续）。

预注册判据冻结于 tasks/task 155.md。v1 训练器（``learn.train``）是口径来源：
按局划分 / split_seed / 按局抽样 / 死维度警戒 / meta 落账字段全沿用（复用其
函数与常量，不重实现）；差异 = 数据形态（v3 文件首行 bf-collect-v3 header +
数据行 features 位置对齐 float list）与规模（45 文件 × ~400 万行 × 560 维），
故统计量全部分块流式累计，绝不整读（``read_collect_v3`` 是整读参考，训练禁用）：

- **流式读取**：逐文件 ``for line in fh``；首行 header 校验（type/format/
  feature_names，名序须 ``eval_v3_names`` 口径——基座 36 维 + 4 区
  cid_ 词表段，不符显式 ValueError）；数据行按 header 名序位置取值，行内
  校验宽度/数值类型/label 域。
- **meta 趟**（轻量，恒跑）：按局计数 + 局 id 集合 + 总行数——按局划分与
  按局抽样的决策输入；不物化数据行（峰值内存 < 2GB 硬约束）。
- **顺序 = 先抽样 → 按局划分 → 两遍统计**（同 v1）：抽样决策（
  ``max_rows_per_game`` 非 None）经 ``train._subsample_pick_indices``
  （subsample_rows 共用核心，语义单一来源）定每局入选行索引（dict
  [(局 id)] -> None 全留 | frozenset 入选序）；其后各趟只累计入选行。
- **pass 1**（``CHUNK_ROWS = 50_000`` 模块常量钉死）：入选训练局行分块
  累计每维 sum/sumsq（numpy float64）→ mean/std；常数维 std 置 1 防除零
  （同 v1 口径；var = sumsq/n − mean²，计数特征 O(1) 值域下 cancellation
  可忽略，负值截 0）。
- **pass 2**：分块 z-score 后拼截距列（恒 1）累 ``Xc.T @ Xc`` / ``Xc.T @ y``
  → ``np.linalg.solve(XᵀX + λI, Xᵀy)``（截距列不正则化，同 v1）。
- **λ 候选六档** ``LAMBDAS_V3 = (0.1, 1, 10, 100, 1000, 10000)``（预注册：
  维数 30→560 改变 XᵀX 尺度、λ 语义漂移；选择规则不变 = 验证 MSE 最小、
  并列取小 λ，复用 ``train._select_lambda``）；评估趟单次流式对全部候选
  权重矩阵算验证/训练 MSE 与常数基线（训练集均值预测器，同 v1）。
- **死维度警戒沿用**：验证 MSE ≥ 常数基线 → meta["warning"] 落账，模型
  照常产出（CLI 退出码 2，见 cli._cmd_train_eval_v3）。
- **确定性声明**：同环境同输入逐位确定——全路径 numpy float64 + 固定趟序 +
  固定 chunk 边界 + 钉死种子，无迭代随机源；训练非复算面（D3-4 延续）：
  权重资产进版本控制即锁定。
- **不猜纪律**：v1 dict 行（无 header）/ header 缺失或 format 错 / 行宽与
  header 名数不符 / 特征名序非 eval_v3_names 口径 / label 出 [0,1] /
  特征含非有限值 → 一律显式 ValueError。

内存口径：常驻 = 统计向量（O(d)）+ 每 chunk 缓冲（50k × 560 float64 ≈
224MB，峰值上界）+ 按局计数/入选结构（O(局数)）；正式数据 4M 行级不物化。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from battlefrontier.agent.eval_features import EVAL_V3_BASE_NAMES, EVAL_V3_ZONES
from battlefrontier.learn.model import LinearModel
from battlefrontier.learn.train import (
    DEFAULT_SPLIT_SEED,
    DEFAULT_SUBSAMPLE_SEED,
    _select_lambda,
    _split_train_ids,
    _subsample_pick_indices,
)

__all__ = ["CHUNK_ROWS", "LAMBDAS_V3", "train_model_v3"]

CHUNK_ROWS = 50_000
LAMBDAS_V3: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0)

_HEADER_FORMAT = "bf-collect-v3"
_REQUIRED_KEYS = {"pair_index", "seed", "features", "label"}

# 行迭代统一产出结构：(局 id, 局内序, features list, label)。
_Row = tuple[tuple[int, int], int, list[float], float]


def _list_files(data_dir: str | Path) -> list[Path]:
    files = sorted(Path(data_dir).glob("pair-*.jsonl"))
    if not files:
        raise ValueError(f"{data_dir} 下无 pair-*.jsonl 数据文件")
    return files


def _read_header(fh, source: str, expected: tuple[str, ...] | None) -> tuple[str, ...]:
    """读并校验单文件首行 header；expected 非 None 时校验与首文件名序一致。"""
    line = fh.readline()
    if not line.strip():
        raise ValueError(f"{source} 为空文件（无 header 行，不猜）")
    try:
        header = json.loads(line)
    except json.JSONDecodeError as e:
        raise ValueError(f"{source} 首行非合法 JSON（{e}；不猜）") from e
    if (not isinstance(header, dict)
            or header.get("type") != "header"
            or header.get("format") != _HEADER_FORMAT
            or not isinstance(header.get("feature_names"), list)
            or not all(isinstance(n, str) for n in header["feature_names"])):
        raise ValueError(f"{source} 首行非 {_HEADER_FORMAT} header（v1 dict 行数据"
                         "请用缺省 --feature-set v1 训练，不猜）")
    names = tuple(header["feature_names"])
    if len(set(names)) != len(names):
        raise ValueError(f"{source} header feature_names 含重名（不猜）")
    if expected is not None and names != expected:
        raise ValueError(f"{source} header 名序与首文件不一致（多文件特征口径须"
                         "逐字一致，不猜）")
    return names


def _parse_v3_names(names: tuple[str, ...], source: str) -> tuple[str, ...]:
    """header 名序 → 卡词表（校验 eval_v3_names 口径：基座 36 维原序 +
    4 区等长 cid_<区>_<卡名> 段；不符显式 ValueError，不猜）。"""
    d_base = len(EVAL_V3_BASE_NAMES)
    if len(names) <= d_base or names[:d_base] != EVAL_V3_BASE_NAMES:
        raise ValueError(f"{source}：header 基座维非 EVAL_V3_BASE_NAMES 原序"
                         "（非 eval_v3_names 口径，不猜）")
    rest = names[d_base:]
    if len(rest) % len(EVAL_V3_ZONES) != 0:
        raise ValueError(f"{source}：header cid_ 区段长度 {len(rest)} 不整除"
                         f"区数 {len(EVAL_V3_ZONES)}（不猜）")
    vocab_size = len(rest) // len(EVAL_V3_ZONES)
    vocab: list[str] = []
    for zi, zone in enumerate(EVAL_V3_ZONES):
        seg = rest[zi * vocab_size:(zi + 1) * vocab_size]
        prefix = f"cid_{zone}_"
        if not all(n.startswith(prefix) for n in seg):
            raise ValueError(f"{source}：header 区段 {zi}（{zone}）键名非"
                             f"{prefix!r} 前缀（不猜）")
        names_zone = [n[len(prefix):] for n in seg]
        if zi == 0:
            vocab = names_zone
        elif names_zone != vocab:
            raise ValueError(f"{source}：header 区段 {zi} 词表与区 0 不一致（不猜）")
    return tuple(vocab)


def _validate_data_row(row, source: str, d: int) -> None:
    """数据行 schema 校验（每趟行级，不猜）：字段齐 / pair_index、seed 为 int /
    features 为定宽 float list / label ∈ [0,1]。"""
    if not isinstance(row, dict) or row.get("type") == "header":
        raise ValueError(f"{source}：数据行位置混入非数据行（不猜）")
    missing = _REQUIRED_KEYS - row.keys()
    if missing:
        raise ValueError(f"{source}：数据行缺字段 {sorted(missing)}（不猜）")
    if not isinstance(row["pair_index"], int) or not isinstance(row["seed"], int):
        raise ValueError(f"{source}：pair_index/seed 非 int（不猜）")  # noqa: TRY004 — 与 v1 _validate_row 同口径：数据行问题一律 ValueError
    feats = row["features"]
    if not isinstance(feats, list) or len(feats) != d:
        raise ValueError(f"{source}：数据行 features 宽度 "
                         f"{len(feats) if isinstance(feats, list) else '非 list'} "
                         f"与 header 名数 {d} 不符（不猜）")
    if not all(isinstance(v, int | float) and not isinstance(v, bool)
               for v in feats):
        raise ValueError(f"{source}：features 含非数值元素（不猜）")
    label = row["label"]
    if (not isinstance(label, int | float) or isinstance(label, bool)
            or not 0.0 <= float(label) <= 1.0):
        raise ValueError(f"{source}：label {label!r} 不在 [0,1]（不猜）")


def _iter_rows(files: list[Path], names: tuple[str, ...]) -> Iterator[_Row]:
    """逐文件逐行流式产出 (局 id, 局内序, features, label)；局内序 = 该局
    在本趟已见行数（文件序 = 产线落盘序，与 subsample_rows 的行索引口径一致）。"""
    d = len(names)
    for f in files:
        seen: dict[tuple[int, int], int] = {}
        with f.open(encoding="utf-8") as fh:
            _read_header(fh, f.name, names)
            for ln, line in enumerate(fh, 2):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{f.name}:{ln} 非合法 JSON（{e}；不猜）") from e
                _validate_data_row(row, f"{f.name}:{ln}", d)
                gid = (row["pair_index"], row["seed"])
                ordinal = seen.get(gid, 0)
                seen[gid] = ordinal + 1
                yield (gid, ordinal, row["features"], float(row["label"]))


def _meta_pass(files: list[Path],
               names: tuple[str, ...]) -> tuple[dict[tuple[int, int], int], int]:
    """meta 趟：按局计数 + 总行数（轻量结构，不物化数据行）。"""
    counts: dict[tuple[int, int], int] = {}
    rows_total = 0
    for gid, _ord, _feats, _label in _iter_rows(files, names):
        counts[gid] = counts.get(gid, 0) + 1
        rows_total += 1
    return counts, rows_total


def _kept(keep: dict[tuple[int, int], frozenset[int] | None] | None,
          gid: tuple[int, int], ordinal: int) -> bool:
    """入选判定：keep None（无抽样）= 全入选；keep[gid] None = 该局全留；
    frozenset = 局内序在入选集内。"""
    if keep is None:
        return True
    picked = keep.get(gid)
    return picked is None or ordinal in picked


def train_model_v3(data_dir: str | Path, *,
                   split_seed: int = DEFAULT_SPLIT_SEED,
                   lambdas: tuple[float, ...] = LAMBDAS_V3,
                   code_version: str = "", pool: str | None = None,
                   max_rows_per_game: int | None = None,
                   subsample_seed: int = DEFAULT_SUBSAMPLE_SEED
                   ) -> LinearModel:
    """v3 采集目录 → 训练完成的 LinearModel（分块两遍流式；meta 全量落账，
    口径与 v1 逐字段对齐，另加 feature_set/card_vocab/zones）。

    ``max_rows_per_game`` 非 None 时先按局确定性抽样（与 v1 同序：抽样 →
    划分 → 统计），meta 落 rows_total（抽样前）/ rows（实际入选）双口径。
    """
    files = _list_files(data_dir)
    with files[0].open(encoding="utf-8") as fh:
        names = _read_header(fh, files[0].name, None)
    card_vocab = _parse_v3_names(names, files[0].name)
    d = len(names)

    counts, rows_total = _meta_pass(files, names)
    game_ids = sorted(counts)
    train_ids = _split_train_ids(game_ids, split_seed)
    val_ids = set(game_ids) - train_ids

    # 抽样决策（先抽样，与 v1 同序）；keep[gid] = None 全留 | frozenset 入选序
    keep: dict[tuple[int, int], frozenset[int] | None] | None = None
    rows_kept = rows_total
    if max_rows_per_game is not None:
        keep = {}
        rows_kept = 0
        for gid in game_ids:
            picked = _subsample_pick_indices(counts[gid], gid[0], gid[1],
                                             max_rows_per_game, subsample_seed)
            rows_kept += len(picked)
            keep[gid] = (None if counts[gid] <= max_rows_per_game
                         else frozenset(picked))

    def _chunks(only_train: bool):
        """分块流式产出 (X 原始块, y, 训练局掩码)；块内校验 features 有限。
        only_train = 只收训练局入选行（掩码全 True）。"""
        buf_x: list[list[float]] = []
        buf_y: list[float] = []
        buf_tr: list[bool] = []
        for gid, ordinal, feats, label in _iter_rows(files, names):
            if not _kept(keep, gid, ordinal):
                continue
            is_train = gid in train_ids
            if only_train and not is_train:
                continue
            buf_x.append(feats)
            buf_y.append(label)
            buf_tr.append(is_train)
            if len(buf_x) >= CHUNK_ROWS:
                yield _flush(buf_x, buf_y, buf_tr)
                buf_x, buf_y, buf_tr = [], [], []
        if buf_x:
            yield _flush(buf_x, buf_y, buf_tr)

    def _flush(buf_x, buf_y, buf_tr):
        x_chunk = np.asarray(buf_x, dtype=np.float64)
        if not np.isfinite(x_chunk).all():
            raise ValueError("features 含 NaN/Inf（不猜）")
        return (x_chunk, np.asarray(buf_y, dtype=np.float64),
                np.asarray(buf_tr, dtype=bool))

    # pass 1：训练局入选行 sum/sumsq → mean/std（常数维置 1 防除零，同 v1）
    sum_x = np.zeros(d, dtype=np.float64)
    sq_x = np.zeros(d, dtype=np.float64)
    n_train_rows = 0
    for x_chunk, _y, _tr in _chunks(only_train=True):
        sum_x += x_chunk.sum(axis=0)
        sq_x += (x_chunk * x_chunk).sum(axis=0)
        n_train_rows += x_chunk.shape[0]
    if n_train_rows == 0:
        raise ValueError("训练集无数据行（不猜）")
    mean = sum_x / n_train_rows
    var = sq_x / n_train_rows - mean * mean
    var = np.maximum(var, 0.0)
    std = np.where(var > 0.0, np.sqrt(var), 1.0)

    def _standardize(x_chunk: np.ndarray) -> np.ndarray:
        """z-score + 截距列（恒 1，不正则化列）。"""
        z = (x_chunk - mean) / std
        return np.column_stack([z, np.ones(z.shape[0], dtype=np.float64)])

    # pass 2：训练局入选行 XᵀX / Xᵀy（截距列入阵、不正则化）
    xt_x = np.zeros((d + 1, d + 1), dtype=np.float64)
    xt_y = np.zeros(d + 1, dtype=np.float64)
    y_sum = 0.0
    for x_chunk, y_chunk, _tr in _chunks(only_train=True):
        z1 = _standardize(x_chunk)
        xt_x += z1.T @ z1
        xt_y += z1.T @ y_chunk
        y_sum += float(y_chunk.sum())

    # 逐 λ 闭式解（截距对角元不加 λ，同 v1）
    weights_by_lam: dict[float, np.ndarray] = {}
    for lam in lambdas:
        a = xt_x.copy()
        a[np.diag_indices(d)] += lam
        weights_by_lam[lam] = np.linalg.solve(a, xt_y)

    # 评估趟：单次流式对全部候选权重矩阵累计 验证/训练 SSE + 常数基线 SSE
    w_mat = np.column_stack([weights_by_lam[lam] for lam in lambdas])
    sse_val = np.zeros(len(lambdas), dtype=np.float64)
    sse_train = np.zeros(len(lambdas), dtype=np.float64)
    sse_base = 0.0
    n_val_rows = 0
    y_bar = y_sum / n_train_rows
    for x_chunk, y_chunk, tr_mask in _chunks(only_train=False):
        z1 = _standardize(x_chunk)
        errs = (z1 @ w_mat - y_chunk[:, None]) ** 2
        sse_train += errs[tr_mask].sum(axis=0)
        sse_val += errs[~tr_mask].sum(axis=0)
        base_err = (y_chunk - y_bar) ** 2
        sse_base += float(base_err[~tr_mask].sum())
        n_val_rows += int((~tr_mask).sum())
    if n_val_rows == 0:
        raise ValueError("验证集无数据行（不猜）")

    results = [(lam, float(sse_val[i] / n_val_rows)) for i, lam in enumerate(lambdas)]
    lam = _select_lambda(results)
    sel = lambdas.index(lam)
    weights = weights_by_lam[lam]
    train_mse = float(sse_train[sel] / n_train_rows)
    val_mse = float(sse_val[sel] / n_val_rows)
    baseline_mse = sse_base / n_val_rows

    # 死维度警戒（同 v1 口径）：验证 MSE 不优于常数基线 → 落账不强行失败
    warning = None
    if val_mse >= baseline_mse:
        warning = (f"死维度警戒：验证集 MSE {val_mse} 不优于常数基线 {baseline_mse}"
                   f"（特征对结局无可解释方差——如实落账，模型照常产出）")

    meta = {
        "baseline_mse": baseline_mse,
        "card_vocab": list(card_vocab),
        "code_version": code_version,
        "feature_set": "v3",
        "games": len(game_ids),
        "lambda": lam,
        "max_rows_per_game": max_rows_per_game,
        "pairs": len({gid[0] for gid in game_ids}),
        "pool": pool,
        "rows": rows_kept,
        "rows_total": rows_total,
        "seed_max": max(s for _, s in game_ids),
        "seed_min": min(s for _, s in game_ids),
        "split_seed": split_seed,
        "subsample_seed": subsample_seed,
        "train_games": len(train_ids),
        "train_mse": train_mse,
        "val_games": len(val_ids),
        "val_mse": val_mse,
        "warning": warning,
        "zones": list(EVAL_V3_ZONES),
    }
    return LinearModel(
        feature_names=names,
        weights=tuple(float(w) for w in weights),
        mean=tuple(float(v) for v in mean),
        std=tuple(float(v) for v in std),
        meta=meta,
    )
