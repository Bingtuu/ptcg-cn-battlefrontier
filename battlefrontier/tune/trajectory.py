"""搜索轨迹 JSONL（D-T4，task 045）：每次评估一行，复算锚点。

行结构：evaluation（0 起序号）/ vector（10 维参数向量）/ score（fitness）/
seed_ranges（各配对 CRN 种子区间）/ pairs（各配对明细）/ wall_seconds。
wall_seconds 为非确定量——确定性对拍走 ``rows_equivalent``（其余字段全等）。
搜索过程局不落结果库（36 万局量级无消费场景），本文件即唯一锚点。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Self

from battlefrontier.tune.fitness import EvalResult

__all__ = ["TrajectoryWriter", "read_trajectory", "rows_equivalent", "trajectory_row"]


def trajectory_row(evaluation_id: int, result: EvalResult) -> dict:
    """一次评估 → 轨迹行（纯数据 dict，键序由写入端 sort_keys 固定）。"""
    return {
        "evaluation": evaluation_id,
        "vector": dict(result.vector),
        "score": result.fitness,
        "seed_ranges": [
            {"pair_index": p.pair_index, "seed_start": p.seed_start,
             "seed_end": p.seed_end}
            for p in result.pairs
        ],
        "pairs": [
            {"pair_index": p.pair_index, "archetype_a": p.archetype_a,
             "archetype_b": p.archetype_b, "games": p.games, "decided": p.decided,
             "wins_a": p.wins_a, "draws": p.draws, "failed": p.failed,
             "winrate": p.winrate}
            for p in result.pairs
        ],
        "wall_seconds": result.wall_seconds,
    }


class TrajectoryWriter:
    """JSONL 追加写入（UTF-8 / ensure_ascii=False / sort_keys，逐行 flush）。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")

    def append(self, row: dict) -> None:
        self._fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def read_trajectory(path: str | Path) -> list[dict]:
    """读出全部轨迹行（重放/对拍用）。"""
    return [json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def rows_equivalent(a: dict, b: dict) -> bool:
    """确定性对拍：除 wall_seconds（非确定量）外逐字段全等。"""

    def strip(r: dict) -> dict:
        return {k: v for k, v in r.items() if k != "wall_seconds"}

    return strip(a) == strip(b)
