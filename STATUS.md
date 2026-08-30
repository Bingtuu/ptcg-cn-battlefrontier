# STATUS.md — ptcg-cn-battlefrontier

> 进展速记：每完成一步更新。规范对齐 db 项目（进展记在这里，不进 README）。

## 当前

**M5 进行中**：task 024 ✅（卡组池锁定 + LLM harness）、task 025 ✅（批 1：小原语批 + A 级处理）。**卡池 v1 = 9 套（全窗口 WUR 覆盖 53.4%，`config/target-pool.v1.yml`）**。缺口 81 张（`docs/m5-coverage-plan.md`）：done 15（DSL 11 + vanilla 4）/ blocked 32 / pending 34（B/C 级）。**关键发现：A 级初判失真严重**（46 张初判「现有原语可写」实测仅 10 张可直接写）——task 026 需按批 1 归并的解锁清单 re-scope。LLM harness 质量数据：批 1 新写 DSL 12 张，first_pass 10/12；**13 张 gate3 待用户核销**（友好宝芬已核销）。
M1–M4 已达成。下一步：task 026（B 级批，先 re-scope：filters/conditions 高频解锁项 + trigger_on_event 分发 + place_damage_counters）。
ptcgdb SDK 已接入（`C:/Vibe Project/Pokearena` 可编辑安装）。

## 里程碑

- ✅ M1 引擎骨架（白板对局 + 同种子复现）——task 001–004 全 ✅（2026-08-25）
- ✅ M2 DSL + 解释器 + 首批原语（第一套目标卡组）——task 005–008、010–017 全 ✅
- ✅ M3 启发式 Agent + Runner + 结果库（百局端到端）——task 018–020 全 ✅（2026-08-29）
- ✅ M4 报告层（胜率 / 决策聚合 / 换卡敏感性）——task 021–023 全 ✅（2026-08-30）
- ⬜ M5 覆盖扩展 + LLM 辅助编写试验
- ⬜ M6 校准基线 + 一期验收

## 工作记录

### 2026-08-30 task 025 批 1：小原语批 + A 级 46 张 ✅

- **小原语批 5 项（子代理 TDD）**：`coin_flip` + 节点级 condition 门控（if_flip_heads/tails，掷币结果经 PendingChoice.flip_result 穿透恢复、不占选择游标）/ `heal` / `switch` own_bench / `bounce`（整叠回手+附着物弃置，附录 A 三条决议含 🔲 待核）/ `modify_damage` 声明式结算（`_effective_damage_modifier` 仿 `_effective_hp`，三路径接入 §6 顺序 2）。代码注册 filters `evolved_pokemon`、condition `own_active_is_basic`；词表 actions +4、selectors +1
- 代表卡 4 张（捕获香氛/交替推车/弗图博士的剧本/不服输头带）闸 1/2 一次通过 4/4，gate3 待核销；交替推车 heal 前置取舍已记决议
- **A 级 swarm 7 波**：done 8（吉尼亚/波波/能量输送/宝可梦交替/皮宝宝/朋友手册/彷徨夜灵/玛俐的捣蛋小妖）+ vanilla 4 + blocked 32；批 1 新写 DSL 12 张 **first_pass 10/12**（2 例 false 均为测试侧笔误、DSL 零修改）；分片测试 `tests/test_dsl_cards_b1_w*.py`
- **关键发现：A 级初判失真严重**——effect_tags 归判 vs text_raw 实测，46 张初判「现有原语可写」仅 10 张可直接写（约 22%）；blocked 32 张的解锁需求已归并（filters/conditions/原语扩展/数据管道四类，详见 task 025.md 批 1 质量小结）→ **task 026 需 re-scope**
- 落账：coverage-plan 81 行状态全量更新（done 15 / blocked 32 / pending 34）；authoring-log 批 1 计 49 条；m2_closeout 计数断言改下限口径（≥28，M5 持续增长）
- 全量 388 绿 + ruff 零告警（含沙奈朵镜像同种子 hash 回归）
- 遗留/待用户：①13 张 gate3 待核销（代表卡 4 + done 8 + 友好宝芬已核销）；②同名组多文本印刷归组口径（彷徨夜灵/波波/皮宝宝目前只覆盖池内实际印刷）；③task 026 re-scope 确认

### 2026-08-30 task 024 卡组池锁定 + LLM harness ✅（M5 启动）

- **卡池 v1（9 套，`config/target-pool.v1.yml` + `data/pool.py` 强校验 loader）**：调研发现退赛断点——db 仅一个合法性快照（standard-2026-07-16），原 WUR top-9 中放逐Box/雷吉铎拉戈/洛奇亚/密勒顿 4 套无任何合法 full 卡组（数据止于 08-05）；用户决议替补补位（退赛后窗口 WUR 前列：玛俐长毛巨魔雪妖女/赛富豪/多龙巴鲁托/赫普的苍响）。代表卡组全过当前快照校验，全窗口覆盖 53.4%
- **缺口全表 `docs/m5-coverage-plan.md`**：81 张（A46/B17/C18），级别=标签归并初判、逐卡以 text_raw 为准；V-UNION 缺口 0
- **LLM harness**：`.kimi-code/skills/dsl-authoring`（输入装配/输出契约/三道闸/不猜纪律/词表扩展路径）；闸 1 工具化 `bfsim dsl-check`；质量日志 `cards/authoring-log.jsonl`（JSONL，不落卡文本，合规）
- **自验（子代理执行友好宝芬）**：流程完整走通且暴露真问题——缺 HP 上限过滤器词（按不猜纪律 blocked 上报）→ 注册 `hp_max:N` 参数化过滤器（chooser）解锁；skill REFACTOR 五处（闸 1 盲点 filters 不校验需闸 2 兜底 / 词表扩展路径 / 注释格式约定 / 样例映射 / 测试函数中文命名）；自验卡过闸 1+2，日志首条 first_pass=false（测试命名返工，严格口径）
- TDD 12 新测试（pool loader / dsl-check 三分支 / 自验卡 4 项）；全量 334 绿 + ruff 零告警
- 遗留：批 1 A 级 46 张归 task 025；友好宝芬 gate3 待用户核销

### 2026-08-30 task 023 换卡敏感性 ✅（M4 达成）

- 实验定义扩展 `variants`（PRD §9 一次提交多组实验）：`SwapCfg{side,out,out_count,in,in_count}`（`in` 走 pydantic alias）+ `VariantCfg{name,swaps}`；校验不猜——Σout≠Σin / 重名 / 未知 side / swaps 空 / out 存量不足 / in 卡名未命中 db 全显式报错
- `apply_swaps` 纯函数（60 张守恒）+ `prepare_variant`（换入卡经 db 解析、DSL 文档补入 card_effects、deck id 标注 `[variant:名]`）+ `execute_group`/`run_group`（baseline + variants 同种子区间依次跑，配对可比）
- 结果库 experiments 加 `group_name`/`variant` 两列；旧库文件打开自动 ALTER TABLE 迁移（FR-10 三层表骨架不变，仅加列）
- `report/sensitivity.py`：ΔWR 95% CI（非合并 SE）+ 两比例 z 检验（合并 SE 双侧，Φ 用 math.erf 手写不引 scipy）；参考值手算对拍（65/100 vs 35/100 → z≈4.24264、p≈2.21e-5）；n=0 记 None 标「不可用」不除零
- CLI：`bfsim run` 遇 variants 定义自动跑整组并逐个打印实验 id + sensitivity 用法提示；新增 `bfsim sensitivity <base> <variant...>` 并排报告
- 真机冒烟（gardevoir-swap 20 局 ×2 组）：baseline 1 局失败为已知 DslError（copy_attack 套娃，task 020 显式不猜项），失败局正常落库不拖垮分组；并排报告数字合理
- TDD 22 新测试（参考值对拍 / 定义校验分支 / apply_swaps / 分组确定性 / 旧库迁移 / CLI）；全量 322 绿 + ruff 零告警；示例 `experiments/gardevoir-swap.example.yml` 入库
- 遗留：M5 覆盖扩展 + LLM 辅助编写试验（M4 已收口）

### 2026-08-29 task 022 choose 决策事件 + observe 锚点 + 决策聚合报告 ✅

- 引擎：`_do_choose` 恢复前落 `choose` 事件（effect_id/card/pool/chosen iids+chosen_names）；`_resolve_choose_names` 扫描双方全区域建 iid→名映射，opponent_active_attack 池解析为招式名；嵌套帧（task 020）effect_id 含 `copy>` 标注
- cards/ 七卡补 `observe: [key_search]` 锚点（高级球/巢穴球/大地容器/厉害钓竿/夜间担架/秘密箱/派帕；observe 为开放字符串，loader 不校验）
- `report/decisions.py`：按（侧, 卡, 池, 选择标签）聚合——occurrences 次数 / games 覆盖决定局（同局重复只计一次）/ 胜率+Wilson CI（复用 winrate.wilson_ci）；effect_observe 锚点经 effect_id 同局关联；空选 = 「（放弃）」；只统计完成局
- CLI `bfsim report --decisions` 追加分节；render.py 补 choose 模板
- TDD 14 新测试（合成库逐项对账 + 嵌套 copy 双事件 + 锚点关联 + CLI）；全量 300 绿 + ruff 零告警（F821 补 PendingChoice 导入——`from __future__ import annotations` 下运行时不炸、仅 lint 捕获，记一笔）
- **M3 基线重记**（choose 入流改变 events_hash，预期变更）：100 局 0 失败、并行 vs 串行逐局一致、胜负 65/35 不变；真实库决策聚合首跑可用（如厉害钓竿 60 次决策分布 × 胜率）
- 遗留：换卡敏感性（variants 配对实验 + ΔWR 显著性）归 task 023，M4 收口

### 2026-08-29 task 021 胜率报告 + bfsim report ✅（M4 启动）

- `report/winrate.py`：`wilson_ci` 手写（z=1.959964，不引 scipy——依赖纪律，正确性靠 4 组参考值对拍 ±1e-3 锁定）；`winrate_report`（完成/决定/平局/失败分层口径，先后手拆分，avg_turns 含平局）；`format_report` 文本（meta 全要素：实验 id/名称/种子区间/代码+数据版本/局数）
- `ResultsDB.experiment()` 访问器；`bfsim report <id> [--results]`（未知 id 明确报错 rc=1）；argparse help 的 `%` 需 `%%` 转义（坑记一笔）
- 口径定稿：胜率分母=决定局（平局单列）；决定局为 0 → 胜率/CI 记 0 不除零
- TDD 13 新测试（11 局合成库逐项对账 + 边界 + CLI）；全量 286 绿 + ruff 零告警
- 真实报告首跑（M3 百局库）：A(启发式) 65.0% CI 55.3..73.6，先攻 70.7% / 后攻 61.0%，平均 10.4 回合
- 遗留：决策事件 + observe 锚点聚合归 task 022；换卡敏感性（variants 配对实验）归 task 023

### 2026-08-29 task 020 copy_attack 嵌套 chooser（二级挂起帧）✅

- `PendingChoice` 增嵌套帧字段：`inner`（内层效果定位：DSL 文档卡名+招式名）/ `outer_cursor` / `outer_choice`；`NeedChoice` 增 `inner`/`inner_cursor` 传播字段（外层 run_effect 覆盖 cursor 前转存内层游标）
- copy_attack：内层 run_effect 挂起从 DslError 改为标注传播；`ctx.inner_done` 标记外层恢复时只回结果（不重复执行内层、不重复发 copy_attack 事件）；内层 effect_id 标注 `>copy:招式名`（事件流可观测）
- `_run_or_suspend` 嵌套恢复路径：inner 定位内层效果续跑 / 同层再挂起沿用帧 / 内层完成带 inner_done 恢复外层 copy 节点续跑后续节点 / 层级 >1（套娃复制）显式 DslError 不猜
- HeuristicAgent `_pick_choose` 池映射补对手场上宝可梦（opponent_pokemon_any 类选择评分可见，确定性不变）
- TDD 7 新测试全红→绿（真实卡回归：梦幻ex 复制吉雉鸡ex 残忍箭矢 / 内层双选择 / 外层续跑 / 套娃 guard / 重放 hash / Agent 驱动）；全量 273 绿 + ruff 零告警
- M3 百局复验：0 失败、并行 vs 串行逐局一致、copy_attack 实际触发 10 次正常结算（A胜 65/B胜 35——Agent 决策口径变化属预期）

### 2026-08-29 task 019 实验定义 + 正式 Runner + 结果库 + bfsim run ✅（M3 达成）

- `runner/experiment.py`：ExperimentDef（Pydantic 强校验：未知 agent type/参数名/来源 不猜报错）+ parse_decklist（`N 卡名` 行格式，经 db search_cards 解析 + 60 张校验）+ build_agents（worker 内同种子规则重建，与 play.py 默认偏移一致）+ prepare/execute/run 三段式；多进程 spawn 池 imap 保序，worker 载荷纯可序列化配置
- `runner/results_db.py`：三层表 experiments/games/game_events（WAL；games 带 error 列——DSL 显式报错等失败局落库继续实验，不掩盖不崩溃）；`play.py` GameResult 补 first_player（§8.3 先后手）
- `bfsim run <实验.yml> [--workers N] [--results PATH] [--db PATH] [--cards-dir DIR]`：装载告警透传，完成回显实验 id/胜负平/失败数/数据版本/种子区间；cli 补 `__main__` 入口
- 验收：TDD 23 新测试（schema/解析/构建/落库/生命周期/CLI e2e 真实卡组）；§8.4 硬验收双保险——stub 卡组两次重跑+串并一致（CI），真实沙奈朵镜像 100 局 4 workers vs 串行重跑逐局一致（实测）
- **M3 里程碑实跑**：heuristic vs random 100 局 = A胜 63/B胜 37/平 0/失败 0，4 workers 约 4.4s（性能基线首记录，PRD §8.2 2000 局分钟级口径达标）；数据版本 2026-07-16 (user_version=13)
- 全量 266 绿 + ruff 零告警；`results/` 进 gitignore；示例实验 `experiments/gardevoir-mirror.example.yml` 入库
- 遗留：copy_attack 嵌套 chooser（残忍箭矢运行时选择）归 task 020——本次百局 0 失败但 CLI 初测曾触发，属已知引擎缺口非 Runner 问题；M4 报告层（Wilson CI/决策聚合/换卡敏感性）

### 2026-08-29 task 018 通用启发式 Agent（M3 启动）✅

- `agent/heuristic.py`：`HeuristicParams` 参数对象（评分权重 + 评估函数五因子权重 + 决策开关全暴露，默认值=PRD 通用启发式）；`pokemon_score`（HP+最大招式伤害+撤退费惩罚，D10 只用通用字段不按卡名分支）；`evaluate` 评估函数（奖赏差/场面战力/手牌质量/能量就绪度/牌库资源线性加权，纯函数为 MCTS rollout 预留）
- 决策规则：开局布阵最高分优先（`max_bench_setup=3` 后 confirm）→ 主阶段排序「特性→进化→能量→斩杀检测→道具→物品→支援者→竞技场→攻击→end_turn」；能量附着「仍有付不起的招式才补能」（全就绪不浪费每回合 1 次）；斩杀检测读弱点 ×2/抗性 -30，凌驾物品/支援者；保守撤退（战斗场无就绪招式且备战区有就绪打手才撤）
- chooser 选择策略：按池内卡评分取最高分子集；promote 取最高分备战；tie-break 全部 iid/下标升序，**不消费引擎随机源**（确定性测试锁定：同视图两次调用 + 跨实例一致）
- `play_game` 增 `agents` 可选注入（默认仍为双 RandomAgent，task 019 Runner 复用）
- TDD 24 新测试（16 首红后修两处口径：能量跳过条件「存在付不起的招式」、evaluate 奖赏差符号=我方领先为正）；全量 243 绿 + ruff 零告警
- 遗留：HeuristicAgent vs RandomAgent 胜率对照实验、参数进实验定义 YAML 归 task 019；评估函数目前仅用于报告/测试，未参与决策（决策为规则式，符合 PRD §7.2 允许口径）

### 2026-08-29 task 017 M2 收口批：三特性 + 基因侵入 + 竞技场骨架 + 支援者两枚 ✅

- 化危为吉：`own_ko_during_opponent_turn` 跨回合标记（对手回合内昏厥置位、我方回合结束 `_on_turn_end` 清除——四条回合结束路径合并）+ condition 注册词；限次复用 once_per_turn_shared
- 亢奋脑力：参数化 condition 前缀 `holder_has_energy:<属性>` + `move_damage_counters` 原语（两段式 chooser；「最多3个」降级 min(3, 来源) 全转，记决议）
- 妖精领域：声明式 `modify_weakness` + `GameEngine._effective_weakness`（龙无弱点=赋予；白板攻击与 DSL damage 两路径共用；备战不结算弱点贯穿规则不变）
- 基因侵入：`copy_attack` 原语 + `opponent_active_attack` 招式维度池（pool_iids=招式索引）；被复制招式不付能量；DSL 绑定以我方视角结算（嵌套挂起=显式 DslError）；白板按我方属性结算弱点
- 竞技场骨架：play_stadium（每回合限 1/同名不可/旧场进 stadium_owner 弃牌区）+ use_stadium（stadium_grant 每方每回合 1 次，可行性门复用 playable_feasible）；深钵镇检索基础（除规则盒 basic_pokemon_no_rule）入备战
- 奇树：`hand_to_deck_bottom`（own/opponent，shuffle 后库底）+ draw 扩展（str 计数表达式 + opponent_deck）；派帕：纯 YAML 组合（两段 search_deck + shuffle）
- 特性枚举补 condition 门（task 011 只查 limit+可行性；未知词 DslError 不猜）
- 定义库 23 卡（+深钵镇/奇树/派帕，四卡补 effect）；TDD 24 新测试（20 首红）；全量 219 绿 + ruff 零告警；真实卡组两 seeds 整局 hash 一致、use_stadium 实际发动
- 遗留：chooser 嵌套游标 / 数值选择建模 / 宝可梦检查（中毒灼伤）/ 同时昏厥顺序 归 M3+ 按需

### 2026-08-29 task 016 evolve 原语（神奇糖果跳阶 + 学习器「进化」）+ 授予招式执行 ✅

- `evolve` 原语注册双模式：`skip_stage`（神奇糖果：手牌 stage2 → 同链基础两段式 chooser，卡面限制「最初回合」走可行性门 first_turn、「刚出场不可」走目标池 exclude entered_play_this_turn）+ `from_deck`（学习器「进化」：≤2 备战逐只牌库检索 evolves_from 匹配形态，即选即进化，carry=(已进化数, 当前, *剩余)）
- 链拓扑数据驱动：`CardDef.evolution_chain` ← db evolution_chain_id（引擎零硬编码）；chooser 新增参数化过滤器前缀 `evolves_from:<名>` / `evolve_skip:<chain>`、`stage2_pokemon`、own_bench 池
- 授予招式执行：attached_tool 招式并入攻击枚举（索引接自身后、能量持有者支付、DSL 文档与效果源取道具卡）；无绑定的授予招式维持不枚举
- cards/ 神奇糖果（CSVH1C-045）入库 + 学习器补 on_attack 绑定（定义库 20 卡）；进化突变统一 `_apply_evolution`（状态清除/伤害保留/evolved_this_turn + evolve 事件）
- TDD 12 新测试红→绿一次通过；全量 195 绿 + ruff 零告警；真实卡组（mik_moe:644634 含两卡）装载零告警 + 整局同种子 hash 一致
- 遗留：竞技场骨架（深钵镇 stadium_grant）/ 剩余特性三枚 / 基因侵入 copy 归 task 017

### 2026-08-29 task 015 宝可梦道具骨架 + 勇气护符 passive HP + 招式学习器框架 ✅

- `InPlayPokemon.attached_tool` 状态位；`attach_tool` 主阶段行动（trainer_subtype==宝可梦道具、每只限 1、不限次，规则行动无需 DSL 文档）；昏厥整叠含道具进弃牌区
- `GameEngine._effective_hp`：道具 passive_static 的 modify_hp 声明式求和（condition holder_is_basic 判定栈顶 stage）；check_knockouts 与 would_survive_20 守卫（chooser hp_of 透传，ability_feasible 签名改 (effect, engine, player)）全走有效 HP；进化后加成立即失效
- `_discard_turn_end_tools`：grant_attack args.discard_at_turn_end 道具在自己回合结束四条路径（end_turn / 白板攻击 / DSL 攻击 / 混乱反面）统一弃置，对手回合末不弃；无 on_attack 绑定的授予招式不枚举（task 016 解锁）
- cards/ 勇气护符（CSV1C-118）+ 招式学习器 进化（CSV5C-119）入库（注释引用 text_raw 原文），定义库 19 卡；词表 actions 补 modify_hp / grant_attack
- TDD 11 新测试（8 首红）；全量 183 绿 + ruff 零告警；含道具卡组同种子 hash 一致
- 遗留：学习器「进化」招式 on_attack + 神奇糖果（evolve 跳阶）归 task 016；竞技场骨架 / 剩余特性三枚 / 基因侵入 copy 归 016/017

### 2026-08-29 task 014 物品批五张 + switch/move_energy 原语 ✅

- 大地容器（弃1→检索≤2基本能量）/ 秘密箱（弃3→四类训练家各≤1顺序检索）/ 厉害钓竿（≤3回牌库 up-to）/ 反击捕捉器（condition 奖赏比多门 + gust 互换 + 换下清状态）/ 能量转移（两段式转附，exclude 来源）
- chooser：trainer 子类过滤器四词、新池 own_attached_energy/opponent_bench、`NeedChoice.exclude_iids`、`condition_met` 注册表（未知词 DslError）、可行性门增 switch/move_energy 落点（无效果不可使用）
- 原语：switch / move_energy / recover_from_discard 增 destination=deck；词表 selectors 补 own_attached_energy
- 定义库 17 卡；TDD 10 新测试（8 首红）；全量 172 绿 + ruff 零告警；含物品卡组同种子 hash 一致
- 遗留：神奇糖果 evolve 跳阶 / 道具·竞技场骨架 / 剩余特性三枚 / 基因侵入归 task 015+

### 2026-08-29 task 013 混乱状态 + apply_status + 精神幻觉 ✅

- 混乱全链路（D1 决议落地）：攻击入口掷币——正面正常结算不解除 / 反面招式完全失败
  （白板/DSL 同检，无 effect_primitive）+ 自身 3 指示物 → check_knockouts
- `GameState.turn_after_promote`：自我昏厥换上后回合权给对手（默认换上方回合不变）
- `apply_status` 原语（status 对齐 SpecialCondition 枚举，未知词 DslError；前序致昏厥空结算）
- cards/愿增猿.yml 入库（定义库 12 卡）；TDD 9 新测试（7 首红）；全量 162 绿 + ruff 零告警
- 遗留：宝可梦检查（中毒/灼伤回合间）随来源卡落地；剩余特性三枚 / 基因侵入 / 道具·竞技场归 task 014+

### 2026-08-29 task 012 on_attack 招式效果框架 + 变量伤害 ✅

- `Effect.attack` 绑定字段（PRD §5.1 同步）：on_attack 绑定招式的伤害与效果全经 DSL 结算，AttackDef.damage 退为装载/展示数据（奇迹之力 190 单次结算测试锁定）
- 原语 `damage`（固定/变量公式 base+per×n、per×n；opponent_active 自动目标 / opponent_pokemon_any chooser 选目标；弱点抗性仅战斗场结算——备战不计算是贯穿规则）+ `clear_status`；计数表达式六词求值（未知词 DslError 不猜）
- 引擎：攻击枚举含 DSL 绑定纯效果招式；completion="attack" 完成推进对手回合，昏厥 promote/终局不覆盖
- 定义库 11 卡（+吉雉鸡ex 残忍箭矢 / 吼叫尾 凶暴吼叫 / 奇鲁莉安 精神强念 / 莉莉艾的皮皮ex 满月回旋曲 / 飘飘球 气球炸弹 / 沙奈朵ex 奇迹之力）
- TDD：12 新测试红→绿；全量 153 绿 + ruff 零告警；含效果招式卡组同种子 hash 一致
- 遗留：混乱状态 / 基因侵入 copy / 剩余特性三枚 / 道具·竞技场骨架归 task 013+

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
