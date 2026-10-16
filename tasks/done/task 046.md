# task 046 · 正式粗扫跑批 + holdout 验证 + 复校准 + 回写裁决

- 状态：完成（2026-10-11）
- 关联：方向 B 设计文档 `docs/superpowers/specs/2026-10-11-heuristic-tuning-design.md`（D-T1~T4）§6 验收 / §7 拆解；前序 task 045（tune 子包）

## 目标

task 045 设施的正式生产使用：全量 36 配对（训练 24 + holdout 12）坐标下降粗扫（~36 万局），
产出维度敏感性报告；top-3 候选 500 局/对复评 + 双门槛 holdout 验证；最优参数全 matrix
复校准对比 M6/M10 基线；默认参数回写裁决呈报（用户裁决，工具不自动执行）。

## 设计决议

- **D-046-1 双门槛口径**（2026-10-11 用户拍板，关闭设计文档 §8 开放项）：候选采纳回写须
  同时满足——①复评训练集胜率 > 0.5（提升，严格）；②holdout 集胜率 ≥ 0.5（不退步，含平）。
  均指「候选参数（侧A）vs 默认参数（侧B）」500 局/对复评口径。双门槛过线者中最终采纳 =
  holdout 胜率最高者（tie → 训练胜率 → 轨迹先见序）；零过线则结论「默认参数即局部最优」，
  如实落账不强行回写。
- **D-046-2 轨迹重建式验证**：tune-verify 不新增 summary 文件——从轨迹 JSONL 逐行重建
  搜索过程（含采纳路径与敏感性记录），重建逻辑内嵌采纳规则一致性校验（重建不出 = 轨迹
  被篡改/损坏，显式报错不猜）。轨迹 JSONL 维持唯一锚点定位（D-T4 不变）。
- **D-046-3 划分种子**：split_seed=20261011（首个通过分层覆盖校验的候选种子，holdout 12 对
  9 archetype 双侧覆盖）；调优定义 `experiments/tune-full.example.yml`。
- **D-046-4 复评局数**：top-3 复评 500 局/对（设计文档 §3），CRN 种子区间同一配对不变
  （games 100→500 为区间前缀扩展，前 100 局种子重合属预期）。

## 验收标准（测试清单）

1. **重建**：`reconstruct_search` 对合法轨迹重建出与搜索器等价的采纳路径/trials；
   篡改行（跳维/多维变更/采纳违反噪声门槛）显式报错（不猜）。
2. **top-3**：`top_candidates` 从重建结果取采纳路径 waypoint 按训练 fitness 降序 top-3
   （含去重——同向量重复采纳只计一次）。
3. **双门槛**：`gate_verdict` 纯函数——训练 >0.5 且 holdout ≥0.5 才过线；选择规则
   （holdout 降序 → 训练降序 → 先见序）逐项单测；零过线输出「默认即局部最优」结论。
4. **敏感性报告**：`sensitivity_rows` 按维聚合 trials（每维各网格点最佳 Δfitness + 试投
   轮次），输出序确定。
5. **CLI**：`bfsim tune-verify <defn> [--trajectory] [--games 500] [--workers N]`
   端到端冒烟（小预算 stub 评估注入，不打真局）；判定结论 + 敏感性表 + 结果 JSON 落盘。
6. **正式跑批**：`bfsim tune experiments/tune-full.example.yml --workers 16` 完成，
   轨迹行数 = 1 + 实际评估数，无失败局异常暴涨（失败率量级对齐 M6 0.067% 口径）。
7. **复校准**：采纳参数（若过线）全 matrix 36 对 × 500 局落库 + `bfsim calibration`
   出表，加权 |Δ| / CI 覆盖率对比 M6（13.2%）/ M10 增强版（9.7%）如实记录（不设死阈值）。
8. 全量 pytest 绿 + ruff 零告警；搜索轨迹确定性复跑对拍（同定义重跑轨迹逐行全等，
   wall_seconds 除外）——抽样复跑前 3 次评估口径。

## 实现要点

- WP1（代码，TDD）：`battlefrontier/tune/verify.py`——`reconstruct_search` /
  `top_candidates` / `gate_verdict` / `sensitivity_rows` / `run_verify`（复用
  fitness.prepare_pairs + execute_plan，holdout 对也走 CRN 种子派生）；CLI 挂
  `tune-verify` 子命令。
- WP2（跑批，与 WP1 并行）：正式粗扫后台跑批 ~36 万局 @16 workers（预算 ≈2h，M6 吞吐外推）。
- WP3（复评）：tune-verify 正式跑（top-3 × 36 对 × 500 局 ≈ 54,000 局 ≈ 20min）。
- WP4（复校准）：过线参数 matrix 跑批（36×500 = 18,000 局 ≈ 7min）+ 偏差表对比。
- WP5（收尾）：回写裁决呈报（参数差异清单 + 双门槛证据）；STATUS.md 落账；task 档归档。

## 结果与遗留

### 进行中记录

- **WP1 主会话复验结论（批准）**：verify.py 重建逻辑与 `search.coordinate_descent` 逐点对齐（settle 顺序 / 扫维序校验 / 严格大于门槛 / 行序首个最优 tie-break），真实轨迹（96 行）重建结果与跑批 CLI 输出逐字段吻合；1153 绿 + ruff 零告警主会话独立复跑确认。冻结约束守住（defn/fitness/search/space/trajectory 零改动，git diff 实证）。
  - **裁决记录（接受的偏差 1 项）**：`select_final` 第三级 tie-break 实为「搜索 fitness 降序」（candidate_id 序 = top_candidates 排序后序），非任务书字面的「轨迹先见序」——影响仅限 holdout+训练胜率精确相等的极端 tie（500×12 局 4 位小数，概率可忽略），本次跑批仅 1 候选不触发。接纳不返工。
  - 子代理上报偏离 1 项（execute 默认 None 运行时解析以保持可注入性）——核实语义等价，批准。
- **WP2 正式粗扫（results/tune-tune-full.jsonl，96 评估 ≈ 23 万局，16 workers 25m01s，零失败暴涨）**：基线 fitness 0.4780 → 最优 0.4946（Δ+1.66pts），2 轮 no_improvement 停；唯一采纳 `deck_low_threshold 6→12`（牌库保护阈值上调 = 更早启动防抽空）。
- **WP3 复评（results/tune-tune-full-verify.json，18,000 局，75s）**：候选 #1 训练 0.5055 / holdout 0.5562 —— **D-046-1 双门槛过线，判定采纳**。holdout 提升幅度（+5.6pts vs 默认镜像基线 0.5）大于训练集（+0.6pts 复评口径），方向一致非过拟合形态。
- **WP3 敏感性重大发现**：w_prize_diff / w_board / w_hand / w_energy_ready / w_deck 五维全部网格点 Δ 恒为 0（两轮 n=2 全零）——评估函数五因子权重**不参与任何决策路径**（决策为规则式，evaluate 仅供报告/测试，task 018 既有口径），当前架构下为死维度；未来 MCTS rollout 剪枝/学习类 Agent 接入评估函数后才成为活参数。活维度中 w_hp(0.0) Δ+0.39pts、max_bench_setup(2) Δ+0.27pts 为正但未过 1.0pts 门槛。
- **WP4 复校准（results/t046-recalibration.db，36 对 × 500 局双侧采纳参数，5m34s 零失败；种子区间与 M6/M9 逐格对齐配对可比）**：加权平均 |Δ| **15.0%（M9 现行基线）→ 16.1%**，CI 覆盖率 13.9% 持平（M6 基线 13.2%/19.4%）；逐格平均绝对移动 1.84pts，最大摆动 赛富豪×多龙巴鲁托 -6.3pts。**方向恶化**——设计文档 §8 预告的「fitness 对默认对手依赖」风险坐实：调优目标 = 打败默认启发式，与贴合人类 meta 有偏。
- **确定性抽验（验收 8）**：训练集前两配对子集重跑（`results/t046-det-check.yml`/.jsonl，跑完即弃不入库），行 0..5（基线 + 首 sweep，采纳决策前向量序列必然一致）× 2 配对与正式轨迹逐字段全等。

### 最终结论与裁决

- **D-046-5 回写裁决（2026-10-11 用户拍板）：折中——存档不回写**。候选 deck_low_threshold 6→12 双门槛过线（训练 0.5055 / holdout 0.5562）但复校准加权 |Δ| 恶化（15.0%→16.1%）；默认参数维持 M6–M10 基线锚点不变，调优参数档存档于 `experiments/t046-recalibration.example.yml` + `results/tune-tune-full-verify.json`，供对抗强度实验直接选用。
- **验收 8 条全过**：1153 绿（1117+36）+ ruff 零告警 / 重建完整性校验 / top-3 / 双门槛 / 敏感性 / CLI e2e / 三批跑批零异常（粗扫 96 评估零失败暴涨、复评 18,000 局、复校准 18,000 局）/ 确定性抽验全等。
- **遗留**：①task 047（(1+λ)-ES 精修）触发条件不成立——本轮零维间交互证据（仅 1 维采纳、第 2 轮整轮无改进），不立项；②5 个评估函数死维度（w_prize_diff/w_board/w_hand/w_energy_ready/w_deck 全网格 Δ 恒零）——若未来接入 MCTS rollout 评估或学习类 Agent 则转活，届时重进搜索空间；卡池 v2 落地后调优需复跑（设计文档 §8 既有口径）；③卡池 v2 立项候选（db 前置调研数据已就绪，task 044）；④方向 A（学习类 Agent）待用户拍板。
