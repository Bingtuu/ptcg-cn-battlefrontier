# task 150 过线判读 — v2.x 评估器重训（2026-11-18）

## 判决：FAIL（预注册线 v2.x AUC ≥ 0.90）——但产出关键归因结论

| 资产 | v2.x 对决（711854×676344，20 局 seed 800000..800019，n=1782） | v1 对决（644634×650353，n=1276，对照臂） |
|---|---|---|
| eval-linear-v1（v1 池训练） | **0.6755**（复现 task 145 读数 0.676，协议声实） | 0.9718 |
| **eval-linear-v2（本任务：v2.x 池 54,000 局 / 4,073,978 行重训）** | **0.6743** | 0.9659 |

训练侧健康：λ=100 验证 MSE 0.1995 vs 常数基线 0.2500（显著优于基线、无死维度警戒、零失败局）——**模型学到了 v2.x 分布内可学的一切，但 AUC 与 v1 资产统计等价（差 0.001）**。

## 归因（单变量变更实验的干净结论）

训练分布 = 评估分布（同池同机制），重训后零提升 → **瓶颈不是数据分布，是 30 维特征层的表达力**：v2.x 新机制状态（136–139 批 lock_play / status_immunity / 工具交互 / 赛场阻断等）在纯 VisibleGameState 30 维下不可见。旁证：同特征在 v1 对决仍 0.966——特征对 v1 时代动态有效，对 v2.x 关键状态失明。

（如实记录：设计段预注册的归因推断句「<0.90 则问题在数据分布/标签而非特征层」被本实验结果否定——in-distribution 重训无效排除了数据分布，归因落在特征层。）

## 处置（预注册 FAIL 条款 = M16 BC 停损评审，Owner 裁决）

1. **选项 A · 特征 v3 立项**（建议）：评估器特征扩维——卡身份 one-hot / 弃牌构成等（task 062 policy v2 已证明 +112 维卡身份特征把 use_ability 一致率从 0.009% 救到 20.9%，同思路移植评估器）；过线后 task 150 重判（重新预注册）。
2. **选项 B · 教师构成去评估器化**：BC 教师改纯 MCTS 全 rollout（弃 eval_cutoff，成本 ×N）或纯启发式教师——BC 上限受损但绕过本门（不推荐，违背 M15 gate 动机）。
3. **选项 C · M16 延期**：BC 线挂起，回 M15 水平线，资产留档。

## 口径与复放

- 采集：`bfsim collect-features --pool config/target-pool.v2.yml --games-per-pair 1200 --seed-start 960000 --out results/m11-v2x-data --workers 16`（45 对 × 1200 = 54,000 局零失败）
- 训练：`bfsim train-eval --data results/m11-v2x-data --pool config/target-pool.v2.yml --out models/eval-linear-v2.json`（超参/λ/split 全沿用 v1 钉死口径）
- 判读：`.kimi-code/t150_eval_gate.py <model.json>`（t145 协议参数化版，冻结脚本不动；exit 0 = PASS）
- 资产：`models/eval-linear-v2.json`（format 同 bf-linear-eval-v1，v1 资产保持可装载）——**未过线但如实入库落账**（训练健康、v1 对决 0.966，非废物资产；value_guide/MCTS cutoff 在 v1 底板仍可用 v1 资产，v2.x 底板两资产均不可用）。
