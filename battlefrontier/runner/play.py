"""最小对局驱动器（task 004）：随机 Agent 打完一局 + 多进程并行。

注意：这不是 M3 的正式实验 Runner——不落库、无实验定义 YAML，
仅用于引擎端到端验证与 M1 确定性验收（PRD §11 M1 / §8.4）。
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
from dataclasses import dataclass, field

from battlefrontier.agent.mcts import Consideration
from battlefrontier.agent.random_agent import RandomAgent
from battlefrontier.engine.actions import Action
from battlefrontier.engine.core import DeckConfigError, GameEngine
from battlefrontier.engine.events import GameEvent
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef, CardInstance, GameState

__all__ = ["DeckConfigError", "GameResult", "play_game", "run_games_parallel"]

# 死循环保护默认回合上限（配置化，不散落硬编码）
DEFAULT_MAX_TURNS = 200

# 观测事件 kind（task 042，D-042-2）：Agent 搜索内部状态的外化，不影响对局
# 行为——events_hash 计算排除该类，保持行为校验跨版本可比
OBSERVATION_KINDS = frozenset({"mcts_consider"})


def _find_card(state: GameState, iid: int) -> CardInstance | None:
    """按 iid 在双方全部区域（手/牌库/弃牌/奖赏/场上整叠/附着/竞技场）找卡实例。"""
    for p in state.players:
        for zone in (p.hand, p.deck, p.discard, p.prizes):
            for c in zone:
                if c.iid == iid:
                    return c
        for m in ([p.active] if p.active else []) + list(p.bench):
            for c in (*m.stack, *m.attached_energy,
                      *((m.attached_tool,) if m.attached_tool else ())):
                if c.iid == iid:
                    return c
    if state.stadium is not None and state.stadium.iid == iid:
        return state.stadium
    return None


def _action_label(engine: GameEngine, player: int, action: Action) -> str:
    """mcts_consider 行动标签（task 042，D-042-3）：kind：可读参数——
    attack→招式名、play_trainer/evolve 等→卡名（attach 类附 →目标）、
    retreat/promote→备战宝可梦名、choose→选中卡名；解析失败回退 kind 原文（不猜）。
    """
    s = engine.state
    if action.kind == "attack":
        active = s.players[player].active
        if active is not None:
            attacks = list(active.current.card.attacks)
            if active.attached_tool is not None:  # 授予招式接在自身招式后（同枚举序）
                attacks += list(active.attached_tool.card.attacks)
            if 0 <= action.attack_index < len(attacks):
                return f"attack：{attacks[action.attack_index].name}"
        return "attack"
    if action.kind in ("retreat", "promote") and action.bench_index is not None:
        bench = s.players[player].bench
        if 0 <= action.bench_index < len(bench):
            return f"{action.kind}：{bench[action.bench_index].current.card.name}"
        return action.kind
    if action.kind == "choose":
        names = [c.card.name for i in action.choices
                 if (c := _find_card(s, i)) is not None]
        return f"choose：{'+'.join(names)}" if names else "choose"
    if action.iid is not None:
        card = _find_card(s, action.iid)
        if card is None:
            return action.kind
        label = f"{action.kind}：{card.card.name}"
        if action.target_iid is not None:
            target = _find_card(s, action.target_iid)
            if target is not None:
                label += f"→{target.card.name}"
        return label
    return action.kind


def _emit_consideration(
    engine: GameEngine, player: int, c: Consideration
) -> None:
    """向引擎事件流追加 mcts_consider 观测事件（seq/turn/phase 与 _emit 同口径）。"""
    considered = [
        {"action": _action_label(engine, player, a), "kind": a.kind, "visits": v}
        for a, v in c.considered
    ]
    engine.events.append(GameEvent(
        seq=len(engine.events), turn=engine.state.turn, phase=engine.state.phase,
        player=player, kind="mcts_consider",
        detail={
            "chosen": _action_label(engine, player, c.chosen),
            "chosen_visits": dict(c.considered)[c.chosen],
            "total_visits": c.total_visits,
            "considered": considered,
        },
    ))


@dataclass
class GameResult:
    winner: int | None
    is_draw: bool
    turns: int
    phase: str
    first_player: int = 0
    events: list[GameEvent] = field(default_factory=list)
    events_hash: str = ""


def play_game(
    deck_a: list[CardDef],
    deck_b: list[CardDef],
    seed: int,
    max_turns: int = DEFAULT_MAX_TURNS,
    card_effects: dict | None = None,
    agents: list | None = None,
) -> GameResult:
    """两个 Agent 打完整局（默认随机 Agent）。同种子逐事件一致（事件流 hash 可比对）。"""
    engine = GameEngine(RandomSource(seed), card_effects=card_effects)
    if agents is None:
        agents = [RandomAgent(RandomSource(seed + 1_000_001)),
                  RandomAgent(RandomSource(seed + 2_000_002))]
    engine.new_game(deck_a, deck_b)

    while engine.state.phase != "game_over":
        if engine.state.turn >= max_turns:
            engine.force_draw(reason="turn_cap")
            break
        player = engine.state.current_player
        actions = engine.legal_actions(player)
        if not actions:  # 防御：理论上各阶段必有可选项
            engine.force_draw(reason="no_legal_actions")
            break
        agent = agents[player]
        if hasattr(agent, "bind_engine"):  # MCTS 挂接钩子（D-034-1）
            agent.bind_engine(engine)
        view = engine.state.visible_state(player)
        action = agent.observe(view, actions)
        # task 042（D-042-1）：MCTS 根统计外化——读 last_consideration（非 None
        # 则追加观测事件并清空防重复记账）；heuristic/random 无此属性，零开销
        consideration = getattr(agent, "last_consideration", None)
        if consideration is not None:
            agent.last_consideration = None
            _emit_consideration(engine, player, consideration)
        engine.apply(player, action)

    s = engine.state
    payload = json.dumps(
        # D-042-2：观测事件（mcts_consider）不进行为校验，payload 过滤
        [ev.model_dump(mode="json") for ev in engine.events
         if ev.kind not in OBSERVATION_KINDS],
        ensure_ascii=False, sort_keys=True,
    )
    return GameResult(
        winner=s.winner,
        is_draw=s.is_draw,
        turns=s.turn,
        phase=s.phase,
        first_player=s.first_player,
        events=engine.events,
        events_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


def _run_one(payload: dict) -> GameResult:
    """多进程 worker 入口（模块级函数，可 pickle）。"""
    return play_game(
        deck_a=[CardDef.model_validate(c) for c in payload["deck_a"]],
        deck_b=[CardDef.model_validate(c) for c in payload["deck_b"]],
        seed=payload["seed"],
        max_turns=payload["max_turns"],
    )


def run_games_parallel(
    deck_a: list[CardDef],
    deck_b: list[CardDef],
    seeds: list[int],
    workers: int = 2,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> list[GameResult]:
    """按种子分片并行；返回顺序与 seeds 一致，结果与串行逐局一致（硬验收）。"""
    payloads = [
        {
            "deck_a": [c.model_dump(mode="json") for c in deck_a],
            "deck_b": [c.model_dump(mode="json") for c in deck_b],
            "seed": s,
            "max_turns": max_turns,
        }
        for s in seeds
    ]
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers) as pool:
        return pool.map(_run_one, payloads)
