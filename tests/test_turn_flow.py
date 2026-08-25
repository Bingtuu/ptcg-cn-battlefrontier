"""task 003-B：回合流转 / 首回合禁攻 / 非法拒绝 / 牌库抽空判负。

规则出处：官方规则书「回合的进行」——回合开始抽 1 张（含第一回合）；
先攻方第一回合不能使用招式；牌库空且必须抽牌时判负。
"""

import pytest
from helpers import deck60, energy, finish_setup, new_game

from battlefrontier.engine.actions import Action, IllegalActionError


def test_first_player_starts_turn_one_after_draw() -> None:
    e = new_game(42)
    finish_setup(e)
    s = e.state
    assert s.turn == 1 and s.phase == "main"
    assert s.current_player == s.first_player
    fp = s.players[s.first_player]
    assert len(fp.hand) == 7  # 起手 7 - 布阵 1 + 回合开始抽 1


def test_first_player_cannot_attack_on_first_turn() -> None:
    e = new_game(42)
    finish_setup(e)
    kinds = {a.kind for a in e.legal_actions(e.state.current_player)}
    assert "attack" not in kinds
    assert "end_turn" in kinds


def test_second_player_may_attack_on_their_first_turn() -> None:
    # 构造局面：第 1 回合轮到后攻方（current=1, first=0），其战斗场有 1 能量
    from helpers import basic, engine_at, in_play, inst

    from battlefrontier.engine.state import GameState, PlayerState

    p0 = PlayerState(active=in_play(1, basic("妙蛙种子"), 1),
                     prizes=tuple(inst(200 + i, basic("妙蛙种子")) for i in range(6)))
    p1 = PlayerState(active=in_play(2, basic("小火龙"), 1),
                     prizes=tuple(inst(400 + i, basic("小火龙")) for i in range(6)))
    e = engine_at(GameState(players=(p0, p1), turn=1, current_player=1,
                            phase="main", first_player=0))
    kinds = {a.kind for a in e.legal_actions(1)}
    assert "attack" in kinds  # 规则书：仅先攻方第一回合不能攻击


def test_illegal_action_rejected() -> None:
    e = new_game(42)
    finish_setup(e)
    with pytest.raises(IllegalActionError):
        e.apply(e.state.current_player, Action(kind="attack"))  # 首回合禁攻


def test_wrong_player_rejected() -> None:
    e = new_game(42)
    finish_setup(e)
    other = 1 - e.state.current_player
    with pytest.raises(IllegalActionError):
        e.apply(other, Action(kind="end_turn"))


def test_end_turn_switches_player_and_auto_draws() -> None:
    e = new_game(42)
    finish_setup(e)
    first = e.state.current_player
    before = len(e.state.players[1 - first].hand)
    e.apply(first, Action(kind="end_turn"))
    assert len(e.state.players[1 - first].hand) == before + 1  # 自动抽牌
    draw_events = [ev for ev in e.events if ev.kind == "draw"]
    assert len(draw_events) == 2  # 双方各抽过 1


def test_deck_out_at_draw_loses() -> None:
    # 13 张卡组：起手 7 + 奖赏 6，牌库空，回合开始无牌可抽 → 判负
    e = new_game(42, [energy()] * 6 + deck60()[:7])
    finish_setup(e)
    assert e.state.phase == "game_over"
    assert e.state.winner == 1 - e.state.first_player
    assert any(ev.kind == "deck_out" for ev in e.events)
