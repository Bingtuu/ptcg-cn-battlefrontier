"""M11 决策一致率评估（task 052 WP3，D-M11-5）：快照重放受测配置比对 argmax。

- 载入快照（runner.snapshot.load_snapshot_file）→ 逐行重建 GameState（Pydantic
  往返）→ 同状态跑受测配置（降预算 + eval_cutoff_turns + 评估器）MCTS 搜索 →
  学生 argmax 结构化 Action 与教师 Action 直接比对（dataclass 值相等，不用
  字符串标签——choose 类卡名拼接有碰撞风险，D-M11-5）。
- **分母口径 v1**：main 阶段且教师选定行动 kind ∈ {attack, play_trainer,
  end_turn} 的决策点；choose/promote/setup 等非 main 阶段与其余 main 行动类
  （retreat/evolve/use_ability/attach_energy 等）不进分母，计数进 appendix。
  唯一合法行动早退点在采集侧已剔除（SnapshotCollector 只落实际搜索的决策点）。
- **种子协议**：学生每次重放 rng 种子 = sha256(f"<config_fingerprint>:<快照序号>")
  前 8 字节 little-endian（快照序号 = 文件内 0 起行序）；config_fingerprint =
  受测配置 dict 的规范 JSON sha256 前 16 hex。两者钉死进报告输出。
- 评估纯确定性：同快照文件 + 同受测配置两跑逐字段一致。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from battlefrontier.agent.mcts import MCTSAgent
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import GameEngine
from battlefrontier.engine.rng import RandomSource
from battlefrontier.runner.snapshot import (
    SnapshotFile,
    load_snapshot_file,
    snapshot_state,
    teacher_action,
)

__all__ = [
    "DENOMINATOR_KINDS",
    "agreement_report",
    "classify_row",
    "config_fingerprint",
    "replay_student",
    "run_agreement",
    "run_agreement_file",
    "student_seed",
]

# 分母口径 v1（D-M11-5）：main 阶段三类行动决策点
DENOMINATOR_KINDS = frozenset({"attack", "play_trainer", "end_turn"})


def classify_row(row: dict) -> str:
    """快照行分类：``denominator``（进分母）/ ``excluded:non_main`` /
    ``excluded:other_main``（附录计数）。"""
    if row["phase"] != "main":
        return "excluded:non_main"
    if row["action_kind"] in DENOMINATOR_KINDS:
        return "denominator"
    return "excluded:other_main"


def config_fingerprint(cfg: dict) -> str:
    """受测配置指纹：规范 JSON（sort_keys）sha256 前 16 hex。"""
    payload = json.dumps(cfg, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def student_seed(fingerprint: str, snapshot_index: int) -> int:
    """学生重放种子 = sha256(f"{fingerprint}:{snapshot_index}") 前 8 字节 LE。"""
    digest = hashlib.sha256(f"{fingerprint}:{snapshot_index}".encode()).digest()
    return int.from_bytes(digest[:8], "little")


def replay_student(row: dict, card_effects, cfg: dict, seed: int) -> tuple[Action, list[Action]]:
    """在快照局面重放受测配置：重建引擎（state 置为快照 GameState，clone 同口径）
    → MCTSAgent（cfg 全量透传）→ bind_engine + observe → 返回 (学生 argmax, 合法行动)。

    快照 state 含隐藏信息真值，但 observe 入口照常 determinize（对手手牌/牌库序/
    奖赏重采样，信息纪律）；引擎自身 rng 由 seed 固定（搜索随机源走 agent._rng）。
    """
    state = snapshot_state(row)
    player = row["player"]
    engine = GameEngine(RandomSource(seed), card_effects=card_effects)
    engine.state = state
    agent = MCTSAgent(RandomSource(seed), **cfg)
    agent.bind_engine(engine)
    legal = engine.legal_actions(player)
    return agent.observe(state.visible_state(player), legal), legal


def run_agreement(snapshot: SnapshotFile, student: dict) -> dict:
    """对一份快照文件跑受测配置并产出一致率报告（纯确定性）。"""
    card_effects = snapshot.card_effects()
    fp = config_fingerprint(student)
    appendix = {"excluded_non_main": 0, "excluded_other_main": 0,
                "teacher_action_not_legal": 0}
    details: list[dict] = []
    agree = 0
    denominator = 0
    for index, row in enumerate(snapshot.rows):
        cls = classify_row(row)
        if cls != "denominator":
            appendix[f"excluded_{cls.split(':', 1)[1]}"] += 1
            continue
        denominator += 1
        seed = student_seed(fp, index)
        student_action, legal = replay_student(row, card_effects, student, seed)
        teacher = teacher_action(row)
        teacher_legal = teacher in legal
        if not teacher_legal:
            appendix["teacher_action_not_legal"] += 1
        ok = teacher_legal and student_action == teacher
        agree += ok
        details.append({
            "index": index,
            "seed": row["seed"],
            "turn": row["turn"],
            "player": row["player"],
            "teacher_kind": row["action_kind"],
            "student_kind": student_action.kind,
            "agree": ok,
            "student_seed": seed,
        })
    return {
        "snapshots_total": len(snapshot.rows),
        "denominator": denominator,
        "agree": agree,
        "agreement_rate": (agree / denominator) if denominator else None,
        "appendix": appendix,
        "config": dict(student),
        "config_fingerprint": fp,
        "seed_protocol": "sha256(config_fingerprint:snapshot_index)[:8] LE",
        "rows": details,
    }


def run_agreement_file(path: str | Path, student: dict) -> dict:
    """载入快照文件 + run_agreement 一步走（CLI 入口用）。"""
    return run_agreement(load_snapshot_file(path), student)


def agreement_report(report: dict) -> str:
    """报告人读渲染（CLI 打印）。"""
    lines = [
        (f"快照 {report['snapshots_total']} 条；分母（main 阶段 "
         f"attack/play_trainer/end_turn）{report['denominator']} 条"),
    ]
    rate = report["agreement_rate"]
    lines.append(
        f"一致率 {rate:.4f}（{report['agree']}/{report['denominator']}）"
        if rate is not None else "一致率 N/A（分母为 0）")
    ap = report["appendix"]
    lines.append(
        f"附录（不进分母）：非 main 阶段 {ap['excluded_non_main']} / "
        f"其余 main 行动类 {ap['excluded_other_main']} / "
        f"教师行动不合法 {ap['teacher_action_not_legal']}")
    lines.append(
        f"受测配置 {json.dumps(report['config'], ensure_ascii=False, sort_keys=True)}"
        f"（fingerprint {report['config_fingerprint']}；种子协议 "
        f"{report['seed_protocol']}）")
    return "\n".join(lines)
