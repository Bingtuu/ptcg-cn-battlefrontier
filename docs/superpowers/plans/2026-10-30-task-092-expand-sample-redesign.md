# 092 扩样本再定刀 Implementation Plan

> **For agentic workers:** 拍板已锁定（Q1–Q9=本文建议）。文档已合；本阶段跑 500 + dig。禁止改 `heuristic.py`、禁止写测试、禁止发明 gate。088–091 不重开。autonote：Owner 离线授权按建议自决 2026-10-30。
>
> 规格 `docs/superpowers/specs/2026-10-30-task-092-expand-sample-redesign.md`。
>
> **Task 1 文档已合 main（PR #23）。Task 2 = 本实验：500 + dig。**

**Goal:** 同格 500 分层 + 未触及对照 dig，再定下一刀。本刀零启发式。

**Architecture:** 文档。实验阶段才是 bfsim 500。

**Tech Stack:** 文档。

## Global Constraints

- 零卡名。零启发式变更。
- 禁止 `prize_pressure_gate` / 081 / 重开 088–091 / 放宽 15。
- 不宣称 30.4%。失败必须 0（若跑 500）。
- 18000 非本刀完成。

### Task 1 — 文档落盘（已合 main PR #23）

- [x] Step 1: 规格、本计划、`tasks/task 092.md`、STATUS
- [x] Step 2: Owner 勾选 Q1–Q9（整包按本文建议；autonote 离线自决）

### Task 2 — 同格 500 + dig（本实验）

- [ ] Step 1: `bfsim run experiments/t092-gard-zoro-500.yml` → `results/t092-gard-zoro-500.db`（种子 208000..208499；失败须 0）
- [ ] Step 2: 分层 dig（触及暗夜 / 未触及；胜率；奖杯结构；对照 100 局轴）
- [ ] Step 3: 未触及对照 dig
- [ ] Step 4: 写 `docs/digs/2026-10-30-task-092-expand-sample.md` + 下一刀菜单（推荐默认基于证据；无频数不发明启发式）
- [ ] Step 5: STATUS 写回验证数字

本文件没有「写测试 / 改 heuristic」的步骤。
