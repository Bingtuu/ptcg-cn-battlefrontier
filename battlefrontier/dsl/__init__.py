"""效果层：效果 DSL + 解释器（PRD §5）。

AST 层（schema）+ 加载器（loader）+ 解释器骨架（interpreter）+ 首批原语（primitives）。
"""

from battlefrontier.dsl import (
    primitives as _primitives,  # noqa: F401  # 导入即注册首批原语
)
from battlefrontier.dsl.interpreter import PRIMITIVES, ExecutionContext, run_effect
from battlefrontier.dsl.loader import (
    DslError,
    Vocabulary,
    load_card_dir,
    load_card_doc,
    load_vocabularies,
    parse_card_doc,
)
from battlefrontier.dsl.schema import ActionNode, CardEffectDoc, CardRef, Effect

__all__ = [
    "PRIMITIVES",
    "ActionNode",
    "CardEffectDoc",
    "CardRef",
    "DslError",
    "Effect",
    "ExecutionContext",
    "Vocabulary",
    "load_card_dir",
    "load_card_doc",
    "load_vocabularies",
    "parse_card_doc",
    "run_effect",
]
