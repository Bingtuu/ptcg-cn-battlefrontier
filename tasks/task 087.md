# task 087 · 非斩杀 setup 时序

> **进展（2026-10-30）**：TDD 绿（setup_before_chip_gate）；086 已合入 main cd67311（PR #16）；100 局待跑。不跑 bfsim、不合并。

> 文档已拍板（2026-10-30 整包按本文建议）。不改 `heuristic.py`。不得破坏 084 Q2=C。

- 状态：**已拍板**（2026-10-30 整包按本文建议）（docs PR：`cursor/task-086-087-docs`）
- 关联：规格 `docs/superpowers/specs/2026-10-30-task-087-nonlethal-setup-timing-design.md`；计划 `docs/superpowers/plans/2026-10-30-task-087-nonlethal-setup-timing.md`；一页纸 `docs/superpowers/specs/2026-10-30-post-085-baseline-and-next-knives.md`
- 依赖：085 已合入；084 Q2=C；083/085 路径可见；081 搁置
- 对外中文名：非斩杀 setup 时序
- 姊妹：task 086（可任序、独立开关）

## 目标

复制/王牌已付清但 `can_ko` 为假时，若窄 `_setup_value`（启用能量 / 检索使下回合可 KO / 治疗扛斩杀）严格大于芯片挥砍，则先 setup；`can_ko` 永不 defer。

## 本文建议（待 Owner 拍板列勾选）

| ID | 建议 |
|---|---|
| Q1 | **087 · 非斩杀 setup 时序** |
| Q2 | **永不 defer** can_ko |
| Q3 | **B**：setup>`chip` 则先 setup，否则跳过零价值后挥砍 |
| Q4 | `_setup_value` = **E+S+H** |
| Q5 | `setup_before_chip_gate: bool = True`，不进 tune |
| Q6 | 启用前提：路径已付清可见（不要求落后） |
| Q7 | 100 局相对 A69；不宣称 30.4% |
| Q8 | 与 086 可任序、独立开关 |
| Q9 | 冻结与禁止全维持 |
| Q10 | 本 PR 停文档 |

## 验收清单

- [x] 规格 + 计划 + 本 task + STATUS + 一页纸
- [ ] Owner 勾选 Q 表
- [ ] 单测 `tests/test_heuristic_setup_before_chip.py`（拍板后）
- [ ] `test_copy_ko_attacks_before_supporter` 绿且断言未改
- [ ] 一百局对照 A69（拍板后）
- [ ] 无 `prize_pressure_gate`；无卡名；本 docs PR 不改 `heuristic.py`

## 明确不做

推迟斩杀、081、宽泛任意抽牌当 setup、改 `pokemon_score`、宣称 30.4%、本 PR 实现/合并。