# 086 奖杯节奏（共享前瞻） Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **待拍板。** 规格 `docs/superpowers/specs/2026-10-30-task-086-prize-race-shared-lookahead-design.md`。**Task 1 = 本 docs PR 停止线。** Task 2 起仅在 Q 表勾选且等于（或改写入）「本文建议」后执行。禁止实现 `prize_pressure_gate`。

**Goal:** 在复制/王牌路径已被 `_ko_prize_lookahead` 看见之后，用剩余奖差微调非斩杀撤退/换上，改善拿奖节奏；绝不复活 081 的印面高低伤落后门。

**Architecture:** 仅加 `HeuristicParams.prize_race_gate`。开着且路径可见时，在 083/085 之后的非斩杀层消费 `prizes_count` + 前瞻；关着回到今天。不改 `_lethal_attack`、不改前瞻 `can_ko`/`via` 语义、不改 `pokemon_score`。

**Tech Stack:** Python 3.12+、pytest、ruff、`bfsim`（Diupi-Yun）。

**权威设计：** 上述规格。姊妹计划：087。

## Global Constraints

- 零卡名。无 `if name ==`。
- **禁止**符号/行为 `prize_pressure_gate`；不合入 PR #10。
- 不改 `_lethal_attack`（084 Q2=C）。
- 不改 `pokemon_score` / `factor_prize_diff`；`tests/test_features.py` 期望不动。
- `prize_race_gate` 不进 tune 10 维；`bool_fields` 登记；`len(search_space())==10`。
- 落后 = `own.prizes_count > opponent.prizes_count`。
- 启用前提：`via=="copy"` 且 `best_damage>0`，或 `can_ko`（攻击仍由短路处理）。
- 不改 DSL/引擎；不读血月减费；不跑 18000；云端不跑 `bfsim`。
- 失败局必须 0。不宣称 30.4%。

## File map

| 文件 | 职责 |
|---|---|
| `battlefrontier/agent/heuristic.py` | `prize_race_gate`；撤退/换上窄消费。Task 1 不改 |
| `tests/test_heuristic_prize_race.py` | 新红测。Task 1 不建 |
| `tests/test_tune_space.py` | 登记字段，维数 10 |
| `tests/test_heuristic_ko_prize_lookahead.py` / `test_heuristic_copy_conversion.py` | 不改断言；须保持绿 |
| `tasks/task 086.md` / `STATUS.md` | 文档状态 |

---

### Task 1 — 文档落盘，然后停

**Files:**
- Create: specs/plans/task 086 + 一页纸（本 PR）
- Modify: `STATUS.md`

- [x] **Step 1: 写规格、计划、task，STATUS 声明待拍板**
- [ ] **Step 2: Owner 勾选 Q1–Q11**
- [ ] **Step 3: 整包采纳后再进入 Task 2**

---

### Task 2 — 红测（仅拍板后）

**Files:** Create `tests/test_heuristic_prize_race.py`；改 `tests/test_tune_space.py`。

**Interfaces:**
- Consumes: `_ko_prize_lookahead`、`HeuristicParams`、`main_state` 夹具
- 不产生：`prize_pressure_gate`、斩杀推迟

建议用例草稿：

```python
"""task 086：路径可见后的奖杯节奏。禁止 prize_pressure_gate。"""

# 1) ko_prize_lookahead_gate=False → prize_race_gate 无效果
# 2) 落后 + 备战 copy 伤严格高于战斗场印面 → retreat（门开）
# 3) 不落后 + 同上 → 不因奖差撤退（085 层另议）
# 4) 落后 + 仅印面更高的非 copy 备战 → 不撤（081 反例）
# 5) can_ko → 仍 attack，先于支援者
# 6) tune 10 维；无 prize_pressure_gate 属性
```

夹具卡名仅为 stub。保持 `test_copy_ko_attacks_before_supporter` 与 `test_neither_ko_does_not_retreat_just_because_behind` 绿。

- [ ] **Step 1: Write failing tests**
- [ ] **Step 2: Run pytest — expect FAIL（新测）**

---

### Task 3 — 最小实现（仅拍板后）

**Files:** `heuristic.py`（字段 + `_pick_retreat` / `_pick_promote` 窄分支）；`tune/space.py` 注释；`test_tune_space.py`。

伪代码（撤退，在 085 copy 层之后或合并条件——实现时对照规格 §3.2，避免双重撤退）：

```python
# 仅当 prize_race_gate and path_visible and behind:
#   允许撤到 via=="copy" 且 best_damage > active_dmg 的最高者
# 禁止：via!="copy" 仅因印面伤更高而撤
```

换上：在 085 `conv_key` 之上，落后时对 copy 候选可加次级键；不得抬无复制高印面压过复制。

- [ ] **Step 1: 字段 `prize_race_gate: bool = True`**
- [ ] **Step 2: 消费者**
- [ ] **Step 3: pytest 相关套件绿；ruff clean**
- [ ] **Step 4: Commit** `task(086): prize-race scoring via shared lookahead when copy path visible`

---

### Task 4 — 一百局（Diupi-Yun）

种子 `208000..208099`。对照 post-085 A69/B31（B prizes 16）。方向相对 A69。回写 task/STATUS。

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t086-gard-zoro.db
```

---

### Task 5 — 行诊断（Q6 默认可选）

若拍板「可选」且 Owner 要跑：沿用 085 四格 YAML 模式，不设过线。

---

### Task 6 — 自检

- [ ] 无 `prize_pressure_gate`
- [ ] 无卡名分支
- [ ] `_lethal_attack` 行为无 diff（复制斩杀仍短路）
- [ ] `pokemon_score` 无 diff
- [ ] tune 维数 10
- [ ] 081 反例测试绿

## 与相邻计划

| 计划 | 关系 |
|---|---|
| 081 | **不执行** |
| 083/084/085 | 已合入/收口；本刀叠加 |
| 087 | 可先或后；开关独立 |