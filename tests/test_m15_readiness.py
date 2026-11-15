"""task 147：M15 readiness 收口——仓库级断言（不依赖 gitignored 数据工件）。

数据级 readiness（标签集落库/快照冒烟/跑批零失败）由
`.kimi-code/t147_m15_readiness.py` 在本机执行并留档；本文件钉死的是
「M15 可以开始」所需的**规格与工具链不变量**：激活门槛在规格里、编号
并线无歧义、装载器加固在位、改表硬门槛在方法论文档里。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PRD = ROOT / "docs/superpowers/specs/2026-11-14-phase4-prd-design.md"
OLD_SPEC = ROOT / "docs/superpowers/specs/2026-10-31-phase4-accuracy-validity-design.md"
SWAP_DESIGN = ROOT / "docs/digs/2026-11-14-deck-swap-search-design.md"
T146_DOC = ROOT / "tasks/done/task 146.md"
T145_DOC = ROOT / "tasks/done/task 145.md"


def test_M15_激活门槛已写入权威规格():
    text = PRD.read_text(encoding="utf-8")
    assert "激活门槛" in text
    assert "有害组合检出率 100%" in text
    assert "naive 流程" in text
    assert "模拟器内自对局胜率差不列入过门证据" in text
    # 收口处置钉死：no-go 不激活 127、value_guide 默认关
    assert "task 127 不激活" in text
    assert "v0.4 修订" in text  # 修订历史声明在位


def test_M15_编号并线无歧义():
    old = OLD_SPEC.read_text(encoding="utf-8")
    assert "编号取代声明" in old
    assert "显式取代" in old


def test_改表硬门槛在方法论文档():
    text = SWAP_DESIGN.read_text(encoding="utf-8")
    assert "改表硬门槛" in text
    assert "印刷级" in text
    assert "组合体" in text and "同种子配对复核" in text


def test_装载器错卡解析加固在位():
    """experiment._resolve_decklist_entry 裸名路径必须有 name_full 严格校验。"""
    src = (ROOT / "battlefrontier/runner/experiment.py").read_text(encoding="utf-8")
    assert "解析到异名卡" in src
    assert "rec.name_full != name" in src


def test_组合标签集与快照任务已归档():
    """t145/t146 任务书须以完成态归档（数据工件存在性由 t147 脚本验）。"""
    assert T146_DOC.exists(), "task 146 未归档——标签集未冻结，M15 不得开始"
    assert T145_DOC.exists(), "task 145 未归档——教师锚点未采集，M15 不得开始"


@pytest.mark.parametrize("deck", [f"L{i:02d}" for i in range(1, 11)])
def test_t146_组合deck印刷级且无裸名行(deck):
    """10 个组合 deck 每行必须带 [card_id] 印刷后缀（task 142 纪律）。"""
    p = ROOT / "experiments/t146/decks" / f"{deck}.txt"
    assert p.exists(), f"{deck} deck 缺失"
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert line.endswith("]") and "[" in line, f"{deck} 存在裸名行: {line}"
