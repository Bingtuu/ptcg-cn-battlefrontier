"""task 155 WP1：评估器特征层 v3（D-062-1 纪律延续，预注册判据冻结于
tasks/task 155.md）。

task 150 FAIL 归因：M11 学得评估器 30 维特征对 v2.x 新机制状态
（lock_play / status_immunity / 工具交互 / 赛场阻断等）失明 → 本模块把
特征扩维到 36 + 4 区 × 词表（v2.x 池 131 词 → 560 维，task 062 把
use_ability 从 0.009% 救到 20.9% 的卡身份思路移植到评估器线）：

- **D-062-1 独立成册，不动钉死清单**：`FEATURE_NAMES`（M11 30 维）与
  `DISCARD_FEATURE_NAMES`（task 062 弃牌构成 6 维）被 eval-linear-v1 等
  入库资产逐键序校验锚定 → 本模块只读复用两者原序组合基座
  （`EVAL_V3_BASE_NAMES`），绝不修改来源文件。
- **基座 36 维**：直接调用既有纯函数 `policy_state_features(view)`
  （features.py 30 维 + 弃牌构成 6 维），不重实现。
- **卡身份分区计数 4 区**（键名 `cid_<区>_<卡名>`）：区 =
  `EVAL_V3_ZONES = (own_hand, own_board, opp_board, stadium)`——
  own_hand = 己方手牌卡名计数；own_board / opp_board = 双方盘面
  （active + bench）的进化栈 + 附着能量 + 附着道具卡名计数
  （`_pokemon_cards` 从 policy_features 导入复用，口径单一来源）；
  stadium = 在场竞技场 one-hot（无场全零）。
- **词表外卡名显式 ValueError**（不猜纪律，D-062-2 延续；学习线锚定
  卡池 v2.x，词表 = `build_card_vocab`）。
- **信息纪律**：全部只读 `VisibleGameState` 可见区域（与 features.py 同
  口径）；对手手牌内容视图不可见——身份不进任何特征，对手侧只有基座维
  `opp_hand_count`。

模块纪律：纯函数、零随机源、零引擎调用；同一视图两次调用逐位相等。
"""

from __future__ import annotations

from battlefrontier.agent.features import FEATURE_NAMES
from battlefrontier.agent.policy_features import (
    DISCARD_FEATURE_NAMES,
    _pokemon_cards,
    policy_state_features,
)
from battlefrontier.engine.state import VisibleGameState

__all__ = [
    "EVAL_V3_BASE_NAMES",
    "EVAL_V3_ZONES",
    "eval_v3_names",
    "feature_vector_v3",
]

# 卡身份分区（区序钉死，预注册判据）：前 3 区卡名计数，stadium one-hot。
EVAL_V3_ZONES: tuple[str, ...] = ("own_hand", "own_board", "opp_board", "stadium")

# 基座 36 维（键序钉死）：M11 FEATURE_NAMES（30）原序 + 弃牌构成 6 维原序
# （D-062-1：两个既有常量只读复用，改动即砸 eval-linear-v1 等入库资产）。
EVAL_V3_BASE_NAMES: tuple[str, ...] = FEATURE_NAMES + DISCARD_FEATURE_NAMES


def eval_v3_names(card_vocab: tuple[str, ...]) -> tuple[str, ...]:
    """v3 特征清单：36 基座 + `cid_<区>_<卡名>`（区序 = EVAL_V3_ZONES、
    卡名序 = 传入 vocab 序——不隐式排序，构建侧 build_card_vocab 保证
    字典序钉死）。词表重名 = 键冲突，显式报错（不猜）。"""
    if len(set(card_vocab)) != len(card_vocab):
        raise ValueError("词表内卡名重复（cid_ 键会冲突，不猜）")
    return EVAL_V3_BASE_NAMES + tuple(
        f"cid_{zone}_{name}"
        for zone in EVAL_V3_ZONES
        for name in card_vocab
    )


def _zone_card_names(view: VisibleGameState) -> dict[str, tuple[str, ...]]:
    """4 区可见卡名（信息纪律：只读 Agent 可见区域）。

    own_hand = 己方手牌；own_board / opp_board = 双方 active + bench 的
    `_pokemon_cards`（进化栈 + 附着能量 + 附着道具）；stadium = 在场竞技
    场（无场 = 空 tuple）。弃牌只进基座 6 维，不进 cid_ 区。
    """
    zones: dict[str, list[str]] = {z: [] for z in EVAL_V3_ZONES}

    def add_board(zone: str, side) -> None:
        if side.active is not None:
            zones[zone].extend(c.card.name for c in _pokemon_cards(side.active))
        for p in side.bench:
            zones[zone].extend(c.card.name for c in _pokemon_cards(p))

    zones["own_hand"].extend(c.card.name for c in view.own.hand)
    add_board("own_board", view.own)
    add_board("opp_board", view.opponent)
    if view.stadium is not None:
        zones["stadium"].append(view.stadium.card.name)
    return {z: tuple(names) for z, names in zones.items()}


def _validate_vocab(names: tuple[str, ...], card_vocab: tuple[str, ...]) -> None:
    """词表外卡名显式 ValueError（不猜纪律，D-062-2 延续）。"""
    vocab = set(card_vocab)
    for name in names:
        if name not in vocab:
            raise ValueError(
                f"卡名 {name!r} 不在词表（词表外不猜，学习线锚定卡池 v2.x）")


def feature_vector_v3(
        view: VisibleGameState, card_vocab: tuple[str, ...],
        zones: tuple[str, ...] = EVAL_V3_ZONES) -> dict[str, float]:
    """可见视图 → v3 特征向量（键序 = eval_v3_names(card_vocab)）。

    基座 36 维 = `policy_state_features(view)` 原值；其后 4 区卡身份计数
    （stadium 区天然 one-hot——同时在场至多 1 张竞技场）。zones 缺省
    EVAL_V3_ZONES，全量 4 区计数词表外卡名即报错。
    """
    zone_names = _zone_card_names(view)
    for names in zone_names.values():
        _validate_vocab(names, card_vocab)
    feats = dict.fromkeys(eval_v3_names(card_vocab), 0.0)
    feats.update(policy_state_features(view))
    for zone in zones:
        for name in zone_names[zone]:
            feats[f"cid_{zone}_{name}"] += 1.0
    return feats
