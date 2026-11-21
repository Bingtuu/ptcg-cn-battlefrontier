# task 090 · 先制造可 KO 局面再转化

> **已收口**（2026-10-30 Asia/Shanghai：Q1–Q9 曾整包按本文建议；Q3 **0/40 FAIL**）。不改 `heuristic.py`，不写测试，不放宽 15/40，不改去 H/Y 再计一次当过。088/089 维持收口。禁止 `prize_pressure_gate` / 081 / 死名。重设计文档是 task 091（**B 约束 A 侧发动机**），不在本任务里开 TDD。

- 状态：**已收口**（2026-10-30 Asia/Shanghai；Q3 **0/40 FAIL**；不写测试、不改 `heuristic.py`）。下一刀文档是 task 091，不重开本任务。
- 关联：规格 `docs/superpowers/specs/2026-10-30-task-090-ko-board-before-ace-design.md`；计划 `docs/superpowers/plans/2026-10-30-task-090-ko-board-before-ace.md`；Q3 dig `docs/digs/2026-10-30-task-090-q3-frequency.md`
- 依赖：088 收口（Q3 **1/40**）；089 收口（Q3 **0/39**）；086 在 main（A69/B31）。证据库 `results/t086-gard-zoro.db` @ `fc25648`。main 经 PR #20 合入拍板文档。
- 对外中文名：先制造可 KO 局面再转化

## 拍板表（曾锁定）

| ID | 本文建议（曾拍板） |
|---|---|
| Q1 | **090 · 先制造可 KO 局面再转化** |
| Q2 | **只 S**（`copy_ko_switch_gate`）；H/Y OUT；禁止并集与 K/E/G |
| Q3 | **≥15/40** 才 TDD；分母 = 088 首触未转化 |
| Q4 | **`copy_ko_switch_gate: bool = True`**，不进 tune |
| Q5 | **B≥34 且失败 0**；持平回滚 |
| Q6 | 电电虫 +≥3pp 否决；18000 非完成 |
| Q7 | 冻结全维持 |
| Q8 | 落后不当启用条件 |
| Q9 | 本步只文档 |

## Owner 拍板与硬门

曾整包按本文建议。硬门 1 = Q3 ≥15/40，否则收口。

### 离线自治

Owner 授权：硬门失败则回滚并试其他方向。本刀 Q3 失败 → 收口 090 → 下一刀文档推荐 **B 约束 A 侧发动机**（dig 选项 C）= task 091。

## 验收清单

- [x] 规格 + 计划 + 本 task + STATUS
- [x] Owner 勾选 Q1–Q9
- [x] Q3 计数（Diupi-Yun，同种子重放）：**0/40 FAIL**；见 dig；**不进入 TDD / 按硬门收口**
- [ ] （关闭）单测与 heuristic
- [ ] （关闭）100 局

## 结果与遗留

拍板已写回。Q3 **0/40 FAIL**（`docs/digs/2026-10-30-task-090-q3-frequency.md`）。按硬门 **收口 090**：不写测试、不改 `heuristic.py`、不开 TDD。诊断：首触前走到支援者 40/40、合法含 switch 支援者 23/40，但「复制前瞻 dmg>0 且分数赢家剩余 HP≤dmg」的 would-change 为 0；score-miss 诊断 1/40（208091）。重设计见 task 091。
