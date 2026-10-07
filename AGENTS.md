# AGENTS.md — ptcg-cn-battlefrontier

BattleFrontier（对战开拓区）：AI 宝可梦卡牌（PTCG 简中环境）对战模拟与卡组强度测试引擎。
[ptcg-cn-db](https://github.com/Bingtuu/ptcg-cn-db)（数据基建层）之上的应用层：完整规则引擎 + 效果 DSL + AI 智能体，通过大规模模拟对局产出卡组胜率、最优策略（决策数据聚合报告）与换卡敏感性分析。

**权威文档**：`docs/superpowers/specs/2026-08-25-battlefrontier-prd-design.md`（一期 PRD v1.0）+ `docs/superpowers/specs/2026-10-03-phase2-prd-design.md`（二期 PRD v1.0，D2-1~D2-8 + 里程碑 M7–M10）——一切设计以它们为准，含 12 条决策记录（D1–D12）与一期里程碑 M1–M6。
**规则事实源**：`docs/rules-manual.md`——依简中官网规则页逐节整理的完整规则说明书（正文事实源）；`docs/rules-reference.md`——引擎/DSL 实现落点速查 + 术语表（「昏厥」等官方用词），争议规则进其附录 A 规则决议日志；规则查询流程已 skill 化（`.kimi-code/skills/ptcg-rules`）。
**数据契约**：上游 db 项目 PRD 的 FR-10 sim 骨架契约——模拟结果永远落独立库，主库只读，经 card_id / name_group / 快照 id 关联。

## 当前状态

一期 M1–M6 全部完成（M6 校准基线 2026-10-03：9 套池 36 无向配对 × 500 局模拟 matchup 矩阵 + 72 格偏差表，加权平均 |Δ| 13.2%）；二期 M7–M10 全部完成（2026-10-05）——MCTS 多世界 determinized UCT 上线（`type: mcts`，迭代预算零墙钟；预算档定案：标准 2×50 / 深档 4×100+ 仅单格深挖），M10 归因闭环（MCTS 增强版偏差表加权 |Δ| 9.7%，|Δ|≥25% 五格全有解释）。其后（2026-10-05~07，task 037–042）：引擎性能优化（MCTS 成本 -38.5%，行为零变化 events_hash 逐局全等）；全库 code review（6 组并行 + 主会话复核，0 Critical / 11 Important）全部修复闭环——legal_actions 缓存契约、DSL args 白名单 + attack 绑定校验、中断/报告告警族、**MCTS 信息泄漏修复**（带冻结集的部分 determinize，挂起根 freeze=pool_iids∪payload + setup 期背面布阵入池重采样）、修复后复核（泄漏贡献 1.8/0.4pts 噪声级，归因结论更硬）、flip_heads_count 穿透第六件 + DSL 路径串并对拍护栏；**MCTS 决策分析上线**（task 042：根节点访问分布经 mcts_consider 观测事件入流，`bfsim report --mcts-consider` 三件套）。卡池 v1 九套（`config/target-pool.v1.yml`）缺口 81 张全覆盖清零，DSL 定义库 101 文件，全量 1063 测试绿。下一步候选（Mega 规则调研 / db 侧数据协同 / 历史日期勘误专项）见 `STATUS.md`（事实源，本文件不抄写细节）。

## 架构分层与边界

```
报告层 → 实验层(Runner) → 决策层(Agent) → 引擎层(规则引擎) → 效果层(DSL+解释器) → 数据层(ptcgdb.sdk)
```

- **引擎对卡牌内容零硬编码**："这张卡做什么"全部由 DSL 定义、解释器执行；引擎只管规则骨架（阶段机、伤害、奖赏、胜负）。
- **DSL 定义库是独立资产**：每（卡名 + 文本）等价类一个 YAML（同名多文本**严格拆分**，如 `火恐龙-大字爆炎.yml` / `火恐龙-闪焰之幕.yml`），Pydantic schema 强校验，进版本控制，单卡效果测试不依赖整局模拟。**装载键 = card_id 精确挂载**（`card_ids` 必填，2026-09-06 决议；无名字兜底——防取错印刷），闸 1 校验走 `bfsim dsl-check --db`（card_id 存在性 / 文件内归一化 text_raw 一致 / 赛制合法性）。
- **Agent 接口统一**：`observe(visible_state, legal_actions) -> action`，启发式 / MCTS / RL 共用；Agent 只见过滤后的可见视图（对手手牌内容不可见），引擎枚举合法行动，AI 永不非法操作。MCTS（task 034）经可选 `bind_engine` 钩子挂接引擎，读真实状态的唯一用途是 determinization 重采样隐藏信息（task 039：挂起根带冻结集部分重采样、setup 期对手背面布阵入池），搜索全程在克隆上进行（信息纪律 + 模拟事件不回流真实事件流）。MCTS 根节点访问分布经 `mcts_consider` 观测事件入流（task 042：events_hash 排除、render 跳过，行为零变化），供 `report --mcts-consider` 决策分析。
- **数据只进不出**：消费 db 项目只读；模拟结果落本项目独立 SQLite。

## 技术栈与约束

- Python（与 db 项目同栈，3.12+）；Pydantic v2（DSL schema + 模型校验）；SQLite WAL（结果库）；YAML（DSL 定义与实验定义）；pytest；ruff。
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
- 一期目标卡组池以 db 项目 `stats_usage(granularity="archetype")` 当前 WUR 排名驱动锁定，不拍脑袋选组（卡池 v1 已锁定：`config/target-pool.v1.yml`）。
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
```

开发自检（Windows Git Bash，提交前必过）：

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m pytest -q
.venv/Scripts/ruff.exe check .
```
