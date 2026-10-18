"""M12 蒸馏策略行动侧特征（task 058 WP2，D-M12-1/2）：Action + 行动方可见视图 → 特征向量。

纯函数 `action_features(action, view) -> dict[str, float]`：零随机、零引擎调用——
只读 Action 结构化字段（kind/iid/target_iid/bench_index/attack_index/choices，
引擎零硬编码纪律：不解析 DSL 语义，招式伤害等卡面量不入行动特征）与
VisibleGameState（目标关系标志经可见在场区 iid 解析，不碰隐藏信息）。键序由
`ACTION_FEATURE_NAMES` 钉死（训练/推理/模型资产共用此序）。

- **D-M12-1 kind 词表 16 类**：core.py 枚举 15 种 + chooser「choose」
  （任务书草稿写「15 类」系漏计 choose——choice 阶段占冒烟样本 28%，
  排除会丢掉该阶段全部监督信号）。排序固定（字母序），词表外 kind 显式报错。
- **D-M12-2 数值标量**：attack_index / has_iid / has_target_iid /
  has_bench_index / bench_index / n_choices + 目标关系标志 4 个
  （target_iid ∈ 己方战斗场/己方备战区/对方战斗场/对方备战区）。
"""

from __future__ import annotations

from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import InPlayPokemon, VisibleGameState

__all__ = ["ACTION_FEATURE_NAMES", "ACTION_KINDS", "action_features"]

# 行动 kind 词表（D-M12-1；引擎 core.py 全量 15 种 + chooser choose，字母序钉死）
ACTION_KINDS: tuple[str, ...] = (
    "attach_energy",
    "attach_tool",
    "attack",
    "choose",
    "confirm_setup",
    "end_turn",
    "evolve",
    "place_active",
    "place_bench",
    "play_stadium",
    "play_trainer",
    "promote",
    "retreat",
    "shrink_bench",
    "use_ability",
    "use_stadium",
)

# 行动特征清单 v1（键序钉死）：kind one-hot 16 + 数值标量 6 + 目标关系标志 4
ACTION_FEATURE_NAMES: tuple[str, ...] = tuple(f"kind_{k}" for k in ACTION_KINDS) + (
    "attack_index",
    "has_iid",
    "has_target_iid",
    "has_bench_index",
    "bench_index",
    "n_choices",
    "target_is_own_active",
    "target_is_own_bench",
    "target_is_opp_active",
    "target_is_opp_bench",
)

_TARGET_FLAG_KEYS = (
    "target_is_own_active",
    "target_is_own_bench",
    "target_is_opp_active",
    "target_is_opp_bench",
)


def _iid_in(iid: int, active: InPlayPokemon | None,
            bench: tuple[InPlayPokemon, ...]) -> tuple[bool, bool]:
    """iid 是否命中 (战斗场, 备战区)（含进化栈底层与附着能量/道具——stack/attached
    全部 iid 均可能被 target 指向）。"""
    def hits(p: InPlayPokemon) -> bool:
        pool = [c.iid for c in p.stack]
        pool += [c.iid for c in p.attached_energy]
        if p.attached_tool is not None:
            pool.append(p.attached_tool.iid)
        return iid in pool

    in_active = active is not None and hits(active)
    in_bench = any(hits(p) for p in bench)
    return in_active, in_bench


def action_features(action: Action, view: VisibleGameState) -> dict[str, float]:
    """结构化 Action + 行动方可见视图 → 特征向量（键序 = ACTION_FEATURE_NAMES）。

    kind 须在 ACTION_KINDS 词表内（词表外显式报错——不猜）；目标关系标志只读
    可见在场区（view.own / view.opponent 的 active/bench），无 target 或 target
    不在可见在场区（如手牌 iid、choice 池 iid）时全 0。
    """
    if action.kind not in ACTION_KINDS:
        raise ValueError(
            f"未知行动 kind：{action.kind!r}（词表 {list(ACTION_KINDS)}，不猜）")
    feats = {f"kind_{k}": float(action.kind == k) for k in ACTION_KINDS}
    feats["attack_index"] = float(action.attack_index)
    feats["has_iid"] = float(action.iid is not None)
    feats["has_target_iid"] = float(action.target_iid is not None)
    feats["has_bench_index"] = float(action.bench_index is not None)
    feats["bench_index"] = float(action.bench_index or 0)
    feats["n_choices"] = float(len(action.choices))
    flags = dict.fromkeys(_TARGET_FLAG_KEYS, 0.0)
    if action.target_iid is not None:
        own_active, own_bench = _iid_in(action.target_iid, view.own.active,
                                        view.own.bench)
        opp_active, opp_bench = _iid_in(action.target_iid, view.opponent.active,
                                        view.opponent.bench)
        flags["target_is_own_active"] = float(own_active)
        flags["target_is_own_bench"] = float(own_bench)
        flags["target_is_opp_active"] = float(opp_active)
        flags["target_is_opp_bench"] = float(opp_bench)
    feats.update(flags)
    return feats
