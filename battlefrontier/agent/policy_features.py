"""task 062 WP1：蒸馏策略 v2 特征层（卡身份 one-hot + 弃牌构成，D-062-1/2/3）。

task 061 根因诊断：M12 蒸馏学生特征零卡面身份、零弃牌构成 → use_ability 类
决策在特征空间不可分（一致率 0.009%）。本模块在 M11 钉死清单之上扩展：

- **D-062-1 独立成册，不动 M11 清单**：`FEATURE_NAMES` / `ACTION_FEATURE_NAMES`
  被已入库模型资产（eval-linear-v1、bf-distilled-policy-v1）装载时逐一键序
  校验，改动即砸既有资产 → v2 特征独立本模块，`POLICY_STATE_NAMES` /
  `policy_action_names(card_vocab)` 以「既有清单 + 追加尾序」组合派生，
  两个旧常量只读复用、绝不修改。
- **D-062-2 卡身份词表**：卡池 v1 各代表卡组全部 CardDef.name 去重 + Python
  字典序排序钉死（`build_card_vocab`）；词表外卡名显式 ValueError（不猜，
  学习线锚定卡池 v1，D3-5）。
- **D-062-3 行动→卡名解析**：只读 VisibleGameState 可见区域反查（信息纪律，
  与 features.py / action_features.py 同口径）——己方手牌 / 双方场上
  （stack + attached_energy + attached_tool）/ 双方弃牌 / pending_pool；
  iid 不在可见区 = 跳过（身份合法地不可见，如实表达，非报错）；attack /
  retreat 无 iid，身份 = 己方战斗场当前形态。

模块纪律：纯函数、零引擎调用、零随机源（`build_card_vocab` 为训练侧词表
构建工具，只做文件/db 装载，不参与对局路径）。
"""

from __future__ import annotations

from battlefrontier.agent.action_features import ACTION_FEATURE_NAMES, action_features
from battlefrontier.agent.features import FEATURE_NAMES, feature_vector
from battlefrontier.data.deck import load_deck
from battlefrontier.data.pool import load_target_pool
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import (
    CardInstance,
    InPlayPokemon,
    Supertype,
    VisibleGameState,
)

__all__ = [
    "DISCARD_FEATURE_NAMES",
    "POLICY_STATE_NAMES",
    "build_card_vocab",
    "policy_action_features",
    "policy_action_names",
    "policy_state_features",
    "resolve_action_card_names",
]

# 弃牌构成 6 维（D-062-1，尾序钉死）：弃牌堆为公开区域（双方可见）。
DISCARD_FEATURE_NAMES: tuple[str, ...] = (
    "own_discard_count",
    "own_discard_energy_count",
    "own_discard_pokemon_count",
    "opp_discard_count",
    "opp_discard_energy_count",
    "opp_discard_pokemon_count",
)

# 状态特征清单 v2（键序钉死）：M11 FEATURE_NAMES（30）原序 + 弃牌构成 6 维。
POLICY_STATE_NAMES: tuple[str, ...] = FEATURE_NAMES + DISCARD_FEATURE_NAMES


def policy_action_names(card_vocab: tuple[str, ...]) -> tuple[str, ...]:
    """行动特征清单 v2：M12 ACTION_FEATURE_NAMES（26）+ 卡身份 one-hot
    （键名 card_<名>，词表序即键序——构建侧 build_card_vocab 保证字典序）。"""
    return ACTION_FEATURE_NAMES + tuple(f"card_{n}" for n in card_vocab)


def build_card_vocab(pool_path, db_path) -> tuple[str, ...]:
    """卡身份词表 = 卡池各代表卡组全部卡名去重 + 字典序排序（D-062-2）。"""
    pool = load_target_pool(pool_path)
    names: set[str] = set()
    for entry in pool.decks:
        deck = load_deck(db_path, entry.deck_id)
        names.update(c.name for c in deck.cards)
    return tuple(sorted(names))


def _pokemon_cards(p: InPlayPokemon) -> tuple[CardInstance, ...]:
    """场上宝可梦全部关联卡实例：进化栈 + 附着能量 + 附着道具。"""
    cards = list(p.stack)
    cards.extend(p.attached_energy)
    if p.attached_tool is not None:
        cards.append(p.attached_tool)
    return tuple(cards)


def _visible_card_names(view: VisibleGameState) -> dict[int, str]:
    """可见视图 iid→卡名映射（信息纪律：只读 Agent 可见区域）。"""
    mapping: dict[int, str] = {}

    def add(cards: tuple[CardInstance, ...] | list[CardInstance]) -> None:
        for c in cards:
            mapping[c.iid] = c.card.name

    add(view.own.hand)
    for side in (view.own, view.opponent):
        if side.active is not None:
            add(_pokemon_cards(side.active))
        for p in side.bench:
            add(_pokemon_cards(p))
        add(side.discard)
    if view.pending_pool is not None:
        add(view.pending_pool)
    return mapping


def resolve_action_card_names(
        action: Action, view: VisibleGameState) -> tuple[str, ...]:
    """行动 → 涉及卡名（可见视图反查，D-062-3）。

    attack / retreat（无 iid）= 己方战斗场当前形态（无战斗场 = 空 tuple）；
    其余行动 = action.iid + action.choices 各 iid 反查；iid 不在可见区
    跳过（身份合法地不可见，非报错）。
    """
    if action.kind in ("attack", "retreat"):
        if view.own.active is None:
            return ()
        return (view.own.active.current.card.name,)
    mapping = _visible_card_names(view)
    names: list[str] = []
    if action.iid is not None and action.iid in mapping:
        names.append(mapping[action.iid])
    for iid in action.choices:
        if iid in mapping:
            names.append(mapping[iid])
    return tuple(names)


def policy_state_features(view: VisibleGameState) -> dict[str, float]:
    """可见视图 → 状态特征向量 v2（键序 = POLICY_STATE_NAMES）。"""
    feats = feature_vector(view)
    for prefix, discard in (("own", view.own.discard),
                            ("opp", view.opponent.discard)):
        feats[f"{prefix}_discard_count"] = float(len(discard))
        feats[f"{prefix}_discard_energy_count"] = float(
            sum(1 for c in discard if c.card.supertype == Supertype.ENERGY))
        feats[f"{prefix}_discard_pokemon_count"] = float(
            sum(1 for c in discard if c.card.supertype == Supertype.POKEMON))
    return feats


def policy_action_features(
        action: Action, view: VisibleGameState,
        card_vocab: tuple[str, ...]) -> dict[str, float]:
    """行动 + 可见视图 → 行动特征向量 v2（键序 = policy_action_names(card_vocab)）。

    卡身份 one-hot：解析出的卡名各置 1.0（choose 多 iid 命中 = multi-hot）；
    解析出的卡名不在词表 → ValueError（词表外不猜，D-062-2）。
    """
    feats = action_features(action, view)
    onehot = dict.fromkeys((f"card_{n}" for n in card_vocab), 0.0)
    for name in resolve_action_card_names(action, view):
        key = f"card_{name}"
        if key not in onehot:
            raise ValueError(
                f"卡名 {name!r} 不在词表（词表外不猜，学习线锚定卡池 v1）")
        onehot[key] = 1.0
    feats.update(onehot)
    return feats
