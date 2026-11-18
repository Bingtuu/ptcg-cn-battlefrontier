# task 149 吞吐 spike 判决 — BC 训练最低需求 vs R2 实测产能（2026-11-18）

## 判决：R2 可行（M16 保持 Python 架构，R1/Rust spike 不立项）

按 task 149 设计段预注册判定门（需求 = 1M 决策点/轮 + 50k 局 rollout/轮，墙钟子预算 24h；门槛 = 日产能 ≥3M 决策点 且 ≥300k 局，×10 余量）：

| 臂 | 实测 | 门槛 | 判定 |
|---|---|---|---|
| heuristic × 沙奈朵 711854 真实卡表 mirror（400 局 × workers=16） | 60.4 局/s（16.6ms/局）→ **5,215,360 局/天**；141.4 决策点/局（串行采样精确计数）→ **737,451,887 决策点/天** | 300k 局/天 ∧ 3M 决策点/天 | **r2**（局 17× / 决策点 245×） |
| policy 纯 numpy 前向微基准（policy-m12-v2，174 维） | 3.5 µs/打分/核 → 理论 289,744 打分/s/核 | — | 小网前向开销可忽略（引擎 step 主导） |
| distilled 引擎臂（policy-m12-v2 × v2.x 卡表） | **装载即报错**：「卡名 '轻飘飘' 不在词表」 | — | 非吞吐项——task 145 发现再确认（蒸馏 v2 词表锚定 v1 池，v2.x 不可用），属 task 150 开工门供给面，不构成本 spike 的吞吐否决 |

## 实测口径（可复放）

- 探针：`bfsim probe-throughput --agent heuristic --games 400 --workers 16 --deck-id mik_moe:711854 --seed-start 940000`（代码 `battlefrontier/runner/throughput.py`，判据函数 decide_r2 预注册冻结）。
- R2 定义兑现：多进程 env pool（spawn Pool 每进程整局）+ 小网 rollout 口径；机器 22 逻辑核 workers=16。
- 教师侧（MCTS 2×50 采集）非瓶颈（task 151 一次性成本，~0.3-1s/局），按设计段不测。

## 结论与处置

1. **R2 可行**：即使在最保守的 engine-only（heuristic）臂下，产能也是门槛的 17×（局）/245×（决策点）——BC 数据飞轮（task 151）与 RL rollout（task 152）的 Python 架构产能充足，**R1/Rust spike 不立项**（M16 kill criteria 的吞吐项解除）。
2. **附确认**：BC 路线剩余 gate = task 150（v2.x 评估器重训 AUC ≥ 0.90）；蒸馏 policy v2 不可用再确认一次（本 spike 臂 2），task 151 种群构成需按 PRD v0.5（纯 MCTS 教师 + 启发式，价值网 MCTS 待 126 重验）。
3. **局限**：实测为单卡表 mirror 口径；多卡表轮换产能同阶（卡表只影响装配，不影响 per-game 成本量级）。决策点/局 = 141（沙奈朵 mirror 采样 20 局），不同卡表 ±30% 内不改变判定。
