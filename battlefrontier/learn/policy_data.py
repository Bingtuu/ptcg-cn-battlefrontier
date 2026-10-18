"""M12 蒸馏策略样本层（task 058 WP2）：教师快照 JSONL → (state, legal actions, teacher) 样本。

- **样本**：快照行（bf-m11-snapshot-v1，完整 GameState + 教师结构化 Action）→
  重建 GameState（runner.snapshot.snapshot_state，Pydantic 往返）→ 行动方
  visible view 状态特征（agent.features.feature_vector，信息纪律：特征只读
  VisibleGameState）→ 引擎重枚举合法行动逐条行动特征化（agent.action_features）
  → 教师 chosen 在合法列内的下标。引擎重建/合法行动枚举口径对齐
  runner.agreement.replay_student。
- **不猜**：教师行动不在合法列 / 数据目录无 pair-*.jsonl / 快照行格式不符
  均显式报错（快照格式校验走 runner.snapshot.load_snapshot_file 既有闸）。
- 本模块零 torch/numpy（训练侧 torch 仅限 learn/train_policy.py，task 056
  防回流基准）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from battlefrontier.agent.action_features import action_features
from battlefrontier.agent.features import feature_vector
from battlefrontier.dsl import CardLibrary
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.runner.snapshot import (
    load_snapshot_file,
    snapshot_state,
    teacher_action,
)

__all__ = ["PolicySample", "load_policy_samples", "row_to_sample"]


@dataclass(frozen=True)
class PolicySample:
    """单决策点训练样本：状态特征 + 合法行动特征列（引擎枚举序）+ 教师下标。

    state 键序 = FEATURE_NAMES；actions 每条键序 = ACTION_FEATURE_NAMES。
    (pair_index, seed) 为局 id（按局划分训练/验证用，同局样本不跨集）。
    """

    pair_index: int
    seed: int
    state: dict[str, float]
    actions: tuple[dict[str, float], ...]
    teacher_index: int


def row_to_sample(row: dict, *, pair_index: int,
                  card_effects: CardLibrary | dict) -> PolicySample:
    """快照行 → PolicySample；教师行动不在合法行动列显式报错（不猜）。"""
    state = snapshot_state(row)
    player = row["player"]
    view = state.visible_state(player)
    engine = GameEngine(RandomSource(row["seed"]), card_effects=card_effects)
    engine.state = state
    legal = engine.legal_actions(player)
    teacher = teacher_action(row)
    if teacher not in legal:
        raise ValueError(
            f"教师行动 {teacher!r} 不在合法行动列（pair {pair_index} seed "
            f"{row.get('seed')} turn {row.get('turn')} phase {row.get('phase')}；不猜）")
    return PolicySample(
        pair_index=pair_index,
        seed=int(row["seed"]),
        state=feature_vector(view),
        actions=tuple(action_features(a, view) for a in legal),
        teacher_index=legal.index(teacher),
    )


def load_policy_samples(data_dir: str | Path) -> list[PolicySample]:
    """读目录下全部 pair-*.jsonl 快照（文件名排序保确定序），逐行转样本。

    快照格式校验（header/format/行类型）走 load_snapshot_file 既有闸；
    card_effects 从各文件 header 重建（自包含，无需 db）。
    """
    files = sorted(Path(data_dir).glob("pair-*.jsonl"))
    if not files:
        raise ValueError(f"{data_dir} 下无 pair-*.jsonl 快照文件")
    samples: list[PolicySample] = []
    for f in files:
        snap = load_snapshot_file(f)
        card_effects = snap.card_effects()
        pair_index = int(snap.header["pair_index"])
        for row in snap.rows:
            samples.append(row_to_sample(row, pair_index=pair_index,
                                         card_effects=card_effects))
    return samples
