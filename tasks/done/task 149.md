# task 149 · 吞吐决策点 spike（BC 前置，原 spec 预占 130 重编号）

- 状态：**已收官（2026-11-18）——判决 R2 可行，R1/Rust spike 不立项**（dig：`docs/digs/2026-11-18-t149-throughput-spike.md`）
- 关联：四期 PRD §4 M16 task 149；kill criteria「R1/R2 吞吐达不到 BC 训练最低需求且 spike 估期 > 6 周」的判定数据源；Owner 已声明可接受重构

## 设计段（2026-11-18 实现期定项落笔，判据随此冻结）

- **BC 训练最低需求（定量定义，spike 判定按此口径；task 152 设计段可引用修订但须显式）**：
  - 数据面：BC 自蒸馏一轮 ≥ **1M 决策点**（锚：M12 试点 171k 决策点训出可用学生 → 6× 余量；Kaggle 先例 6,533 局 ≈ 20-40 万决策点 → 3-5× 余量）；
  - rollout 面：RL 微调一轮 ≥ **50k 局** on-policy rollout（PPO 小 batch × 迭代轮数预注册下限）；
  - 墙钟子预算：一轮「采集 + rollout」≤ **24h**（21 天成本门内划给数据产的子预算，其余给训练本身）。
- **实测口径（R2 定义）**：多进程 env pool（spawn Pool 每进程整局，现有 runner 同款纪律）+ 小网 rollout（distilled policy 双盲 mirror 局，numpy 前向）= RL 自对弈的连续产能侧；教师侧（MCTS 2×50 采集）是 task 151 一次性成本、已知 ~0.3-1s/局非瓶颈，不重复测。两档测：heuristic mirror（引擎纯开销下限锚）+ distilled mirror（policy 前向开销锚）。机器口径：22 逻辑核 workers=16（留核给系统/主进程）。
- **决策函数（预注册，三态）**：决策点日产能 ≥ **3M/天 且** 局日产能 ≥ **300k/天**（= 需求 ×10 安全余量）→ **R2 可行**（M16 保持 Python 架构）；不足 → R1 spike 估期（Rust 引擎热路径预期 10-50×，估期人力日级拆解）≤ **6 周** → **R1 spike 立项**；估期 > 6 周或不可信 → **M16 kill 如实记录**（回 M15 水平线，管线资产留档）。
- **探针实现**：`battlefrontier/runner/throughput.py`——串行采样 pass 数决策点（CountingAgent 包装 observe 精确计数）+ 并行计时 pass（复用 execute_experiment 落临时库计完成局数）；`decisions/s = games/s × decisions/game`；`bfsim probe-throughput --games N --workers W [--deck-id X | 缺省 stub]`。判定函数纯函数可单测（合成数字三态分支全覆盖）。零行为变更：探针只读测量，不落正式结果库。
- **R1 spike 预埋验收（若立项）**：现有全量测试绿 + **events_hash 跨实现逐局等价**（种子确定性红线同口径）；spike 范围仅限引擎热路径，DSL 语义/规则零变化。

## 目标

在 task 152（BC+RL 训练）任何投入之前，实测并判定 M16 架构走向：**R2（多进程 env pool + 小网 rollout，纯 Python）够不够 BC 训练的吞吐下限；不够则 R1 spike（Rust 核心 + DSL 预编译）估期是否 ≤ 6 周门**。结论二选一：R2 可行（M16 保持 Python 架构）/ R1 spike 立项（重构路线）/ 两者皆否（M16 no-go 留档，kill criteria 触发）。

## 预注册验收标准（开工时判据冻结进设计段）

1. **吞吐实测**：R2 路径（多进程 env pool + numpy 小网 rollout 前向）在单机 22 逻辑核上实测决策点/秒，按 BC 训练最低需求（task 152 设计段预注册，参考量级 = Kaggle 先例 6,533 局挖矿 + 自对弈飞轮产能）换算日产量；数字与测算过程留档可复算；
2. **判定门**：BC 训练最低需求可满足 → R2 结论落档；不可满足 → R1 spike 估期（人力日级拆解：Rust 核心范围/DSL 预编译/等价测试适配）≤ 6 周方可立项 spike，否则触发 M16 kill criteria（如实记录，回 M15 水平线）；
3. **R1 spike 若立项的验收**（预埋）：现有全量测试绿 + **events_hash 跨实现逐局等价**（种子确定性红线同口径）；spike 范围仅限引擎热路径，DSL 语义/规则零变化；
4. 纯测量/spike 性质：默认**零行为变更**；任何代码改动走 TDD + 全量绿 + ruff；CHANGELOG 记账。

## 设计段（开工时定项）

- BC 训练最低需求的定量定义（与 task 152 预注册联动，先钉需求再测供给）
- R2 方案的 env pool 设计（复用 runner 多进程纪律；并行/串行逐局一致）
- R1 spike 的范围切片（引擎热路径边界 = 哪些模块进 Rust、DSL 解释器是否预编译为字节码/查表）
- 决策记录格式：落 docs/digs/，三态结论显式（R2 可行 / R1 spike / no-go）

## 结果与遗留

**判决（2026-11-18）：R2 可行**——按预注册判定门（≥3M 决策点/天 且 ≥300k 局/天）：

- heuristic × 沙奈朵 711854 真实卡表 mirror（400 局 × 16 workers）：60.4 局/s → **5,215,360 局/天**（门槛 17×）；141.4 决策点/局（串行采样精确计数）→ **737,451,887 决策点/天**（门槛 245×）→ decide_r2 = "r2"。
- policy 纯 numpy 前向微基准（policy-m12-v2，174 维）：3.5 µs/打分/核——小网前向开销可忽略，引擎 step 主导。
- distilled 引擎臂装载即报错（「轻飘飘 不在词表」）= task 145 发现再确认，归 task 150 供给面，不构成吞吐否决。

**处置**：M16 保持 Python 架构，**R1/Rust spike 不立项**（kill criteria 吞吐项解除）；BC 路线剩余 gate = task 150（v2.x 评估器重训 AUC ≥ 0.90）。复放命令与口径见 dig；探针代码 `battlefrontier/runner/throughput.py` + `bfsim probe-throughput`（9 新测含 decide_r2 三态分支全覆盖 + 真资产微基准）。

**遗留**：实测为单卡表 mirror 口径（卡表只影响装配不影响 per-game 成本量级，决策点/局 ±30% 内不改变判定）；task 151 种群构成按 PRD v0.5（纯 MCTS 教师 + 启发式，价值网 MCTS 待 126 重验过线后增补）。
