# task 085 · 王牌转换质量

> **待拍板。** 本文件只登记拆解。不改 `heuristic.py`，不写测试，不跑 `bfsim`。

- 状态：**文档已写，Q1–Q10 待 Owner 勾选**
- 关联：规格 `docs/superpowers/specs/2026-10-29-task-085-ace-conversion-quality-design.md`；计划 `docs/superpowers/plans/2026-10-29-task-085-ace-conversion-quality.md`（停在 Task 1）
- 依赖：083 已合入 main `4262a9f`（PR #12）。084 已收口（Q2=C，main `a3f1937`）。**081 搁置**（PR #10 不合并）
- 对外中文名：王牌转换质量

Owner 已选残差方向 A（2026-10-29）：王牌招式被摸到之后要转换，不重做击杀可见性，也不重开 081 的落后窄门。规格第 5 节的「本文建议」还没有勾选，不是实现授权。

## 拍板（待 Owner）

| ID | 本文建议 |
|---|---|
| Q1 | 任务编号 **085**，对外名「王牌转换质量」 |
| Q2 | 主刀 **B**：非斩杀复制输出。斩杀短路维持 084 Q2=C。不做奖张门 / 081 |
| Q3 | **四项都做**：能量启用分、撤退、换上、非斩杀 `_pick_attack`。单招复制身体上 `_pick_attack` 无操作 |
| Q4 | 换上非斩杀层：**有复制候选才按前瞻伤害**，击杀层仍比 `pokemon_score` |
| Q5 | 字段 `copy_conversion_gate: bool = True`，不进 tune |
| Q6 | 沙奈朵×N索 100 局是过线口径。N索中速控制四格必跑、不设过线。同格 500 只诊断 |
| Q7 | 对照 t080 A78/B22 与 t083 A72/B28。方向相对 A72：向 60–70%，或 B prizes 高于 14，或触及后胜率离开「贴着整体 sim」。不宣称 30.4% |
| Q8 | 同格 500 与加权 \|Δ\| 不是完成条件 |
| Q9 | 冻结全维持（`pokemon_score` / `factor_prize_diff` / 084 Q2=C / 血月 / end_turn / stadium / 081 / 卡名例外空） |
| Q10 | 本 PR 停在文档 |

## 目标

一条一层 `copy_attack` 已经付清，或再贴一张印面能量就付清时，能量、撤退、换上和非斩杀出招读 `_ko_prize_lookahead` 里的复制伤害。印面伤害为空的复制路径不再只靠 `pokemon_score` 的 0。

`_lethal_attack` 保持 main `a3f1937`：能复制斩杀仍先于训练家。

## 验收标准（测试清单）

Q 表未勾选。下面是「本文建议」被整包采纳之后才生效的清单。现在全部不做。

- [ ] 不在勾选前修改 `heuristic.py`
- [ ] 单测见计划 Task 2（新文件 `tests/test_heuristic_copy_conversion.py`）
- [ ] 旧断言保持：`test_copy_ko_attacks_before_supporter`、`test_neither_ko_does_not_retreat_just_because_behind`
- [ ] 一百局种子 `208000..208099`，失败 0，对照 t080 与 t083
- [ ] 四格行诊断回写后才标收口；行不动不否决一百局的方向记录
- [ ] 无 `prize_pressure_gate`，无卡名分支，不改 `pokemon_score`

## 实现要点

无代码变更。计划 Task 2 起在拍板前不执行。

建议落点（未授权）：`copy_conversion_gate`。关则四个非斩杀消费者回到今天。`ko_prize_lookahead_gate=False` 时复制不可见，转换开关无事可做。

## 与 084

| 项 | 084 收口后 | 本任务（建议，未拍板） |
|---|---|---|
| 复制斩杀先于训练家 | 维持 | **维持** |
| 非斩杀复制伤害 | 印面表为 0 | 能量 / 撤退 / 换上 / 多招出招可读前瞻 |
| 同格 500 \|Δ\| 47.2 | 不由 084 关 | 仍不是完成条件 |

## 结果与遗留

- 文档落在 main `a3f1937` 之上。未改启发式。
- 未做：TDD、字段、一百局、行诊断、18000、宣称到 30.4%。
- 已知证据仍是 STATUS 里的那些：正式矩阵加权 \|Δ\| 19.0%；沙奈朵×N索 sim 80% / real 30.4% / Δ +49.6%；消融同格 500 收到 77.6% / \|Δ\| 47.2；100 局 t080 A78/B22（B prizes 9），083 A72/B28（B prizes 14）。
