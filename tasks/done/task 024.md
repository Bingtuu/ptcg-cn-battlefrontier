# task 024 — M5 启动：目标卡组池锁定 + LLM 辅助 DSL 编写 harness

来源：PRD §5.5（LLM 辅助编写管线：harness 固定为 skill + 严格 prompt + 三道验收闸）、§11 M5（覆盖扩展至目标卡组池 + LLM 管线试验；验收：目标卡组全部可模拟 + LLM 质量数据报告）、§10.3（记录一次通过率/人工修改量）、§13 开放问题（dsl-authoring skill 的 prompt 与上下文装配 M5 前定稿）。
卡组池调研：2026-08-30 数据调研（口径：WUR 窗口 2026-05-30~08-28 / master·cn / 6 场 / min_n=5 / mapping full / 快照 standard-2026-07-16 / name_group_rules_hash=c47538c37ca8），用户拍板 9 套含放逐区。

## 设计

### A. 卡组池锁定入库（机器可读资产）

- `config/target-pool.v1.yml`：锁定口径全字段（窗口/赛区/basis/min_n/快照/name_group_rules_hash）+ 9 条 `{archetype, wur, n, deck_id, note}`。后续 task 的装载验收与 M6 校准统一以此为卡池事实源。
- `battlefrontier/data/pool.py`：pydantic 模型 + `load_target_pool(path)`；结构强校验（9 条、deck_id 格式 `xxx:数字`、口径字段齐全、WUR 降序）。
- `docs/m5-coverage-plan.md`：94 张缺口卡全表（卡名 / 所属卡组 / 级别 A|B|C / 依赖原语 / 状态），活文档随 task 025–030 逐卡核销。

### B. LLM harness（三道闸工具化 + skill）

执行者 = 会话内 agent（无需外部 API key，已与用户确认）。

- **`.kimi-code/skills/dsl-authoring/SKILL.md`**（按 writing-skills 规范；触发：编写/修改 cards/ DSL）：
  - 输入装配（固定顺序）：db `get_card` 取 `text_raw` 原文 + `effect_tags` + `sentences` 句级标签（排除 `rule_reference` 句，task 009 约定）→ 读 `dsl/schema.py` + `dsl/vocabularies.yml` → 读编写规范（skill 内嵌）→ 参考同机制既有卡（如检索类看高级球）。
  - 输出契约：`cards/<name_group>.yml`（每个 effect 注释逐句引用 text_raw 原文，不改写不做术语规范化）+ 单卡单元测试。
  - 硬性纪律：未知词/未知机制**不猜**——报 DslError 并暂停上报用户；超出现有原语体系的效果标记 blocked（记 m5-coverage-plan），不降级乱写；检索类关键决策声明 `observe:` 锚点；词表开放字符串，新词须先加 vocabularies.yml 并在 PR 说明。
  - 单卡测试约定：测试从 `cards/` 真实文件装载（`load_card_doc`），集中写入 `tests/test_dsl_cards.py`（按批次分节注释）；stub 引擎驱动（helpers.main_state 模式）。
  - 三道闸：①`bfsim dsl-check`（schema + 词表）→ ②pytest 单卡测试 → ③人工核销（用户确认后才把日志 gate3 置 true）。
- **闸 1 工具化**：CLI `bfsim dsl-check <yml>...`——逐文件 `load_card_doc`，打印 OK 或带文件名的错误，任一失败 exit 1。
- **质量数据**：`cards/authoring-log.jsonl`（进版本控制，不含卡牌文本，合规），每卡一行：
  `{"date","card","card_id","author":"llm"|"human","batch":N,"gate1":bool,"gate2":bool,"gate3":bool,"first_pass":bool,"human_edit_lines":int|null,"notes":""}`
  - `first_pass` 定义：闸 1+2 首次提交即过 且 人工零修改；`human_edit_lines` 核销时以 git diff --numstat 辅助估。

### C. 自验（harness 全流程走通证明）

用 dsl-authoring skill 写 1 张批 1 A 级新卡（要求：现有原语可写、含检索 + observe 锚点，有代表性；候选：友好宝芬/波波，开工时按 db text_raw 定），走完：装配输入 → 草稿 → 闸 1 → 闸 2 → 日志首条（gate3=false 待用户核销）→ 卡组装载复验。

## 验收标准

- [x] `config/target-pool.v1.yml` 入库：9 套卡组 + 完整复算口径；`load_target_pool` 强校验（条数/deck_id 格式/口径字段/WUR 降序），畸形文件显式报错。
- [x] `docs/m5-coverage-plan.md`：缺口卡逐卡全表（81 张，替补后实际值；级别/依赖原语标注）。
- [x] `.kimi-code/skills/dsl-authoring/SKILL.md` 入库，符合 skill 规范（frontmatter name/description 触发条件），覆盖输入装配/输出契约/三道闸/不猜纪律。
- [x] `bfsim dsl-check`：合法文件 rc=0；schema 错 / 未知词 rc=1 且错误含文件名。
- [x] 自验卡：友好宝芬 DSL 入库 + 单卡测试过 + dsl-check 过 + authoring-log.jsonl 首条（gate3 待人工）。
- [x] 全量 pytest 绿（334）+ ruff 零告警。
- [x] STATUS.md 更新 + 本文档归档。

## 记录

- 2026-08-30 设计定稿（用户确认池规模 9 套含放逐区；harness 无需外部 API key）。
- 2026-08-30 完成。**两处计划外发现**：①退赛断点——db 仅一个合法性快照（07-16），原 top-9 中 4 套（放逐Box/雷吉铎拉戈/洛奇亚/密勒顿）无任何合法 full 卡组；用户决议替补补位（玛俐长毛巨魔雪妖女/赛富豪/多龙巴鲁托/赫普的苍响），池改 5 保留+4 替补，全窗口覆盖 53.4%，代表卡组全过当前快照校验；②原估缺口 94 张 → 替补后实际 81 张（A46/B17/C18）。
- harness 自验（子代理写友好宝芬）：完整走通且暴露真问题——缺 HP 上限过滤器 → 按不猜纪律 blocked 上报 → 注册 `hp_max:N`（chooser 参数化过滤器，与 evolves_from 同构）解锁；skill REFACTOR 五处（闸 1 盲点告诫 / 词表扩展路径 / 注释格式约定 / 样例补巢穴球 / 测试函数中文命名）。自验卡闸 1+2 过，日志首条 first_pass=false（测试命名返工，严格口径）。
- 闸 1 盲点（filters/observe/condition/args 不校验）为已知设计事实：filters 正确性靠闸 2 兜底，已写入 skill；是否给闸 1 加 filters 校验留待 task 031 质量数据复盘时评估。
