# 首触转化×时序混合 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 本文件停在文档。Q3 过线之前禁止写测试、禁止改 `heuristic.py`。规格 `docs/superpowers/specs/2026-10-30-task-093-convert-timing-hybrid-design.md`。
>
> **Task 1 = 本 PR 停止线。**

**Goal:** 把 092 dig 选项 E 收成可计数的新识别器 R（落后且零伤复制时，用 `place_bench` 放上供体基础），并写明独立 Q3 与 100 局硬门。

**Architecture:** 新开关 `convert_timing_hybrid_gate`（不进 tune）。将来只插在 `_decide_main` 末尾、`_pick_attack` 之前。`_lethal_attack`、`_pick_choose`、`_pick_promote`、`_pick_retreat`、`_pick_ability`、支援者序都不动。

**Tech Stack:** 本 PR 只有 Markdown。实现阶段才是 Python / pytest / bfsim。证据库在 Diupi，不在本仓库。

## Global Constraints

- 机制只 R。would-change 不是 088 C、089 P、090 S、091 L。
- 零卡名。供体识别用 `copy_attack` 的 `filters` + `matches_in_play` + `_copied_strike`。
- 禁止 `prize_pressure_gate` / 081 / 死名 pressure。禁止把行为写进 `prize_race_gate` 或其他已有闸。
- 冻结 088–091 的机制、字段、15 局门槛。冻结 084 斩杀短路与 086 现有撤退。
- Q3：触及负 236 局里 R would-change ≥15 才允许 TDD。分母重算不是 236 则停。
- Q5：100 局种子 `208000..208099`，B≥34 且失败 0，否则回滚。
- 电电虫同种子 +≥3pp 否决。18000 非完成。不宣称 30.4%。
- 本 PR 不改 `heuristic.py`，不写测试，不跑 `bfsim`。

### Task 1 — 文档落盘，然后停

- [x] Step 1: 规格、本计划、`tasks/task 093.md`、`STATUS.md` 焦点与工作记录
- [ ] Step 2: Owner 勾选 Q1–Q9
- [ ] Step 3: 仅当拍板含 Q3=计数且重放 ≥15/236：另开实现 PR（先红测，再改 `_decide_main`）

本文件没有「写测试 / 改 heuristic」的步骤。
