# 088 触及后转化 / 奖杯完成 Implementation Plan

> **待拍板。** 规格 `docs/superpowers/specs/2026-10-30-task-088-posttouch-conversion-design.md`。
>
> **Task 1 = 本 PR 停止线。** TDD 步骤故意不写在这里。087 在拍板前就把红测写进计划，随后 100 局持平、PR #17 关闭。088 在 Owner 勾选 Q 表、且 Q3 计数过线之前，不新增测试文件、不改 `heuristic.py`。

**Goal:** 复制/王牌已付清的当回合，把已挂起的对手目标从「高 `pokemon_score`」改成「这一击能 KO，多个 KO 时奖张能收完优先」。

**Architecture:** 无新字段。行为挂在现有 `attack_quality_gate` 的 `_pick_choose` 分支。`_decide_main` 大顺序不动。`_lethal_attack` 不动。

**Tech Stack:** 文档。实现阶段才是 Python 3.12+、pytest、ruff、`bfsim`。

## Global Constraints

- 零卡名。暗夜王牌只出现在证据叙述里。
- 禁止 `prize_pressure_gate`、禁止 081 行为、禁止新死名、禁止把新行为写进 `prize_race_gate`。
- 禁止复活 `setup_before_chip_gate`。`can_ko` 为真时仍立刻攻击。
- 不改 `pokemon_score` 函数、不改 `factor_prize_diff`、不改 `_ko_prize_lookahead` 的 `can_ko` / `via` 语义。
- 不把「己方奖杯落后」当作启用条件。
- 不跑 18000。不宣称 30.4%。失败必须为 0。
- Q5 硬过线：同种子 B 胜 ≥34。持平不合。

## File map（拍板且 Q3 过线之后才许改）

| 文件 | 职责 |
|---|---|
| `battlefrontier/agent/heuristic.py` | `_pick_choose` 对 `opponent_bench` / `opponent_pokemon_any` 的排序键。本 PR 不改 |
| 新测试文件 | Q3 过线后另开。本计划不给出测试正文 |
| `tests/test_tune_space.py` | 默认不加字段，故不改 |

---

### Task 1 — 文档落盘，然后停

- [x] Step 1: 规格、本计划、`tasks/task 088.md`、`STATUS.md`
- [ ] Step 2: Owner 勾选 Q1–Q9
- [ ] Step 3: 仅当拍板含 Q3=计数且计数 ≥15/40：另开实现 PR，先写失败测试再改启发式

本文件没有 Step「写测试 / 改 heuristic」。那两步在 Q 表改选之后重写计划，不在本 PR 预填。
