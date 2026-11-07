# BattleFrontier（对战开拓区）

> AI 宝可梦卡牌（PTCG 简中环境）对战模拟与卡组强度测试引擎

**BattleFrontier** 让两个 AI 选手在完整的简中 PTCG 规则下自动对战，通过大规模模拟对局回答三类问题：

- **强度**：卡组 A 对抗卡组 B 的胜率是多少？（附置信区间与先后手拆分）
- **策略**：某卡组在某对阵下的最优打法是什么？（从对局决策数据中聚合产出）
- **敏感性**：换掉卡组里的几张卡，胜率变化显著吗？

> ⚠️ 边界：以上数字都是**自对局模拟结果**，不构成真实胜率预测——格级外部效度未建立是定量证实的结构事实（task 102/103）。对外引用前请对照 [claims register](docs/claims-register.md)。

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

**当前口径（2026-11-07）**：产品定位已收窄并钉死为「**对局模拟 + 决策分析工具**」——模拟胜率是**自对局结果，不构成真实胜率预测**（v1/v2 双池格级 sim↔real 相关 ≈ 0，跨池 + 跨窗 + 低混因子图稳健，task 102/103 定量关闭）；对外宣称边界见 [claims register](docs/claims-register.md)（两层宣称 + 三态复活条件 + 使用守则，报告/校准输出已内嵌限定语）。证据边界内全部路径闭环：

- **validity 线终局**（097–107）：MCTS 预算 no-go 封顶（27h/600 局）；窄刀时代收官（088–101，16 大格归因全闭环）；报告层单调校准证伪（102）；赛制混因排除（103，低混因子图 12 格 Pearson −0.010）；对齐窗重验 R3「不可验证（供给约束）」（105→107：上游 2026 年起 GHI 赛事 pairings 结构性断档，预注册 RUN 协议 + 双 sentinel 值守保留）。
- **对齐窗门槛修订**（110）：上游 data_version 4 落地 GHIJ 收割轮后供给结构性修复（窗内 221 场 intl_aligned 赛事、池内 1,492 局、周供给 ~200 局），但 Gardevoir / Charizard Pidgeot 在对齐窗零出场、判定池上限 21 对 → 原 RUN 门（≥26）数学不可达；修订为可达子池口径（判定池动态、门 = min(26,⌈0.85K⌉) = 现 18 对 n≥20 且 ≥1,000 局），105 §2 判决协议不动，附带「真实侧 = 国际线上周赛 meta」限定语。
- **引擎与观测层收官**（108）：事件序观感债修复（招式效果窗口内昏厥/拿奖事件滞后到链收尾入流，replay 抽查 20/20 四指标等价 + 排水内层帧漏洞修复）。
- **M12 残留盲区清零**（109）：use_ability / play_stadium / end_turn 三盲区预注册诊断预检全部关闭（教师强信号 lift 均 ≤ 0——use_ability 甚至 −8.5pp 反向；end_turn 与 066 低上限结论互证）。

**度量地基**：`results/m13-baseline/` 三份双轨偏差包（full/development/validation，72/72 格 `sim_failed=0`，串行=并行 100/100）；启发式加权 |Δ| 15.0%–18.1% 为**自对局结构度量**，非精度指标。全量 **1704 测试绿** + ruff 零告警；DSL 定义库 134 份（v1/v2 池零缺口）；四类 AI（启发式 / 随机 / MCTS / 蒸馏学生）+ 学得评估器与蒸馏模型资产 `models/`。

**待触发（无需人工值守）**：t105 哨兵 + cron 值守持续跑批（当前 WAIT：8/18 对 n≥20、池内 1,492 局），无向格达标（≥18 对且 ≥1,000 局）即自动出 RUN 判决（R1 解禁 / R2 钉死）；新方向立项待 Owner 拍板（候选：换卡敏感性 v2 正式资产；大项如构筑 GUI / LLM / JEV 超出当前证据边界）。

**历史脉络（当前口径以上段为准）**：一期 M1–M6（2026-10-03）；二期 M7–M10 收官（2026-10-05，MCTS 落地 + M10 加权 |Δ| 9.7%）；其后引擎性能优化（MCTS 成本 −38.5%）、全库 code review 闭环、MCTS 信息泄漏修复与决策分析上线（task 037–042）；方向 B 启发式参数自调优收官（045–047）；**三期 M11–M12 收官**（2026-10-21）：M11 学得评估器双锚达成，M12 蒸馏终判部分达成收口（D3-7，学生定位「分钟级粗筛」）+ 063/064 promote 空场判平修复 + 065/066 盲区归因与处置证伪 + 067 复校准地基 9.715%；**卡池 v2 锁定**（068，WUR 覆盖 80.5%）+ 069/070/071 引擎扩展两批与 DSL 缺口清零（134 份）；M13 校准地基（094–096）→ M14 结构归因 no-go（097）→ 098–101 决策差异挖掘与窄刀证伪收官 → 102/103 格级外部效度零信号钉死（2026-11-02/03）→ 104 claims register → 105–107 对齐窗线终局 → 108 事件序观感债修复 → 109 M12 盲区触发式闭环 → 110 对齐窗门槛修订（上游供给修复后，2026-11-07）。详细逐日进展见 [STATUS.md](STATUS.md)。

## ⚖️ 合规声明

本项目与 Nintendo、The Pokémon Company、宝可梦（上海）**无任何隶属或背书关系**。卡面文本与卡牌数据版权归宝可梦（上海）/ The Pokémon Company 所有；本项目不采集、不存储、不分发卡图与卡牌数据，仅限本地研究与工具自用。

## 📄 License

代码与文档基于 MIT License 发布（卡牌数据版权见上方声明，不在许可范围内）。
