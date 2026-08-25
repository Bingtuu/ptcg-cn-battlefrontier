"""单一可注入随机源（PRD §6.3：种子决定一切，引擎任何位置不得直接调 random）。

洗牌 / 掷币 / 抽牌等一切随机只经 RandomSource；状态可快照/恢复，
是 MCTS determinization 与并行分发的前置（PRD §7.3、§8.2）。
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class RandomSource:
    """包装 random.Random 的确定性随机源。"""

    def __init__(self, seed: int) -> None:
        self._r = random.Random(seed)

    def shuffle(self, seq: Sequence[T]) -> tuple[T, ...]:
        """返回洗牌后的新元组，不改原序列。"""
        items = list(seq)
        self._r.shuffle(items)
        return tuple(items)

    def flip_coin(self) -> bool:
        """掷币：True = 正面。"""
        return bool(self._r.getrandbits(1))

    def snapshot(self) -> object:
        """当前内部状态快照（可 JSON 化由调用方另行处理）。"""
        return self._r.getstate()

    def restore(self, state: object) -> None:
        """恢复到 snapshot() 拍下的状态。"""
        self._r.setstate(state)
