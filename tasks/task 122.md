# task 122 · 决策理由标注（Agent 自省 → 回放可读）

- 状态：待拍板细化（Owner 已拍板立项 P3，设计按本文执行）
- 关联：task 042（mcts_consider 观测事件先例）/ task 120（盘面快照）；策略透明化线
- 日期：2026-11-14 立项

## 目标

回放从「操作 + 盘面」升级为「操作 + 盘面 + 为什么」：启发式 Agent 在关键决策点的 top-N 候选与评分入事件流，回放渲染为可读的决策理由。让策略**可审计**——备赛研习时能明确看到 bot 的理由并逐条判断「它错在哪」，而不是只能看到结果。

## 边界（先钉死）

- **只加观测事件，不改任何决策行为**（task 042 先例：`agent_explain` 观测事件排除 events_hash、render 正常显示、行为零变化）。
- 标注对象是启发式的**既有评分结构**（`pokemon_score` / 斩杀前瞻 / 能量付清判定），不为标注新造评分逻辑。
- 不承诺「标注 = 策略正确」；它解决的是策略**透明**，不是策略**质量**（质量线 = MCTS 预算 no-go 已封顶，task 097）。

## 设计

- `HeuristicAgent` 在关键决策点（首刀范围：`_pick_attack` / `_pick_retreat` / `_pick_promote` / `_pick_ability` / 能量附着目标）把 top-3 候选与各自评分存入 `last_explanation`（纯内存属性，无随机源交互）。
- Runner 层（agent.observe 返回后）若 agent 带 `last_explanation`，经引擎 `_emit("agent_explain", ...)` 入流（seq 正常，hash 排除，render 显示）。
- 回放渲染：`· 决策[attack]：奇迹之力(160) > 精神幻觉(80) > 换人(0) → 奇迹之力`（紧凑单行，跟在对应操作行前）。
- 量控：每决策点一条，不含逐卡展开（细节在 detail dict 里，渲染只取 top-3）。

## 验收标准（TDD）

1. 红测 → 绿：启发式在构造局面下产生 `agent_explain` 事件，top-3 候选与评分与内部评分函数一致。
2. 红测 → 绿：events_hash 排除 explain 事件（同种子开/关标注结果逐局一致）。
3. 红测 → 绿：回放渲染含决策理由行；旧库回放不破。
4. 全量 pytest 绿 + ruff 零告警；replay 抽查（串并 events_hash 20/20）。

## 结果与遗留

- **实现（验收 1–3 ✅）**：`HeuristicAgent` 自省机制（`explain_enabled` + `last_explanation`，observe 重置防重复记账）+ 三决策点标注（attack = 与 rank 同口径有效伤害；promote = pokemon_score，全部分支 return 点覆盖；place = 放置键同序）。Runner 层发射 `agent_explain` 观测事件（task 042 同口径），render 渲染 `决策[kind]：候选 a(分) > b(分) → 选择`。
- **hash 口径修正（验收 2 抓出的真问题）**：观测事件插入使后续事件 seq 错位，过滤 payload 的 seq 不再连续 → `events_hash_for` 单一直接来源（过滤 + seq 重编号）；开/关标注同种子 hash 逐局一致（测试实证）。旧 mcts_analysis 复写算法的测试改引权威函数（口径收敛，防再漂移）。
- **范围调整（如实记录）**：首刀落地 attack / promote / place 三个数值键决策点；retreat / ability / 能量附着为门控 tuple 键（含 can_ko 层/奖差层），逐分支设计留档——不造新评分逻辑约束下不为标注硬拆键结构。
- **抽查（验收 4 部分 ✅）**：局部 46 passed + ruff 零告警；串并 events_hash 20/20（新口径）。全量回归后台收尾。
- **遗留**：全量回归结果回填 + 提交；retreat/ability/能量标注 = 后续 task 候选。
