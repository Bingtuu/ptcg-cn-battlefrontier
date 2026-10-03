# task 032 · M8a 启发式修复批（A1→A2→A4→A3）

- 状态：进行中
- 关联：二期 PRD §3.1 / 里程碑 M8a；归因报告 `docs/m7-attribution-report.md`（task 031）；基线 `results/m6-calibration.db`

## 目标

修复归因确认的 Agent 四缺陷，全部保持通用规则（守 D10 不按卡名分支）、确定性不破（纯规则无随机源）。WP 划分：

- WP1 = A1 代价/收益选择方向
- WP2 = A2 变量伤害入斩杀表 + A3 囤能例外 + A4 牌库资源管理（共享 card_effects 入 Agent 的管道）
- WP3 = M8b 复校准：matrix 同定义重跑 + calibration 对比 M6 基线

## 设计决议（D-032-x）

- **D-032-1（A1 穿透链）**：解释器挂起时把扁平步骤的 phase 标注上 NeedChoice（`step_phase`，默认 `"actions"`）→ chooser.build_pending 透传 → PendingChoice 加 `step_phase: str = "actions"`（FrozenModel 加默认值字段，序列化兼容）。Agent 经既有 `view.pending_choice` 读取，零可见视图变更。选择方向：**cost 段取最低评分子集，actions 段维持最高评分**；tie-break iid 升序不变。
- **D-032-2（card_effects 入 Agent）**：`HeuristicAgent(params, card_effects=None)`；`experiment._build_one` / `build_agents` 加可选 card_effects 参数（worker payload 已带 DSL docs，可原地重建）；play.py 默认 None 兼容存量调用。DSL 文档 = 公开卡面信息，不违反可见视图纪律。None 时全部行为回退现状（静态伤害表）。
- **D-032-3（变量伤害估算口径）**：对战斗场宝可梦栈顶卡的 DSL 文档，找 trigger=on_attack 且绑定该招式名的效果，取 selector=opponent_active 的 damage 节点求值：count 词映射可见状态量（attached_energy_on_both_actives / opponent_taken_prizes 等直接求值；`discarded_this_effect` 回读同效果前序 discard 节点池——pool=own_hand → 手牌中匹配 filters 的卡数，pool=own_attached_energy → 该宝可梦附着能量数）；未知计数词 / 无 DSL 文档 / 嵌套 copy → 回退静态基值（现状行为）。效果级 condition 仅求值奖赏类词（opponent_prizes_eq / opponent_prizes_in），其余未知 condition → 该招式不参与斩杀判定但基值仍入表。估算纯函数、零随机。
- **D-032-4（斩杀最小弃置）**：pending choose 为 any_count discard 且同效果后续步骤含 `damage count=discarded_this_effect` 时：能斩杀 → 选达到斩杀的最小张数；不能斩杀 → 选最大（倾泻）。其他 any_count discard 维持现状。
- **D-032-5（A3 囤能例外）**：主动宝可梦带「手牌弹药型」伤害模式（DSL 检测：on_attack 效果含 discard pool=own_hand + 后续 damage count=discarded_this_effect）→ `_pick_energy_attach` 返回 None（能量留手牌作弹药）。无 DSL 文档时现状不变。
- **D-032-6（A4 牌库保护）**：HeuristicParams 新参 `deck_protect: bool = True` + `deck_low_threshold: int = 6`（默认值即新行为，旧实验 YAML 无参兼容）。牌库余量 ≤ threshold 时：含 draw 节点的 play_trainer 抑制（改走后续排序）；攻击选择中含 draw 的招式降权（有其他攻击则不选它）。检测经 DSL 文档（含 draw 节点即计，不过度细分「纯过牌」）。

## 验收标准（测试清单）

WP1（A1）：
1. PendingChoice.step_phase 字段默认值 + 序列化往返
2. cost 段挂起标注 step_phase="cost"（真实卡：大地容器 / 超级能量回收效果内挂起）
3. heuristic cost 选择取最低分（构造 pending：池含高分宝可梦 + 低分能量 → 选能量）
4. actions 段维持最高分（回归断言）
5. 全量 pytest 绿 + ruff 零告警（既有 choose 事件流不受影响）

WP2（A2+A3+A4）：
6. HeuristicAgent(card_effects=None) 行为与现状逐案一致（回退路径）
7. 淘金潮型估算 = 50 × 手牌基本能量数；极雷轰型 = 70 × 自身附着能量数（fixture DSL 文档驱动，不碰卡名）
8. 斩杀检测使用估算值（可斩杀 → 攻击优先于训练家）
9. D-032-4 最小斩杀弃置 / 不可斩杀倾泻两分支
10. A3 囤能：手牌弹药型主动在场 → 跳过附着；无 DSL 文档 → 现状
11. A4：deck ≤ 阈值抑制含 draw 训练家；> 阈值正常打出；攻击侧 draw 招式降权
12. 效果 condition 奖赏词求值（古月鸟型：不满足 → 不参与斩杀）
13. 全量绿 + ruff 零告警 + `dsl-check --db` 全库 OK

WP3（M8b 复校准）：
14. matrix 同定义重跑（`experiments/m6-calibration.example.yml`，新库 `results/m8b-recalibration.db`），确定性复核（抽样 ≥2 格串/并行逐局一致）
15. `bfsim calibration` 出表对比 M6 基线：赛富豪 8 格 Δ 方向预期全线回正；加权平均 |Δ| 与 CI 覆盖率如实记录（不设死阈值）

## 实现要点

- 流程：主会话任务书（本文）→ 子代理 TDD 串行（WP1 → WP2，09-20 降本裁决口径）→ 主会话独立复验 + 规格/质量合并复核 → WP3 主会话跑批 → 落账
- 落点：interpreter.py（挂起标注）/ chooser.py build_pending（透传）/ state.py PendingChoice / heuristic.py（_pick_choose 方向 + 伤害估算 + 囤能 + 牌库保护）/ experiment.py（build_agents 管道）
- 伤害估算器放独立模块（如 `agent/dsl_estimate.py`）保持 heuristic.py 聚焦
- 复跑注意：Agent 行为变更 → 事件流与 M6 基线不同属预期；确定性验收 = 新代码同种子串/并行一致

## 结果与遗留

（完工填写）
