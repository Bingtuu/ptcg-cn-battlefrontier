# 083 共享击杀/拿奖前瞻 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **已拍板（2026-10-29）。** Q1–Q15 取规格「本文建议」整列（Q15 = 是）。下文执行 **F1+F3**；跳过 F2；不实现 F4 / 不合并 081；082 并入为 WP-copy。

**Goal:** 提供一个共享击杀/拿奖前瞻接口（自己招式 / 一层 copy / promote 后同一口径），让撤退、promote、攻击击杀分支消费同一出口；修复「暗夜王牌估 0 → 换含羞苞」类自残，而不把 081 的落后策略门合进 main。

**Architecture:** 在 `HeuristicAgent` 内抽出 `_ko_prize_lookahead`（名待拍板）。F1 把 `copy_attack` 一层前瞻并入该出口；F3 让 `_lethal_attack`、`_max_paid_ko_damage`（或由其替换的查询）、`_pick_retreat`、（按 Q15）`_pick_promote` 只读该出口。不写进 `_attack_table`。不实现 `prize_pressure_gate`。

**Tech Stack:** Python 3.12+、`tests/helpers.py`、pytest、ruff。局级验收用 `bfsim`（Diupi-Yun / 本机 `ptcg-cn.db`）。

**权威设计：** `docs/superpowers/specs/2026-10-29-task-083-shared-ko-prize-lookahead-design.md`。

## Global Constraints

- 零卡名分支。`owner` / DSL `filters` 经 `matches_in_play`；未知 filter 的 `DslError` 不猜。
- `pokemon_score` 与 `factor_prize_diff` 不动。`tests/test_features.py` 期望不得改。
- 开关（建议 `ko_prize_lookahead_gate`）不进 tune 的 10 维。`bool_fields` 可含该字段，`len(search_space())` 仍是 10。
- 费用继续印面 `_energy_satisfied`。不读 `modify_attack_cost`。
- 不改 `_pick_energy_attach`、`_place_key`、`_copy_donor_key`、`_pick_choose`、`_attack_table`、非击杀 `_pick_attack`、`play_stadium` / `end_turn`、`_decide_main` 大顺序。
- **不**新增或合入 `prize_pressure_gate`。不实现落后换更高非击杀。PR #10 保持不合并。
- 复制前瞻只一层、只 `selector=own_bench_attack`。供体不用自己付费。不递归嵌套 `copy_attack`。
- 不引入 JEV/LLM，不改 MCTS/蒸馏，不改 DSL/引擎，不跑 18000。
- 失败局必须是 0。云端无库，不跑 `bfsim`。
- tie-break 用下标升序，不消费随机源。
- 局级对照 = main/080 同种子 A78/B22，不是 081 的 A80。

## File map

| 文件 | 职责 |
|---|---|
| `battlefrontier/agent/heuristic.py` | 共享接口 + F1 copy 展开；retreat/attack(/promote) 改消费 |
| `tests/test_heuristic_ko_prize_lookahead.py` | 契约与 copy 可见性红测（吸收原 082 场景） |
| `tests/test_tune_space.py` | `bool_fields` 登记新开关；维数仍 10 |
| `tests/test_heuristic_attack_quality.py` | 回归：chooser 断言不改 |
| `tests/test_heuristic_board_gate.py` | 回归：078 击杀撤退 |
| `tasks/task 083.md` / `STATUS.md` | 实现收尾时回写（本规划 PR 只写规格状态） |

不创建 `tests/test_heuristic_prize_pressure.py`（081 不进本刀）。不把 PR #10 的文件 cherry-pick 进本分支。

---

### Task 1 — WP-copy / F1：共享接口 + copy 展开估值

**Files:**
- Create: `tests/test_heuristic_ko_prize_lookahead.py`
- Modify: `battlefrontier/agent/heuristic.py`
- Modify: `tests/test_tune_space.py`

**Interfaces:**
- Consumes: `doc_for`、`find_attack_effect`、`flatten_steps`、`matches_in_play`、`_copied_strike`、`_energy_satisfied`、`_attack_table`
- Produces: `HeuristicParams.ko_prize_lookahead_gate: bool = True`（若 Q7 改名则跟拍板）
- Produces: `_ko_prize_lookahead(view, mon=None) ->` 含 `best_damage` / `can_ko` / `via`
- Produces: `_lethal_attack` 与「最高已付清有效输出」查询在开关开时看见一层 copy
- 不产生：`prize_pressure_gate`、`_attack_table` 改动、080 chooser 改动

- [ ] **Step 1: Write the failing tests（copy 可见 + 接口契约）**

覆盖规格 D-083-7 单测清单中与 F1 相关的条目。夹具可参考 `docs/superpowers/plans/2026-10-29-task-082-copy-lethal.md` 的 COPY_DOC / 供体 stub（历史参考，实现以 083 规格为准）。

关键断言方向：

1. 复制手印面 `damage=None`，N 供体印面足够、对手残血低 → 默认 `observe` 返回 `attack`（击杀优先压过支援者）
2. `ko_prize_lookahead_gate=False` → 仍走今天（看不见 copy 击杀）
3. 供体费用未满足、复制手费用满足 → 仍 `attack`（供体不必付费）
4. 共享接口对同一 `view`：`can_ko` 与 `best_damage` 稳定；无文档时不猜

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_heuristic_ko_prize_lookahead.py -q
```

- [ ] **Step 3: Implement minimal F1**

抽出 `_ko_prize_lookahead`；copy 分支复用 `_copied_strike`；`_lethal_attack` 与 `_max_paid_ko_damage`（或内联替换为读 lookahead 的 `best_damage`）在开关开时合并前瞻。不改 `_attack_table`。

- [ ] **Step 4: Run tests — expect PASS；ruff clean**

```bash
python -m pytest tests/test_heuristic_ko_prize_lookahead.py tests/test_heuristic_attack_quality.py tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/heuristic.py tests/test_heuristic_ko_prize_lookahead.py tests/test_tune_space.py
```

- [ ] **Step 5: Commit**

```bash
git add battlefrontier/agent/heuristic.py tests/test_heuristic_ko_prize_lookahead.py tests/test_tune_space.py
git commit -m "task(083): F1 shared KO/prize lookahead with copy expand"
```

---

### Task 2 — F3：retreat / promote / attack 共用接口

**Files:**
- Modify: `battlefrontier/agent/heuristic.py`（`_pick_retreat`、按 Q15 `_pick_promote`）
- Modify: `tests/test_heuristic_ko_prize_lookahead.py`（F3 契约）
- Modify: `tests/test_heuristic_board_gate.py`（回归，断言不改语义）

**Interfaces:**
- Consumes: 仅 `_ko_prize_lookahead` / `_view_as_active`
- Produces: 078 击杀撤退改读共享接口（复制能击杀的战斗场不撤）
- Produces（若 Q15=是）：promote 在存在「换上后 can_ko」候选时优先于纯 `pokemon_score`
- 不产生：落后判定、`prize_pressure_gate`、非击杀高低伤换人

- [ ] **Step 1: Write failing F3 tests**

1. 战斗场复制能击杀、备战印面也能击杀 → 不撤（复制可见）
2. 两边都不能击杀 → 行为与今天 078 一致（付不起才撤）；**不要**写 081 落后撤更高伤
3. （Q15=是）promote：墙高分 vs 能击杀的低分打手 → 选击杀手；开关关 → 仍墙
4. （Q15=否）跳过 promote 行为测；可保留「接口对 `_view_as_active` 可调用」的单元契约

- [ ] **Step 2: Implement — retreat/attack 只读共享出口；promote 按 Q15**

删除或内联不再分叉的重复伤害循环。禁止在 `_pick_retreat` 里再手写一份 copy 展开。

- [ ] **Step 3: Regression suite**

```bash
python -m pytest tests/test_heuristic_ko_prize_lookahead.py tests/test_heuristic_board_gate.py tests/test_heuristic_agent.py tests/test_heuristic_attack_quality.py tests/test_features.py tests/test_tune_space.py -q
python -m ruff check battlefrontier/agent/heuristic.py tests/test_heuristic_ko_prize_lookahead.py
```

- [ ] **Step 4: Commit**

```bash
git commit -am "task(083): F3 retreat/promote/attack consume shared lookahead"
```

---

### Task 3 — 局级验收（Diupi-Yun；云端跳过）

仅当 Q12/Q13 拍板后执行。对照 **main/080 A78/B22**，种子 `208000..208099`。

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t083-gard-zoro.db
bfsim report <id> --results results/t083-gard-zoro.db --decisions
```

记下：A/B 胜率、prizes/deck_out/no_pokemon、暗夜王牌触及、失败数。失败必须 0。

**不要**对照 081 的 A80。短行仅当 Q14 要求。

回写 `tasks/task 083.md` 结果节与 `STATUS.md`。

---

### Task 4 — 明确不做（实现 PR 自检清单）

- [ ] 无 `prize_pressure_gate` 字段
- [ ] 未 cherry-pick PR #10 行为
- [ ] 无卡名分支
- [ ] `tests/test_features.py` 未改期望
- [ ] tune `len(search_space()) == 10`
- [ ] 未读 `modify_attack_cost`
- [ ] 未改 `end_turn` / `play_stadium` / 080 chooser

## 与历史计划的关系

| 旧计划 | 关系 |
|---|---|
| `docs/superpowers/plans/2026-10-29-task-081-prize-pressure.md` | **不执行**。保留作文档；实现以本计划为准且默认不含其 Task 1 行为 |
| `docs/superpowers/plans/2026-10-29-task-082-copy-lethal.md` | **吸收为 Task 1（WP-copy）**。红测场景可复用，文件名与开关名跟 083 规格 |

F2 / F4：本计划无对应 Task。Owner 若改勾选，先改规格再开补丁计划。
