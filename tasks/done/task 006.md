# task 006 · DSL schema（Pydantic + YAML 加载 + 强校验）

- 状态：完成
- 关联：PRD §5.1 / §5.2，里程碑 M2；输入 = task 005 首批原语清单

## 目标

落地 DSL 载体形态：每卡一个 YAML，Pydantic v2 schema 强校验（写错字段名、缺参数直接报错），原语/触发器/选择器词表走开放字符串 + 词表文件（不写死代码）。本任务只产出 AST 层（解析 + 校验），不执行效果（解释器归 task 007）。

## 验收标准（测试清单）

- [x] PRD §5.2「博士的研究」示例 YAML 解析成功，字段值逐项正确
- [x] 写错字段名（如 `triger:`）→ 校验报错，错误信息含字段名与位置
- [x] 未知原语 / 选择器 / 触发器（不在词表文件）→ 报错，信息提示词表文件位置
- [x] `count` 接受 int / `all` / 词表计数表达式（如 `own_remaining_prizes`）；非法值（负数、乱字符串）→ 报错
- [x] 缺 `card.name_group` → 报错
- [x] cost / conditions / observe 锚点可表达且校验
- [x] YAML 语法错误 → 带文件上下文的 DslError
- [x] 词表文件可独立加载、非空、无重复条目
- [x] 多卡复杂示例（含 cost + 多 action + observe）解析成功
- [x] pytest 全绿 + ruff 零告警

## 实现要点

- 新增依赖 `pyyaml`（PRD §5.1 已定 YAML 载体），入 pyproject dependencies
- `battlefrontier/dsl/schema.py`：CardRef / ActionNode / Effect / CardEffectDoc，frozen + extra="forbid"
- `battlefrontier/dsl/vocabularies.yml`：actions / selectors / triggers / counters 四段词表，初版 = task 005 清单
- `battlefrontier/dsl/loader.py`：YAML → CardEffectDoc，错误统一 DslError（含文件路径上下文）
- ActionNode 公共字段强校验（action/selector/count/filters/destination），原语私有参数走 `args` 字典逃逸口，逐原语参数校验随 task 008+ 原语实现注册（本任务文档注明此边界）
- count 词表表达式（counters 段）覆盖 task 005 变量伤害/计数抽需求

## 结果与遗留

- 交付：`dsl/schema.py`（CardRef/ActionNode/Effect/CardEffectDoc，frozen + extra=forbid）、`dsl/vocabularies.yml`（六段词表：actions 18 / selectors 10 / triggers 6 / counters 7 / destinations 6 / limits 3，初版 = task 005 清单）、`dsl/loader.py`（parse_card_doc / load_card_doc / load_vocabularies，统一 DslError 带文件上下文）
- 词表校验在 loader 层（schema 保持纯结构），未知词报错并提示词表文件路径——符合「枚举开放：词表文件，不写死代码」
- 新增依赖 pyyaml（pyproject dependencies + package-data 收 vocabularies.yml）
- 设计边界：ActionNode 公共字段（action/selector/count/filters/destination）强校验；原语私有参数走 `args` 字典逃逸口，逐原语参数校验随 task 008+ 原语实现注册
- 14 个新测试（TDD 红→绿）；全量 68 测试全绿 + ruff 零告警
- 遗留：解释器（task 007）消费 CardEffectDoc；`condition` 为开放字符串，条件结构化随解释器需求定稿；M1 的 `runner/play.py` 事件流与 DSL 事件流的合流点在 task 007 设计
