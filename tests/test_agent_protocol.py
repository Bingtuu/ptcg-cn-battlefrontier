"""task 003：Agent 协议定型（PRD §7.1 observe(visible_state, legal_actions) -> action）。"""

from helpers import new_game

from battlefrontier.agent.base import Agent
from battlefrontier.engine.actions import Action
from battlefrontier.engine.state import VisibleGameState


class FirstActionAgent:
    """最小实现：永远选第一个合法行动（测试用）。"""

    def observe(self, view: VisibleGameState, legal_actions: list[Action]) -> Action:
        return legal_actions[0]


def test_agent_protocol_runtime_checkable() -> None:
    assert isinstance(FirstActionAgent(), Agent)


def test_agent_drives_setup_and_turn_via_protocol() -> None:
    e = new_game(42)
    agent = FirstActionAgent()
    steps = 0
    while e.state.phase != "main" and steps < 20:
        player = e.state.current_player
        view = e.state.visible_state(player)
        actions = e.legal_actions(player)
        e.apply(player, agent.observe(view, actions))
        steps += 1
    assert e.state.phase == "main"
    # observe 拿到的是过滤视图：对手手牌只剩数量
    assert not hasattr(view.opponent, "hand")
