# task 037 · 引擎性能优化（MCTS 规模化瓶颈清偿）

- 状态：完成（2026-10-14，MCTS 基准 -38.5% 过线 + 行为零变化双口径验收）
- 关联：task 034 遗留②（引擎单步成本是 MCTS 规模化的唯一瓶颈，cProfile 94% 在 rollout 引擎侧）；二期 PRD 开放问题外的自包含技术债
- 立项依据：用户拍板 2026-10-14（下一步方向调研第一优先——唯一能把所有后续方向都变便宜的杠杆）

## 目标

在不改变任何对局行为的前提下压低引擎单步成本，使 MCTS 标准档（2×50）单局成本显著下降。**行为零变化是头号硬约束**——同种子 events_hash 逐局全等（启发式与 MCTS 双口径），胜率分布只允许统计噪声内的差异（理论上应为逐局全等）。

## Profiling 摸底（2026-10-14，cProfile 实测，优化前基线）

启发式 40 局（沙奈朵×赛富豪，串行）：8.7s 总（含 ~5s 启动/prepare）；MCTS 2 局 @1×10：29.4s（含启动），热点（tottime）：

1. `pydantic validate_python` 1.82M 次 2.29s——热路径模型重复构造/校验（事件 emit 15.4 万次、visible_state 4.7 万次等）
2. `engine/core._main_actions`（合法行动枚举）63k 次 cum 7.79s——内含每候选行动重算 `_effective_retreat_cost`(56k) / `_effective_attack_cost`(88k) / `_ability_suppressed`(482k)
3. `clone()` 链：`model_copy(deep=True)` cum 4.11s + `copy.deepcopy` cum 2.34s + `__deepcopy__`——MCTS 每迭代克隆的 pydantic 深拷贝开销
4. `effect_doc_by_ref`/`effect_doc` 1.96M 次 ~1.5s——逐次 dict 查找 helper
5. `pydantic __eq__` 537k 次 1.16s——模型相等比较（行动/卡牌 in 与去重）
6. `chooser.enumerate_choices` 30k 次 2.03s + `matches` 782k 次
7. `state.current` property 2.1M 次 0.25s

## 设计决议（D-037-x）

- **D-037-1 行为零变化硬验收**：优化前后同种子 events_hash 逐局全等——启发式 40 局（种子 1000..1039，沙奈朵×赛富豪 + 沙奈朵镜像两卡组组合）+ MCTS 小预算 20 局（1×10，种子 117000..117019）双口径钉死；全量 pytest 绿 + ruff 零告警。
- **D-037-2 基准口径**：固定基准脚本（不入库，/tmp）记录优化前后——启发式 100 局串行 wall、MCTS 2 局 @1×10 wall、MCTS 标准档单局外推。每项优化单独测量单独落账，回退恶化的项。
- **D-037-3 优化顺序（收益/风险比排序，逐项独立可回退）**：
  - WP2 低风险投资组合：effect_doc 查找缓存化（模块级 dict 直查）；热路径模型构造走 `model_construct`（跳过重复校验，仅限引擎内部自构造的不可变对象）；`__eq__` 快路径（identity 先行）；`state.current` 内联/缓存
  - WP3 clone 快速路径：手写 GameState 结构拷贝替代 pydantic 深拷贝（不可变对象共享、可变容器逐层 copy）——MCTS 每迭代收益最大项
  - WP4 合法行动枚举优化：单次枚举内费用/抑制扫描结果缓存（一次 _main_actions 调用内 aura 扫描只做一次）
- **D-037-4 不做**：不改 DSL 语义、不改事件流结构、不引入 C 扩展/第三方加速依赖、不并行化引擎内部（局级并行既有）。

## 验收标准

1. 行为零变化：优化后同种子 events_hash 逐局全等（D-037-1 双口径）
2. 全量 pytest 绿 + ruff 零告警
3. 性能目标：MCTS @1×10 基准 wall 提升 ≥30%（2 局串行同机对比）；启发式 100 局 wall 提升如实记录
4. 每项优化（WP2/WP3/WP4）单独的前后测量数据落账
5. STATUS.md 落账 + 本档归档

## WP 划分

- WP1 基准与回归 harness：基准脚本 + 优化前 events_hash 快照（启发式 40 局 ×2 卡组组合 + MCTS 20 局）
- WP2 低风险投资组合（查找缓存 / model_construct / __eq__ 快路径 / current 内联）
- WP3 clone 快速路径
- WP4 合法行动枚举优化
- WP5 验收测量 + 落账

## 结果与遗留

**优化结果（2026-10-14，全部验收过线）**：

| 基准（串行） | 优化前 | 优化后 | 变化 |
|---|---|---|---|
| MCTS 20 局 @1×10（赛富豪×苍响） | 2m54.8s | **1m47.6s** | **-38.5%**（目标 ≥30% ✅） |
| 启发式 40 局（沙奈朵×赛富豪） | 5.5s | 4.7s | -14%（含 ~3.5s 固定启动开销，纯对局段改善更大） |
| 启发式 40 局（沙奈朵镜像） | 4.7s | 4.7s | 持平（启动开销主导） |

- **落地优化三项**（逐项实测，行为零变化）：
  - WP2a `Action` pydantic FrozenModel → **dataclass(frozen, slots)**（热路径单局百万级构造；pydantic validate 与 model_construct 双端开销在此都是纯浪费——教训：cProfile 对 Python 层函数有放大失真，model_construct 绕行方案实测无收益后回退，以 wall A/B 为准）
  - WP2b `effect_doc` 引擎级记忆化（`_effect_doc_cache` 按 card_id，克隆共享只读缓存；1.96M 次调用 1.5s→0.3s profile 口径）
  - WP3 `clone()` 深拷贝 → **浅拷贝结构共享**（状态图全 FrozenModel + tuple/frozenset 持久不可变风格实证——87 处 model_copy(update=) 重建、零原地变异、无 __setattr__  hack；深浅语义全等）
  - WP4 `legal_actions` **状态恒等缓存**（缓存槽持有 GameState 强引用防 id 复用误判；apply 的非法校验与驱动循环枚举天然相邻——枚举量直接减半，「引擎枚举合法行动、非法拒绝」纪律不变）
- **验收**：996 绿 + ruff 零告警（WP2/WP4 后各一轮）；events_hash 五元组（name/seed/hash/winner/turns）优化前后 **100/100 逐局全等 × 两轮**（启发式 40×2 + MCTS 20 双口径）
- **外推**：MCTS 标准档 2×50 ≈ 219s → ~135s/局/worker；全 matrix 铺开 68.7h → ~42h（量级不变，MCTS 定位 = 定点格分析维持）；阶段 B 五格级铺开 9.5h → ~5.8h

**遗留**：①剩余热点 = `_main_actions` 枚举逻辑本体（2.1s tottime profile 口径）与状态重建 model_copy（持久化固有成本）——继续深挖需结构性改动（如枚举增量复用），风险/收益比下降，本任务收口；②heuristic.score（42.6 万次调用）若优化属 Agent 侧，另开任务评估。
