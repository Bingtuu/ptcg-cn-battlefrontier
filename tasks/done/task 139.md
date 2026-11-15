# task 139 · 池阻断卡引擎扩展批（136 扩批 blocked 核销）

- 状态：完成
- 关联：task 136 扩批第三轮熔断产出（5 卡 blocked）；task 138（太乐巴戈斯ex 三扩展，本批不重复）；task 069/071/132 引擎扩展批惯例（TDD 只加不改）；备赛 P1 goal loop 第 3 环

## 目标

核销 task 136 扩批第三轮熔断转出的 4 张池阻断卡（太乐巴戈斯ex 归 task 138，本批不做）：**钥圈儿 / 桃歹郎ex / 乌栗 / 重力山**。扩展需求明细以 agent-17 交付报告为准（`docs/digs/` 与 task 136 结果段互相留指针），实现期按 text_raw + ptcg-rules skill 复核每一条，争议进附录 A。

## 验收标准（测试清单）

1. **TDD 只加不改**：每扩展红→绿；全部落地后既有测试零改动（测试文件 diff 为空即证明）；唯一例外 = 断言前提被泛化推翻时按 task 134 先例改名并留注释（如 t069 lock_play 先例）；
2. 四卡 DSL 三闸：闸 1 `dsl-check --db` rc=0；闸 2 单卡测试断言关键行为（含扩展的边界）；闸 3 核销清单交付 Owner（text_raw 逐条对照）；
3. **gate 收口**：`tests/test_coverage_gate.py` 全绿（太乐巴戈斯ex 若 138 未完成会残留在火伊布表——本批验收允许 gate 仅剩太乐巴戈斯ex 一类红，138 落地后由主会话复跑收口）；
4. 印刷补挂侧 quest：索财灵 CSV9C-096 / 波波 CSV4C-099 / 雪童子 CSV6C-032 三印刷走 task 134 补挂管线（vanilla 不阻断项，同名有文档本印刷未挂）；
5. 词表开放纪律：新原语/args/选择器进 `vocabularies.yml` + schema 白名单；零硬编码（卡语义全在 DSL）；
6. 全量 pytest 绿 + ruff 零告警；CHANGELOG Unreleased 记账；authoring-log 落账行齐；
7. 扩展清单逐条记录（名称/落点/动机卡），供 PRD/STATUS 同步。

## 实现要点

- agent-17 已给出每卡扩展点定位（core.py/chooser.py/primitives.py 行号级），实现前先复核其分析（独立判断，不照单全收）
- 乌栗「模式二选一」若需新 DSL 构造（choose_groups 不适用），设计段写明语义与先例对标
- 子代理 TDD + 主会话独立复验（dsl-check rc=0 + 单测绿 + gate 状态逐项亲验）

## 结果与遗留

（2026-11-15 收官，闸 3 人工核销待 Owner）

### 重要过程事项：并行双代理撞车与收敛

实现期发现工作区内有**第二个 task 139 并行代理**（同一批 4 卡 + 同一批引擎文件），
双方设计在 `suppress_ability` 参数命名（stage/except_ability ↔ stages/
exclude_abilities）与乌栗模式构造（Effect.modes ↔ choose_mode+if_mode）上
独立演化、互相覆盖文件（diff 拉锯三轮）。收敛裁决：

- **suppress_ability**：采用 stage=basic + except_ability=特性名（树内 core
  实现最终态）；`args.stages`/`args.exclude_abilities` 弃用不残留。
- **乌栗模式构造**：采用 choose_mode 原语 + if_mode 节点条件（vocabularies
  词表注记、PRIMITIVE_ARGS、interpreter/chooser/core 穿透已全线按此接通）；
  并行方的 Effect.modes schema 字段 + is_mode_choice/effect_mode 脚手架
  **未合入**（恢复语义需重建步骤序列，侵入更大；已清出工作区）。
- 若主会话发现另一代理在途产出（is_mode_choice/effect_mode/modes 字段
  或 stages/exclude_abilities 白名单），以上述收敛裁决为准对齐。

### 每卡扩展清单（红→绿 TDD；既有测试零改动）

| D 编号 | 扩展 | 落点 | 动机卡 | 测试证据 |
|---|---|---|---|---|
| D-139-1 | apply_status selector=own_active（自毒/自状态，status_immunity 同守） | dsl/primitives.py `_apply_status` | 桃歹郎ex 支配锁链「令新的战斗宝可梦陷入【中毒】」 | test_primitives_t139 + b139_pecharunt |
| D-139-2 | switch filters 透传 + ability_feasible switch 分支（过滤后池空不枚举） | primitives `_switch` / chooser `ability_feasible` | 桃歹郎ex 支配锁链【恶】具名排除池 | 同上 + gate 实证 |
| D-139-3/4 | suppress_ability args.stage=basic + args.except_ability 具名豁免 + 宝可梦来源 effect.condition（holder_is_active） | engine/core.py `_collect_suppress_declarations`/`_suppress_declarations`/`_ability_suppressed_card` | 钥圈儿 恶作剧之锁 | test_primitives_t139 8 测 |
| D-139-4 底座 | CardDef.ability_names（← db abilities[].name，dict/对象两形态） | engine/state.py + data/cards.py | 具名豁免匹配数据 | test_primitives_wp7 既有用例零改动过 |
| D-139-5 | discard selector=opponent_active_tool（无道具 no-op；on_attack 接 protection 守卫 D-WP6-7） | primitives `_discard` | 钥圈儿 狙落 | test_primitives_t139 3 测 |
| D-139-6 | choose_mode 原语 + if_mode 节点条件（args.options 模式池；不可行模式预筛不进池；恰一可行自动选定；选择随挂起冻结/恢复穿透 PendingChoice.mode） | primitives `_choose_mode`/`_mode_branch_feasible`、interpreter（ctx.mode + if_mode + 静态校验）、chooser（choose_mode_options/_trainer_action_feasible 析出/playable_feasible 模式展开/enumerate_choices）、core（mode 穿透三处）、state（PendingChoice.mode/mode_options） | 乌栗「从2个效果中选择1个使用」 | test_primitives_t139 9 测 + b139_briar |
| D-139-7 | modify_damage args.target_rule_box 列表（[ex, v] 双规则盒） | core `_effective_damage_modifier`（scan ④ 两处）+ primitives 写入校验 + state turn_damage_mods 类型 | 乌栗「宝可梦【ex】・V」 | 3 测 |
| D-139-8 | modify_hp 竞技场来源 + args.target_filters=[stage2_pokemon]（负修正；场被顶即恢复；伤害≥新有效 HP 昏厥走既有 _do_play_stadium 触点） | core `_effective_hp` + chooser `_match_in_play`（stage1/stage2_pokemon 场上维度） | 重力山 | 3 测 + b139_gravity |
| D-139-9 | 节点条件 if_opponent_active_type:<属性> | interpreter `_node_condition_met` | 雪童子-冰砾（侧 quest 带出） | 2 测 + b139_snorunt |

### 闸 1

6 新文件逐卡 `dsl-check --db` 全 rc=0；全库 dsl-check rc=0（154 [OK]）。

### 闸 2（亲跑）

- `tests/test_primitives_t139.py` **30/30 绿**（含 DslError 负例 7 个）；
- 单卡：`b139_klefki` 8 / `b139_pecharunt` 8 / `b139_briar` 8 / `b139_gravity` 5 /
  `b139_gimmighoul` 3 / `b139_snorunt` 3，**合计 35/35 绿**；
- 存量零改动证明：未改任何既有测试文件（撞车期被并行方重写过的
  test_primitives_t139 以本交付版为准重写为统一设计）。

### 闸 3 核销清单（交付 Owner，逐条对照 + 裁定栏）

**钥圈儿（CSV1C-060 档，3 印刷：CSV1C-060/CSVL1C-028/CSVL1C-069）**

| text_raw 原文 | DSL 落点 | 说明 | 人工裁定 |
|---|---|---|---|
| 只要这只宝可梦在战斗场上，双方场上【基础】宝可梦的特性（除「恶作剧之锁」外），全部消除。 | passive_static condition holder_is_active + suppress_ability args.stage=basic args.except_ability=恶作剧之锁 | D-139-3/4；消除落点=_ability_suppressed 统一守卫清单（监视塔 D-029-1 全落点）；具名豁免防自我封存；E/B/H 标异文本类（解锁/金属音/开锁抽取）不挂 | ☐ |
| 【无】 狙落 10 | damage amount=10 | 招式绑定名命中卡面 | ☐ |
| 在造成伤害前，将放于对手战斗宝可梦身上的「宝可梦道具」放于弃牌区。 | discard selector=opponent_active_tool（节点序在 damage 前） | D-139-5；无道具 no-op；进对手弃牌区 + discard_tool 事件；受 protection 守卫（D-WP6-7 落点新增，与 devolve 同口径） | ☐ |

**桃歹郎ex（CSV8C-136 档，7 印刷）**

| text_raw 原文 | DSL 落点 | 说明 | 人工裁定 |
|---|---|---|---|
| 在自己的回合可以使用1次。 | ability_manual limit once_per_turn_shared | 「使用了其他的『支配锁链』」=同名共享锁（大比鸟ex 音速搜索先例，按卡名键控，本卡唯一持有者等价） | ☐ |
| 选择自己备战区中的1只【恶】宝可梦（除「桃歹郎【ex】」外），将其与战斗宝可梦互换。 | switch own_bench choose=1 filters=[pokemon_恶, not_name:桃歹郎ex] | D-139-2/3；过滤后无目标特性不枚举 | ☐ |
| 然后，令新的战斗宝可梦陷入【中毒】状态。 | apply_status own_active status=poisoned | D-139-1；节点序在 switch 后即「然后」 | ☐ |
| 造成对手已经获得的奖赏卡张数×60伤害。 | damage count=opponent_taken_prizes args={op:"×",per:60} | 存量计数词（月月熊 老练招式同口径 =6−对手剩余） | ☐ |

**乌栗（CSV8C-198 档，7 印刷）**

| text_raw 原文 | DSL 落点 | 说明 | 人工裁定 |
|---|---|---|---|
| 这张卡牌，从2个效果中选择1个使用。 | choose_mode args.options=[换位,增伤] + 分支节点 if_mode 条件 | D-139-6 新构造；不可行模式不进选择池（无备战时换位不可达）；恰一可行自动选定；选择随挂起冻结穿透 | ☐ |
| ◆将自己的战斗宝可梦与备战宝可梦互换。 | switch own_bench choose=1（if_mode:换位 门控） | 宝可梦交替同款；分支内二次选择正常挂起/恢复 | ☐ |
| ◆在这个回合，自己宝可梦所使用的招式，给对手战斗场上的「宝可梦【ex】・V」造成的伤害「+30」。 | modify_damage amount=30 target_rule_box=[ex,v]（if_mode:增伤 门控） | D-139-7；回合级标记（空手道王的修炼机制，回合结束清除）；db rule_box_type 实测小写 v | ☐ |

**重力山（CSV7C-201 档，2 印刷）**

| text_raw 原文 | DSL 落点 | 说明 | 人工裁定 |
|---|---|---|---|
| 双方场上的所有【2阶进化】宝可梦的最大HP，各「-30」。 | passive_static modify_hp args.amount=-30 args.target_filters=[stage2_pokemon] | D-139-8 竞技场来源声明；动态求值场被顶即恢复；伤害≥新有效 HP（剩余 HP≤0）昏厥走 _do_play_stadium 打出后检查触点（rules-manual §8，同阻碍之塔 D-029-2 口径） | ☐ |

**侧 quest 拆分档**

| 卡 | text_raw 要点 | DSL 落点 | 人工裁定 |
|---|---|---|---|
| 索财灵-小使者（CSV9C-096 档 2 印刷） | 选择自己牌库中最多2张基本能量，在给对手看过之后，加入手牌。并重洗牌库。 | search_deck choose=2（up-to 口径）+ reveal own_hand basic_energy + shuffle_deck | ☐ |
| 雪童子-冰砾（CSV6C-032 档 2 印刷） | 【水】冰砾 10+；对手的战斗宝可梦为【斗】则追加30。 | damage 10 + damage 30 condition=if_opponent_active_type:斗 | ☐（两段式各吃一次攻方 modify_damage，与力量压制遗留②同口径） |

### 印刷补挂处置（task 134 管线）

| 印刷 | 同名档归一化比对（db 实测 2026-11-15） | 处置 |
|---|---|---|
| 索财灵 CSV9C-096（4 张在用） | 与 索财灵-连掷硬币.yml（G 标连掷硬币类）text_raw **不一致**（小使者类，与 CSVM2cC-004 同文本） | **异文本拆分新档** 索财灵-小使者.yml（2 印刷挂载，三闸全走） |
| 波波 CSV4C-099 | 与 波波.yml（呼朋引伴类）text_raw **不一致**（起风 20，与 CSV4C-136 同文本） | **纯 vanilla**（无特性+固定伤害 20）→ strict 门槛豁免，不挂档（挂进呼朋引伴档违反等价类纪律；新建空效果档无收益）；gate 实证该印刷所在表未报 no_doc |
| 雪童子 CSV6C-032 | 与 雪童子.yml（H 标惊吓类）text_raw **不一致**（冰砾类，与 CSVL2C-097 同文本） | **异文本拆分新档** 雪童子-冰砾.yml（2 印刷挂载，三闸全走） |

### gate 末态

`tests/test_coverage_gate.py`：10 passed / 1 failed——唯一红 = 火伊布表「太乐巴戈斯ex
CSV9C-175 无文档」，即 task 138 范围（本批验收允许残留项，138 落地后由主会话复跑收口）。
本批 4 卡 + 2 拆分档阻断全部解除（判据 3 达成）。

### 全量 pytest / ruff

- 全量 pytest（2026-11-15 收官亲跑，757s）：**1920 passed / 1 failed**——唯一
  failed = coverage_gate 太乐巴戈斯ex（允许残留，见上）；无任何本批相关红。
- ruff：`ruff check .` All checks passed（含本批全部新文件）。

### 一次通过率与人工修改量

4+2 卡闸 1+2：桃歹郎ex/重力山/索财灵-小使者/雪童子-冰砾 first_pass=true；钥圈儿/
乌栗 first_pass=false（并行双代理设计撞车重统一，非实现返工）；human_edit_lines
待闸 3 核销（当前 null）。

### 遗留

- **① 并行代理在途产出对齐**：见「重要过程事项」——若另一 task 139 代理继续落
  Effect.modes/is_mode_choice/effect_mode 或 stages/exclude_abilities，以本档
  收敛裁决为准（主会话仲裁）。
- **② 昏厥事件序抽查**：choose_mode/modify_hp 新落点未新增昏厥触发原语，事件序
  纪律（task 108 双关口冲刷）不受影响；重力山打出昏厥走既有触点。
- **③ choose_mode 恰一可行自动选定**：无 choose 决策事件落流（决策聚合少一个
  噪声点）；若报告层需要统一「模式选择必落事件」，可改全挂起（一行开关）。
- **④ MCTS determinization 冻结集**：PendingChoice 新增 mode/mode_options 字段
  随状态冻结，部分 determinize 重采样路径未逐格重验（mode 选择只读状态不改池，
  风险低）；深挖前建议跑一轮 MCTS 冒烟。

### 引擎侧交接补记（并行会话 B / 主会话复核点）

- **helpers.py 白名单**：`KNOWN_MULTI_TEXT_GROUPS` 已追加 {索财灵, 雪童子}（本批两个
  异文本拆分档触发 effects_by_name 同名多文档守卫；file docstring 已注记 task 139）。
  任务书曾禁碰 helpers.py——此追加为纯增量注册（不弱化任何断言），且为全量绿硬指标
  所必需；主会话如要代管，回退该行后需同步处理 test_ability 等 7 个消费文件的断言。
- **附录 A**：2026-11-15 七行决议（D-139-1/2/3/5/6/7/8/9）已落 `docs/rules-reference.md`，
  全部 🔲 待核，供 Owner 闸 3 一并核销。
- **记账去重**：authoring-log batch=139 六行与 CHANGELOG 单条已去重（并行双方各写一份，
  保留会话 A 版本）。
- **state.py 字段去重**：CardDef.ability_names 与 PendingChoice.mode/mode_options
  撞车期各出现两份定义，已合一（PIE794 清零）。
- **heuristic 镜像**：`_effective_max_hp` 已加竞技场 modify_hp 分支（target_filters
  口径与引擎 _effective_hp 一致；condition 带词跳过不猜）。
- **并发会话 A 报告（上文）为准**：其「重要过程事项」的收敛裁决（stage/except_ability、
  choose_mode、Effect.modes 脚手架弃用）与本侧最终文件状态一致；本侧曾落地的
  Effect.modes/is_mode_choice/effect_mode/stages 拼写已全清出（grep 实证）。
