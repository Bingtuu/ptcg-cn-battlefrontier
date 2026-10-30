# 092 扩样本再定刀 Implementation Plan

> **For agentic workers:** 本文件停在文档。禁止改 `heuristic.py`、禁止写测试、禁止发明 gate。088–091 不重开。autonote：Owner 离线授权按建议自决 2026-10-30。
>
> 规格 `docs/superpowers/specs/2026-10-30-task-092-expand-sample-redesign.md`。
>
> **Task 1 = 本 PR 停止线。**

**Goal:** 同格 500 分层 + 未触及对照 dig，再定下一刀。本刀零启发式。

**Architecture:** 文档。实验阶段才是 bfsim 500。

**Tech Stack:** 文档。

## Global Constraints

- 零卡名。零启发式变更。
- 禁止 `prize_pressure_gate` / 081 / 重开 088–091 / 放宽 15。
- 不宣称 30.4%。失败必须 0（若跑 500）。
- 18000 非本刀完成。

### Task 1 — 文档落盘，然后停

- [x] Step 1: 规格、本计划、`tasks/task 092.md`、STATUS（随本提交）
- [ ] Step 2: Owner 勾选 Q1–Q9
- [ ] Step 3: 仅当拍板含「跑 500」：另开实验与 dig

本文件没有「写测试 / 改 heuristic」的步骤。
