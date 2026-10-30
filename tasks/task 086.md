# task 086 · 奖杯节奏（共享前瞻）

> 文档已拍板（2026-10-30 整包按本文建议）。不改 `heuristic.py`。禁止 `prize_pressure_gate` / PR #10。

- 状态：**TDD 单元绿**（2026-10-30；分支 `cursor/task-086-prize-race-tdd`）；100 局 pending Diupi-Yun；不宣称矩阵闭环
- 关联：规格 `docs/superpowers/specs/2026-10-30-task-086-prize-race-shared-lookahead-design.md`；计划 `docs/superpowers/plans/2026-10-30-task-086-prize-race-shared-lookahead.md`；一页纸 `docs/superpowers/specs/2026-10-30-post-085-baseline-and-next-knives.md`
- 依赖：085 已合入 `5a29664`；post-085 500 基线 A68.8% / Δ+38.4pp；083/084(Q2=C)；**081 搁置**
- 对外中文名：奖杯节奏（共享前瞻）
- 姊妹：task 087（可任序、独立开关）

## 目标

复制/王牌路径已被 `_ko_prize_lookahead` 看见后，用奖差微调非斩杀撤退/换上节奏。不是 081 落后印面高低伤门。

## 本文建议（待 Owner 拍板列勾选）

| ID | 建议 |
|---|---|
| Q1 | **086 · 奖杯节奏（共享前瞻）** |
| Q2 | **B** 撤退+换上窄消费；禁止 D=081 |
| Q3 | 启用前提：copy 可见或 can_ko |
| Q4 | 落后 = `own.prizes_count > opponent.prizes_count` |
| Q5 | `prize_race_gate: bool = True`，不进 tune；**禁止死名** |
| Q6 | 100 局过线；行诊断可选 |
| Q7 | 相对 post-085 **A69**；向 60–70% 或 B prizes>16 或触及后改善；不宣称 30.4% |
| Q8 | 同格 500 诊断非完成条件 |
| Q9 | 与 087 可任序、开关独立 |
| Q10 | 冻结与禁止全维持 |
| Q11 | 本 PR 停文档 |

## 验收清单

- [x] 规格 + 计划 + 本 task + STATUS + 一页纸
- [x] Owner 勾选 Q 表（整包按本文建议）
- [x] 单测 `tests/test_heuristic_prize_race.py`（TDD 绿）
- [x] 无 `prize_pressure_gate`；无卡名；083/084/085 回归绿
- [ ] 一百局对照 A69（pending Diupi-Yun；本 PR 不跑 bfsim）
- [x] heuristic 窄改（`prize_race_gate` + 撤退/换上）；未改 `_lethal_attack` / `pokemon_score`

## 明确不做

081 复活、自残换人、卡名分支、推迟 `can_ko`、改 `pokemon_score`、宣称 30.4%、本刀不合并；100 局待跑；不实现 087。