"""task 149：吞吐决策点 spike 探针——BC 训练最低需求 vs R2 实测产能。

判据预注册（task 149 设计段）：需求 = 1M 决策点/轮 + 50k 局 rollout/轮
（墙钟子预算 24h）；三态判定 = 决策点日产能 ≥3M/天 且 局日产能 ≥300k/天
（需求 ×10 余量）→ "r2"；否则 "r1_spike"（6 周估期门 Owner 侧评估）→ 不可信
则 "kill"。探针只读测量，不落正式结果库（零行为变更）。
"""

import time
from dataclasses import dataclass
from pathlib import Path

from battlefrontier.runner.experiment import (
    AgentCfg,
    AgentSides,
    DeckSides,
    DeckSourceCfg,
    ExperimentDef,
    PreparedExperiment,
    build_agents,
    execute_experiment,
)
from battlefrontier.runner.play import play_game
from battlefrontier.runner.results_db import ResultsDB

_DECISION_SAMPLE_CAP = 20  # 串行采样决策点/局的局数上限
_SECONDS_PER_DAY = 86400.0

# BC 训练最低需求（task 149 设计段预注册冻结；task 152 设计段可引用修订）
BC_REQUIREMENT = {"decisions_per_day": 3_000_000, "games_per_day": 300_000}


@dataclass(frozen=True)
class ProbeResult:
    agent_type: str
    games: int                  # 计划局数
    workers: int
    wall_s: float               # 并行计时 pass 墙钟
    games_per_s: float
    sec_per_game: float
    decisions_per_game: float   # 串行采样（精确计数）
    decisions_total: int        # = decisions_per_game × games_completed（估计）
    turns_total: int            # 串行采样回合数合计
    games_completed: int

    @property
    def decisions_per_s(self) -> float:
        return self.games_per_s * self.decisions_per_game

    @property
    def decisions_per_day(self) -> float:
        return self.decisions_per_s * _SECONDS_PER_DAY

    @property
    def games_per_day(self) -> float:
        return self.games_per_s * _SECONDS_PER_DAY


class CountingAgent:
    """包装 agent 精确计数 observe 调用（决策点）；属性全量委托底层。"""

    def __init__(self, base) -> None:
        self._base = base
        self.decisions = 0

    def observe(self, view, actions):
        self.decisions += 1
        return self._base.observe(view, actions)

    def __getattr__(self, name):
        return getattr(self._base, name)


def probe_defn(agent_type: str, games: int, seed_start: int,
               policy_path: str | None, deck_id: str = "probe") -> ExperimentDef:
    params = {"policy_path": policy_path} if agent_type == "distilled" else {}
    cfg = AgentCfg(type=agent_type, params=params)
    return ExperimentDef(
        name="probe", games=games, seed_start=seed_start,
        decks=DeckSides(a=DeckSourceCfg(source="db", deck_id=deck_id),
                        b=DeckSourceCfg(source="db", deck_id=deck_id)),
        agents=AgentSides(a=cfg, b=cfg))


def net_forward_probe(policy_path: str | Path, *, n: int = 10_000,
                      seed: int = 0) -> str:
    """policy 纯 numpy 前向微基准（小网 rollout 的单决策打分地板锚，不经引擎）。"""
    import time

    import numpy as np

    from battlefrontier.learn.policy_model import load_policy_model

    model = load_policy_model(policy_path)
    w1 = np.asarray(model.weights["w1"], dtype=np.float64)
    b1 = np.asarray(model.weights["b1"], dtype=np.float64)
    w2 = np.asarray(model.weights["w2"], dtype=np.float64)
    b2 = np.asarray(model.weights["b2"], dtype=np.float64)
    rng = np.random.default_rng(seed)
    x = rng.random((w1.shape[1],))
    t0 = time.perf_counter()
    for _ in range(n):
        hidden = np.maximum(x @ w1.T + b1, 0.0)
        _ = hidden @ w2.T + b2
    dt = time.perf_counter() - t0
    per = dt / n
    return (f"policy 前向微基准：{w1.shape[1]} 维输入 × {n} 次 = "
            f"{per * 1e6:.1f} µs/次 → 理论上限 {1.0 / per:,.0f} 打分/s/核")


def stub_prep() -> PreparedExperiment:
    """内置 stub 卡组（20 基础带招 + 4 一阶 + 20 基础带招 + 16 能量，零 db 冒烟用）。"""
    from battlefrontier.engine.state import AttackDef, CardDef

    def _basic(name: str) -> CardDef:
        return CardDef(
            card_id=f"stub-{name}", name=name, supertype="pokemon",
            hp=70, stage=0,
            attacks=(AttackDef(name="撞击", cost=("无",), damage=20),),
            retreat_cost=1)

    def _stage1(name: str, pre: str) -> CardDef:
        return CardDef(
            card_id=f"stub-{name}", name=name, supertype="pokemon",
            hp=90, stage=1, evolves_from=pre,
            attacks=(AttackDef(name="猛撞", cost=("草",), damage=40),),
            retreat_cost=1)

    def _energy() -> CardDef:
        return CardDef(card_id="stub-能量", name="基本草能量", supertype="energy",
                       energy_type="草", is_basic_energy=True, provides=("草",))

    deck = ([_basic("种子甲")] * 20 + [_stage1("种子乙", "种子甲")] * 4
            + [_basic("火种甲")] * 20 + [_energy()] * 16)
    assert len(deck) == 60
    return PreparedExperiment(deck_a=deck, deck_b=list(deck), card_effects={},
                              deck_a_id="stub", deck_b_id="stub",
                              data_version="stub")


def probe_throughput(agent_type: str, games: int, workers: int, seed_start: int, *,
                     prep: PreparedExperiment,
                     results_path: str | Path,
                     policy_path: str | None = None) -> ProbeResult:
    """串行采样决策点/局 + 并行计时局产能 → ProbeResult。

    prep 由调用方装配（stub 或真实卡组）；distilled 必须给 policy_path（不猜）。
    """
    if agent_type == "distilled" and not policy_path:
        raise ValueError("distilled 探针需要 policy_path（不猜）")
    defn = probe_defn(agent_type, games, seed_start, policy_path)

    # 串行采样 pass：精确决策点计数（主进程内，包装器可见）
    sample = min(games, _DECISION_SAMPLE_CAP)
    decisions = 0
    turns = 0
    for i in range(sample):
        seed = seed_start + i
        counters = [CountingAgent(a) for a in build_agents(defn, seed, {})]
        result = play_game(prep.deck_a, prep.deck_b, seed=seed,
                           card_effects=prep.card_effects, agents=counters)
        decisions += sum(c.decisions for c in counters)
        turns += result.turns

    # 并行计时 pass：复用 execute_experiment（并串一致纪律继承），落临时库
    t0 = time.perf_counter()
    exp_id = execute_experiment(prep, defn, results_path, workers=workers,
                                definition_yaml="probe")
    wall = time.perf_counter() - t0
    db = ResultsDB(results_path)
    try:
        rows = db.games(exp_id)
        completed = sum(1 for g in rows if g["error"] is None)
    finally:
        db.close()

    games_per_s = completed / wall if wall > 0 else 0.0
    dpg = decisions / sample if sample > 0 else 0.0
    return ProbeResult(
        agent_type=agent_type, games=games, workers=workers, wall_s=wall,
        games_per_s=games_per_s,
        sec_per_game=wall / completed if completed > 0 else 0.0,
        decisions_per_game=dpg,
        decisions_total=round(dpg * completed),
        turns_total=turns, games_completed=completed)


def decide_r2(result: ProbeResult, requirement: dict | None = None) -> str:
    """三态判定（预注册门槛）：双过线 → "r2"；否则 "r1_spike"。

    "kill" 由 Owner 侧在 r1_spike 估期 >6 周或不可信时裁决（探针不替 Owner 拍板）。
    """
    req = requirement or BC_REQUIREMENT
    if (result.decisions_per_day >= req["decisions_per_day"]
            and result.games_per_day >= req["games_per_day"]):
        return "r2"
    return "r1_spike"


def format_probe(result: ProbeResult, decision: str) -> str:
    """人类可读测量报告（限定语头注同 report 层纪律）。"""
    from battlefrontier.report import SIM_INTERPRETATION_NOTE
    return "\n".join([
        SIM_INTERPRETATION_NOTE, "",
        (f"探针：agent={result.agent_type} 计划 {result.games} 局 / workers="
        f"{result.workers} / 完成 {result.games_completed} 局 / 墙钟 "
        f"{result.wall_s:.1f}s"),
        (f"产能：{result.games_per_s:.1f} 局/s（{result.sec_per_game * 1000:.1f} "
        f"ms/局）→ {result.games_per_day:,.0f} 局/天"),
        (f"决策点：{result.decisions_per_game:.1f}/局（串行采样精确计数）→ "
        f"{result.decisions_per_s:,.0f}/s → {result.decisions_per_day:,.0f}/天"),
        (f"判定（预注册门槛：≥{BC_REQUIREMENT['decisions_per_day']:,.0f} 决策点/天 "
        f"且 ≥{BC_REQUIREMENT['games_per_day']:,.0f} 局/天）：{decision}"),
    ])
