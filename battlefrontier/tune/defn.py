"""调优定义 TuneDef（D-T4，task 045）——Pydantic 强校验，不猜纪律同 ExperimentDef。

字段：卡池路径 / 每配对局数 / 划分种子与 holdout 大小 / 算法 / 轮数上限 /
噪声门槛 / 可选显式配对子集（冒烟调试用；缺省 = 全量 36 对分层划分）。
坐标下降本身不消费随机性（split_seed 之外的通用 seed 字段待 ES 立项再加，YAGNI）。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["TuneDef", "load_tune"]

ALGORITHMS = ("coordinate",)


class TuneDef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    pool: str = Field(min_length=1)           # target-pool YAML 路径
    games_per_pair: int = Field(gt=0, le=1000)  # le=CRN 种子区间宽（防相邻配对撞种子）
    split_seed: int = 0                       # 训练/holdout 划分种子（可复算锚点）
    holdout_size: int = Field(default=12, gt=0)
    algorithm: str = "coordinate"
    max_rounds: int = Field(default=3, ge=1, le=3)   # D-T3：最多 3 轮
    noise_threshold: float = Field(default=0.01, ge=0.0)  # D-T2：默认 1.0pts
    pairs: list[tuple[str, str]] | None = None  # 显式训练配对（冒烟）；缺省=分层划分

    @model_validator(mode="after")
    def _check(self) -> TuneDef:
        if self.algorithm not in ALGORITHMS:
            raise ValueError(
                f"未知算法（不猜）: {self.algorithm}（支持 {ALGORITHMS}；"
                f"ES 精修视粗扫结果另行立项）")
        if self.pairs is not None:
            if not self.pairs:
                raise ValueError("pairs 为空（不猜；要全量划分请省略该字段）")
            for a, b in self.pairs:
                if a == b:
                    raise ValueError(f"pairs 含相同 archetype 的镜像对（不猜）: {a}")
            normalized = [frozenset(p) for p in self.pairs]
            if len(set(normalized)) != len(normalized):
                raise ValueError("pairs 含重复配对（不猜）")
        return self


def load_tune(path: str | Path) -> TuneDef:
    text = Path(path).read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise TypeError(f"调优定义须为 YAML 映射: {path}")
    return TuneDef.model_validate(raw)
