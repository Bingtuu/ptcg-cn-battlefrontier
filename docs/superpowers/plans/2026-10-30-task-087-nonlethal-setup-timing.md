# 087 非斩杀 setup 时序 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.
>
> **待拍板。** 规格 `docs/superpowers/specs/2026-10-30-task-087-nonlethal-setup-timing-design.md`。**Task 1 = docs 停止线。** 禁止推迟 `can_ko`。禁止 `prize_pressure_gate`。

**Goal:** 复制/王牌已付清但非斩杀时，若窄 `_setup_value` 严格大于本回合芯片挥砍，则先 setup；`can_ko` 时行为与今天（084 Q2=C）完全一致。

**Architecture:** `HeuristicParams.setup_before_chip_gate`。在 `_decide_main` 的物品/支援者段（及落入 `_pick_attack` 前）比较 setup vs chip；斩杀短路段不改。

**Tech Stack:** Python 3.12+、pytest、ruff、`bfsim`。

## Global Constraints

- 零卡名。
- `can_ko` → 必须仍返回 attack；`test_copy_ko_attacks_before_supporter` 断言不改。
- `_setup_value` 仅 E（启用能量）/ S（检索使下回合可 KO）/ H（治疗扛斩杀）。
- 不改 `pokemon_score` / `factor_prize_diff`。
- `setup_before_chip_gate` 不进 tune 10 维。
- 不实现 081；不改 `_ko_prize_lookahead` 语义。
- 不跑 18000；不宣称 30.4%。失败 0。

## File map

| 文件 | 职责 |
|---|---|
| `heuristic.py` | 字段；`_setup_value`；物品/支援者与非斩杀攻击比较。Task 1 不改 |
| `tests/test_heuristic_setup_before_chip.py` | 新红测 |
| `test_tune_space.py` | 登记字段 |
| 既有 ko/copy 测试 | 断言保持 |

---

### Task 1 — 文档落盘，然后停

- [x] Step 1: 规格/计划/task/STATUS
- [ ] Step 2: Owner 勾选 Q1–Q10
- [ ] Step 3: 进入 Task 2

---

### Task 2 — 红测

建议用例：

```python
"""task 087：非斩杀 setup 优先于芯片；斩杀不 defer。"""

# 1) copy can_ko + 支援者在手 → Action(attack, 0)  （084）
# 2) copy 付清、对手血厚、手牌有「再贴能量即可 can_ko」的物品路径
#    → 先 play_trainer（门开）；门关则按今天 min(iid)/序
# 3) 非斩杀 + 仅无 setup 价值的物品 → 按 Q3：跳过零价值后 attack，或维持序但不优先生造
# 4) setup_before_chip_gate=False → 与 main 行为一致
# 5) 路径不可见（无 copy/未付清）→ 门无效果
```

- [ ] Write failing tests
- [ ] pytest 新文件红

---

### Task 3 — 最小实现

1. 字段 `setup_before_chip_gate: bool = True`
2. `_setup_value(view, action) -> float`（E/S/H；未知 0）
3. `_chip_value(view) -> float`（即将 `_pick_attack` 的有效伤）
4. 在物品/支援者选择处：若门开且路径可见且非 `can_ko`：
   - 取 setup 分最高且 `> chip` 的训练家则 return
   - 否则跳过零价值列表（或整段），落到攻击
5. **若 `can_ko`：不进入上述分支**

```bash
python -m pytest tests/test_heuristic_setup_before_chip.py \
  tests/test_heuristic_ko_prize_lookahead.py \
  tests/test_heuristic_copy_conversion.py \
  tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/heuristic.py tests/test_heuristic_setup_before_chip.py
```

Commit: `task(087): prefer narrow setup over non-lethal ace chip`

---

### Task 4 — 一百局

同种子对照 A69。回写。可与 086 分 PR。

---

### Task 5 — 自检

- [ ] 斩杀回归绿且源断言未改
- [ ] 无 `prize_pressure_gate`
- [ ] 无卡名分支
- [ ] tune 10 维
- [ ] `_lethal_attack` 无行为 diff

## 与相邻计划

| 计划 | 关系 |
|---|---|
| 084 | Q2=C 硬约束 |
| 085 | 依赖路径可见/付清；不回滚转换 |
| 086 | 开关独立；可先可后 |