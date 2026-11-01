# task 098 · M14 后低成本决策差异归因 loop

- 状态：进行中
- 关联：M14 / M15 前置归因；`docs/digs/2026-11-01-m14-structure-feasibility.md`
- 分支：`task/m14-decision-mining`
- 边界：只读分析 M14 既有结果库；不新增 MCTS；不修改 Agent、DSL、引擎规则；不把 MCTS 参照当成部署候选

## 目标

在零新增 MCTS 预算的前提下，复用 M14 600 局与同种子启发式对照，完成一个可复现的低成本决策差异归因 loop：

1. **方案 A（自动挖掘）**：从 `mcts_consider` 与事件流中提取可解释的决策差异模式，先在首批种子发现、再用第二批独立种子验证。
2. **方案 B（回退）**：若方案 A 没有模式过线，则对最接近的翻转局面做一次关键回放/标注，检查是否漏掉必须由局面上下文表达的模式。
3. 最终给出二选一结论：**存在可进入启发式规则验证的候选模式**，或 **该方向 no-go 并给出下一低成本方案**。

## 预注册数据范围

只使用本机已有结果库：

- 目标强信号配对：多龙×电电虫
  - 首批：`results/m14-drag-joltik-heuristic.db` + `results/m14-drag-joltik-mcts.db`
  - 二批：`results/m14-drag-joltik-confirm-heuristic.db` + `results/m14-drag-joltik-confirm-mcts.db`
- 目标近失配对：多龙×N索
  - 首批：`results/m14-drag-zoro-heuristic.db` + `results/m14-drag-zoro-mcts.db`
  - 二批：`results/m14-drag-zoro-confirm-heuristic.db` + `results/m14-drag-zoro-confirm-mcts.db`
- 低残差对照：喷火龙×玛俐
  - `results/m14-char-grim-heuristic.db` + `results/m14-char-grim-mcts.db`
- 反向 sanity check：沙奈朵×N索
  - `results/m14-gard-zoro-heuristic.db` + `results/m14-gard-zoro-mcts.db`

必须覆盖 600 局 MCTS 与同种子启发式对照，并解析不少于 110,000 个 `mcts_consider` 决策点。

## 候选模式过线指标

候选模式必须全部满足以下指标才算 pass：

1. **确定性可提取**：同一脚本在同一结果库上重复运行，模式判定逐局一致。
2. **覆盖**：目标配对的两个独立种子批次中，每批至少覆盖 20 个决策点且至少出现在 5 局。
3. **稳定方向**：首批发现方向与二批验证方向一致；不允许一批改善、一批反向。
4. **合并效果显著**：两个独立批次合并后的逐种子改善量 CI 下界 >0；方向仍按 M14 CRN 口径（向真实值改善）。
5. **对照无显著反向**：喷火龙×玛俐低残差对照中，同一模式没有显著恶化；沙奈朵×N索反向格不得出现更强的反向证据。
6. **可表达**：能用不超过 3 条具体规则描述，并映射到明确的 `mcts_consider` chosen action / event kind / 局面上下文。

## Loop 与回退

1. 先实现只读分析脚本/命令，输出候选模式、覆盖率、逐批方向、合并 CRN CI、对照检查。
2. 方案 A 在首批种子做发现，在第二批种子做验证；不得用二批反复调参后再宣称独立验证。
3. 若没有任何候选模式同时过 6 项指标，执行一次方案 B：
   - 多龙×电电虫与多龙×N索各取最多 10 个逐种子胜负翻转样本；
   - 回放 MCTS 与启发式的关键分歧点；
   - 只记录是否能形成一个仍满足 6 项指标的新模式。
4. 方案 B 仍无合格模式，则结论为 **no-go**：保留证据，建议转入下一低成本方向（例如更宽的事件上下文特征或人工规则头脑风暴），但不进入 M15 Agent 修改。

## 验收标准（测试清单）

- [ ] `tasks/task 098.md` 完成预注册并经复核；指标与回退条件同当前 goal contract 一致。
- [ ] 分析实现为可重复运行的脚本/命令，输出可复现；不修改 Agent/DSL/引擎规则。
- [ ] 数据覆盖 600 局、≥110,000 个 `mcts_consider` 决策点，且解析失败为 0。
- [ ] 方案 A 输出候选模式完整评估表：覆盖、逐批方向、合并 CI、对照检查。
- [ ] 若方案 A 未过线，执行一次方案 B 并记录结果。
- [ ] 最终给出“候选模式 pass”或“no-go + 下一方案”结论。
- [ ] 全量 pytest 与 Ruff 通过；`STATUS.md` 与本 task 同步。

## 结果与遗留

待填。
