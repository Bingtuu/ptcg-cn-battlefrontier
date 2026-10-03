"""隐藏信息 determinizer（task 034 WP1，D-034-3）：MCTS 多世界采样的世界生成器。

从 player 视角重采样隐藏区——①对手手牌内容（数量已知）；②双方奖赏卡内容
（对双方均隐藏，rules-manual §3）；③双方牌库顺序（内容己方可知、序不可知）。
可见区（自己手牌、双方场上/弃牌堆、竞技场）逐卡不动；reveal 记忆不建模
（v1 已知近似，D-034-3）。

采样池按方构造：己方 = deck + prizes（手牌内容已知，保持原样不参与）；对手
= hand + deck + prizes 三区合并。重洗后按原区域大小切回——各区计数守恒、
pool 多重集合不变。纯函数：返回新 GameState，不改动入参。
"""

from __future__ import annotations

from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import GameState


def determinize(state: GameState, player: int, rng: RandomSource) -> GameState:
    """从 player 视角重采样隐藏区，返回新 GameState（入参不动）。

    洗牌消费顺序固定（己方 → 对手），同 state + 同 rng 种子必得同输出
    （种子确定性硬规矩）。
    """
    players = list(state.players)
    for idx in (0, 1):
        p = state.players[idx]
        if idx == player:
            # 己方：手牌内容已知不参与；仅 deck 顺序 + prizes 内容重洗
            pool = rng.shuffle(p.deck + p.prizes)
            players[idx] = p.model_copy(update={
                "deck": pool[: len(p.deck)],
                "prizes": pool[len(p.deck):],
            })
        else:
            # 对手：hand + deck + prizes 三区合并重洗，按原区域大小切回
            pool = rng.shuffle(p.hand + p.deck + p.prizes)
            n_hand = len(p.hand)
            n_deck = len(p.deck)
            players[idx] = p.model_copy(update={
                "hand": pool[:n_hand],
                "deck": pool[n_hand: n_hand + n_deck],
                "prizes": pool[n_hand + n_deck:],
            })
    return state.model_copy(update={"players": (players[0], players[1])})
