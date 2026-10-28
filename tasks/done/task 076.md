# task 076 · 正式 v2 矩阵两大失败

- 状态：完成
- 关联：task 072 正式矩阵（失败 1748；IndexError 888 + copy_attack 858 + 基因侵入 2）

## 目标

钉死并修掉启发式矩阵里抬高加权 |Δ| 的两处引擎/Agent 失败。不复跑 18000（云端无 ptcg-cn.db）。不引入 JEV/LLM，不扫全池。

## 验收标准（测试清单）

- [x] 红测：能量涡轮附着后启发式 `observe` / 攻击表长度（修前 `IndexError: list index out of range`）
- [x] 红测：copy_attack 嵌套 ≥2 打出内层伤害；基因侵入套暗夜王牌同路径
- [x] 同一 (来源 iid, 招式名) 再入复制链则不可选；纯套娃空结算、不循环
- [x] 一层复制（task 020）存量测试仍绿

## 实现要点

- IndexError：`resolve_tool_attacks` 为枚举、执行、启发式攻击表的同一函数。根因不是精神拥抱
- copy_attack：`copy_stack` 帧栈，不设层数上限。终止条件记附录 A（🔲）：链上已有的招式不再入池，池空 = 既有 no_copyable

## 结果与遗留

- 相关测试绿。完整矩阵复跑留本机
- backlog 仍留：特性使用质量 / play_stadium / end_turn
