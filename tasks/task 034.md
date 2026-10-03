# task 034 · MCTS 决策层（M8 主线，D2-3 门控已通过）

- 状态：进行中
- 关联：二期 PRD §3.1（MCTS 技术口径预登记）/ §7.3 一期预留（状态快照 + determinization + evaluate 纯函数）；M8b 复校准结论（剩余偏差由策略深度主导，局部规则修复已尽）
- 立项依据：用户拍板 2026-10-13（M8b 评估点论证成立后的正式启动）

## 目标

落地 MCTS Agent（`type: mcts`），先单格验证（赛富豪×苍响，M6/M9 最大偏差格）再评估铺开。

## 设计决议（D-034-x，随落地进附录 A 或本档核销）

- **D-034-1 协议不动，挂接扩展**：Agent 协议 `observe(view, legal_actions)` 签名不变；MCTS 经可选钩子 `bind_engine(engine)`（play_game 驱动循环在 observe 前调用，`hasattr` 探测）拿到引擎引用。**信息纪律**：MCTS 读真实状态的唯一用途是喂 determinizer；搜索全程在 determinized 克隆上进行，对手手牌/牌库序/奖赏内容不进决策。
- **D-034-2 快照克隆**：`GameEngine` 增 `clone()`——state `model_copy(deep=True)`（pending_choice 在 GameState 内，挂起上下文随拷贝）+ 新 RandomSource + 共享 card_effects（不可变文档）+ 全新 events 列表（模拟事件**不回流**真实对局事件流）。
- **D-034-3 Determinization（单观察者）**：从当前玩家视角重采样隐藏区——①对手手牌内容（数量已知）；②双方奖赏卡内容（对双方均隐藏，rules-manual §3）；③双方牌库顺序（内容己方可知、序不可知）。采样池 = 该方 60 卡表 − 全部可见/公开区域（等价于从真实状态三区收集，与公开卡表信息等价）。reveal 记忆不建模（v1 已知近似）。
- **D-034-4 搜索形态 = 多世界 determinized UCT**：每决策采样 K 个世界，每世界内独立 UCT（UCB1，c=√2）跑 I 次迭代，跨世界按访问次数聚合取最优。每世界内部自洽，无跨世界信息泄漏。
- **D-034-5 Rollout 策略 = HeuristicAgent 复用**（PRD 预登记）：克隆上双方均以启发式打到底；终局计分 胜 1 / 负 0 / 平 0.5；rollout 回合计 cap = 根回合 + 50（防死局拖死，超限按平局计）。
- **D-034-6 预算 = 迭代次数，零墙钟**：`params: {worlds: K, iterations: I}` 暴露实验定义（AgentCfg.params 既有通道）；禁用 time budget（种子确定性硬规矩）。
- **D-034-7 随机源隔离**：MCTS agent 自带 RandomSource(seed+offset)（对齐 RandomAgent 偏移先例），引擎随机流零消费——heuristic 对局与 mcts 对局同种子不可比是预期口径（agent 类型改变事件流），但**同实验定义重跑必须逐局一致**（硬验收）。
- **D-034-8 对手建模**：搜索树内对手节点同样以 heuristic rollout 估值（不为对手建搜索树，v1 不建模对手隐藏信息推理）。
- **D-034-9 挂起根不决定化**（WP1 复验补丁）：根状态处于 `pending_choice` 挂起中时**不做 determinization**——挂起池 pool_iids 已被真实对局固定且对选择方是已知信息（search_deck 类揭示池），重洗会使恢复非法且丢失合法已知信息；该决策直接在真实状态上搜索。

## 验收标准

1. 克隆/决定化单测：pending_choice 挂起态克隆可续跑；determinizer 输出合法（区域计数守恒、可见区不动、隐藏区重洗）
2. MCTS 单测：同种子同状态同决策（确定性）；预算参数生效；挂起选择节点进搜索树
3. 同实验定义同种子双跑 events_hash 逐局一致；串/并行 500/500
4. 全量 pytest 绿 + ruff 零告警 + dsl-check 101 全 OK
5. 单格验证：赛富豪(MCTS)×苍响(启发式) 500 局，对比 M9 基线（赛富豪胜率 15.2%，m9-recalibration 格 #35 反面 93/403）胜率变化如实记录（方向预期：MCTS 侧提升；不设死阈值）；两侧互换（苍响 MCTS×赛富豪启发式）同跑对照
6. 性能基线：单局均耗时记录；matrix 全铺开可行性评估落账

## WP 划分

- WP1 引擎克隆 + determinizer（纯函数，TDD）
- WP2 MCTS 搜索核心（多世界 UCT + rollout）
- WP3 接线（bind_engine / AgentCfg type=mcts / build_agents / worker 透传）+ 确定性验收
- WP4 单格验证实验 + 性能基线 + 落账

## 实现要点

- 大批次走「子代理 TDD + 主会话独立复验 + 规格/质量双重复核」（task 026 惯例）；WP1→WP2→WP3 串行（依赖序）
- 实验定义示例：`agents: {a: {type: mcts, params: {worlds: 4, iterations: 100}}, b: {type: heuristic}}`

## 结果与遗留

（完工填写）
