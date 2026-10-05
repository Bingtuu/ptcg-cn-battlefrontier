"""隐藏信息 determinizer（task 034 WP1，D-034-3；task 039 WP1/WP3，D-039-1/3）：
MCTS 多世界采样的世界生成器。

从 player 视角重采样隐藏区——①对手手牌内容（数量已知）；②双方奖赏卡内容
（对双方均隐藏，rules-manual §3）；③双方牌库顺序（内容己方可知、序不可知）。
可见区（自己手牌、双方场上/弃牌堆、竞技场）逐卡不动；reveal 记忆不建模
（v1 已知近似，D-034-3）。

冻结集（D-039-1，task 039）：``freeze`` 内 iid 的卡保持原区域原位置
（位置语义保留：own_deck 检视池在牌顶 N 张，挂起期间不漂移），其余隐藏区
照常重洗切回。实现 = 每区域 mask 冻结位 → 洗非冻结部分 → 原位回填。
挂起根（pending_choice）由 mcts.py 以 freeze=pool_iids ∪ payload 调用
（D-039-2）：候选池对选择方全已知，冻结非泄漏。

setup 期对手场上入池（D-039-3，task 039）：phase ∈ {setup_active, setup_bench}
（state.py face_down 口径）且对手场上非空时，「场上=可见区」前提不成立——
布阵背面放置是隐藏信息。对手场上卡收回采样池（与 hand+deck+prizes 合并），
先按基础宝可梦子集采样发回场上原数量（setup 只能放基础宝可梦；池含真实
多重集合故基础数必然够），剩余重洗按原区域大小切回；entered_play_this_turn
随新场上卡同步（rules-manual §1.1 首回合登场锁定）。己方场上/手牌已知不动；
对手场上为空时退回普通三区重洗。

采样池按方构造：己方 = deck + prizes（手牌内容已知，保持原样不参与）；对手
= hand + deck + prizes 三区合并（setup 期追加场上卡）。重洗后按原区域大小
切回——各区计数守恒、pool 多重集合不变。纯函数：返回新 GameState，不改动入参。

洗牌消费顺序固定（种子确定性硬规矩）：先己方后对手。每方非 setup 路径一次
合并池洗牌（冻结时洗非冻结子序列，消费顺序 = 池序过滤后的相对序）；对手
setup 路径两次洗牌——先基础宝可梦子集（取前 N 发回场上），再剩余合并池
（按 hand → deck → prizes 序回填）。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from battlefrontier.engine.rng import RandomSource
from battlefrontier.engine.state import (
    CardInstance,
    GameState,
    InPlayPokemon,
    PlayerState,
    Supertype,
)

_SETUP_PHASES = ("setup_active", "setup_bench")  # 布阵期（state.py face_down 口径）


def _is_basic_pokemon(c: CardInstance) -> bool:
    return c.card.supertype == Supertype.POKEMON and c.card.stage == 0


def _shuffle_masked(
    cards: Sequence[CardInstance], freeze: frozenset[int], rng: RandomSource
) -> tuple[CardInstance, ...]:
    """合并池洗牌：freeze 内 iid 原位保留（位置 mask），非冻结部分洗牌后原位回填。"""
    if not freeze:
        return rng.shuffle(cards)
    shuffled = iter(rng.shuffle([c for c in cards if c.iid not in freeze]))
    return tuple(c if c.iid in freeze else next(shuffled) for c in cards)


def _redistribute_opp_setup(
    p: PlayerState, rng: RandomSource, freeze: frozenset[int]
) -> PlayerState:
    """setup 期对手侧（D-039-3）：场上（背面放置 = 隐藏）卡收回采样池与
    hand/deck/prizes 合并，先按基础宝可梦子集采样发回场上原数量（约束：setup
    只能放基础宝可梦；池含真实多重集合故基础数必然够），剩余重洗按原区域
    大小切回。entered_play_this_turn 随新场上卡同步（首回合登场锁定口径不变）。
    """
    slots = ([p.active] if p.active is not None else []) + list(p.bench)
    field_cards = tuple(m.current for m in slots)
    pool = p.hand + p.deck + p.prizes + field_cards
    movable = [c for c in pool if c.iid not in freeze]
    need = sum(1 for m in slots if m.current.iid not in freeze)
    basics = [c for c in movable if _is_basic_pokemon(c)]
    assert len(basics) >= need  # 池含真实布阵（全是基础），必然够
    field_pick = rng.shuffle(basics)[:need]
    picked = Counter(c.iid for c in field_pick)
    rest = []
    for c in movable:
        if picked[c.iid]:
            picked[c.iid] -= 1
        else:
            rest.append(c)
    fill = iter(rng.shuffle(rest))

    def refill(zone: tuple[CardInstance, ...]) -> tuple[CardInstance, ...]:
        return tuple(c if c.iid in freeze else next(fill) for c in zone)

    pick_iter = iter(field_pick)
    new_slots = tuple(
        m if m.current.iid in freeze else InPlayPokemon(stack=(next(pick_iter),))
        for m in slots
    )
    n_active = 1 if p.active is not None else 0
    entered = (p.entered_play_this_turn - {m.current.iid for m in slots}) | {
        m.current.iid for m in new_slots
    }
    return p.model_copy(update={
        "hand": refill(p.hand),
        "deck": refill(p.deck),
        "prizes": refill(p.prizes),
        "active": new_slots[0] if p.active is not None else None,
        "bench": new_slots[n_active:],
        "entered_play_this_turn": entered,
    })


def determinize(
    state: GameState,
    player: int,
    rng: RandomSource,
    freeze: frozenset[int] = frozenset(),
) -> GameState:
    """从 player 视角重采样隐藏区，返回新 GameState（入参不动）。

    洗牌消费顺序固定（己方 → 对手），同 state + 同 rng 种子 + 同 freeze
    必得同输出（种子确定性硬规矩）。freeze 内 iid 保持原区域原位置（D-039-1）。
    """
    players = list(state.players)
    for idx in (0, 1):
        p = state.players[idx]
        if idx == player:
            # 己方：手牌内容已知不参与；仅 deck 顺序 + prizes 内容重洗
            pool = _shuffle_masked(p.deck + p.prizes, freeze, rng)
            players[idx] = p.model_copy(update={
                "deck": pool[: len(p.deck)],
                "prizes": pool[len(p.deck):],
            })
        else:
            # 对手：setup 期且场上非空 → 场上（背面=隐藏）卡收回采样池（D-039-3）；
            # 否则 hand + deck + prizes 三区合并重洗，按原区域大小切回
            if state.phase in _SETUP_PHASES and (p.active is not None or p.bench):
                players[idx] = _redistribute_opp_setup(p, rng, freeze)
                continue
            pool = _shuffle_masked(p.hand + p.deck + p.prizes, freeze, rng)
            n_hand = len(p.hand)
            n_deck = len(p.deck)
            players[idx] = p.model_copy(update={
                "hand": pool[:n_hand],
                "deck": pool[n_hand: n_hand + n_deck],
                "prizes": pool[n_hand + n_deck:],
            })
    return state.model_copy(update={"players": (players[0], players[1])})
