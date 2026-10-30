# 089 触及时点 / 早期奖杯止血 Implementation Plan

> **待拍板。** 规格 `docs/superpowers/specs/2026-10-30-task-089-early-prize-keep-design.md`。
>
> **Task 1 = 本 PR 停止线。** TDD 步骤故意不写在这里。088 在 Q3 **1/40** 之后收口，没有进入启发式。089 在 Owner 勾选 Q 表、且 Q3 计数过线之前，不新增测试文件、不改 `heuristic.py`。

**Goal:** 第一下复制攻击之前，换上时不要把一张会被对手场上已可见招式直接 KO 的 ≥2 奖身体送上去，只要备战里有打不死的替身。

**Architecture:** 新开关 `early_prize_keep_gate`（不进 tune）。只插在 `_pick_promote` 今天会落到 `pokemon_score` 的那条非击杀回落上。`_pick_retreat` 不动。`prize_race_gate` 不动。`_lethal_attack` 不动。

**Tech Stack:** 文档。实现阶段才是 Python 3.12+、pytest、ruff、`bfsim`。

## Global Constraints

- 零卡名。暗夜王牌只出现在证据叙述和计数脚本的事件过滤里，不进启发式。
- 禁止 `prize_pressure_gate`、禁止 081 行为、禁止新死名、禁止把新行为写进 `prize_race_gate`。
- 禁止「己方剩余奖赏多于对手 → 撤退或换上」。
- 禁止复活 `setup_before_chip_gate`。`can_ko` 为真时仍立刻攻击、换上仍优先能击杀的身体。
- 不改 `pokemon_score` 函数、不改 `factor_prize_diff`、不改 `_ko_prize_lookahead` 的 `can_ko` / `via` 语义。
- 不跑 18000。不宣称 30.4%。失败必须为 0。
- Q5 硬过线：同种子 B 胜 ≥34。持平则回滚本步并重设计。

## File map（拍板且 Q3 过线之后才许改）

| 文件 | 职责 |
|---|---|
| `battlefrontier/agent/heuristic.py` | `_pick_promote` 的非击杀回落。本 PR 不改 |
| `battlefrontier/tune/space.py` | 新开关不进 `search_space()`；注释列表在实现 PR 里补一行。本 PR 不改 |
| 新测试文件 | Q3 过线后另开。本计划不给出测试正文 |

---

### Task 1 — 文档落盘，然后停

- [x] Step 1: 规格、本计划、`tasks/task 089.md`、`STATUS.md`
- [ ] Step 2: Owner 勾选 Q1–Q9
- [ ] Step 3: 仅当拍板含 Q3=计数且计数 ≥15/39：另开实现 PR，先写失败测试再改启发式

本文件没有 Step「写测试 / 改 heuristic」。那两步在 Q 表改选之后重写计划，不在本 PR 预填。
