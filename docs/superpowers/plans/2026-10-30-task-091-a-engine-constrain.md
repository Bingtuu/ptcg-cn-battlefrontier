# 091 约束 A 侧发动机 Implementation Plan

> **For agentic workers:** 本文件停在文档。Q1–Q9 已拍板。仍禁止在 Q3 过线之前写测试或改 `heuristic.py`。计数 ≥15/52 之后，另开实现计划。autonote：Owner 离线授权按建议自决 2026-10-30。
>
> 规格 `docs/superpowers/specs/2026-10-30-task-091-a-engine-constrain-design.md`。
>
> **Task 1 = 本 PR 停止线。**

**Goal:** 领先且无斩杀时，少发交易类循环特性，减轻触及后对侧发动机碾压。

**Architecture:** 新开关 `leader_cycle_throttle_gate`（不进 tune）。只插在 `_pick_ability` 的循环分支。`_lethal_attack` 不动。

**Tech Stack:** 文档。实现阶段才是 Python / pytest / bfsim。

## Global Constraints

- 零卡名。循环识别用 `_is_cycle_discard_draw`。
- 禁止 `prize_pressure_gate` / 081 / 重开 088–090 / 放宽 15。
- 不改 `_pick_choose` / `pokemon_score` / 084 短路。
- 不跑 18000。不宣称 30.4%。失败必须 0。
- Q5：B≥34 且失败 0，否则回滚。电电虫 +≥3pp 否决。

### Task 1 — 文档落盘，然后停

- [x] Step 1: 规格、本计划、`tasks/task 091.md`、STATUS
- [x] Step 2: Owner 勾选 Q1–Q9（2026-10-30 整包按本文建议 + 硬门；autonote：Owner 离线授权按建议自决 2026-10-30）
- [ ] Step 3: 仅当拍板含 Q3=计数且 ≥15/52：另开实现 PR

本文件没有「写测试 / 改 heuristic」的步骤。
