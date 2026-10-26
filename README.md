# BattleFrontier（对战开拓区）

> AI 宝可梦卡牌（PTCG 简中环境）对战模拟与卡组强度测试引擎

**BattleFrontier** 让两个 AI 选手在完整的简中 PTCG 规则下自动对战，通过大规模模拟对局回答三类问题：

- **强度**：卡组 A 对抗卡组 B 的胜率是多少？（附置信区间与先后手拆分）
- **策略**：某卡组在某对阵下的最优打法是什么？（从对局决策数据中聚合产出）
- **敏感性**：换掉卡组里的几张卡，胜率变化显著吗？

## 快速开始

### 1. 安装

要求 Python 3.12+：

```bash
git clone <本仓库地址>
cd Pokebattle
pip install -e .
```

安装后获得命令行工具 `bfsim`。

### 2. 准备卡牌数据

本项目不自带卡牌数据，需要搭配数据项目 [ptcg-cn-db](https://github.com/Bingtuu/ptcg-cn-db) 使用：

```bash
# 安装数据层 SDK（指向你本机的 ptcg-cn-db 检出）
pip install -e "C:/path/to/ptcg-cn-db"

# 复制配置模板，填写本机的卡牌数据库路径
cp config/battlefrontier.example.yml config/battlefrontier.local.yml
```

`battlefrontier.local.yml` 已被 gitignore，支持 SQLite 直读或 JSONL 导出目录两种数据源。

### 3. 跑第一个实验

实验用一个 YAML 文件定义——对阵双方、AI 类型、局数、随机种子：

```yaml
# my-first-match.yml
name: my-first-match
games: 100            # 对局数
seed_start: 1000      # 随机种子起点（同种子可完整复现每一局）
decks:
  a: {source: db, deck_id: "mik_moe:644634"}   # 数据层中的赛事卡组 id
  b: {source: db, deck_id: "mik_moe:650353"}
agents:
  a: {type: heuristic}   # 启发式 AI（内置）
  b: {type: random}      # 随机 AI（内置，常用作对照）
  # 也可用 MCTS：{type: mcts, params: {worlds: 2, iterations: 50}}
  # （多世界 determinized UCT；迭代预算而非墙钟，同种子仍可复现——
  #   注意单局成本约两分钟/进程级，适合定点分析而非大批量）
  # 或蒸馏策略学生：{type: distilled, params: {policy_path: models/policy-m12-v2.json}}
  # （MCTS 行为蒸馏产物，~0.06s/局，定位「分钟级粗筛」而非精排）
```

运行（`--workers` 开启多进程并行，结果与串行逐局一致）：

```bash
bfsim run my-first-match.yml --workers 4
```

```
实验 #1「my-first-match」完成：100 局 A胜 65 / B胜 35 / 平 0 / 失败 0（结果库 results/battlefrontier-results.db）
数据版本 2026-07-16 (user_version=13)；种子区间 1000..1099
```

更多示例见 `experiments/` 目录。

### 4. 查看报告

```bash
bfsim report 1              # 1 = 实验 id（run 完成时会打印）
bfsim report 1 --decisions  # 追加「关键决策聚合」分节：每张卡的选择分布与对应胜率
bfsim report 1 --mcts-consider  # 追加 MCTS 决策分析：行动类别访问份额 / 高熵决策点 / 置信×胜率
```

```
实验 #1「my-first-match」胜率报告
meta：种子区间 1000..1099 / 代码 d084e13 / 数据 2026-07-16 / 局数 100
完成 100 局（决定局 100，平 0，失败 0），平均回合 10.4
A 胜 65 / B 胜 35 —— A 胜率 65.0%（Wilson 95% CI 55.3%..73.6%，分母=决定局）
先攻时 A 胜率 70.7%（CI 57.7%..81.5%）
后攻时 A 胜率 61.0%（CI 44.5%..75.4%）
```

### 5. 换卡敏感性分析

在实验定义里加 `variants`，一次跑出 baseline 与若干变体（同种子区间配对可比）：

```yaml
variants:
  # 对照组：A 方 2 反击捕捉器 → 2 巢穴球（卡组保持 60 张）
  - name: swap-catcher-to-nestball
    swaps:
      - {side: a, out: 反击捕捉器, out_count: 2, in: 巢穴球, in_count: 2}
```

```bash
bfsim run with-variants.yml --workers 4        # 自动依次跑 baseline + 各变体
bfsim sensitivity 1 2                          # baseline vs 变体并排对比
```

报告给出每个变体的胜率变化（ΔWR）、95% 置信区间与显著性检验（两比例 z 检验）。

### 6. matchup 矩阵与校准（M6）

实验定义改用 `matrix` 段，即可对卡组池自动展开全部无向配对（镜像不打）：

```yaml
# my-matrix.yml
name: my-matrix
seed_start: 100000
matrix:
  pool: config/target-pool.v1.yml   # 卡组池（9 套 → 36 个配对）
  games_per_pair: 500               # 每配对局数
agents:
  a: {type: heuristic}
  b: {type: heuristic}
```

```bash
bfsim run my-matrix.yml --workers 8         # 自动逐配对跑批，统一分组落库
bfsim calibration my-matrix.yml             # 模拟 vs 真实赛事 matchup 偏差表
```

偏差表逐格给出模拟胜率（含置信区间）与真实赛事胜率的差值 Δ，按 |Δ| 降序，并附加权平均 |Δ| 等汇总——用于校准模拟与真实环境的偏差。

### 7. 启发式参数自调优

`bfsim tune` 对启发式 AI 的决策参数（评分权重 / 决策开关）做坐标下降搜索：候选参数 vs 默认参数在训练对阵集上配对对局，逐维采纳显著提升（>噪声门槛）的取值：

```bash
bfsim tune experiments/tune-smoke.example.yml --workers 4
```

评估全程走与 `bfsim run` 相同的确定性路径（公共随机数种子协议，跨候选共享种子区间降方差）；搜索过程不产生正式结果，轨迹逐次评估落 `results/tune-<名>.jsonl`（含采纳历史与逐维敏感性）。搜索到的参数是否回写为默认值需人工裁决，不在工具内自动执行。

### 8. 校验卡牌定义

每张有效果的卡牌由 `cards/` 下一个 YAML 文件定义（引擎不认识任何具体卡牌，全部行为由数据驱动）。新增或修改卡牌定义后校验：

```bash
bfsim dsl-check cards/博士的研究.yml            # 结构与词法校验
bfsim dsl-check cards/*.yml --db <卡牌数据库>   # 追加校验：卡牌存在、文本一致、赛制合法
```

## 设计理念

- **卡牌效果即数据**：每张卡做什么全部写在 YAML 里，由解释器执行；规则引擎只负责回合流程、伤害、胜负等骨架，对卡牌内容零硬编码。
- **完全可复现**：所有随机（洗牌、掷币、抽牌）走单一随机源——同一个实验定义 + 同一段种子，重跑结果逐局一致，并行与串行一致。
- **AI 接口统一**：`observe(可见状态, 合法行动) -> 行动`。合法行动由引擎枚举，AI 永远不会违规操作；启发式、蒙特卡洛树搜索（MCTS）、MCTS 行为蒸馏学生（distilled，均已实现）、强化学习（远期）可互换、可混编对照。
- **结果独立存放**：模拟结果写入独立的 SQLite 结果库，卡牌数据库始终只读。

## 项目状态

一期里程碑 M1–M6 全部完成（2026-10-03）；二期 M7–M10 全部收官（2026-10-05）——MCTS（多世界 determinized UCT）落地并经预算标定（标准档 2×50），M10 校准复核达成：MCTS 增强版偏差表加权 |Δ| 9.7%（M6 基线 13.2%），|Δ|≥25% 大偏差格归因全闭环（实证「策略深度主导」，沙奈朵格双侧 MCTS vs 真实 65.1% 命中）。其后（2026-10-05~07）：引擎性能优化（MCTS 成本 -38.5%，行为零变化）；全库 code review（0 Critical / 11 Important）并全部修复闭环——含 MCTS 信息泄漏修复（带冻结集的部分 determinize）与修复后复核（泄漏贡献噪声级，归因结论更硬）；MCTS 决策分析上线（根节点访问分布导出 + `--mcts-consider` 报告）。其后（2026-10-07~11）：历史日期勘误专项（以 git 为准修正文档错位日期）；苍响格小样本复核（EN 侧数据供给已封顶，样本量不可增长）+ 偏差表低置信标注（真实样本 n<100 格标 ⚠低置信）；**方向 B 启发式参数自调优收官**（task 045 tune 子包 + 坐标下降 + `bfsim tune`；task 046 正式跑批 + `bfsim tune-verify` 双门槛 holdout 验证——唯一采纳 deck_low_threshold 6→12 过线但复校准 |Δ| 恶化，用户裁决折中存档不回写，参数档见 `experiments/t046-recalibration.example.yml`）。**方向 A（学习类 Agent）三期 PRD 已批准**（2026-10-16：[三期 PRD](docs/superpowers/specs/2026-10-16-phase3-prd-design.md)——M11 学得评估器接 MCTS rollout 先行 → M12 MCTS 行为蒸馏主线，目标为 MCTS 口径例行化而非超人强度；[可行性报告](docs/superpowers/specs/2026-10-16-learning-agent-feasibility.md)）。**三期 M11–M12 收官**（2026-10-21）：M11 学得评估器接 MCTS rollout 双锚达成（决策一致率相对教师天花板口径 100.2%；锚 2 按同预算净效应口径达成）；M12 MCTS 行为蒸馏终判 = 部分达成收口（D3-7）——锚 1 一致率 ✅（相对天花板 88.8%）、锚 3 ✅（蒸馏学生全 matrix 18000 局仅 7.4min，教师口径 ~9h → 73×）、锚 2 过第一门槛（学生口径加权 |Δ| 12.5% ≤ 启发式基线 13.2%）；蒸馏学生正式定位「分钟级粗筛」（跨配对保序实证不成立，精排/深挖仍归 MCTS）。其后（2026-10-21）：引擎侧对局形态诊断（task 063）坐实引擎 bug「跨扫描全场清空漏判负」（promote 空场误判平，影响面 m9 1.4% / v2 0.5% 局），task 064 修复收官（昏厥结算点立即判负 + 四组单测 + 附录 A 决议已核销）。其后（同日）：task 065 残留盲区归因（锚 2 瓶颈实证在决策「质」非机制「量」）+ task 066 零采集重加权处置两轮实证证伪（剂量-响应三点全单调，|Δ| 12.5%→15.9%→18.6% 随机制量拉回而单调恶化），用户拍板维持 v2 基线收口、B 特征 v3 不立项。已可用：完整规则引擎、卡牌效果定义库（101 份定义，覆盖当前竞技环境 9 套主流卡组池）、启发式 / 随机 / MCTS / 蒸馏策略四类 AI（附学得评估器与蒸馏学生模型资产 `models/`）、启发式参数自调优、批量实验运行器（含 matchup 矩阵模式）、胜率/决策/敏感性/MCTS 决策分析报告与模拟 vs 真实赛事校准偏差表（1404 项测试绿）。详细进展见 [STATUS.md](STATUS.md)，设计文档见 [一期 PRD](docs/superpowers/specs/2026-08-25-battlefrontier-prd-design.md) 与 [二期 PRD](docs/superpowers/specs/2026-10-03-phase2-prd-design.md)，规则依据见 [rules-manual](docs/rules-manual.md)（简中官方规则整理）。

## ⚖️ 合规声明

本项目与 Nintendo、The Pokémon Company、宝可梦（上海）**无任何隶属或背书关系**。卡面文本与卡牌数据版权归宝可梦（上海）/ The Pokémon Company 所有；本项目不采集、不存储、不分发卡图与卡牌数据，仅限本地研究与工具自用。

## 📄 License

代码与文档基于 MIT License 发布（卡牌数据版权见上方声明，不在许可范围内）。
