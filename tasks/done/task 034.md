# task 034 · MCTS 决策层（M8 主线，D2-3 门控已通过）

- 状态：完成（2026-10-03，500×2 向验证落账；MCTS 铺开与预算档待用户拍板）
- 关联：二期 PRD §3.1（MCTS 技术口径预登记）/ §7.3 一期预留（状态快照 + determinization + evaluate 纯函数）；M8b 复校准结论（剩余偏差由策略深度主导，局部规则修复已尽）
- 立项依据：用户拍板 2026-10-03（M8b 评估点论证成立后的正式启动）

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
  - ⚠️ **task 039 修订（D-039-2）**：本条已废止——挂起根改为带冻结集的部分 determinize（`freeze = pool_iids ∪ payload`，已知候选池原位冻结），残余隐藏区（对手手牌/双方牌库序/奖赏）不再携带真值进搜索；D-034-9 原论证只覆盖选择池已知，未覆盖残余隐藏区泄漏。

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

**WP1（引擎克隆 + determinizer，子代理 TDD + 主会话复验）**：`GameEngine.clone()`（state 深拷贝含 pending_choice 挂起上下文 / card_effects 共享 / events 全新 / rng 独立）+ `agent/determinize.py`（己方 deck+prizes 重洗、对手 hand+deck+prizes 三区合并重洗切回；计数与多重集合守恒；13 测试）。

**WP2（MCTS 搜索核心，子代理 TDD + 主会话复验修订）**：`agent/mcts.py`——多世界 determinized UCT（UCB1 c=√2；跨世界按根行动访问数聚合，平手取 legal 序靠前者）；rollout = HeuristicAgent 打到底（胜 1/平 0.5/负 0，回合 cap=根+50）；挂起根不决定化（D-034-9）。**主会话复验修订**：逐迭代克隆 rng 原实现逐迭代抽新种子 → 同行动路径回放遇概率事件（掷币）状态分叉、树边行动可能失真/非法；修为世界内固定 iter_seed（determinization 钉死未来随机性），回归测试钉住口径。

**WP3（接线，主会话直改）**：play_game 驱动循环 `bind_engine` hasattr 钩子；AgentCfg type=mcts + MCTS_PARAMS 词表（worlds/iterations/rollout_turn_cap，禁墙钟）；build_agents 独立随机流（seed+offset 先例）。996 绿 + ruff 零告警。

**WP4 单格验证（进行中）**：格 = 赛富豪×赫普的苍响（M6 最大偏差格，∓53.8；M9 基线赛富豪 93/403=18.75%）；种子区间对齐 matrix k=34（117000..117499）；预算 worlds=2/iterations=50。
- 冒烟 20 局：A胜10/B胜9/平1/失败0——赛富豪胜率 18.75%→52.6%（n=20 仅方向性信号）
- 性能基线：2×50 预算 ≈ 187s/局/worker（瓶颈 = 引擎单步成本非搜索框架，WP2 cProfile 实测 94% 在 rollout 引擎侧）
- 确定性：小预算 20 局串/并行 events_hash 20/20 全等（m8c-det-serial/parallel.db）
- 500×2 向全量（results/m8c-mcts.db，workers=16，wall 3h48m ≈ 219s/局/worker，失败 0）：
  - **赛富豪(MCTS)×苍响(heuristic)：219胜251负30平 → 46.6%**（基线 18.75%，+27.9pts，向真实侧 ~72% 收敛过半）
  - **苍响(MCTS)×赛富豪(heuristic)：476胜24负0平 → 苍响 95.2%**（基线 81.25%，+13.9pts）
  - 双向一致：MCTS 显著提升使用方胜率，实证 M8b 归因「剩余偏差由策略深度主导」与 D2-3 门控结论
- matrix 全铺开可行性：~219s/局/worker × 18000 局 / 16 workers ≈ 68.7h——不适合例行 matrix；MCTS 定位 = 定点格分析/高预算单格，铺开与否与预算档（2×50 基线）调整待用户拍板

**遗留**：①MCTS 半格收敛（46.6% vs 真实 ~72%）——预算加深（worlds/iterations 上调）或 rollout 质量改善的空间待评估；②串并一致实测 20/20（500 全量串行 ≈30h 不现实，单元级同种子双跑 hash 一致 + 实验级 20/20 为证据链）；③引擎单步成本是 MCTS 规模化的唯一瓶颈（cProfile 94% rollout 引擎侧），性能优化若立项另开 task。
