"""实验定义 + 正式 Runner（PRD §8，task 019）。

实验即一份 YAML（§8.1）；执行 = 种子分片多进程 + 主进程增量落库（§8.2）；
可复现 = 实验定义 + 代码版本 + 数据版本三者锁定（experiments 行全量回显）。

worker 载荷只传可序列化配置（卡组/DSL 文档 dump + agent 配置 dict + 种子），
agent 实例在 worker 内按同一种子规则重建——并行与串行逐局一致（§8.4）。
"""

from __future__ import annotations

import multiprocessing as mp
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from battlefrontier.agent.heuristic import HeuristicAgent, HeuristicParams
from battlefrontier.agent.random_agent import RandomAgent
from battlefrontier.data.cards import carddef_from_db
from battlefrontier.data.deck import load_deck
from battlefrontier.dsl import load_card_dir
from battlefrontier.dsl.schema import CardEffectDoc
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef
from battlefrontier.runner.play import GameResult, play_game
from battlefrontier.runner.results_db import ResultsDB

DEFAULT_RESULTS_PATH = "results/battlefrontier-results.db"
DEFAULT_CARDS_DIR = "cards"
DEFAULT_CONFIG_PATH = "config/battlefrontier.local.yml"

AGENT_TYPES = ("random", "heuristic")


# ── 实验定义（§8.1，Pydantic 强校验）──────────────────────

class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class DeckSourceCfg(FrozenModel):
    """卡组来源：db = 真实赛事卡组（load_deck）；file = 本地 decklist（每行 "N 卡名"）。"""

    source: str
    deck_id: str | None = None
    path: str | None = None

    @model_validator(mode="after")
    def _check_source(self) -> DeckSourceCfg:
        if self.source == "db" and not self.deck_id:
            raise ValueError("source=db 需要 deck_id")
        if self.source == "file" and not self.path:
            raise ValueError("source=file 需要 path")
        if self.source not in ("db", "file"):
            raise ValueError(f"未知卡组来源: {self.source}")
        return self


class AgentCfg(FrozenModel):
    type: str = "random"
    params: dict[str, float | int | bool] = {}

    @model_validator(mode="after")
    def _check_agent(self) -> AgentCfg:
        if self.type not in AGENT_TYPES:
            raise ValueError(f"未知 agent type: {self.type}（支持 {AGENT_TYPES}）")
        unknown = set(self.params) - set(HeuristicParams.__dataclass_fields__)
        if unknown:
            raise ValueError(f"未知 HeuristicParams 参数（不猜）: {sorted(unknown)}")
        return self


class DeckSides(FrozenModel):
    a: DeckSourceCfg
    b: DeckSourceCfg


class AgentSides(FrozenModel):
    a: AgentCfg = Field(default_factory=AgentCfg)
    b: AgentCfg = Field(default_factory=AgentCfg)


# ── 换卡敏感性：variants（PRD §9，task 023）───────────────

class SwapCfg(FrozenModel):
    """一次换卡：side 方卡组拿出 out×out_count，放入 in×in_count（`in` 为关键字走别名）。"""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    side: str = "a"
    out: str
    out_count: int = Field(gt=0)
    in_: str = Field(alias="in")
    in_count: int = Field(gt=0)

    @model_validator(mode="after")
    def _check_side(self) -> SwapCfg:
        if self.side not in ("a", "b"):
            raise ValueError(f"未知 side: {self.side}（仅 a/b）")
        return self


class VariantCfg(FrozenModel):
    """对照组定义：相对 baseline 卡组仅差 swaps 声明的若干张卡。"""

    name: str = Field(min_length=1)
    swaps: list[SwapCfg] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_balanced(self) -> VariantCfg:
        total_out = sum(s.out_count for s in self.swaps)
        total_in = sum(s.in_count for s in self.swaps)
        if total_out != total_in:
            raise ValueError(
                f"variant「{self.name}」换卡不平衡（不猜）：拿出 {total_out} 张 / "
                f"放入 {total_in} 张，卡组须保持 60 张")
        return self


class ExperimentDef(FrozenModel):
    name: str
    games: int = Field(gt=0)
    seed_start: int = 0
    decks: DeckSides
    agents: AgentSides = Field(default_factory=AgentSides)
    snapshot_date: str | None = None
    variants: list[VariantCfg] = []

    @model_validator(mode="after")
    def _check_variants(self) -> ExperimentDef:
        names = [v.name for v in self.variants]
        if len(names) != len(set(names)):
            raise ValueError(f"variant 重名（不猜）: {sorted(n for n in names if names.count(n) > 1)}")
        return self


def load_experiment(path: str | Path) -> ExperimentDef:
    text = Path(path).read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise TypeError(f"实验定义须为 YAML 映射: {path}")
    return ExperimentDef.model_validate(raw)


# ── 本地 decklist ────────────────────────────────────────

def parse_decklist(text: str) -> list[tuple[int, str]]:
    """行格式「N 卡名」（# 注释、空行跳过）。"""
    entries: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit() or int(parts[0]) <= 0:
            raise ValueError(f"decklist 第 {lineno} 行格式错误（应为「N 卡名」）: {raw!r}")
        entries.append((int(parts[0]), parts[1].strip()))
    if not entries:
        raise ValueError("decklist 为空")
    return entries


# ── 换卡应用（纯函数，可单测）────────────────────────────

def apply_swaps(deck: list[CardDef], swaps: list[SwapCfg],
                in_cards: dict[str, CardDef]) -> list[CardDef]:
    """对一份 60 张卡组应用换卡声明；out 存量不足 / in 未解析显式报错（不猜）。"""
    new_deck = list(deck)
    for swap in swaps:
        remaining = swap.out_count
        kept: list[CardDef] = []
        for card in new_deck:
            if card.name == swap.out and remaining > 0:
                remaining -= 1
            else:
                kept.append(card)
        if remaining > 0:
            raise ValueError(
                f"卡组中「{swap.out}」存量不足：需拿出 {swap.out_count} 张，"
                f"差 {remaining} 张")
        in_card = in_cards.get(swap.in_)
        if in_card is None:
            raise ValueError(f"换入卡「{swap.in_}」未解析（不猜）")
        kept.extend([in_card] * swap.in_count)
        new_deck = kept
    return new_deck


# ── Agent 构建（worker 内同规则重建）─────────────────────
def _build_one(cfg: AgentCfg, seed: int, offset: int):
    if cfg.type == "heuristic":
        return HeuristicAgent(HeuristicParams(**cfg.params))
    return RandomAgent(RandomSource(seed + offset))


def build_agents(defn: ExperimentDef, seed: int) -> list:
    """与 play.py 默认随机源偏移一致（seed+1_000_001 / +2_000_002），保证口径稳定。"""
    return [_build_one(defn.agents.a, seed, 1_000_001),
            _build_one(defn.agents.b, seed, 2_000_002)]


# ── 准备（卡组解析 + DSL 文档 + 数据版本）────────────────

@dataclass(frozen=True)
class PreparedExperiment:
    deck_a: list[CardDef]
    deck_b: list[CardDef]
    card_effects: dict[str, CardEffectDoc]
    deck_a_id: str
    deck_b_id: str
    data_version: str
    warnings: list[str] = field(default_factory=list)


def load_db_path(config_path: str | Path = DEFAULT_CONFIG_PATH) -> str:
    """db 路径来自本机配置（gitignored）；缺失时给出复制模板的指引。"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"缺少本机配置 {config_path}——请复制 config/battlefrontier.example.yml 填写")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        return str(cfg["db"]["sqlite_path"])
    except (TypeError, KeyError) as e:
        raise ValueError(f"{config_path} 缺少 db.sqlite_path") from e


def _data_version(db_path: str, snapshot_date: str | None) -> str:
    """数据版本锚点：快照日期（默认最新 standard）+ db user_version（只读连接）。"""
    from ptcgdb.sdk import open_db

    db = open_db(db_path)
    try:
        snapshots = db.snapshots("standard")
        date = snapshot_date or (snapshots[-1].effective_from if snapshots else "unknown")
    finally:
        db.close()
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)  # 主库只读（FR-10）
        try:
            uv = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
        return f"{date} (user_version={uv})"
    except sqlite3.Error:
        return str(date)


def _load_decklist_file(db, path: str) -> tuple[list[CardDef], list[str]]:
    entries = parse_decklist(Path(path).read_text(encoding="utf-8"))
    cards: list[CardDef] = []
    warnings: list[str] = []
    ids: list[str] = []
    for count, name in entries:
        found = db.search_cards(name=name, limit=1)
        if not found:
            raise ValueError(f"decklist 卡名未命中（不猜）: {name}")
        card_id = found[0].card_id
        card_def, ws = carddef_from_db(db.get_card(card_id))
        warnings.extend(ws)
        cards.extend([card_def] * count)
        ids.extend([card_id] * count)
    if len(cards) != 60:
        raise ValueError(f"decklist 展开后为 {len(cards)} 张，应为 60")
    return cards, warnings


def prepare_experiment(defn: ExperimentDef, db_path: str,
                       cards_dir: str | Path = DEFAULT_CARDS_DIR) -> PreparedExperiment:
    """解析双方卡组（db/file）+ 按卡组卡名过滤 DSL 文档 + 锁定数据版本。"""
    from ptcgdb.sdk import open_db

    warnings: list[str] = []
    decks: list[list[CardDef]] = []
    ids: list[str] = []
    for side in (defn.decks.a, defn.decks.b):
        if side.source == "db":
            loaded = load_deck(db_path, side.deck_id)
            decks.append(loaded.cards)
            warnings.extend(loaded.warnings)
            ids.append(side.deck_id)
        else:
            db = open_db(db_path)
            try:
                cards, ws = _load_decklist_file(db, side.path)
            finally:
                db.close()
            decks.append(cards)
            warnings.extend(ws)
            ids.append(f"file:{side.path}")

    names = {c.name for d in decks for c in d}
    all_effects = load_card_dir(cards_dir)
    card_effects = {n: doc for n, doc in all_effects.items() if n in names}
    return PreparedExperiment(
        deck_a=decks[0], deck_b=decks[1], card_effects=card_effects,
        deck_a_id=ids[0], deck_b_id=ids[1],
        data_version=_data_version(db_path, defn.snapshot_date), warnings=warnings)


def prepare_variant(prep: PreparedExperiment, variant: VariantCfg,
                    db_path: str,
                    cards_dir: str | Path = DEFAULT_CARDS_DIR) -> PreparedExperiment:
    """baseline 准备结果应用 variant 换卡声明；换入卡经 db 解析（与 decklist 同规则）。

    换入卡可能不在 baseline 卡组里，其 DSL 文档需从定义库补入 card_effects。
    """
    from ptcgdb.sdk import open_db

    db = open_db(db_path)
    try:
        in_cards: dict[str, CardDef] = {}
        for swap in variant.swaps:
            if swap.in_ in in_cards:
                continue
            found = db.search_cards(name=swap.in_, limit=1)
            if not found:
                raise ValueError(f"换入卡名未命中（不猜）: {swap.in_}")
            card_def, _ = carddef_from_db(db.get_card(found[0].card_id))
            in_cards[swap.in_] = card_def
    finally:
        db.close()

    sides = {"a": list(prep.deck_a), "b": list(prep.deck_b)}
    ids = {"a": prep.deck_a_id, "b": prep.deck_b_id}
    touched: set[str] = set()
    for swap in variant.swaps:
        sides[swap.side] = apply_swaps(sides[swap.side], [swap], in_cards)
        touched.add(swap.side)
    for side in touched:
        ids[side] = f"{ids[side]} [variant:{variant.name}]"

    card_effects = dict(prep.card_effects)
    names = {c.name for d in sides.values() for c in d}
    missing = names - set(card_effects)
    if missing:
        all_effects = load_card_dir(cards_dir)
        card_effects.update({n: doc for n, doc in all_effects.items() if n in missing})
    return PreparedExperiment(
        deck_a=sides["a"], deck_b=sides["b"], card_effects=card_effects,
        deck_a_id=ids["a"], deck_b_id=ids["b"], data_version=prep.data_version,
        warnings=list(prep.warnings))


# ── 执行（§8.2/§8.4）────────────────────────────────────

def _code_version() -> str:
    """git short sha + dirty 标记；取不到记 unknown（不阻塞实验）。"""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"],
                               capture_output=True, text=True, check=True).stdout.strip()
        return sha + ("+dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _run_one_experiment(payload: dict) -> tuple[int, GameResult | None, str | None]:
    """多进程 worker 入口（模块级函数，可 pickle）。失败局返回错误文本而非抛出。"""
    try:
        agents_cfg = AgentSides.model_validate(payload["agents"])
        agents = [
            _build_one(agents_cfg.a, payload["seed"], 1_000_001),
            _build_one(agents_cfg.b, payload["seed"], 2_000_002),
        ]
        result = play_game(
            deck_a=[CardDef.model_validate(c) for c in payload["deck_a"]],
            deck_b=[CardDef.model_validate(c) for c in payload["deck_b"]],
            seed=payload["seed"],
            card_effects={n: CardEffectDoc.model_validate(d)
                          for n, d in payload["card_effects"].items()},
            agents=agents,
        )
        return payload["seed"], result, None
    except Exception as e:  # noqa: BLE001 — 不猜纪律：任何失败局显式落库，不拖垮实验
        return payload["seed"], None, f"{type(e).__name__}: {e}"


def execute_experiment(prep: PreparedExperiment, defn: ExperimentDef,
                       results_path: str | Path, *, workers: int = 1,
                       definition_yaml: str = "",
                       group_name: str = "", variant: str = "") -> int:
    """跑完实验并增量落库；返回 experiment_id。异常时状态记 aborted 后抛出。"""
    db = ResultsDB(results_path)
    try:
        exp_id = db.start_experiment(
            name=defn.name, definition_yaml=definition_yaml,
            code_version=_code_version(), data_version=prep.data_version,
            group_name=group_name, variant=variant)
        seeds = [defn.seed_start + i for i in range(defn.games)]

        def record(seed: int, result: GameResult) -> None:
            db.record_game(exp_id, seed=seed, first_player=result.first_player,
                           result=result, deck_a_id=prep.deck_a_id, deck_b_id=prep.deck_b_id)

        def record_error(seed: int, error: str) -> None:
            db.record_error(exp_id, seed=seed, deck_a_id=prep.deck_a_id,
                            deck_b_id=prep.deck_b_id, error=error)

        try:
            if workers > 1:
                payloads = [{
                    "deck_a": [c.model_dump(mode="json") for c in prep.deck_a],
                    "deck_b": [c.model_dump(mode="json") for c in prep.deck_b],
                    "card_effects": {n: d.model_dump(mode="json")
                                     for n, d in prep.card_effects.items()},
                    "agents": defn.agents.model_dump(mode="json"),
                    "seed": s,
                } for s in seeds]
                ctx = mp.get_context("spawn")
                with ctx.Pool(workers) as pool:
                    for seed, result, error in pool.imap(_run_one_experiment, payloads):
                        if error is not None:
                            record_error(seed, error)
                        else:
                            record(seed, result)
            else:
                for seed in seeds:
                    try:
                        result = play_game(prep.deck_a, prep.deck_b, seed=seed,
                                           card_effects=prep.card_effects,
                                           agents=build_agents(defn, seed))
                    except Exception as e:  # noqa: BLE001 — 失败局落库继续（不猜纪律）
                        record_error(seed, f"{type(e).__name__}: {e}")
                    else:
                        record(seed, result)
        except Exception:
            db.finish_experiment(exp_id, status="aborted")
            raise
        db.finish_experiment(exp_id)
        return exp_id
    finally:
        db.close()


def execute_group(defn: ExperimentDef, preps: list[PreparedExperiment],
                  results_path: str | Path, *, workers: int = 1,
                  definition_yaml: str = "") -> list[int]:
    """换卡敏感性分组执行（PRD §9）：baseline + 各 variant 同种子区间依次跑。

    preps[0] 为 baseline，其后与各 variant 一一对应；同 defn.games/seed_start
    保证配对可比。返回 [base_id, *variant_ids]。
    """
    if len(preps) != 1 + len(defn.variants):
        raise ValueError(
            f"preps 数 {len(preps)} 与 1+variants 数 {len(defn.variants)} 不符")
    ids = [execute_experiment(preps[0], defn, results_path, workers=workers,
                              definition_yaml=definition_yaml,
                              group_name=defn.name)]
    for variant, prep in zip(defn.variants, preps[1:], strict=True):
        ids.append(execute_experiment(prep, defn, results_path, workers=workers,
                                      definition_yaml=definition_yaml,
                                      group_name=defn.name, variant=variant.name))
    return ids


def run_group(defn: ExperimentDef, db_path: str,
              results_path: str | Path = DEFAULT_RESULTS_PATH, *,
              workers: int = 1, cards_dir: str | Path = DEFAULT_CARDS_DIR,
              definition_yaml: str = "") -> tuple[list[int], list[str]]:
    """prepare（baseline + variants）+ execute_group 一步走（CLI 入口用）。

    返回 (实验 id 列表, 装载告警列表)。
    """
    prep = prepare_experiment(defn, db_path, cards_dir=cards_dir)
    preps = [prep] + [prepare_variant(prep, v, db_path, cards_dir=cards_dir)
                      for v in defn.variants]
    warnings = [f"[{label}] {w}" for label, p in
                zip(["baseline"] + [v.name for v in defn.variants], preps, strict=True)
                for w in p.warnings]
    ids = execute_group(defn, preps, results_path, workers=workers,
                        definition_yaml=definition_yaml)
    return ids, warnings


def run_experiment(defn: ExperimentDef, db_path: str,
                   results_path: str | Path = DEFAULT_RESULTS_PATH, *,
                   workers: int = 1, cards_dir: str | Path = DEFAULT_CARDS_DIR,
                   definition_yaml: str = "") -> int:
    """prepare + execute 一步走（CLI 入口用）。"""
    prep = prepare_experiment(defn, db_path, cards_dir=cards_dir)
    return execute_experiment(prep, defn, results_path, workers=workers,
                              definition_yaml=definition_yaml)
