"""task 003-A：开局布阵与 mulligan（官方规则书·游戏准备）。

规则出处：PTCG 简中官方规则书「游戏的准备」——掷币定先后手、起手 7 张、
无基础宝可梦则 mulligan（展示手牌洗回重抽，对手可按 mulligan 次数抽牌）、
放置战斗场 1 只 + 备战区任意只、奖赏卡 6 张。
"""

from helpers import basic, energy, finish_setup, new_game


def test_new_game_deterministic_same_seed() -> None:
    e1, e2 = new_game(42), new_game(42)
    assert e1.state.model_dump(mode="json") == e2.state.model_dump(mode="json")


def test_new_game_different_seed_differs() -> None:
    assert (
        new_game(1).state.model_dump(mode="json")
        != new_game(2).state.model_dump(mode="json")
    )


def test_setup_deals_seven_hand_and_no_prizes_yet() -> None:
    """奖赏卡在双方战斗场放置完成后才设置（rules-reference §1，2026-08-28 核对）。"""
    e = new_game()
    for p in e.state.players:
        assert len(p.hand) == 7
        assert len(p.prizes) == 0
        assert len(p.deck) == 60 - 7


def test_prizes_set_after_both_actives_placed() -> None:
    e = new_game()
    # 玩家 0 完成布阵：奖赏仍未设置
    act = next(a for a in e.legal_actions(0) if a.kind == "place_active")
    e.apply(0, act)
    confirm = next(a for a in e.legal_actions(0) if a.kind == "confirm_setup")
    e.apply(0, confirm)
    assert all(len(p.prizes) == 0 for p in e.state.players)
    # 玩家 1 完成布阵：双方奖赏卡此时设置
    finish = [a for a in e.legal_actions(1)]
    e.apply(1, next(a for a in finish if a.kind == "place_active"))
    e.apply(1, next(a for a in e.legal_actions(1) if a.kind == "confirm_setup"))
    for idx, p in enumerate(e.state.players):
        assert len(p.prizes) == 6
        # 先攻方已抽回合开始牌（_begin_turn），另一人尚未
        expected = 60 - 7 - 6 - (1 if idx == e.state.first_player else 0)
        assert len(p.deck) == expected
    # 事件顺序：set_prizes 在所有 place_active 之后
    kinds = [ev.kind for ev in e.events]
    assert kinds.index("set_prizes") > max(i for i, k in enumerate(kinds) if k == "place_active")


def test_setup_board_face_down_until_both_confirmed() -> None:
    """布阵背面放置：对方 confirm 前，visible_state 看不到其布阵内容（rules-reference §1）。"""
    e = new_game()
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "place_active"))
    view = e.state.visible_state(1)
    assert view.opponent.active is None  # 内容不可见
    assert view.opponent.face_down_pokemon == 1  # 但放置数量公开
    # 双方完成布阵后翻开
    e.apply(0, next(a for a in e.legal_actions(0) if a.kind == "confirm_setup"))
    e.apply(1, next(a for a in e.legal_actions(1) if a.kind == "place_active"))
    e.apply(1, next(a for a in e.legal_actions(1) if a.kind == "confirm_setup"))
    view = e.state.visible_state(1)
    assert view.opponent.active is not None  # 双方完成后翻开
    assert view.opponent.face_down_pokemon == 0


def test_setup_starts_with_place_active_choices() -> None:
    e = new_game()
    actions = e.legal_actions(0)
    kinds = {a.kind for a in actions}
    assert kinds == {"place_active"}
    # 只能选手牌中的基础宝可梦（本 fixture 起手必有）
    assert all(a.iid is not None for a in actions)


def test_mulligan_reshuffles_until_basic() -> None:
    # 59 能量 + 1 基础：几乎必然多次 mulligan
    deck = [energy()] * 59 + [basic("独角虫")]
    e = new_game(7, deck)
    kinds = [ev.kind for ev in e.events]
    assert "mulligan" in kinds
    # mulligan 事件记录展示的手牌内容（回放保真；规则书：给对手看过）
    mulligan_events = [ev for ev in e.events if ev.kind == "mulligan"]
    assert all(len(ev.detail["hand"]) == 7 for ev in mulligan_events)
    # mulligan 后双方起手都必有基础宝可梦
    for p in e.state.players:
        assert any(c.card.supertype.value == "pokemon" and c.card.stage == 0 for c in p.hand)


def test_place_active_and_confirm_setup_enters_main() -> None:
    e = new_game()
    finish_setup(e)
    assert e.state.phase == "main"
    assert e.state.turn == 1
    for p in e.state.players:
        assert p.active is not None
