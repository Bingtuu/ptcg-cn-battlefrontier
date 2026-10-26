"""task 066 WP1（D-066-1/2/3）：per-kind 样本权重 + end_turn 双投票降噪权重向量。

- **D-066-1 kind 权重方案 kind-weights-v1**：教师标签 kind = play_stadium →
  w=3.0；use_ability → w=2.0；其余 → 1.0。依据：play_stadium 有效正例质量
  13.5%×3 ≈ 对齐 attack 档；use_ability ×2 对治坍缩到 end_turn 的形态。
- **D-066-2 end_turn 双投票降噪**：第二投票 = 既有 anchor1-ceiling 异种子重放
  （``results/m12-anchor1-ceiling/pair-*.json``，rows[i] = agreement 详情行）。
  join 口径精确复刻 runner.agreement.run_agreement：ceiling 行 ``index`` =
  **快照文件内 0 起行号**（``enumerate(snapshot.rows)``，仅分母口径三类
  attack/play_trainer/end_turn 有行——真实数据 pair-0 实证：按文件行号 join
  teacher_kind 全匹配，按分母序号 join 不匹配）。快照行 kind=end_turn 且
  对应 ceiling 行 agree=false → w=0.25；agree=true 或非 end_turn → 按
  D-066-1。缺票 / ceiling 文件缺失 / index 重复 / teacher_kind 不匹配 均显式
  报错（不猜不跳过）。
- **权重序 = load_policy_samples 样本序**：sorted glob ``pair-*.jsonl`` × 文件
  内行序，两函数同一份枚举口径，逐位对齐。
- 归一化口径钉死（meta 记录）：loss = sum(w×nll)/sum(w)。
- 本模块零 torch/numpy（训练侧 torch 仅限 learn/train_policy.py，task 056
  防回流基准）。
"""

from __future__ import annotations

import json
from pathlib import Path

from battlefrontier.runner.snapshot import load_snapshot_file

__all__ = [
    "DEFAULT_CEILING_DIR",
    "END_TURN_UNSTABLE_WEIGHT",
    "END_TURN_UNSTABLE_WEIGHT_V2",
    "KIND_WEIGHTS_V1",
    "KIND_WEIGHTS_V2",
    "LOSS_NORMALIZATION",
    "WEIGHT_SCHEMES",
    "WEIGHT_SCHEME_KIND_V1",
    "WEIGHT_SCHEME_KIND_V2",
    "WEIGHT_SCHEME_NONE",
    "compute_sample_weights",
]

WEIGHT_SCHEME_NONE = "none"
WEIGHT_SCHEME_KIND_V1 = "kind-weights-v1"
WEIGHT_SCHEME_KIND_V2 = "kind-weights-v2"
WEIGHT_SCHEMES = (WEIGHT_SCHEME_NONE, WEIGHT_SCHEME_KIND_V1,
                  WEIGHT_SCHEME_KIND_V2)

# D-066-1 kind 权重表（未列 kind = 1.0）
KIND_WEIGHTS_V1 = {"play_stadium": 3.0, "use_ability": 2.0}
# D-066-2 双投票不一致 end_turn 点降权
END_TURN_UNSTABLE_WEIGHT = 0.25
# D-066-5 A2 降剂量（2026-10-21 用户拍板）：v1 剂量锚 1 过冲（attack 让位
# -35.7pts）且锚 2 恶化（|Δ| 12.5%→18.6%）后的中间档
KIND_WEIGHTS_V2 = {"play_stadium": 1.5, "use_ability": 1.25}
END_TURN_UNSTABLE_WEIGHT_V2 = 0.5

_SCHEME_PARAMS = {
    WEIGHT_SCHEME_KIND_V1: (KIND_WEIGHTS_V1, END_TURN_UNSTABLE_WEIGHT),
    WEIGHT_SCHEME_KIND_V2: (KIND_WEIGHTS_V2, END_TURN_UNSTABLE_WEIGHT_V2),
}
# 归一化口径（钉死，meta 记录）
LOSS_NORMALIZATION = "sum(w*nll)/sum(w)"
# 第二投票数据源缺省路径（开发期固定，D-066-2）
DEFAULT_CEILING_DIR = "results/m12-anchor1-ceiling"


def _load_ceiling_votes(ceiling_path: Path, snapshot_name: str) -> dict[int, dict]:
    """ceiling JSON → {快照文件行号: 行}；文件缺失 / index 重复 显式报错。"""
    if not ceiling_path.exists():
        raise ValueError(
            f"ceiling 文件缺失：{ceiling_path}（快照 {snapshot_name} 的第二投票"
            "数据源，不猜不跳过）")
    report = json.loads(ceiling_path.read_text(encoding="utf-8"))
    rows = report.get("rows")
    if not isinstance(rows, list):
        raise TypeError(
            f"ceiling 文件 rows 缺失或非列表：{ceiling_path}（不猜）")
    votes: dict[int, dict] = {}
    for r in rows:
        idx = r["index"]
        if idx in votes:
            raise ValueError(
                f"ceiling 文件 {ceiling_path} index {idx} 重复（不猜）")
        votes[idx] = r
    return votes


def compute_sample_weights(data_dir: str | Path, *, scheme: str,
                           ceiling_dir: str | Path | None = None,
                           ) -> tuple[list[float], dict | None]:
    """快照目录 → (逐样本权重, weight_scheme meta 段)；序 = load_policy_samples。

    scheme = none → 全 1.0、meta None（等价现状，不读 ceiling）；
    scheme = kind-weights-v1 → D-066-1 kind 权重 × D-066-2 end_turn 双投票降噪，
    meta 段 = 方案名 + kind 权重表 + end_turn_unstable_weight + 归一化口径 +
    ceiling 数据源锚点（目录 / 文件数 / end_turn 点数 / 降权点数）。
    """
    if scheme not in WEIGHT_SCHEMES:
        raise ValueError(
            f"未知 weight 方案：{scheme!r}（支持 {WEIGHT_SCHEMES}，不猜）")
    files = sorted(Path(data_dir).glob("pair-*.jsonl"))
    if not files:
        raise ValueError(f"{data_dir} 下无 pair-*.jsonl 快照文件")
    if scheme == WEIGHT_SCHEME_NONE:
        n = sum(len(load_snapshot_file(f).rows) for f in files)
        return [1.0] * n, None

    cdir = Path(ceiling_dir) if ceiling_dir is not None \
        else Path(DEFAULT_CEILING_DIR)
    kind_weights, unstable_w = _SCHEME_PARAMS[scheme]
    weights: list[float] = []
    end_turn_points = 0
    end_turn_unstable = 0
    for f in files:
        snap = load_snapshot_file(f)
        votes = _load_ceiling_votes(cdir / (f.stem + ".json"), f.name)
        for i, row in enumerate(snap.rows):
            kind = row["action_kind"]
            if kind != "end_turn":
                weights.append(kind_weights.get(kind, 1.0))
                continue
            end_turn_points += 1
            vote = votes.get(i)
            if vote is None:
                raise ValueError(
                    f"缺票：快照 {f.name} 行 {i}（end_turn）在 ceiling 文件无"
                    "对应第二投票行（index = 快照文件行号，不猜不跳过）")
            if vote["teacher_kind"] != kind:
                raise ValueError(
                    f"kind 不匹配：快照 {f.name} 行 {i} = {kind!r}，ceiling 行 "
                    f"teacher_kind = {vote['teacher_kind']!r}（join 错位，不猜）")
            if vote["agree"]:
                weights.append(1.0)
            else:
                end_turn_unstable += 1
                weights.append(unstable_w)
    meta = {
        "name": scheme,
        "kind_weights": dict(kind_weights),
        "end_turn_unstable_weight": unstable_w,
        "loss_normalization": LOSS_NORMALIZATION,
        "ceiling_dir": str(cdir),
        "ceiling_files": len(files),
        "end_turn_points": end_turn_points,
        "end_turn_unstable_points": end_turn_unstable,
    }
    return weights, meta
