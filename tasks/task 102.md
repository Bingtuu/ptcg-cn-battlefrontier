# task 102 — 报告层经验校准：预注册验证（validity 线）

- 日期：2026-11-02
- 分支：`task/t102-report-calibration`
- 性质：**预注册判别式验证，零行为变更**（文档 + 只读脚本 + 结果 JSON；不实现校准模块，PASS 才另开实现 task）
- 先例：task 097（M14 no-go）/ 099（标定证伪）/ 100（跨格预检）——no-go 证据合 main 的范式

## 1. 背景与动机

16 大格归因地图闭环（task 101 收口）后，加权 |Δ|≈18% 残差被定性为「策略整体质量层」。本次立项的 validity 线假设：格级 |Δ| 中存在**系统性可压缩成分**——模拟器夸大强度散布（sim 强度 SD ≈13pts vs real ≈1.4pts），报告层单调映射（dev 拟合 → val 验证）可把格级预测压回真实量程，从而在不碰 Agent/引擎的前提下提升效度。

## 2. 预检发现（探索性，先于预注册；已跑，数字可复算）

**这些数字只用于设计判别门，不作为验证结论。**

1. **v2 池格级 sim↔real 相关 ≈ 0**（m13-baseline 双轨包）：
   - development（286 场，72 格）：Pearson −0.102 / Spearman −0.111；无向 36 对：−0.064 / −0.053
   - validation（123 场）：无向 36 对：+0.142 / +0.167
2. **v1 池同样 ≈ 0**（`results/m6-calibration.db` 现场重出偏差包 `results/t102-v1-deviation/`）：72 格 Pearson +0.019 / Spearman +0.109；剔 8 低置信格（64 格）+0.032 / +0.112；无向 36 对 +0.058 / +0.160。**零信号不是 v2 池特有，是启发式自对局矩阵的跨池属性。**
3. **单调映射塌缩为常数**：dev 加权 logit 线性拟合 `logit(real)=a+b·logit(sim)` 得 a≈0.000、b≈−0.028（斜率置信区间必含 0）；等渗（PAVA，real_n 加权）几乎相同。
4. **val 外样本读数**：恒等 16.27% → logit 线性 5.58% / 等渗 5.50%，但 **flat 预测器（恒报 dev 加权均值 50.00%）本身已 5.51%**——映射的「改善」全部来自预测真实分布的平坦性，不含任何 sim 信号。

**含义**：若预注册主指标只用「val 加权 |Δ| ≤ 13%」，会被 flat 预测器平凡通过（5.5% ≪ 13%）——那是空洞胜利。因此主指标必须是**判别式**的：校准映射必须在 val 上显著优于 flat 预测器。

## 3. 预注册协议（写于验证跑批前）

### 3.1 数据

- dev = `results/m13-baseline/development/deviation.json`（72 格，权重 real_n；286 场窗口）
- val = `results/m13-baseline/validation/deviation.json`（72 格；123 场窗口）
- 限制声明（manifest 已载）：val 划分自 M13 起前瞻冻结，但真实全量聚合在 M13 前已被本项目查看——非绝对 holdout，证据强度相应降档。

### 3.2 臂

- **臂 A：logit 线性** `p̂=σ(a+b·logit(s))`，dev 加权最小二乘（权重 real_n）拟合。
- **臂 B：等渗回归**（PAVA，real_n 加权）。
- **参照**：恒等（基线）、flat（dev real_n 加权均值常数）。

### 3.3 门（全部过 = PASS；任一 FAIL = 路径关闭，按 no-go 证据处理）

| # | 门 | 判据 |
|---|---|---|
| G1（主，判别式） | 校准映射 vs flat，val 成对逐格绝对误差 | 两臂各自：均值改善 > 0.5pts 且 10k 次有放回逐格 bootstrap 的 95% CI 下界 > 0 |
| G2（次） | val 加权 \|Δ\| | 臂 A 或臂 B ≤ 13%（且不得主要靠塌缩：若 G1 FAIL 则 G2 自动无效） |
| G3（信号存在性） | dev 上 logit 线性斜率 b | b 的 95% CI 不含 0 |
| G4（护栏） | 映射结构 | 单调（递增或递减任一方向）、值域 [0,1]、纯报告层（零对局、零行为变更）；脚本可复现 |

### 3.4 判定与处置

- **PASS（意外）**：G1–G4 全过 → 另开 task 做报告层校准模块 TDD（带独立预注册）。
- **FAIL（预期）**：关闭「报告层单调校准」路径；task 文档 + 脚本 + 结果 JSON 作为 no-go 证据合入 main；STATUS 写回：v1/v2 双池格级 sim 信号 ≈ 0 定量结论 + 产品定位收窄为「对局模拟 + 决策分析」（格级胜率预测/强度排序宣称下线）。
- 不重开：MCTS 预算破例（task 097 no-go）、窄刀（088–101 全闭）、R 机制（task 093）。

## 4. 实现形式

- 脚本：`.kimi-code/t102_calibrate.py`（只读偏差包 JSON，复算预检全部数字 + 正式门）
- 结果：`results/t102-calibration.json`
- 零 `battlefrontier/`、`tests/` 变更；**不实现校准模块**

## 5. 复现

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 .kimi-code/t102_calibrate.py
```
