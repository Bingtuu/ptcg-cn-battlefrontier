# task 085 · 王牌转换质量

> 已合入 main `5a29664`（PR #14）。局级与行诊断见下。

- 状态：**已合入 main `5a29664`（PR #14）**
- 关联：规格 `docs/superpowers/specs/2026-10-29-task-085-ace-conversion-quality-design.md`；计划 `docs/superpowers/plans/2026-10-29-task-085-ace-conversion-quality.md`（Task 2–3 完成；Task 4 未跑）
- 依赖：083 已合入 main `4262a9f`（PR #12）。084 已收口（Q2=C，main `a3f1937`）。**081 搁置**（PR #10 不合并）
- 对外中文名：王牌转换质量

Owner 已选残差方向 A（2026-10-29）：王牌招式被摸到之后要转换，不重做击杀可见性，也不重开 081 的落后窄门。2026-10-30 Owner 整包按「本文建议」拍板，授权进入 TDD。

## 拍板（2026-10-30 Owner，整包按规格「本文建议」）

| ID | 拍板 |
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
| Q10 | 本 docs PR 停在文档；TDD 另开 |

## 目标

一条一层 `copy_attack` 已经付清，或再贴一张印面能量就付清时，能量、撤退、换上和非斩杀出招读 `_ko_prize_lookahead` 里的复制伤害。印面伤害为空的复制路径不再只靠 `pokemon_score` 的 0。

`_lethal_attack` 保持 main `a3f1937`：能复制斩杀仍先于训练家。

## 验收标准（测试清单）

- [x] 不在勾选前修改 `heuristic.py`（docs 先行）
- [x] 单测见计划 Task 2（新文件 `tests/test_heuristic_copy_conversion.py`）——Diupi-Yun TDD 绿
- [x] 旧断言保持：`test_copy_ko_attacks_before_supporter`、`test_neither_ko_does_not_retreat_just_because_behind`
- [x] 一百局种子 `208000..208099`，失败 0，对照 t080 与 t083（A69/B31，B prizes 16，暗夜王牌 293/80，触及后 35%）
- [x] 四格行诊断已回写（多龙 A88/B12；黑夜 A70/B30；玛俐 A48/B52）；行不动不否决一百局方向
- [x] 无 `prize_pressure_gate`，无卡名分支，不改 `pokemon_score`

## 实现要点

- `HeuristicParams.copy_conversion_gate: bool = True`（不进 tune 10 维）
- `_one_layer_copy(..., extra_types=())` + `_copy_cost_paid`；空元组仍走 `_energy_satisfied`
- 四个消费者：`_newly_enabled_damage` / `_pick_retreat` / `_pick_promote` / `_pick_attack`
- `ko_prize_lookahead_gate=False` 时复制不可见，转换开关无事可做
- `_lethal_attack` / `pokemon_score` / `factor_prize_diff` 未改

## 与 084

| 项 | 084 收口后 | 本任务（已拍板） |
|---|---|---|
| 复制斩杀先于训练家 | 维持 | **维持** |
| 非斩杀复制伤害 | 印面表为 0 | 能量 / 撤退 / 换上 / 多招出招可读前瞻 |
| 同格 500 \|Δ\| 47.2 | 不由 084 关 | 仍不是完成条件 |

## 结果与遗留

- TDD（Task 2–3）在 Diupi-Yun 落地：相关套件 94 passed；ruff clean。
- 偏差：`test_promote_does_not_prefer_false_copy_ko_under_charm` 按 Q4 保守层改写——护符仍挡住 `can_ko`；转换开时非斩杀层按前瞻伤害抬复制；转换关回到 pokemon_score。
- **Task 4（2026-10-30 Diupi-Yun）**：`results/t085-gard-zoro.db`，代码 `635c053`。A**69**/B31，失败 0。对照 t080 A78/B22（B prizes 9）与 t083 A72/B28（B prizes 14）。B prizes **16**；暗夜王牌 **293/80**；触及后 B 胜率 **35.0%**（t080 24.3% / t083 32.0%）。相对 t083 翻转 A→B 5 / B→A 2。方向落入 60–70% 带，杠杆未证伪。
- **Task 5**：`experiments/t085-nzoro-row/` 三份 + 沙奈朵格。多龙 88/12；黑夜 70/30；玛俐 48/52。不设过线。
- 合并：Owner 拍板 A → PR #14 @ `5a29664`。未做：同格 500、18000、宣称到 30.4%。
