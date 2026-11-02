"""M14 后决策差异归因（task 098）：只读既有结果库的候选模式评估。

口径：模式只描述 MCTS A 侧实际选中的行动（`mcts_consider.chosen`），
效果仍沿用 M14 CRN——以共同种子比较启发式与 MCTS 的 A 侧胜负，方向取
“向真实胜率改善”。本模块不跑新实验、不接触 Agent/DSL/引擎规则。
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from battlefrontier.report.winrate import Z_95

ACTION_KINDS = frozenset({
    "attack", "copy_attack", "retreat", "promote", "use_ability",
    "play_stadium", "use_stadium", "attach_energy", "attach_tool",
    "play_trainer", "evolve", "place_bench", "end_turn", "place_active",
})
DISCOVERY_KINDS = ACTION_KINDS - {"choose", "end_turn"}
# 启发式 attach_energy 事件没有能量名，只有目标；token 模式不可对照。
TOKENLESS_DISCOVERY_KINDS = frozenset({"attach_energy"})

MIN_POINTS_PER_BATCH = 20
MIN_GAMES_PER_BATCH = 5


@dataclass(frozen=True)
class DecisionRecord:
    seed: int
    side: int
    turn: int
    phase: str
    kind: str
    action: str


@dataclass(frozen=True)
class ActionRecord:
    seed: int
    side: int
    turn: int
    phase: str
    kind: str
    action: str


@dataclass(frozen=True)
class PatternSpec:
    name: str
    kind: str | None = None
    bucket: str | None = None
    contains: str | None = None
    side: int = 0

    def matches(self, record: DecisionRecord | ActionRecord) -> bool:
        if record.side != self.side:
            return False
        if self.kind is not None and record.kind != self.kind:
            return False
        if self.bucket is not None and turn_bucket(record.turn, record.phase) != self.bucket:
            return False
        return self.contains is None or self.contains in record.action


@dataclass(frozen=True)
class BatchData:
    label: str
    real_wr: float
    decisions: tuple[DecisionRecord, ...]
    mcts_outcomes: dict[int, int]
    heuristic_outcomes: dict[int, int]
    heuristic_actions: tuple[ActionRecord, ...] = ()


@dataclass(frozen=True)
class PatternBatchStat:
    label: str
    points: int
    games: int
    mcts_rate: float
    heuristic_rate: float
    effect: float | None
    ci_low: float | None
    ci_high: float | None


@dataclass(frozen=True)
class PatternEvaluation:
    spec: PatternSpec
    batch_stats: tuple[PatternBatchStat, ...]
    combined_effect: float | None
    combined_ci_low: float | None
    combined_ci_high: float | None
    control_significant_deterioration: bool
    reverse_significant_deterioration: bool
    fail_reasons: tuple[str, ...]

    @property
    def passes(self) -> bool:
        return not self.fail_reasons


def turn_bucket(turn: int, phase: str) -> str:
    if phase.startswith("setup"):
        return "setup"
    if turn <= 3:
        return "early"
    if turn <= 8:
        return "mid"
    return "late"


def _connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _games(con: sqlite3.Connection, experiment_id: int) -> tuple[sqlite3.Row, ...]:
    rows = tuple(con.execute(
        "SELECT id, seed, winner, is_draw, error FROM games WHERE experiment_id=?",
        (experiment_id,),
    ))
    for row in rows:
        if row["error"] is not None:
            raise ValueError(f"种子 {row['seed']} 存在失败局")
        if row["is_draw"] or row["winner"] not in (0, 1):
            raise ValueError(f"种子 {row['seed']} 存在平局或非决定局")
    return rows


def _chosen_kind(detail: dict) -> str:
    chosen = str(detail.get("chosen", ""))
    kind = detail.get("chosen_kind")
    if kind:
        return str(kind)
    for sep in ("：", ":"):
        if sep in chosen:
            return chosen.split(sep, 1)[0]
    for item in detail.get("considered", ()):
        if item.get("action") == chosen and item.get("kind"):
            return str(item["kind"])
    raise ValueError(f"mcts_consider 无法解析 chosen kind：{chosen!r}")


def load_decision_records(path: str, *, experiment_id: int = 1,
                          side: int | None = 0) -> tuple[DecisionRecord, ...]:
    con = _connect(path)
    try:
        records: list[DecisionRecord] = []
        for game in _games(con, experiment_id):
            for row in con.execute(
                "SELECT event_json FROM game_events WHERE game_id=? ORDER BY seq",
                (game["id"],),
            ):
                event = json.loads(row["event_json"])
                if event.get("kind") != "mcts_consider":
                    continue
                if side is not None and event.get("player") != side:
                    continue
                records.append(DecisionRecord(
                    seed=int(game["seed"]), side=int(event["player"]),
                    turn=int(event["turn"]), phase=str(event["phase"]),
                    kind=_chosen_kind(event["detail"]),
                    action=str(event["detail"].get("chosen", "")),
                ))
        return tuple(records)
    finally:
        con.close()


def load_action_records(path: str, *, experiment_id: int = 1,
                        side: int | None = 0) -> tuple[ActionRecord, ...]:
    con = _connect(path)
    try:
        records: list[ActionRecord] = []
        for game in _games(con, experiment_id):
            for row in con.execute(
                "SELECT event_json FROM game_events WHERE game_id=? ORDER BY seq",
                (game["id"],),
            ):
                event = json.loads(row["event_json"])
                if event.get("kind") not in ACTION_KINDS:
                    continue
                if side is not None and event.get("player") != side:
                    continue
                records.append(ActionRecord(
                    seed=int(game["seed"]), side=int(event["player"]),
                    turn=int(event["turn"]), phase=str(event["phase"]),
                    kind=str(event["kind"]),
                    action=f"{event['kind']}：{json.dumps(event.get('detail', {}), ensure_ascii=False, sort_keys=True)}",
                ))
        return tuple(records)
    finally:
        con.close()


def _tokens(action: str) -> tuple[str, ...]:
    return tuple(t for t in re.split(r"[：:+→/、，,\s]+", action) if len(t) >= 2)


def discover_patterns(decisions: Iterable[DecisionRecord], *,
                      max_candidates: int = 128,
                      tokens_per_group: int = 8,
                      side: int = 0) -> tuple[PatternSpec, ...]:
    decisions = tuple(record for record in decisions if record.side == side)
    specs: set[PatternSpec] = set()
    tokens_by_group: dict[tuple[str, str], Counter[str]] = {}
    for record in decisions:
        if record.kind not in DISCOVERY_KINDS:
            continue
        bucket = turn_bucket(record.turn, record.phase)
        group = (record.kind, bucket)
        specs.add(PatternSpec(name=f"{record.kind}@{bucket}", kind=record.kind,
                              bucket=bucket, side=side))
        if record.kind in TOKENLESS_DISCOVERY_KINDS:
            continue
        counts = tokens_by_group.setdefault(group, Counter())
        for token in _tokens(record.action):
            if token != record.kind:
                counts[token] += 1
    for kind, bucket in sorted(tokens_by_group):
        counts = tokens_by_group[(kind, bucket)]
        for token, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:tokens_per_group]:
            specs.add(PatternSpec(name=f"{kind}@{bucket}[{token}]", kind=kind,
                                  bucket=bucket, contains=token, side=side))
    unique: dict[tuple[int, tuple[int, ...]], PatternSpec] = {}
    for spec in specs:
        matches = tuple(record for record in decisions if spec.matches(record))
        signature = (len(matches), tuple(sorted({record.seed for record in matches})))
        complexity = sum(value is not None for value in (spec.kind, spec.bucket, spec.contains))
        current = unique.get(signature)
        if current is None or (complexity, spec.name) < (
            sum(value is not None for value in (current.kind, current.bucket, current.contains)),
            current.name,
        ):
            unique[signature] = spec
    return tuple(sorted(unique.values(), key=lambda spec: spec.name)[:max_candidates])


def _effect_ci(effects: list[int]) -> tuple[float | None, float | None, float | None]:
    if len(effects) < 2:
        return None, None, None
    effect = statistics.mean(effects)
    se = statistics.stdev(effects) / math.sqrt(len(effects))
    margin = Z_95 * se
    return effect, effect - margin, effect + margin


def _direction(batch: BatchData) -> int:
    heuristic_wr = sum(1 for winner in batch.heuristic_outcomes.values()
                       if winner == 0) / len(batch.heuristic_outcomes)
    direction = (batch.real_wr > heuristic_wr) - (batch.real_wr < heuristic_wr)
    if direction == 0:
        raise ValueError(f"{batch.label} 改善方向不可用")
    return direction


def _batch_stat(batch: BatchData, spec: PatternSpec) -> PatternBatchStat:
    seeds = set(batch.mcts_outcomes)
    if seeds != set(batch.heuristic_outcomes):
        raise ValueError(f"{batch.label} 种子集合不一致")
    pattern_games = {r.seed for r in batch.decisions if spec.matches(r)}
    pattern_points = sum(1 for r in batch.decisions if spec.matches(r))
    heuristic_games = {r.seed for r in batch.heuristic_actions if spec.matches(r)}
    effects = [
        _direction(batch) * ((batch.mcts_outcomes[s] == 0) -
                             (batch.heuristic_outcomes[s] == 0))
        for s in sorted(pattern_games)
    ]
    effect, ci_low, ci_high = _effect_ci(effects)
    return PatternBatchStat(
        label=batch.label,
        points=pattern_points,
        games=len(pattern_games),
        mcts_rate=len(pattern_games) / len(seeds),
        heuristic_rate=len(heuristic_games) / len(seeds),
        effect=effect,
        ci_low=ci_low,
        ci_high=ci_high,
    )


def _has_significant_deterioration(batches: Iterable[BatchData],
                                   spec: PatternSpec) -> bool:
    for batch in batches:
        stat = _batch_stat(batch, spec)
        if stat.ci_high is not None and stat.ci_high < 0:
            return True
    return False


def evaluate_pattern(spec: PatternSpec, target_batches: tuple[BatchData, ...], *,
                     control_batches: tuple[BatchData, ...] = (),
                     reverse_batches: tuple[BatchData, ...] = ()) -> PatternEvaluation:
    if len(target_batches) < 2:
        raise ValueError("候选模式至少需要两个独立批次")
    batch_stats = tuple(_batch_stat(batch, spec) for batch in target_batches)
    combined_effects: list[int] = []
    for batch, stat in zip(target_batches, batch_stats, strict=True):
        pattern_games = {r.seed for r in batch.decisions if spec.matches(r)}
        combined_effects.extend(
            _direction(batch) * ((batch.mcts_outcomes[s] == 0) -
                                 (batch.heuristic_outcomes[s] == 0))
            for s in sorted(pattern_games)
        )
    combined_effect, combined_ci_low, combined_ci_high = _effect_ci(combined_effects)
    control_bad = _has_significant_deterioration(control_batches, spec)
    reverse_bad = _has_significant_deterioration(reverse_batches, spec)

    failures: list[str] = []
    for stat in batch_stats:
        if stat.points < MIN_POINTS_PER_BATCH or stat.games < MIN_GAMES_PER_BATCH:
            failures.append(f"{stat.label} 覆盖不足（{stat.points} 点 / {stat.games} 局）")
        if stat.effect is None:
            failures.append(f"{stat.label} 无法估计逐种子效果")
        elif stat.effect <= 0:
            failures.append(f"{stat.label} 方向未改善")
    if combined_effect is None or combined_ci_low is None:
        failures.append("合并效果无法估计")
    elif combined_ci_low <= 0:
        failures.append("合并效果 CI 下界未 >0")
    if control_bad:
        failures.append("低残差对照出现显著反向")
    if reverse_bad:
        failures.append("反向 sanity check 出现显著反向")
    return PatternEvaluation(
        spec=spec,
        batch_stats=batch_stats,
        combined_effect=combined_effect,
        combined_ci_low=combined_ci_low,
        combined_ci_high=combined_ci_high,
        control_significant_deterioration=control_bad,
        reverse_significant_deterioration=reverse_bad,
        fail_reasons=tuple(failures),
    )


def evaluate_patterns(specs: Iterable[PatternSpec], target_batches: tuple[BatchData, ...], *,
                      control_batches: tuple[BatchData, ...] = (),
                      reverse_batches: tuple[BatchData, ...] = ()) -> tuple[PatternEvaluation, ...]:
    evaluations = [
        evaluate_pattern(spec, target_batches, control_batches=control_batches,
                         reverse_batches=reverse_batches)
        for spec in specs
    ]
    return tuple(sorted(
        evaluations,
        key=lambda item: (
            not item.passes,
            -(item.combined_effect if item.combined_effect is not None else -9.0),
            item.spec.name,
        ),
    ))


def analyze_pair(name: str, discovery: BatchData, validation: BatchData, *,
                 control_batches: tuple[BatchData, ...] = (),
                 reverse_batches: tuple[BatchData, ...] = (),
                 max_candidates: int = 256) -> tuple[PatternEvaluation, ...]:
    """首批发现、二批验证的 task 098 标准分析入口。"""
    specs = discover_patterns(discovery.decisions, max_candidates=max_candidates)
    evaluations = evaluate_patterns(
        specs, (discovery, validation),
        control_batches=control_batches,
        reverse_batches=reverse_batches,
    )
    return tuple(sorted(
        evaluations,
        key=lambda item: (
            not item.passes,
            -(abs(item.batch_stats[0].mcts_rate - item.batch_stats[0].heuristic_rate)
              if item.batch_stats else 0.0),
            -(item.combined_effect if item.combined_effect is not None else -9.0),
            item.spec.name,
        ),
    ))


def evaluation_to_dict(evaluation: PatternEvaluation) -> dict:
    return {
        "spec": evaluation.spec.name,
        "passes": evaluation.passes,
        "combined_effect": evaluation.combined_effect,
        "combined_ci": [evaluation.combined_ci_low, evaluation.combined_ci_high],
        "control_significant_deterioration": evaluation.control_significant_deterioration,
        "reverse_significant_deterioration": evaluation.reverse_significant_deterioration,
        "fail_reasons": list(evaluation.fail_reasons),
        "batches": [
            {
                "label": stat.label,
                "points": stat.points,
                "games": stat.games,
                "mcts_rate": stat.mcts_rate,
                "heuristic_rate": stat.heuristic_rate,
                "effect": stat.effect,
                "ci": [stat.ci_low, stat.ci_high],
            }
            for stat in evaluation.batch_stats
        ],
    }


def _batch_from_paths(label: str, heuristic_db: str, mcts_db: str,
                      real_wr: float) -> BatchData:
    from battlefrontier.report.paired import paired_outcomes
    from battlefrontier.runner.results_db import ResultsDB

    heuristic = ResultsDB(heuristic_db)
    mcts = ResultsDB(mcts_db)
    try:
        rows = paired_outcomes(heuristic, 1, mcts, 1)
        return BatchData(
            label=label,
            real_wr=real_wr,
            decisions=load_decision_records(mcts_db, side=None),
            mcts_outcomes={seed: mcts_win for seed, _, mcts_win in rows},
            heuristic_outcomes={seed: heuristic_win for seed, heuristic_win, _ in rows},
            heuristic_actions=load_action_records(heuristic_db, side=0),
        )
    finally:
        heuristic.close()
        mcts.close()


def load_standard_batches() -> dict[str, BatchData]:
    """task 098 预注册数据集；路径固定，确保命令可重复。"""
    real = {
        "j": 0.503968253968254,
        "z": 0.4777777777777778,
        "c": 0.49074074074074076,
        "g": 0.2786885245901639,
    }
    return {
        "j1": _batch_from_paths("j1", "results/m14-drag-joltik-heuristic.db",
                                "results/m14-drag-joltik-mcts.db", real["j"]),
        "j2": _batch_from_paths("j2", "results/m14-drag-joltik-confirm-heuristic.db",
                                "results/m14-drag-joltik-confirm-mcts.db", real["j"]),
        "z1": _batch_from_paths("z1", "results/m14-drag-zoro-heuristic.db",
                                "results/m14-drag-zoro-mcts.db", real["z"]),
        "z2": _batch_from_paths("z2", "results/m14-drag-zoro-confirm-heuristic.db",
                                "results/m14-drag-zoro-confirm-mcts.db", real["z"]),
        "control": _batch_from_paths("control", "results/m14-char-grim-heuristic.db",
                                     "results/m14-char-grim-mcts.db", real["c"]),
        "reverse": _batch_from_paths("reverse", "results/m14-gard-zoro-heuristic.db",
                                     "results/m14-gard-zoro-mcts.db", real["g"]),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json as jsonlib

    parser = argparse.ArgumentParser(description="task 098 M14 decision-difference mining")
    parser.add_argument("--pair", choices=("drag-joltik", "drag-zoro", "both"),
                        default="both")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    parser.add_argument("--out", help="write JSON summary to this path")
    args = parser.parse_args(argv)

    batches = load_standard_batches()
    targets = {
        "drag-joltik": ("j1", "j2"),
        "drag-zoro": ("z1", "z2"),
    }
    selected = targets if args.pair == "both" else {args.pair: targets[args.pair]}
    analyses = {
        name: analyze_pair(
            name, batches[keys[0]], batches[keys[1]],
            control_batches=(batches["control"],),
            reverse_batches=(batches["reverse"],),
        )
        for name, keys in selected.items()
    }
    payload = {
        "total_decisions": sum(len(batch.decisions) for batch in batches.values()),
        "games": {key: len(batch.mcts_outcomes) for key, batch in batches.items()},
        "analyses": {
            name: [evaluation_to_dict(item) for item in evaluations]
            for name, evaluations in analyses.items()
        },
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            jsonlib.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json or args.out:
        print(jsonlib.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"total_decisions={payload['total_decisions']}")
        for name, evaluations in analyses.items():
            passing = [item for item in evaluations if item.passes]
            print(f"\n[{name}] candidates={len(evaluations)} passing={len(passing)}")
            for item in evaluations[:args.top]:
                stat0, stat1 = item.batch_stats
                rate_delta = stat0.mcts_rate - stat0.heuristic_rate
                print(
                    f"{item.spec.name}\tpass={item.passes}"
                    f"\tdelta1={rate_delta:.3f}"
                    f"\teffect={item.combined_effect:.3f}"
                    f"\tci=({item.combined_ci_low:.3f},{item.combined_ci_high:.3f})"
                    f"\tcov={stat0.points}/{stat0.games},{stat1.points}/{stat1.games}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
