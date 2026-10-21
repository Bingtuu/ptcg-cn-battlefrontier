# task 060 · M12 WP4 双锚验收 + 全 matrix 分钟级口径

- 状态：✅ 完成（2026-10-19 出数；锚 2 未达 → task 061 诊断 → task 062 处置，
  M12 终判随 task 062 WP4 呈报）
- 关联：task 056 拍板定案；task 058 WP2（训练管线）；task 059 WP3
  （distilled Agent 接入）；PRD §3.2 M12 验收口径
- 前置：task 057 试点采集验收 + task 058/059 完成复验 + 试点数据训出
  正式学生资产（bf-distilled-policy-v1，进版本控制 D3-4）

## 验收锚点（PRD §3.2 + task 056 呈报口径）

1. **锚 1 决策一致率**：学生 vs 教师（同局面异种子），相对口径——
   先例：M11 实测教师异种子自一致率天花板 0.40–0.46，绝对阈值不可达；
   任务书定稿阈值 = 试点实测后报呈。工具链复用 `runner/agreement.py`
   （task 059 加 distilled 学生分支）。**口径注意**：M11 分母 v1 = main
   阶段 attack/play_trainer/end_turn 三类；M12 行为克隆覆盖全 15 类
   action_kind → 锚 1 主口径沿用 v1 分母（与 M11 数字可比），全类别
   一致率作附录观察
2. **锚 2 matrix 复校准**：学生双侧（type: distilled）全 36 配对 matrix
   跑批 → `bfsim calibration` 加权 |Δ| ≤ 9.7%（不劣于 M10 增强版）
3. **锚 3 分钟级口径**：全 matrix 学生口径跑批墙钟达分钟级
   （对照：教师 MCTS 口径 ~10h 量级 → 学生目标 < 30 min）

## 范围

0. **前置：train_policy 向量化**（task 058 遗留性能风险坐实：逐样本构图
   4.18s/epoch@984 点 → 试点 20 万点×100 epochs 外推 23h，不可接受；
   拍平大张量 + 分段 logsumexp 向量化，数学语义等价 atol 1e-5 测试钉死，
   目标 <0.2s/epoch——**已完成**（2026-10-18）：实测 0.216s/epoch（含
   拍平预处理，提速 ~20×/边际 ~200×），等价性测试含 loss ≤1e-5 + 梯度
   allclose(atol 1e-5) + argmax 精确一致；自适应线程数（每 5 万拍平行
   1 线程），全量 1304 绿 + ruff 零告警）
1. 试点数据（task 057，1008 局快照）正式训练学生资产 → meta 回显
   （种子/数据版本/码版本/超参/holdout 指标），资产进版本控制
   （models/policy-m12-v1.json，D3-4）
2. 锚 1：**离线快照重放口径**（无需新采集）——快照行含完整 GameState
   dump + 教师 chosen Action（task 052 产线），离线重建 engine state →
   枚举合法行动 → 学生 numpy 前向掩码 argmax vs 教师 chosen = 一致率；
   天花板 = 教师异种子在同局面重搜的自一致率（同套重建工具 + MCTS
   异种子重放，M11 锚 1 工具链复用）。M11 实测天花板 0.40–0.46 作参考带
3. 锚 2+3：matrix 实验定义（学生双侧）跑批 + calibration 报告 + 墙钟实测
4. M12 里程碑验收结论呈报（**用户拍板点，不得自行越过**）

## 验收标准

1. 三锚全过（锚 1 阈值呈报拍板后核定；锚 2 ≤ 9.7%；锚 3 分钟级实测落档）
2. 种子确定性：学生口径 matrix 同种子区间小样重跑逐局一致
3. 全量 pytest 绿 + ruff 零告警
4. STATUS.md / AGENTS.md 落账 + 归档 + M12 验收结论呈报

## 结果与遗留

- **正式训练**：171219 点 / 1005 局（split_seed 20261018），100 epochs /
  hidden 64，764s；holdout argmax 0.4222；double-run 逐字节全等；资产
  `models/policy-m12-v1.json` 入库（8439f1e，D3-4）
- **锚 1 ✅（相对口径）**：学生 0.3652（21881/59919）/ 天花板 0.4115 →
  相对 88.8% ≥ 0.85（M11 判例）
- **锚 2 ❌**：加权 |Δ| 16.7% > 9.7%（12 格 |Δ|≥20% 极化形态）→ task 061
  根因诊断（特征盲区，use_ability 不可分 0.009%）→ task 062 特征 v2 处置
- **锚 3 ✅**：18000 局 17.3min（教师口径 ~9h → ~30×）
- **确定性 ✅**：det-check 10 局串/并行 events_hash 逐局全等；失败 2 局
  同一已知形态（梦幻ex copy_attack 嵌套）
- 遗留：锚 2 处置经 task 061/062 闭环，M12 终判随 task 062 WP4 呈报
