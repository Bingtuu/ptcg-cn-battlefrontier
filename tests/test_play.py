"""task 004：白板对局端到端与 M1 确定性验收（PRD §8.4 / §11 M1）。"""

import pytest
from helpers import basic, deck60, energy

from battlefrontier.report.render import render_log
from battlefrontier.runner.play import (
    DeckConfigError,
    play_game,
    run_games_parallel,
)


def test_random_agents_complete_100_games() -> None:
    results = [play_game(deck60(), deck60(), seed=s) for s in range(100)]
    assert len(results) == 100
    for r in results:
        assert r.phase == "game_over"
        assert r.winner in (0, 1, None)
        assert r.turns >= 1
    # 白板随机局应有胜有负（统计冒烟，非精确断言）
    assert any(r.winner is not None for r in results)


def test_same_seed_same_event_hash() -> None:
    a = play_game(deck60(), deck60(), seed=7)
    b = play_game(deck60(), deck60(), seed=7)
    assert a.events_hash == b.events_hash
    assert a.winner == b.winner and a.turns == b.turns


def test_different_seeds_usually_differ() -> None:
    hashes = {play_game(deck60(), deck60(), seed=s).events_hash for s in range(10)}
    assert len(hashes) > 1


def test_serial_parallel_consistency() -> None:
    seeds = list(range(12))
    serial = [play_game(deck60(), deck60(), seed=s) for s in seeds]
    parallel = run_games_parallel(deck60(), deck60(), seeds, workers=2)
    assert [r.events_hash for r in serial] == [r.events_hash for r in parallel]
    assert [(r.winner, r.turns) for r in serial] == [(r.winner, r.turns) for r in parallel]


def test_render_log_human_readable() -> None:
    r = play_game(deck60(), deck60(), seed=3)
    log = render_log(r.events)
    assert "昏厥" in log or "game_over" not in log  # 白板局未必每局都昏厥，但渲染不崩
    assert "回合" in log


def test_turn_cap_forces_draw() -> None:
    r = play_game(deck60(), deck60(), seed=5, max_turns=2)
    assert r.phase == "game_over" and r.is_draw and r.winner is None
    assert any(ev.kind == "turn_cap" for ev in r.events)


def test_deck_without_basic_raises_clear_error() -> None:
    with pytest.raises(DeckConfigError, match="基础宝可梦"):
        play_game([energy()] * 60, deck60(), seed=1)


def test_deck_too_small_raises() -> None:
    with pytest.raises(DeckConfigError):
        play_game([basic("绿毛虫")] * 5, deck60(), seed=1)
