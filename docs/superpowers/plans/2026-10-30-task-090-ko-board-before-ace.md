# 090 先制造可 KO 局面再转化 Implementation Plan

> **For agentic workers:** 本文件停在文档。Owner 2026-10-30 禁止在 Q3 过线之前写测试或改 `heuristic.py`。不要把下面没有写出的 TDD 步骤补进去。Q 表勾选且计数 ≥15/40 之后，另开实现计划，再使用 superpowers:subagent-driven-development 或 superpowers:executing-plans。
>
> 规格 `docs/superpowers/specs/2026-10-30-task-090-ko-board-before-ace-design.md`。
>
> **Task 1 = 本 PR 停止线。**

**Goal:** 第一下复制攻击之前，若一张 `switch` 按今天的目标排序会把剩余 HP 不超过复制前瞻伤害的对手备战换上来，就打这张，然后仍由现有的斩杀短路完成击杀。

**Architecture:** 新开关 `copy_ko_switch_gate`（不进 tune）。只插在 `_decide_main` 已经走过 `_lethal_attack` 之后的支援者档。`_pick_choose` 不动。`_pick_energy_attach` 不动。`_lethal_attack` 不动。

**Tech Stack:** 文档。实现阶段才是 Python 3.12+、pytest、ruff、`bfsim`。

## Global Constraints

- 零卡名。暗夜王牌、换位牌的名字只出现在证据叙述里。switch 的识别是 DSL 的 `action: switch` 且 `selector: opponent_bench`。
- 禁止 `prize_pressure_gate`、禁止 081 行为、禁止新死名、禁止把新行为写进 `prize_race_gate`。
- 禁止用 089 的 K / E / G 给 089 补过。禁止用 H / Y 或 H+S+Y 的并集给 090 补过。
- 禁止放宽 088 的 ≥15/40、禁止放宽 089 的 ≥15/39、禁止重开这两份 TDD。
- 禁止复活 `setup_before_chip_gate`。`can_ko` 为真时仍立刻攻击。
- 禁止改 `_pick_choose`。088 的 C 维持收口。
- 不改 `pokemon_score` 函数、不改 `factor_prize_diff`、不改 `_ko_prize_lookahead` 的 `can_ko` / `via` 语义。
- 不把「己方奖杯落后」当作启用条件。
- 复制前瞻 `best_damage` 为 0 时，支援者序维持 `min(iid)`。不另加「0 伤害就禁止攻击」。
- 不跑 18000。不宣称 30.4%。失败必须为 0。
- Q5 硬过线：同种子 B 胜 ≥34 且失败 0。持平则回滚本步并重设计。电电虫同种子再 +≥3pp 则否决。

## File map（拍板且 Q3 过线之后才许改）

| 文件 | 职责 |
|---|---|
| `battlefrontier/agent/heuristic.py` | `_decide_main` 的支援者档。本 PR 不改 |
| `battlefrontier/tune/space.py` | 新开关不进 `search_space()`；注释列表在实现 PR 里补一行。本 PR 不改 |
| 新测试文件 | Q3 过线后另开。本计划不给出测试正文 |

---

### Task 1 — 文档落盘，然后停

- [x] Step 1: 规格、本计划、`tasks/task 090.md`、`STATUS.md` 当前焦点与一条工作记录
- [x] Step 2: Owner 勾选 Q1–Q9（2026-10-30 整包按本文建议 + 硬门 + 离线自治）
- [ ] Step 3: 仅当拍板含 Q3=计数且重放计数 ≥15/40：另开实现 PR。先写失败测试，再改支援者档。测试正文到那时才写

本文件没有「写测试 / 改 heuristic」的步骤。那两步在 Q 表改选或计数过线之后重写计划，不在本 PR 预填。
