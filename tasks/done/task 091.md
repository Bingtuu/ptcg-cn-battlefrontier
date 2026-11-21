# task 091 · 约束 A 侧发动机

> **已收口**（2026-10-30 Asia/Shanghai：Q1–Q9 曾整包按本文建议；Q3 **0/52 FAIL**）。autonote：Owner 离线授权按建议自决 2026-10-30。不改 `heuristic.py`，不写测试，不放宽 15/52，不发明新启发式。088/089/090 维持收口。禁止 `prize_pressure_gate` / 081 / 死名。下一刀文档是 task 092（**扩样本再定刀**），不在本任务里开 TDD。

- 状态：**已收口**（2026-10-30 Asia/Shanghai；Q3 **0/52 FAIL**；不写测试、不改 `heuristic.py`）。下一刀文档是 task 092，不重开本任务。
- 关联：规格 `docs/superpowers/specs/2026-10-30-task-091-a-engine-constrain-design.md`；计划 `docs/superpowers/plans/2026-10-30-task-091-a-engine-constrain.md`；Q3 dig `docs/digs/2026-10-30-task-091-q3-frequency.md`
- 依赖：090 收口（Q3 **0/40**）；089 **0/39**；088 **1/40**；086 在 main（A69/B31）。证据库 `results/t086-gard-zoro.db` @ `fc25648`。拍板提交本地 `f5c9e03`。
- 对外中文名：约束 A 侧发动机

## 拍板表（曾锁定）

| ID | 本文建议（曾拍板） |
|---|---|
| Q1 | **091 · 约束 A 侧发动机** |
| Q2 | **只 L**（`leader_cycle_throttle_gate`：领先且无斩杀时节流 `_is_cycle_discard_draw`） |
| Q3 | **≥15/52** 才 TDD；分母 = dig 触及负 |
| Q4 | **`leader_cycle_throttle_gate: bool = True`**，不进 tune |
| Q5 | **B≥34 且失败 0**；持平回滚 |
| Q6 | 电电虫 +≥3pp 否决；18000 非完成 |
| Q7 | 冻结全维持（088–090 不重开） |
| Q8 | 落后不当启用（gate 看领先） |
| Q9 | docs done |

## Owner 拍板与硬门

曾整包按本文建议。硬门 1 = Q3 ≥15/52，否则收口。

### 离线自治

Owner 授权：硬门失败则回滚并试其他方向。本刀 Q3 失败 → 收口 091 → 下一刀文档 **扩样本再定刀** = task 092（dig 选项 C：同格 500 分层 + 未触及对照；088–091 作负面结果）。

## 验收清单

- [x] 规格 + 计划 + 本 task + STATUS
- [x] Owner 勾选 Q1–Q9（autonote 离线自决）
- [x] Q3 计数（Diupi-Yun，同种子重放）：**0/52 FAIL**；见 dig；**不进入 TDD / 按硬门收口**
- [ ] （关闭）单测与 heuristic
- [ ] （关闭）100 局

## 结果与遗留

拍板已写回。Q3 **0/52 FAIL**（`docs/digs/2026-10-30-task-091-q3-frequency.md`；脚本 `experiments/t091_q3_frequency.py`）。诊断：A 侧触及负里高频特性是愿增猿/`move_damage_counters` 与沙奈朵ex/`attach_energy`，**不是** `_is_cycle_discard_draw`，故 L 识别器分子为 0。按硬门 **收口 091**：不写测试、不改 `heuristic.py`、不开 TDD、不放宽门槛、不发明启发式。重设计见 task 092。
