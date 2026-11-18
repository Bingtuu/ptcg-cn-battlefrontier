"""task 127：agent 种群联赛——注册表 schema + 细胞规划 + 执行编排。

定位 = M16（BC 路线）评估面前置：注册表钉死规模，CRN 双向配对（同种子区间
ab/ba 共享），评级主估计子 BT-MLE 在 report/league.py（task 148 教训：禁固定
大步长顺序 Elo）。
"""

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from battlefrontier.runner.experiment import (
    DEFAULT_CARDS_DIR,
    AgentCfg,
    AgentSides,
    DeckSides,
    DeckSourceCfg,
    ExperimentDef,
    execute_experiment,
    prepare_experiment,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class LeagueAgent(FrozenModel):
    """注册表中的一个 agent 成员（扁平 yml 表达）：id + type/params。

    type/params 白名单「不猜」校验复用 AgentCfg——装载时即实例化校验一次。
    """

    id: str = Field(min_length=1)
    type: str = "random"
    params: dict[str, float | int | bool | str] = {}

    @model_validator(mode="after")
    def _check_cfg(self) -> "LeagueAgent":
        AgentCfg(type=self.type, params=self.params)  # 白名单校验（不猜），结果丢弃
        return self

    @property
    def cfg(self) -> AgentCfg:
        return AgentCfg(type=self.type, params=self.params)


class LeagueDef(FrozenModel):
    """联赛注册表：规模全部钉死在 yml（成本纪律）。"""

    name: str = Field(min_length=1)
    seed_start: int = Field(ge=0)
    seed_stride: int = Field(gt=0)
    games_per_cell: int = Field(gt=0)
    decks: list[DeckSourceCfg] = Field(min_length=1)
    agents: list[LeagueAgent] = Field(min_length=2)

    @model_validator(mode="after")
    def _check_agents(self) -> "LeagueDef":
        ids = [a.id for a in self.agents]
        if len(ids) != len(set(ids)):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"agent id 必须唯一（不猜）: {dup}")
        return self

    @model_validator(mode="after")
    def _check_stride(self) -> "LeagueDef":
        if self.seed_stride < self.games_per_cell:
            raise ValueError(
                f"seed_stride({self.seed_stride}) 必须 ≥ games_per_cell"
                f"({self.games_per_cell})——否则细胞种子区间重叠（不猜）")
        return self


def load_league(path: str | Path) -> LeagueDef:
    text = Path(path).read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise TypeError("联赛注册表必须是 yml 映射（不猜）")
    return LeagueDef.model_validate(raw)


class CellPlan(FrozenModel):
    """一个联赛细胞：双向（ab/ba）之一 × 一个无序对 × 一个 deck。

    同无序对的全部细胞共享种子区间（CRN 双向配对，先手偏差聚合层对消）。
    """

    name: str
    defn: ExperimentDef
    agent_a_id: str
    agent_b_id: str
    deck_index: int
    pair_index: int
    i: int
    j: int
    direction: str  # "ab" | "ba"
    registry_sha256: str = ""

    @property
    def definition_yaml(self) -> str:
        return yaml.safe_dump(
            {"experiment": self.defn.model_dump(mode="json"),
             "league": {"agents": {"a": self.agent_a_id, "b": self.agent_b_id},
                        "deck_index": self.deck_index,
                        "registry_sha256": self.registry_sha256}},
            allow_unicode=True, sort_keys=True)


def plan_cells(lg: LeagueDef, *, registry_sha256: str = "") -> list[CellPlan]:
    """注册表 → 细胞列表（确定性枚举：无序对注册表序 × decks 列表序 × ab/ba）。"""
    cells: list[CellPlan] = []
    n = len(lg.agents)
    k = 0
    for i in range(n):
        for j in range(i + 1, n):
            seed_start = lg.seed_start + k * lg.seed_stride
            for d, deck in enumerate(lg.decks):
                for direction, (ai, aj) in (("ab", (i, j)), ("ba", (j, i))):
                    name = f"{lg.name}-c{k:03d}-d{d}-{direction}"
                    defn = ExperimentDef(
                        name=name, games=lg.games_per_cell, seed_start=seed_start,
                        decks=DeckSides(a=deck, b=deck),
                        agents=AgentSides(a=lg.agents[ai].cfg, b=lg.agents[aj].cfg))
                    cells.append(CellPlan(
                        name=name, defn=defn,
                        agent_a_id=lg.agents[ai].id, agent_b_id=lg.agents[aj].id,
                        deck_index=d, pair_index=k, i=i, j=j,
                        direction=direction, registry_sha256=registry_sha256))
            k += 1
    return cells


def run_league(lg: LeagueDef, db_path: str, results_path: str | Path, *,
               workers: int = 1, cards_dir: str | Path = DEFAULT_CARDS_DIR,
               registry_path: str | Path | None = None) -> list[int]:
    """逐细胞 prepare + execute（全量复用 runner：并串一致/增量落库/失败局继续）。

    返回实验 id 列表。registry_path 给定时其 sha256 记入每个细胞的
    definition_yaml 元段（报告层 meta 回显）。
    """
    sha = (hashlib.sha256(Path(registry_path).read_bytes()).hexdigest()
           if registry_path is not None else "")
    ids: list[int] = []
    for cell in plan_cells(lg, registry_sha256=sha):
        prep = prepare_experiment(cell.defn, db_path, cards_dir=cards_dir)
        ids.append(execute_experiment(
            prep, cell.defn, results_path, workers=workers,
            definition_yaml=cell.definition_yaml, group_name=lg.name,
            variant=f"{cell.agent_a_id}-vs-{cell.agent_b_id}"))
    return ids
