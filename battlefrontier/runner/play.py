"""最小对局驱动器（task 004）：随机 Agent 打完一局 + 多进程并行。

注意：这不是 M3 的正式实验 Runner——不落库、无实验定义 YAML，
仅用于引擎端到端验证与 M1 确定性验收（PRD §11 M1 / §8.4）。
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
from dataclasses import dataclass, field

from battlefrontier.agent.random_agent import RandomAgent
from battlefrontier.engine.core import DeckConfigError, GameEngine
from battlefrontier.engine.events import GameEvent
from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import CardDef

__all__ = ["DeckConfigError", "GameResult", "play_game", "run_games_parallel"]

# 死循环保护默认回合上限（配置化，不散落硬编码）
DEFAULT_MAX_TURNS = 200


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
        view = engine.state.visible_state(player)
        engine.apply(player, agents[player].observe(view, actions))

    s = engine.state
    payload = json.dumps(
        [ev.model_dump(mode="json") for ev in engine.events],
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
