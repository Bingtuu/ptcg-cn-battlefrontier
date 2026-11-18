# task 127 · Elo 联赛基础设施

- 状态：**已收官（2026-11-18）**——TDD 全程（RED→GREEN 逐环），31 新测 + 全量 2017 绿 + ruff 零告警；归档 commit 见 git log
- 关联：四期 PRD §3 M15 任务拆分 + **v0.5 修订**；M16 评估面前置（task 152 提升门依赖）；**估计子纪律（task 148 教训）：评级用 BT-MLE（Bradley-Terry MLE），禁用固定大步长顺序 Elo**（K=32 实证未收敛至自身数据的 BT-MLE，预注册修正条款）

## 目标

建 agent 种群联赛设施：agent 种群注册表（YAML）+ 成对对战调度（CRN 种子纪律）+ BT-MLE 评级计算 + `bfsim league` 报告。定位 = BC 路线（M16）的评估面前置：task 152 提升门（混合栈 vs 启发式净胜 CI / vs 纯 MCTS 2×50 教师基线中位 Elo 差）在本设施上评测。~~评测面替换口径：task 126 净效应门是否改用联赛——~~ task 126 已 no-go 归档，该拍板项随路线关闭消除。

## 验收标准（测试清单）

1. **注册表**：YAML 定义 agent 种群（启发式参数档 / MCTS 预算档 / value_guide 开关 / 蒸馏学生 policy 资产），schema 校验；非法引用（未知 agent 类型/缺资产文件）报清晰错误；
2. **确定性**：同注册表 + 同种子区间重跑，Elo 序一致（全序或并列处理显式定义）；逐局结果可复算（CRN 成对调度复用 task 117/124 口径）；
3. **计算正确性**：Elo/TrueSkill 实现带单测（已知对局序列的期望分值手算复现；K 因子/初值/场次数加权写进 meta）；**评级主估计子 = BT-MLE**（Bradley-Terry MLE，确定性），任何顺序 Elo 只可作对照臂、不得作默认输出（task 148 预注册修正条款）；
4. **报告**：`bfsim league` 输出排序表 + 成对净胜率矩阵 + CI + 限定语头注（自对局先验）；meta 回显注册表 hash/种子/版本；
5. 全量 pytest 绿 + ruff 零告警；既有行为零变化（纯新增实验/报告层）；CHANGELOG Unreleased 记账。

## 设计段（2026-11-18 实现期定项落笔，判据随此冻结）

- **模块切分**：`battlefrontier/runner/league.py` = 注册表 schema（`LeagueDef`）+ `plan_cells` 纯规划 + `run_league` 执行编排；`battlefrontier/report/league.py` = `bt_mle` 评级 + `collect_league_games` + `league_report`。CLI 增 `bfsim league`（仿 `swap-search` 注册/分发模式，模块内延迟 import）。
- **注册表 yml**：`name / seed_start / seed_stride / games_per_cell / decks[](复用 DeckSourceCfg) / agents[]（id + 复用 AgentCfg——type/params 白名单「不猜」校验直接继承）`。校验：≥2 agents 且 id 唯一；≥1 deck；`seed_stride ≥ games_per_cell`（否则显式报错）。
- **细胞规划（plan_cells，纯函数）**：无序 agent 对（注册表序）× decks（列表序）；每对每 deck 两个实验——(a=i,b=j) 与 (a=j,b=i)，**同种子区间** `[seed_start + k·stride, +games)`（k = 无序对序；ab/ba 共享区间 = CRN 双向配对，先手偏差在聚合层对消）；卡组 mirror（双方同一 deck 源）= 纯 agent 强度对比，deck 方差在配对内归零。
- **执行（run_league）**：逐细胞 `prepare_experiment` + `execute_experiment`（全量复用 runner：多进程/串行逐局一致、增量落库、失败局落 error 继续）。实验名 `f"{league}-c{k:03d}-{ab|ba}"`，`group_name=league 名`；`definition_yaml` = 细胞 ExperimentDef dump + league 元段（`league.agents.a/b` = 注册表 id、`deck_index`、`registry_sha256`）——报告层按 group_name 回收时解析元段还原 agent 身份（games 表无 agent 列，不改 schema）。
- **评级（bt_mle）**：t148 先例提升为包内纯函数——MM 迭代（tol=1e-10 / max 500），平局 0.5，零均值 log-strength 输出 + Elo 标度换算（`1500 + 400·v/ln10`，仅展示）。**主估计子仅此一个**；顺序 Elo 不交付（task 148 教训预注册）。
- **报告（league_report）**：BT-MLE 排序表 + 成对胜率矩阵（行 vs 列，含 n；双向合并）+ meta 行（registry sha256 / 种子区间 / 局数 / 代码+数据版本）+ `SIM_INTERPRETATION_NOTE` 限定语头注（report/__init__ 常量复用）。
- **CLI**：`bfsim league <registry.yml> --results db [--workers N] [--cards DIR] [--db PATH]`（跑+报）；`bfsim league --report <league名> --results db`（纯报告模式，不回放）。
- **规模纪律**：联赛规模在注册表钉死（agents × decks × games_per_cell）；默认 smoke 档 = 2 agents × 1 deck × 10 局（实现验证用），生产档 M16 立项时定。
- **测试映射**（验收 1–5 → 测试文件）：注册表校验 → test_league_registry.py；评级解析锚（双人 log-odds 精确锚/循环对称/交换对称/确定性）→ test_league_rating.py；plan_cells 结构 + run_league 双跑逐局一致 + 并串一致（monkeypatch prepare_experiment 为 stub 卡组边界，底下真引擎真随机源）→ test_league_runner.py；报告内容/限定语/error 局剔除 → test_league_report.py。

## 实现要点

- 复用面：`runner` 多进程调度（并行/串行逐局一致纪律）、report CI 计算、task 124 败局解剖可挂联赛实验
- 成本纪律：联赛规模（种群数 × 对局数）在实验定义层钉死；默认档参考 2×50 预算下可承受的成对局数（实现期测算写入设计段）
- TrueSkill 若引入需纯 Python/numpy 实现（runtime 纪律），否则只交付 Elo——实现期定案并记录 trade-off

## 结果与遗留

**交付（2026-11-18）**：注册表 yml（`LeagueDef`，规模钉死：agents[id 唯一] × decks × games_per_cell，seed_stride ≥ games 防区间重叠；type/params 白名单复用 AgentCfg）→ `plan_cells` 纯规划（无序对 × decks × ab/ba 双向，同无序对共享种子区间 = CRN 双向配对，卡组 mirror）→ `run_league` 逐细胞复用 execute_experiment（并串逐局一致/增量落库/失败局 error 继续纪律全继承）→ `league_report`（BT-MLE 排序 + 成对胜率矩阵 + meta 回显 registry sha256/种子/版本 + 限定语头注）。CLI：`bfsim league <registry.yml> --results db [--workers N]`（跑+报）与 `--report <league名>`（纯报告）。

- **验收核对**：① 注册表校验 9 测（唯一性/≥2 agents/≥1 deck/stride/白名单继承）✓；② 确定性——同注册表同种子双跑逐局一致 + 并串一致（test_experiment §8.4 同款硬验收）✓；③ bt_mle 解析锚（双人 ln(s/(n−s)) 精确复现）+ 循环对称 + 结果取反对称 + 平局 0.5 + 确定性 ✓；④ 报告含排序/矩阵/CI 限定语/meta，error 局剔除，异联赛不混入 ✓；⑤ 全量 2017 绿 + ruff 零告警 + CHANGELOG 记账；既有测试零改动 ✓。
- **实现期定项与设计段一致**，两处测试侧修正记录：winner 编码（0=a 侧）在手工灌库测试中的初版笔误、BT 对称性测试取「结果取反」而非「换边」（换边+取反 = 恒等，数据不变）。
- **遗留**：生产档联赛规模（种群数 × decks × games_per_cell）M16 立项时定；TrueSkill 未引入（BT-MLE 已满足主估计子需求，YAGNI）；冒烟注册表 `experiments/league-smoke.example.yml`（启发式 vs MCTS 2×50 × 沙奈朵/多龙黑夜）供 task 152 评测面直接复用。
