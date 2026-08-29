# STATUS.md — ptcg-cn-battlefrontier

> 进展速记：每完成一步更新。规范对齐 db 项目（进展记在这里，不进 README）。

## 当前

**M2 进行中**：task 005 ✅（锁定沙奈朵卡组 + 首批原语清单）、task 006 ✅（DSL schema + 词表 + loader）、task 007 ✅（解释器骨架 + 事件流 + play_trainer）、task 008 ✅（CardDef 升级：能量类型成本/多招式/弱点抗性/规则盒奖赏 + check_knockouts 任意时机入口）、task 009 ✅（chooser 挂起-恢复机制 + 检索/回收/选择式弃牌四原语，高级球/巢穴球/夜间担架 e2e）、task 010 ✅（卡组装载层 db → CardDef + DSL 定义库 cards/ 落盘，沙奈朵卡组 60 张装载零告警 + e2e）、task 011 ✅（特性框架 ability_manual：use_ability 枚举 + 三种限次 + 可行性门；chooser 两段式选择 carry 协议；attach_energy/draw until_hand 原语；精神拥抱/再起动 e2e，全量 141 绿）。下一步：task 012+ 招式附加效果（on_attack）/ 混乱状态 / 道具·竞技场骨架 / 计数表达式 / 剩余特性（化危为吉跨回合触发、亢奋脑力转伤、妖精领域弱点改写），直至沙奈朵卡组全覆盖。
ptcgdb SDK 已接入（`C:/Vibe Project/Pokearena` 可编辑安装）。

## 里程碑

- ✅ M1 引擎骨架（白板对局 + 同种子复现）——task 001–004 全 ✅（2026-08-25）
- ⬜ M2 DSL + 解释器 + 首批原语（第一套目标卡组）
- ⬜ M3 启发式 Agent + Runner + 结果库（百局端到端）
- ⬜ M4 报告层（胜率 / 决策聚合 / 换卡敏感性）
- ⬜ M5 覆盖扩展 + LLM 辅助编写试验
- ⬜ M6 校准基线 + 一期验收

## 工作记录

### 2026-08-29 task 011 特性框架 + 精神拥抱/再起动落地 ✅

- `use_ability` 行动：场上宝可梦有 ability_manual DSL 文档即枚举（栈顶 iid），三种限次强制（once_per_turn 按 iid / once_per_turn_shared 按卡名 / unlimited），未声明 limit 报错不猜；可行性门 `ability_feasible`（attach_energy 双侧池非空 / draw 恒可行 / 未知原语 DslError）
- chooser 协议扩展：**同节点两段式选择**（NeedChoice.carry → PendingChoice.payload → ctx.carry）；新池 `own_pokemon_in_play`（InPlayPokemon 维度）+ 过滤器 energy_超 / pokemon_超 / would_survive_20（精神拥抱「会昏厥不可选」守卫）
- 原语：`attach_energy`（弃牌区→场上附着 + damage_counters，完成 check_knockouts）、`draw` 增 `args.until_hand=N`；`_run_or_suspend` 完成模式（trainer 弃置 / ability 不弃）
- cards/ 定义库六卡（+沙奈朵ex 精神拥抱 unlimited、梦幻ex 再起动 once_per_turn）
- TDD：14 新测试红→绿；全量 141 绿 + ruff 零告警；含特性卡组 play_game 同种子 hash 一致
- 遗留：化危为吉跨回合触发 / 亢奋脑力转伤 / 妖精领域弱点改写 / 招式 on_attack 效果 / 混乱状态 / 道具·竞技场骨架归 task 012+

### 2026-08-29 task 010 卡组装载层 + DSL 定义库落盘 ✅

- `battlefrontier/data/` 新包：`cards.py::carddef_from_db`（SDK Card → CardDef：card_type/stage 中文词表映射、provides→能量属性、attacks 展开 cost、弱点抗性取值）+ `deck.py::load_deck`（get_deck → validate_deck → 展开 60 张，日期 = 最新 standard 快照 effective_from）
- 校验口径（不猜）：prize_cards vs 引擎 PRIZE_BY_RULE_BOX 不符 / 弱点抗性值非 ×2/-30 → warning 返回；未知 card_type/stage → ValueError
- `AttackDef.damage_modifier` + `CardDef.is_ace_spec` 补位；`dsl/loader.py::load_card_dir`（name_group 键、重复报错）
- `cards/` 定义库首批四卡入库（博士的研究/高级球/巢穴球/夜间担架，注释引用 text_raw 原文）；沙奈朵卡组（mik_moe:644634）60 张装载零告警 + 四卡效果 play_game e2e 同种子 hash 一致
- TDD：11 新测试红→绿；全量 127 绿 + ruff 零告警
- 遗留：挂载键 name_full 待 db SDK 暴露 group_key 后切换；特性/道具/竞技场/混乱状态/计数表达式归 task 011+

### 2026-08-29 task 009 chooser 机制 + 检索/回收/选择式弃牌原语 ✅

- chooser 挂起-恢复协议：原语返回 NeedChoice → phase="choice" + PendingChoice（池挂起瞬间冻结为 pool_iids，可序列化）→ Agent 选择（`Action.choices`）→ 游标恢复续跑；Effect 树不入状态（card_effects 重取），选择不消耗随机源
- 原语四件：discard（choose=N 成本）/ search_deck（filters + up-to 可不找 + hand/bench 去向，bench 联动登场锁定）/ shuffle_deck / recover_from_discard（池空 no-op）；未知 filter/成本形式 DslError 不猜
- 引擎：成本可行性门（高级球手牌不足不枚举、巢穴球备战满不枚举）；`visible_state` 仅向选择方揭示牌库检索池
- 三卡 e2e：高级球/巢穴球/夜间担架；TDD 14 新测试 + 1 旧测试改约；全量 116 绿 + ruff 零告警；含高级球整局同种子 hash 一致
- 遗留：撤退弃能量选择式/奖赏任意顺序拿取可复用本机制（引擎层行动）；特性触发器/道具/竞技场/混乱状态/计数表达式归 task 010+

### 2026-08-29 db 支撑批（044–049）接入 review ✅

- 背景：db 项目完成下游支撑批（text_raw 逐字对账 / SDK get_deck·list_decks + legal_at 缓存 / 跨源 EN 对账 99.2% / errata 监控闭环 / Q&A 供给端不存在·搁置 / 句级打标 sentences+rule_reference），逐项实测验证通过
- **结论：已完成代码（task 005–008）零返工**。实测确认三个天然对齐：能量属性记号双方都是中文单字（"超"/"恶"/"无"）；弱点抗性 db 值 `×2`/`-30` 与引擎常量一致；db 词表仍 29+3 与 task 005 口径不变
- **task 010 卡组装载层的接入约定**（立项时照此执行）：①奖赏张数以 db `prize_cards` 字段为准，引擎 `PRIZE_BY_RULE_BOX` 作骨架兜底 + 装载校验（不符告警）；②能量卡属性取 db `provides` 字段（能量卡 `types` 为 NULL）；③弱点/抗性装载时校验 value 是否为 `×2`/`-30`，偏差告警不猜；④跨源对账残留 38 张人工核销待办——装载前先核对目标卡组 27 种卡是否在内
- DSL harness（M5）prompt 上下文改用 db `detail.sentences` 句级标签、排除 `rule_reference` 句（吼叫尾误标 lock 已由 db task 049 根治，task 005 归档文档为历史记录不回改）

### 2026-08-28 task 008 引擎骨架扩展（能量成本/弱点抗性/规则盒奖赏/任意时机昏厥）✅

- `CardDef` 升级：`AttackDef`（成本为能量属性符号列表，"无"=无色任意抵）、`energy_type`/`weakness`/`resistance`/`rule_box`；删 `attack_damage`/`attack_cost`，全仓迁移（helpers/test_state/test_engine_setup/core）
- 引擎：`_energy_satisfied` 成本匹配、`_attack_damage` 伤害顺序（基准 → 弱点 ×2 → 抗性 -30，rules-manual §6）、`PRIZE_BY_RULE_BOX`（ex/V/VSTAR=2，VMAX=3）、`check_knockouts()` 任意时机统一昏厥入口（含备战区，铺伤前置框架）
- TDD 红→绿：11 新测试；全量 101 绿 + ruff 零告警；rules-manual §10 映射表同步
- 遗留：chooser、检索/回收原语、特性/道具/竞技场、混乱+宝可梦检查归 task 009+

### 2026-08-28 对照 rules-manual 二次审计 + 首回合进化修复 ✅

- 逐节对照 rules-manual §1–§8 审计引擎骨架：开局/区域公开性/回合结构/行动限制/昏厥胜负均一致（结论见会话报告）
- **P1 修复（TDD 红→绿）**：setup 放置的宝可梦在双方各自第一回合可被进化——`_begin_turn` 无条件清空 `entered_play_this_turn`/`evolved_this_turn` 所致；改为 turn==1（双方第一回合）不清除，第二回合起解锁（rules-manual §1.1「自己最初回合无法进化」）
- 清理 core.py 过时注释（new_game docstring 顺序、头部事实源指向 rules-manual）
- 1 新测试；全量 90 绿 + ruff 零告警

### 2026-08-28 规则说明书 + 规则 skill + 撤退次数修复 ✅

- 抓取简中官网规则页（pokemon.cn/tcg/rules basic_rules01–08 全 8 节）整理为 **`docs/rules-manual.md`**（10 章 + 待核清单附录，含 §10 引擎落点映射表）；pokemon.com EN PDF 被反爬拦截，简中官网为当前可及权威源
- **`docs/rules-reference.md` 重新定位**：正文事实源移交 rules-manual；同步修正——撤退每回合限 1 次、奖赏卡背面对双方隐藏且拿取不看正面/任意顺序、mulligan 奖励抽为「最多等量可不抽」；附录 A 补 4 条决议
- 引擎修复（TDD 红→绿）：**撤退每回合限 1 次**（`PlayerState.retreated_this_turn` + 主阶段行动守卫 + 回合开始重置，`VisibleSelfState` 同步）；render 文案修正奖赏设置为背面非公开
- 规则查询流程 skill 化：`.kimi-code/skills/ptcg-rules`（查询顺序 rules-manual → rules-reference → 决议日志；信息公开性纪律；规则不猜）
- 遗留：rules-manual 附录「待核清单」列出一期暂不影响的细化点（如灼伤数值时代差异、同时昏厥结算顺序），随覆盖扩展逐条核销

### 2026-08-28 对战顺序核对 + 开局规则修正 ✅

- 用户核对官方规则书回复 D 组三问，rules-reference 落稿（§1 游戏准备 ✅ / §4 混乱 ✅ / 附录 A 两条决议）：
  - **开局完整顺序**：掷币定先后 → 各抽 7（mulligan：给对手看过→洗回重抽，对方按次数多抽等量手牌）→ 双方战斗场放置完成 → 各取 6 张奖赏卡
  - **混乱**：只对战斗场生效；攻击时掷 1 次硬币，正面正常发动且不解除，反面招式失败 + 自身 3 伤害指示物（实现随 task 008+ 特殊状态落地）
- 引擎修正（TDD 红→绿，5 失败→全绿）：奖赏卡设置从 `new_game` 移至双方 confirm_setup 后；布阵背面遮罩（setup 阶段 `visible_state` 隐藏对手 active/bench 内容，新增 `face_down_pokemon` 数量字段）；`take_prize` 事件补卡身份、mulligan 事件补展示手牌内容；清理 `new_game` 死代码
- 全量 88 绿 + ruff 零告警；C-4（奖赏卡自选拿取）维持记录待「查看奖赏卡」类效果落地

### 2026-08-28 区域状态管理审计 + P1/P2 修复 ✅

- 审计牌库/手牌/弃牌区/战斗场/备战区/场地的状态管理，对照 PRD §6.3 与 rules-reference 逐区核对
- **P1 规则缺口修复**：主阶段从手牌放置基础宝可梦到备战区（不限次，≤5，当回合登场不可进化联动）——此前只在 setup 阶段枚举
- **P2 隐藏信息修复**：`visible_state` 自己侧改 `VisibleSelfState`——牌库顺序与奖赏卡内容对 Agent 隐藏（只余数量），回合规则标记保留可见（PRD §6.3 合规，M3 启发式/MCTS 前置）
- **P3 记录待核**：mulligan 奖励抽牌时点（引擎现为奖赏放置前）进 rules-reference 附录 A；撤退弃能量选择式、奖赏卡自选拿取列入 M2 随能量类型/查看奖赏类效果落地
- 3 新测试（红→绿）；全量 86 绿 + ruff 零告警

### 2026-08-28 task 007 解释器骨架 + 事件流 + play_trainer ✅

- `dsl/interpreter.py`（ExecutionContext / PRIMITIVES 注册表 / run_effect）+ `dsl/primitives.py`（draw、discard）；事件序列 effect_start → effect_primitive ×N → effect_observe → effect_end，字段对齐 PRD §5.4
- 引擎接入 `play_trainer`：物品不限次、支援者回合限 1 + 先攻首回合禁用 + 次回合重置（PRD §6.6）；`CardDef.trainer_subtype` / `PlayerState.supporter_played_this_turn` / `GameEngine(card_effects=)` / render 模板
- 博士的研究端到端切片跑通；含训练家卡对局同种子 hash 一致；14 新测试，全量 82 绿 + ruff 零告警
- 遗留：chooser 机制（选择式弃牌/检索）、计数表达式求值、道具/竞技场骨架、特性触发器归 task 008+

### 2026-08-28 task 006 DSL schema ✅

- `dsl/schema.py`（CardRef/ActionNode/Effect/CardEffectDoc，frozen + extra=forbid 强校验）+ `dsl/vocabularies.yml` 六段词表（开放字符串不写死代码）+ `dsl/loader.py`（统一 DslError 带文件上下文）
- 词表校验在 loader 层；ActionNode 私有参数走 `args` 逃逸口，逐原语校验随 task 008+ 注册；新增依赖 pyyaml（含 package-data）
- TDD 红→绿：14 新测试；全量 68 绿 + ruff 零告警

### 2026-08-28 task 005 锁定第一套目标卡组与首批原语清单 ✅（M2 启动）

- db WUR 查询（canonical `wur.sql`，窗口 2026-05-30~08-28，master/cn，n_tournaments=6，快照 `data_version=v20260809.1` / `user_version=13`）：**沙奈朵** archetype WUR 第一（0.129，n=56），锁定为 M2 第一套目标卡组
- 代表卡表 `mik_moe:644634`（2026-08-01 冠军，mapping full，60 张校验通过）；27 种卡逐卡核对 text_raw/effect_tags（合规：原文不落库，快照 id + 查询条件为复算锚点）
- 首批原语清单四类归并完成（动作 14 / 选择器 8 / 触发器 5 / 成本限制 6，对齐 db 29+3 词表）；引擎缺口列明（弱点抗性、备战昏厥、trainer/道具/竞技场骨架、混乱状态、跨回合 flag、ex 2 奖赏）
- 边界：本卡组零硬币卡，首批原语不含掷币；基因侵入（copy）与妖精领域（弱点改写）排最后、允许降级；M2 只做镜像对局验收
- 54 测试全绿 + ruff 零告警（纯分析任务，无代码改动）

### 2026-08-25 项目初始化

- PRD v1.0 定稿（D1–D12），README / AGENTS.md / STATUS.md 建立，仓库推送完成
- M1 拆解为 4 个 task（001 脚手架 / 002 随机源+GameState / 003 阶段机+行动枚举 / 004 白板对局端到端），验收标准先行
- 开放问题见 PRD §13

### 2026-08-25 task 001 项目脚手架 ✅

- venv（Python 3.14.6）+ `pip install -e .` 成功；4 测试全绿 + ruff 零告警；`bfsim` 入口可用
- ptcgdb SDK 已接入（`C:/Vibe Project/Pokearena` 可编辑安装，`test_ptcgdb_sdk_importable` 绿）

### 2026-08-25 task 002 随机源与 GameState ✅

- `engine/rng.py` RandomSource（同种子序列一致 / 快照恢复）+ `engine/state.py` GameState（区域完整 / 不可变 / 序列化往返 / 可见视图过滤）
- 17 测试全绿 + ruff 零告警；遗留：牌库实际抽洗操作归 task 003

### 2026-08-25 task 004 白板对局端到端与 M1 确定性验收 ✅（M1 达成）

- `runner/play.py`（play_game / 2 进程并行 / 事件流 sha256）+ `agent/random_agent.py` + `report/render.py` 人类可读回合记录
- M1 硬验收全过：同种子 hash 一致 / 串行与并行逐局一致 / 100 局零异常 / 回合上限判平 / 异常卡组 DeckConfigError
- 54 测试全绿 + ruff 零告警；遗留：play.py 非正式 Runner（M3 接管）

### 2026-08-25 task 003 阶段机与合法行动枚举 ✅

- `engine/core.py` GameEngine（开局+mulligan / 阶段机 / 主阶段四行动 / 昏厥奖赏换上 / 三种胜负）+ `actions.py` / `events.py` / `agent/base.py` Agent 协议
- 45 测试全绿 + ruff 零告警；规则出处逐条注释在 core.py
- 术语修正：knockout 统一为官方用词「昏厥」（全仓替换，规则决议日志首条）
- 新增 `docs/rules-reference.md` 规则事实源（官方规则梳理 + 术语表 + 决议日志附录 A）；PRD 补 §6.6 训练家卡与 ACE SPEC 骨架规划
- 遗留：特殊状态回合间结算（M2 随效果落地）、mulligan 抽牌与让先选择权 Agent 化

## 决策日志

| 日期 | 决策 | 出处 |
|------|------|------|
| 2026-08-25 | D1–D12 | PRD §2 |
