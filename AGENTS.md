# AGENTS.md — ptcg-cn-battlefrontier

BattleFrontier（对战开拓区）：AI 宝可梦卡牌（PTCG 简中环境）对战模拟与卡组强度测试引擎。
[ptcg-cn-db](https://github.com/Bingtuu/ptcg-cn-db)（数据基建层）之上的应用层：完整规则引擎 + 效果 DSL + AI 智能体，通过大规模模拟对局产出卡组胜率、最优策略（决策数据聚合报告）与换卡敏感性分析。

**权威文档**：`docs/superpowers/specs/2026-08-25-battlefrontier-prd-design.md`（一期 PRD v1.0）+ `docs/superpowers/specs/2026-10-03-phase2-prd-design.md`（二期 PRD v1.0，D2-1~D2-8 + 里程碑 M7–M10）+ `docs/superpowers/specs/2026-10-16-phase3-prd-design.md`（三期 PRD v1.0 已批准，D3-1~D3-6 + 里程碑 M11–M12，方向 B 设计文档并入）——一切设计以它们为准，含 12 条决策记录（D1–D12）与一期里程碑 M1–M6。
**规则事实源**：`docs/rules-manual.md`——依简中官网规则页逐节整理的完整规则说明书（正文事实源）；`docs/rules-reference.md`——引擎/DSL 实现落点速查 + 术语表（「昏厥」等官方用词），争议规则进其附录 A 规则决议日志；规则查询流程已 skill 化（`.kimi-code/skills/ptcg-rules`）。
**数据契约**：上游 db 项目 PRD 的 FR-10 sim 骨架契约——模拟结果永远落独立库，主库只读，经 card_id / name_group / 快照 id 关联。

## 当前状态

一期 M1–M6 全部完成（M6 校准基线 2026-10-03：9 套池 36 无向配对 × 500 局模拟 matchup 矩阵 + 72 格偏差表，加权平均 |Δ| 13.2%）；二期 M7–M10 全部完成（2026-10-05）——MCTS 多世界 determinized UCT 上线（`type: mcts`，迭代预算零墙钟；预算档定案：标准 2×50 / 深档 4×100+ 仅单格深挖），M10 归因闭环（MCTS 增强版偏差表加权 |Δ| 9.7%，|Δ|≥25% 五格全有解释）。其后（2026-10-05~07，task 037–042）：引擎性能优化（MCTS 成本 -38.5%，行为零变化 events_hash 逐局全等）；全库 code review（6 组并行 + 主会话复核，0 Critical / 11 Important）全部修复闭环——legal_actions 缓存契约、DSL args 白名单 + attack 绑定校验、中断/报告告警族、**MCTS 信息泄漏修复**（带冻结集的部分 determinize，挂起根 freeze=pool_iids∪payload + setup 期背面布阵入池重采样）、修复后复核（泄漏贡献 1.8/0.4pts 噪声级，归因结论更硬）、flip_heads_count 穿透第六件 + DSL 路径串并对拍护栏；**MCTS 决策分析上线**（task 042：根节点访问分布经 mcts_consider 观测事件入流，`bfsim report --mcts-consider` 三件套）。**方向 B 启发式参数自调优收官**（task 045 设施 + task 046 正式跑批：唯一采纳 deck_low_threshold 6→12 双门槛过线、复校准 |Δ| 恶化 → D-046-5 折中存档不回写；task 047 ES 不立项）。其后（2026-10-16~18，task 049–055）：**M11 学得评估器收官、里程碑达成（2026-10-18 用户确认）**——数据产线 10 万局启发式自对局 → 30 维特征层（纯 VisibleGameState，守信息纪律）→ 纯 Python 岭回归评估器（`models/eval-linear-v1.json`，D3-4 进版本控制）→ MCTS rollout 浅截断接入（`eval_cutoff_turns`，默认零变化）→ 双锚达成（锚 1 一致率相对教师天花板 100.2%；锚 2 同预算净效应口径——满预算验证格 2×50 K=10 学生 66.4% vs 基准 62.0% CRN 覆盖 0，低预算档 -10.6pts 全部来自预算减半）。其后（2026-10-18~21，task 056–062）：**M12 MCTS 行为蒸馏收官、终判 = 部分达成收口（2026-10-21 用户拍板 D3-7）**——torch dev-only 训练 + numpy runtime 推理（D3-3 核销）+ 训练非复算面声明（D3-4）；教师 2×50 十³ 试点采集（171k 决策点）→ v1 学生锚 1 ✅（相对天花板 88.8%）/ 锚 3 ✅ / 锚 2 ❌ 16.7% → task 061 根因诊断（特征盲区：零卡面身份/零弃牌构成 → use_ability 不可分 0.009%）→ task 062 特征 v2（+112 卡身份 one-hot +6 弃牌构成，`bf-distilled-policy-v2` 资产 format 分派、v1 保持可装载）零新采集重训复测：use_ability 一致率 20.9%（终止判据 ✅）、锚 2 收敛 12.5%（过第一门槛 ≤13.2%，未及 M10 9.7%）、墙钟 7.4min。**蒸馏学生正式定位「分钟级粗筛」**（跨配对保序两版实证不成立；精排/深挖仍归 MCTS）；残留盲区进 backlog（特性使用质量 / play_stadium / end_turn / copy_attack 多级嵌套）。三期 M11 ✅ M12 ✅（部分达成）主线收官；可选线 = 卡池 v2 独立线（D3-5，数据就绪）。其后（2026-10-21，task 063–064）：引擎侧对局形态诊断（deck_out = Agent 行为 artifact，规则正确；超短局 = 快攻 + 自移除盲区 + 自爆）坐实引擎 bug「promote 空场判平」（`check_knockouts` 的 wipe 检查不跨扫描，影响面 m9 1.4% / v2 0.5% 局）→ 修复收官：时序语义定案（胜利条件②与①同时点 = 昏厥结算点立即判；换上仍推迟 D-WP2-1），扫描结束补全场空检（ko_settled 门控），TDD 四测 + 5306 重放实证（判平→p1 胜）；附录 A 新决议「跨扫描全场清空的判负时点」✅ 已核（2026-10-21 用户核销——064 文档闭环）；观感债单列不随修（knockout/game_over 先于触发原语的 effect_primitive 事件）。其后（同日，task 065–066）：M12 残留盲区归因（play_stadium = 教师信号近定率噪声下 CE 少数标签坍缩；特性质量 = 特征不可分按效果类型整类坍缩；end_turn = 天花板 33.6% 低上限 kind）→ A 包零采集重训两轮（per-kind 重加权 + end_turn 双投票降噪，harness 保留入库）**证伪收口**——剂量-响应三点全单调（锚 1 目标 kind 受益 ↔ attack 受损 ↔ |Δ| 12.5%→15.9%→18.6%），锚 2 瓶颈实证在决策「质」非机制「量」；用户拍板维持 v2 基线、B 特征 v3 不立项。其后（同日，task 067）：064 修复后复校准收官——matrix 重跑（18000 局平 0，247 旧口径局清零，启发式加权 |Δ| 15.0% 持平）+ MCTS 高残留 3 格定点重跑 → 增强版偏差表 9.715%（修复前后持平）。其后（同日，task 068）：**卡池 v2 锁定**（`config/target-pool.v2.yml`：09-16 后窗口 46 场 + Top-9 全新排，覆盖 80.48%，snapshot standard-2026-09-16 J 标；索罗亚克/火伊布猫头夜鹰/电电虫Box 新入；校准真实侧 72/72 格全覆盖零低置信）；DSL 缺口 34 张 + 引擎扩展 5 项定案，附录 A 待核决议 2 条。其后（同日，task 069）：**卡池 v2 引擎扩展批收官**——5 机制 + 3 原语小扩全落地（新原语 `modify_evolution` 虹色因子 / `prevent_ko` 顽强之心三落点截顶 / `modify_attack_cost types:all` 璀璨结晶 / `own_turn_end` 力之沙漏（D-069-1）/ `lock_play ace_spec` 盖诺赛克特（D-069-2 广义五门类）+ discard choose=N / `attached_energy_on_opponent_all` / heal own_bench），1454 绿 + ruff 零告警，存量测试零改动；附录 A 决议 5 行（2 已核 3 待核攒批）。其后（2026-10-27，task 070–071）：**070 DSL 批次第一批收官**——落地 15/34（老大的指令纯挂载 + 14 张新写闸 1/2 全一次通过零返工；逆转能量 chooser 组合词主会话直做），blocked 19/34 全部为引擎/DSL 表达力缺口（精确到读点）→ **071 引擎扩展第二批立项**（任务书 D-071-1~5 定稿；组 A/B1/C 派遣遭配额 429 中断，组 A 留 TDD 红阶段 25 测遗产，待窗口恢复 resume）→ 阶段 2 DSL 批 → v2 装载零缺口 → v2 matrix + 校准；M12 残留盲区触发式处理。事实源见 `STATUS.md`（历史工作记录归档 `docs/status-archive.md`）。卡池 v1 九套（`config/target-pool.v1.yml`）缺口 81 张全覆盖清零，卡池 v2 九套已锁定（`config/target-pool.v2.yml`，task 068），DSL 定义库 115 文件，全量 1512 测试绿。Mega 环境演进线暂缓（2026-10-07 用户决议：简中环境无 Mega）。

## 架构分层与边界

```
报告层 → 实验层(Runner) → 决策层(Agent) → 引擎层(规则引擎) → 效果层(DSL+解释器) → 数据层(ptcgdb.sdk)
```

- **引擎对卡牌内容零硬编码**："这张卡做什么"全部由 DSL 定义、解释器执行；引擎只管规则骨架（阶段机、伤害、奖赏、胜负）。
- **DSL 定义库是独立资产**：每（卡名 + 文本）等价类一个 YAML（同名多文本**严格拆分**，如 `火恐龙-大字爆炎.yml` / `火恐龙-闪焰之幕.yml`），Pydantic schema 强校验，进版本控制，单卡效果测试不依赖整局模拟。**装载键 = card_id 精确挂载**（`card_ids` 必填，2026-09-06 决议；无名字兜底——防取错印刷），闸 1 校验走 `bfsim dsl-check --db`（card_id 存在性 / 文件内归一化 text_raw 一致 / 赛制合法性）。
- **Agent 接口统一**：`observe(visible_state, legal_actions) -> action`，启发式 / MCTS / RL 共用；Agent 只见过滤后的可见视图（对手手牌内容不可见），引擎枚举合法行动，AI 永不非法操作。MCTS（task 034）经可选 `bind_engine` 钩子挂接引擎，读真实状态的唯一用途是 determinization 重采样隐藏信息（task 039：挂起根带冻结集部分重采样、setup 期对手背面布阵入池），搜索全程在克隆上进行（信息纪律 + 模拟事件不回流真实事件流）。MCTS 根节点访问分布经 `mcts_consider` 观测事件入流（task 042：events_hash 排除、render 跳过，行为零变化），供 `report --mcts-consider` 决策分析。
- **数据只进不出**：消费 db 项目只读；模拟结果落本项目独立 SQLite。

## 技术栈与约束

- Python（与 db 项目同栈，3.12+）；Pydantic v2（DSL schema + 模型校验）；SQLite WAL（结果库）；YAML（DSL 定义与实验定义）；pytest；ruff；numpy（M12 起 runtime：distilled 策略模型推理前向，task 056）。
- 训练侧 torch（**dev-only**，M12 蒸馏训练，task 056 D3-3 核销）：engine/agent runtime 路径零 torch import；训练含不可锁随机源，已声明「训练非复算面」（D3-4：权重 JSON 进版本控制即锁定，推理确定性不受损）。
- 依赖上游 `ptcgdb` SDK（`open_db` / `open_jsonl` 双后端），不自带卡牌数据。
- 无外部服务依赖，全本地运行；实验执行 = 单机多进程（一期不做分布式）。

## 硬性规矩（来自 PRD，改动前必须确认有充分理由）

- **种子确定性**：所有随机（洗牌/掷币/抽牌）走单一可注入随机源；同实验定义 + 同种子区间重跑，结果逐局一致。多进程并行与串行结果必须一致。
- **规则不猜**：规则骨架以简中官方规则书 + 官方 Q&A 为事实源，每条规则实现配单元测试并标注出处；争议规则进规则决议日志。
- **原文保真延伸**：DSL 注释引用 `text_raw` 原文，不改写、不做术语规范化。
- **枚举开放**：DSL 原语、触发器、选择器等词表一律开放字符串 + 词表文件（对齐 db 项目 `effect_tags.yml` 29+3 词表），不写死在代码里。
- **可复算**：实验可复现 = 实验定义 + 代码版本 + 数据版本三者锁定；一切报告 meta 回显实验 id / 种子区间 / 版本 / 局数，数字可原样重放。
- **观测性内建**：解释器执行即产出结构化事件流（回放 / 人工 check / 过程统计共用一份数据）；DSL 可声明 `observe:` 统计锚点。
- **可观测范围纪律**：一期不含裁判判罚/超时等赛事规则；V-UNION 不实现；ACE SPEC 必须支持（每卡组限 1 张）；其他特殊机制按"一期目标卡组需要才做"逐个评估（YAGNI）。
- **合规**：不采集/存储/分发卡图与卡牌数据；本项目不公开分发任何数据库文件。

## 工作方式

- **任务循环**：开发按 `tasks/` 目录的标准循环执行——每个任务一个 `task NNN.md`，流程：读设计文档 → 设计 TDD（验收标准先行）→ 开发 → 测试（pytest 全绿 + ruff 通过）→ 更新 `STATUS.md` + task 文档归档 `tasks/done/`。规范见 `tasks/README.md`。
- 变更架构、DSL 语义、结果库 schema、统计口径前，**先改 PRD** 并保持代码与 PRD 同步。
- 一期目标卡组池以 db 项目 `stats_usage(granularity="archetype")` 当前 WUR 排名驱动锁定，不拍脑袋选组（卡池 v1 已锁定：`config/target-pool.v1.yml`；卡池 v2 已锁定：`config/target-pool.v2.yml`，task 068）。
- 大批次实现走「子代理 TDD + 主会话独立复验 + 规格/质量双重复核」（task 026 WP2–WP6 惯例）；子代理不得改权威测试迁就实现，测试断言存疑报主会话裁决。
- LLM 辅助 DSL 编写走固定 harness（skill + 严格 prompt），三道验收闸（schema 校验 → 单卡单元测试 → 人工核销）全过才入库；一期为试验性，需记录一次通过率与人工修改量。
- CHANGELOG.md 四段式：Added / Changed / Deprecated / Removed。

## 常用命令

CLI 入口 `bfsim`（`pip install -e .` 后可用；开发期等价于 `python -m battlefrontier.cli`）：

```bash
# 跑实验（实验定义见 experiments/*.example.yml；--workers 多进程，结果与串行逐局一致）
bfsim run experiments/gardevoir-mirror.example.yml --workers 4 --results results/exp.db

# 报告（实验 id 由 run 完成时回显；--decisions 追加决策聚合分节；--mcts-consider 追加 MCTS 决策分析）
bfsim report 1 --results results/exp.db [--decisions] [--mcts-consider]

# 换卡敏感性（实验定义含 variants 时 run 自动跑整组）
bfsim sensitivity <base_id> <variant_id>... --results results/exp.db

# matchup 矩阵（实验定义含 matrix 段时 run 自动展开卡池全部无向配对，group_name 归组）
bfsim run experiments/m6-calibration.example.yml --workers 8 --results results/exp.db

# 校准偏差表（模拟矩阵 vs 真实赛事 matchup；参数 = matrix 实验定义路径）
bfsim calibration experiments/m6-calibration.example.yml --results results/exp.db

# DSL 校验（闸 1）：schema + 词表 + args 键名白名单；--db 追加 card_id 存在性 / 文本等价类一致 / 赛制合法 / on_attack 招式名绑定命中卡面（task 038）
bfsim dsl-check cards/*.yml --db "C:/Vibe Project/Pokearena/data/ptcg-cn.db"

# 启发式参数自调优（task 045：坐标下降，轨迹 JSONL 落 results/tune-<name>.jsonl，不落结果库）
bfsim tune experiments/tune-smoke.example.yml --workers 4

# M11 一致率快照采集（task 052：教师 MCTS 跑局落决策点快照，不落结果库，正式落 results/m11-eval/）
bfsim collect-snapshots --pool config/target-pool.v1.yml --games-per-pair 10 --seed-start 500000 --out results/m11-eval --workers 4

# M11 决策一致率评估（task 052：快照 × 受测配置重放比对；K>0 须配 --evaluator）
bfsim agreement results/m11-eval/pair-0-xxx.jsonl --worlds 1 --iterations 25 --eval-cutoff-turns 10 --evaluator models/eval-linear-v1.json

# M12 蒸馏策略训练（task 058：torch dev-only；快照目录 → 权重资产，超参全钉死写 meta；
# task 066：--weight-scheme kind-weights-v1/v2 = per-kind 加权 + end_turn 双投票降噪，缺省 none 逐位不变）
bfsim train-policy --data results/m12-teacher-pilot --pool config/target-pool.v1.yml --out models/policy-m12-v2.json

# M12 蒸馏学生一致率（task 059：--policy 与 MCTS 预算 flags 互斥；v1/v2 资产按 format 自动分派）
bfsim agreement results/m12-teacher-pilot/pair-0-xxx.jsonl --policy models/policy-m12-v2.json

# 蒸馏学生跑局（type: distilled，~0.06s/局；锚 3 全 matrix 18000 局 7.4min）
bfsim run experiments/m12-distilled-matrix.example.yml --workers 16 --results results/exp.db
```

开发自检（Windows Git Bash，提交前必过）：

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m pytest -q
.venv/Scripts/ruff.exe check .
```
