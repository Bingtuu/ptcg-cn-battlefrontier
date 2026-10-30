# post-085 · 基线与下一刀（086 / 087）拍板一页纸

- 日期：2026-10-30
- 状态：**已拍板**（2026-10-30 Owner：086/087 整包按各自规格「本文建议」；TDD 顺序 086→087）。085 已合入；同格 500 基线已回写。本 PR 仍只文档。
- 阶段锁定：贴近真实策略 / 结果（sim–real 差距）。
- Owner 授权（chat）：先 A（基线）再 **B 与 C 都尝试**；流水线 拆解→文档→拍板→TDD→…

## 1. 已落地的事实

| 项 | 数字 / 事实 |
|---|---|
| 085 合入 | PR #14 → main `5a29664` / 文档叠 `11ef281`；实现 HEAD `635c053` |
| 100 局（种子 `208000..208099`） | A**69** / B31；B prizes **16**；暗夜王牌 293/80；触及后 B WR **35.0%** |
| 同格 500 基线 A（`t085-gard-nzoro-500`，种子 `208000..208499`，main `11ef281`） | A**68.8%** / B31.2%；失败 0；相对 real 30.4% → Δ **+38.4pp**（t080 +49.6；083 消融 +47.2） |
| 暗夜王牌触及后（500） | 触及 381 局；触及后 B WR **38.1%** |
| 084 Q2=C | 复制击杀仍进 `_lethal_attack`，先于训练家 |
| 081 / PR #10 | **不合并**；禁止复活 `prize_pressure_gate`、含羞苞自残窄门、卡名分支 |

含义：085 主杠杆有效（触及后胜率离开「贴整体 sim」）；该格仍远高于 real。下一刀不是再做击杀可见性，也不是 081 落后换高伤。

## 2. 两把待拍板的刀（可顺序、可独立开关）

| 刀 | 任务 | 中文名 | 一句话 | 建议开关 |
|---|---|---|---|---|
| **B** | **086** | 奖杯节奏（共享前瞻） | 复制/王牌路径**已可见**后，用共享 `_ko_prize_lookahead` 做奖杯/落后资源节奏；**不是** 081 的 `prize_pressure_gate` | `prize_race_gate: bool = True`（不进 tune） |
| **C** | **087** | 非斩杀 setup 时序 | 已付清复制但**非斩杀**时，若窄定义 `_setup_value` 严格优于挥砍，则先 setup；**不得**推迟 `can_ko` | `setup_before_chip_gate: bool = True`（不进 tune） |

顺序：拍板后可 **086→087** 或 **087→086** 串行 TDD；两开关正交。Owner 说两把都试——规格允许，不强制同 PR 实现。

## 3. 必须维持 / 明确禁止

**维持：**

- 084 Q2=C：复制击杀短路
- 083 共享 `_ko_prize_lookahead` + 有效 HP
- 085 `copy_conversion_gate` 行为
- `pokemon_score` / `factor_prize_diff` 冻结
- 零卡名（D10）

**禁止：**

- `prize_pressure_gate` / 合入 PR #10 / 081 式「落后且都不能斩杀 → 换更高印面伤」
- 系统性索罗亚克ex→含羞苞自残
- 卡名 `if name ==` 例外
- 本 docs PR 改 `heuristic.py`、合并实现

## 4. 建议默认（整包「本文建议」时可一键采纳）

详见各规格 Q 表。摘要：

**086：** 仅当复制/王牌路径已对前瞻可见时启用奖杯节奏评分；`prize_race_gate=True` 不进 tune；无自残撤退；消费共享前瞻；100 局相对 post-085 **A69** 向 real（约 60–70% 或 B prizes / 结构改善）；中速行诊断可选。

**087：** `_setup_value` 窄定义 = 启用下一能量 / 检索使下回合可 KO / 治疗使己方扛住对方斩杀；仅非斩杀可 defer；`can_ko` 不 defer；`setup_before_chip_gate=True`；保持致命短路。

## 5. 文档入口

| 文件 | 用途 |
|---|---|
| `docs/superpowers/specs/2026-10-30-task-086-prize-race-shared-lookahead-design.md` | 086 规格 + Q 表 |
| `docs/superpowers/plans/2026-10-30-task-086-prize-race-shared-lookahead.md` | 086 TDD 计划 |
| `tasks/task 086.md` | 086 摘要清单 |
| `docs/superpowers/specs/2026-10-30-task-087-nonlethal-setup-timing-design.md` | 087 规格 + Q 表 |
| `docs/superpowers/plans/2026-10-30-task-087-nonlethal-setup-timing.md` | 087 TDD 计划 |
| `tasks/task 087.md` | 087 摘要清单 |

**已拍板（2026-10-30）**：整包采纳「本文建议」；顺序 **086→087**。合 docs 后开 TDD。不改 heuristic 于本 PR。