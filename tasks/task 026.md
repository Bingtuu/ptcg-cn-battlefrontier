# task 026 · 批 2 re-scope：解锁项驱动 + harness 装配校验

- 状态：进行中
- 关联：PRD §5.5（LLM 辅助编写）/ 里程碑 M5；输入 = task 025 批 1 质量小结（blocked 32 张解锁需求归并）

## 目标

批 1 实测证伪 A/B/C 初判（46 张 A 级仅 10 张可直接写，约 22%），批 2 不再按字母批组织，
改为**解锁项驱动**：先建 filter/condition/原语/数据管道，能解锁的卡（无论原标 A/B）随解锁落地。

范围经用户 2026-09-06 拍板（C1 四点全确认）：

0. **前置：harness 装配校验（版本检查/赛制标签）**——dsl-authoring 装配环节强制以卡池代表卡组的
   card_id 取 text_raw（不得按 name_group 任取印刷），并校验赛制标在当前 standard 快照内合法；
   防彷徨夜灵事故（D 标文本顶替 H 标池内印刷）重演。落点：`.kimi-code/skills/dsl-authoring` +
   `bfsim dsl-check` 工具化校验。含三项子工作：
   - 闸 1 新增「文本等价类一致性」校验：DSL 文件内所有 card_ids 的归一化 text_raw 必须一致
   - 装载键 name_group → card_id 精确挂载（loader 改造，同名多文本文件共存，命名约定 `<名>-<区分词>.yml`）
   - 现有 DSL 审计拆分：朋友手册（「最多2张」/「2张」混挂）、巢穴球、高级球、神奇糖果等着
     异文本印刷收窄或拆文件（池内实测清单见 STATUS 2026-09-06 记录）
1. **filters/conditions 高频项先行**（成本低、解锁面大）：
   - filters（chooser 注册）：`name:<卡名>`、`owner_pokemon:<名>`（db cards.owner 可供数）、
     `energy_<属性>`（参数化）、`pokemon_no_rule_or_basic_energy`、in-play 基础宝可梦、
     古代特质（依赖 CardDef.labels 数据管道）
   - conditions：`self_is_active`/`holder_is_active`、`first_own_turn`、`own_tera_in_play`
     （依赖 CardDef.is_tera）、`opponent_prizes_eq:N`/`opponent_prizes_in:[...]`、`holder_hp_le:N`
2. **B 级域核心机制**：`trigger_on_event` 引擎分发 + `place_damage_counters` 原语
   （彷徨夜灵 H 标咒怨炸弹/摔角鹰人/沙铃仙人掌等多卡在等；自我昏厥原语随咒怨炸弹落地）
3. **其余原语按解锁卡数排序**：search_deck top_n 检视、deck_top 去向+有序排列、
   recover_from_discard bench 去向、attach_energy up-to-N/bench-only/多目标各附1、
   discard 附着能量+区间弃置、counters 词（attached_energy_on_target 等）、
   modify_retreat_cost、modify_attack_cost、招式冷却、devolve、coin_flip until_tails、
   bounce 附着物回手参数、bench_size 覆写、奖赏修正、对手手牌随机回库、二选一组合约束、
   distinct-type 检索+拆分去向
4. **老大的指令顺带落地**（gust 无门控版，用户已确认可直接写；池内 9 套中 8 套使用，最高频卡）

数据管道（随解锁项需要接入）：CardDef.is_tera / labels（古代·未来特质）/ owner。

## 验收标准（测试清单）

开发启动时按 TDD 细化逐条测试清单；批次级验收口径：

### WP0 前置（harness 装配校验 + card_id 挂载 + 审计拆分）——测试清单已定稿

loader / CardLibrary（`dsl/loader.py`）：
1. `load_card_dir` 返回 CardLibrary（dict 子类，键 = card_id），按 card_id 精确取文档
2. 同名两文件（card_ids 不相交）共存不报错；`by_name(name)` 返回全部文档
3. card_id 跨文件重复 → DslError（含文件名上下文）
4. card_ids 为空 → DslError（挂载键必填，2026-09-06 决议）

引擎解析（`engine/core.py` `effect_doc()` 助手，~16 处调用点 + `dsl/primitives.py:687`）：
5. 同名两文本合成对局：两只同名不同 card_id 的宝可梦各自结算各自 DSL 文档（事件断言）
6. card_id 未覆盖但同名有文档 → 返回 None（不兜底、不错挂——彷徨夜灵事故回归测试）
7. 朴素 dict 注入（存量测试兼容路径）仍按 name 键工作

Runner 装配（`runner/experiment.py` prepare / prepare_variant）：
8. prepare 按 card_id 过滤 card_effects；同名两文本分属两套卡组时各挂各的
9. 印刷未覆盖 + 同名有效果文档 → warnings 透传（不硬报错：波波式 vanilla 印刷合法）
10. prepare_variant 换入卡按 card_id 补入 DSL 文档，缺失带告警

dsl-check 闸 1 增强（`cli.py`，`--db PATH` 可选旗标）：
11. 无 --db 行为不变（schema + 词表）
12. 未知 card_id → FAIL
13. 文件内 card_ids 归一化 text_raw 不一致 → FAIL（列出分歧 card_id）
14. 赛制标不在最新 standard 快照（退环境印刷）→ FAIL
15. 全绿 → OK 并回显卡名/效果数（现状保持）

审计拆分（cards/ 现有定义库）：
16. 异文本混挂文件收窄 card_ids 至单一文本等价类：不服输头带 / 厉害钓竿 / 反击捕捉器 /
    巢穴球 / 朋友手册 / 高级球 / 神奇糖果 / 能量转移 / 夜光能量（池内实测清单）；
    被收窄印刷均非池内使用（池内同名异效两例——火恐龙/索财灵——均本就 blocked/vanilla）
17. D 标彷徨夜灵.yml（CS2.5C-018，退环境 + 池内零使用）移出库，分片测试同步删除；
    H 标 CSV8C-082 待 WP2（place_damage_counters）落地时新写
18. 审计后 `dsl-check --db` 全库扫全 OK；已核销卡的池内印刷 card_id 断言被覆盖

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归一致
同步纪律：PRD 若有 name_group 主键/挂载表述与新口径冲突，先改 PRD 再落代码

### WP1（filters/conditions 高频解锁项 + CardDef 数据管道 + 随之解锁卡）——测试清单定稿

数据管道（`engine/state.py` CardDef + `data/cards.py::carddef_from_db` + tests/test_deckload.py）：
1. CardDef 新增 `is_tera: bool` / `owner: str | None` / `labels: tuple[str, ...]`，默认空值兼容存量构造
2. carddef_from_db 映射：is_tera←cards.is_tera；owner←cards.owner；labels←effect_tags.labels
   （db 无独立特质列，labels = mik 机制标签「古代/未来」等，db PRD v1.23 契约键）；缺 effect_tags → 空组
3. 映射不猜：db 无赫普组 owner 数据（实测 DISTINCT owner = 玛俐/竹兰/莉莉艾/N/火箭队）——
   不回落卡名前缀硬推，赫普的包包随之记 blocked

filters（`dsl/chooser.py::_match_one` 卡维度 / `_match_in_play` 场上维度，参数化前缀风格）：
4. `name:<卡名>`（卡维度）；未知名不报错（开放字符串，匹配不上即空池）
5. `owner_pokemon:<名>`（卡维度：宝可梦且 owner 命中）
6. `energy_<属性>` 参数化（原字面词 energy_超 泛化为前缀机制，行为不变回归）
7. `pokemon_no_rule_or_basic_energy`（无规则盒宝可梦 或 基本能量）
8. `trait:<特质>`（卡维度 + 场上维度双注册：CardDef.labels 含该特质，如 trait：古代）
9. in-play 基础宝可梦：`basic_pokemon` 在场上维度同词注册（栈顶 stage==0；与卡维度同义复用）
10. 未知词仍 DslError 不猜（含参数化前缀的畸形参数）

conditions（`dsl/chooser.py::_CONDITIONS` / `condition_met` 参数化前缀）：
11. `self_is_active` / `holder_is_active`：持有者/自身为当前战斗宝可梦（栈顶 iid 比对）
12. `first_own_turn`：自己最初的回合（state.turn == 1，turn 仅在先攻方回合开始递增）
13. `own_tera_in_play`：自己场上有太晶宝可梦（依赖 CardDef.is_tera）
14. `opponent_prizes_eq:N` / `opponent_prizes_in:[...]`：对手剩余奖赏卡数判定（参数化）
15. `holder_hp_le:N`：持有者剩余 HP ≤ N（有效 HP 含 modify_hp 修正 − 已受伤害）

引擎钩子（`engine/core.py::_do_attack`）：
16. on_attack 效果带 condition 且不满足 → 招式失败（不结算伤害/效果，回合照常结束，
    攻击事件落 failed 标记）；满足 → 正常 DSL 结算（赫普的古月鸟「则这个招式失败」语义）

随之解锁卡（三道闸，分片 tests/test_dsl_cards_b2_wp1.py）：
17. 老大的指令（CSVH1aC-023，支援者）：gust 无门控版——挂起选对手备战 1 只互换；
    对手无备战不可用（可行性门回归）；38 个印刷同文本等价类全挂载
18. 尖钉镇道馆（CSV10C-216，竞技场）：stadium_grant 检索 owner_pokemon：玛俐 入手+洗牌；
    负例：非玛俐宝可梦/训练家/能量不进池；双方各每回合 1 次（stadium_used 引擎强制）
19. 赫普的古月鸟（CSV10C-188）：随性喷吐 condition opponent_prizes_in:[4,3]——
    满足 120 伤害；不满足招式失败（无伤害、回合结束）；奖赏 5 张不满足

仍 blocked（装配复核更新原因，详见 coverage-plan 落账）：多龙奇（原因失真，实测需
top_n 检视）、水莲的照顾（recover hand up-to）、赫普的包包（db 无赫普 owner 数据）、
奥琳博士的气魄（attach 多目标各附1）等——逐项原因随批末落账更新。

### WP2（trigger_on_event 分发 + place_damage_counters + ko_self）——测试清单定稿（2026-09-07）

设计决议（随落地进 rules-reference 附录 A / STATUS 落账）：

- **D-WP2-1 效果中途昏厥的换上时点**：效果内造成的昏厥（含自我昏厥）整叠进弃牌区、对手立即拿奖赏
  （文本语序保真）；换上（promote）推迟到**效果全部结算完毕**后按队列统一进行，换上完成后回到
  当前回合方的主阶段（ability/trainer/stadium 类完成）。咒怨炸弹语序「先自我昏厥、后放指示物」
  的奖赏结算顺序严格保持；换上推迟对游戏状态无可观测影响（换上选择不依赖中间状态）。
  依据：rules-manual §8 换上义务 + 附录待核清单「同时昏厥结算顺序」条目，🔲 待核。
- **D-WP2-2 多换上队列**：一次效果结算产生多个待换上（如咒怨炸弹自爆 + 指示物昏厥对手战斗场），
  按昏厥结算顺序（玩家 0→1、备战区→战斗场扫描序）排入 `promote_queue` 逐条换上；🔲 待核。
- **D-WP2-3 触发式特性「可使用 N 次」的放弃选项不建模**：trigger_on_event 满足即自动发动，
  目标选择按「尽力而为」（池不足 min_choose 收缩至池大小；池空 no-op 不挂起）。指示物放于
  对手场上为纯收益，放弃选项无策略价值；🔲 待核。
- **D-WP2-4 promote_to_main 归并**：task 025 bounce 的 `promote_to_main` 标记并入统一机制
  `resume_after_promotes=(player, phase)`，行为不变（回归测试保持）。

测试清单：

promote 队列与 resume 机制（`engine/core.py` / `engine/state.py`）：
1. 攻击昏厥对手战斗场 → 换上 → 对手回合开始（既有行为回归，走队列机制不变式）
2. 混乱反面自我昏厥 → `turn_after_promote` 给对手（既有行为回归）
3. bounce 战斗场 → 换上后回主阶段（既有行为回归，改走 resume_after_promotes）
4. 一次效果两个待换上（自爆 + 对手战斗场被指示物昏厥）→ 队列逐条 promote，
   顺序 = 入队序，全部完成后回效果方主阶段
5. 亢奋脑力（move_damage_counters）昏厥对手战斗场 → 换上后回**我方**主阶段
   （修正现行为：此前错进对手回合）
6. 双方同时无可换上（各自战斗场昏厥且备战空）→ is_draw 平局（§8 同时胜利口径，🔲 待核）
7. run_effect 节点循环遇 phase=="game_over" → 中断后续节点（奖赏拿完后不再执行）

ko_self 原语（`dsl/primitives.py`，词表 actions 补 `ko_self`）：
8. 备战位自我昏厥：整叠（含能量/道具）进弃牌区、对手按规则盒拿奖赏、无换上、回合继续
9. 战斗场自我昏厥 + 有备战 → 效果完成后换上、回我方主阶段
10. 战斗场自我昏厥 + 无备战 → 立即 game_over(no_pokemon)
11. 自我昏厥使对手拿完最后奖赏 → game_over(prizes)，后续节点不执行
12. selector≠self / 来源不在场上 → DslError（不猜）

place_damage_counters 原语（词表已有词，本期实现）：
13. opponent_pokemon_any choose=1 + args.counters=5 → 目标 +50 伤害（指示物×10）
14. 指示物致对手战斗场昏厥 → 队列换上 → ability 完成后回我方主阶段；致备战昏厥 → 无换上
15. opponent_bench choose=2 + counters=1 → 两只各 +10；池=1 时 min 收缩为 1；池空 no-op 不挂起
16. 未知 selector / 缺 counters 参数 / counters 非正 → DslError
17. ability_feasible / playable_feasible 支持两原语（ko_self 恒可行；place_damage_counters
    对手场上无宝可梦不可行）；未知形式仍 DslError

trigger_on_event 引擎分发（`Effect.event` 字段 + `_do_place_bench` 主阶段分发点）：
18. schema：event 字段仅 trigger_on_event 可用；trigger_on_event 缺 event → loader DslError；
    非 trigger_on_event 带 event → loader DslError；event 词查 vocabularies 新段 `events`
19. 主阶段从手牌放备战区 → 匹配 `own_play_from_hand_to_bench` 的 effect 发动（可挂起 chooser，
    完成后回主阶段；特性卡本体不弃置）
20. setup 阶段放备战区不触发；DSL search_deck destination=bench（巢穴球）不触发（非「从手牌」）
21. 一张卡多个同事件 trigger_on_event 效果 → DslError（不猜，需要时再扩展）
22. 触发效果的 condition 不满足 → 不发动（走 condition_met，为猫头夜鹰等后续卡备）

卡牌落地（三道闸，分片 `tests/test_dsl_cards_b2_wp2.py`）：
23. 彷徨夜灵 H 标（CSV8C-082 + 同文本等价类 CSV8C-211/CSV9.5C-070/SVP-347，db 实测归一化
    text_raw 一致）：ability_manual + once_per_turn + ko_self + place_damage_counters(5)；
    用例：备战位发动 / 战斗位发动+换上+回主阶段 / 限次 / 昏厥拿奖
24. 摔角鹰人 G 标（CSV1C-079 + 同文本等价类 CSV9.5C-095/CSVE2pC-005/CSVL1C-035/CSVL1C-076/
    CSVM2bC-003/SVP-079/SVP-289）：trigger_on_event own_play_from_hand_to_bench +
    place_damage_counters(opponent_bench, choose=2, counters=1)；用例：主阶段放置触发 /
    对手备战 1 只收缩 / 对手备战空 no-op / setup 不触发 / 巢穴球不触发
25. 沙铃仙人掌维持 blocked（招式「穷追不舍」撤退锁属 task 029 域；特性需 KO 来源追踪 +
    attacker 目标词，本 WP 不建——无落地卡的原语不先行）

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归 +
`dsl-check --db` 全库全 OK + 词表同步（actions +ko_self、新段 events）

### WP3（recover 去向扩展 + top_n 检视 + attach 多目标 + own_evolve_from_hand + reveal）——测试清单定稿（2026-09-14）

范围按「解锁卡数」排序（task 026 re-scope c 点）：recover 扩展解锁 2 卡居首，其余各 1 卡。
5 张目标卡的池内机制需求（text_raw 实测 2026-09-07）：

- 夜巡灵 H 标渡魂（招式）：「选择自己弃牌区中最多3张『夜巡灵』，放于备战区」→ recover bench 去向
- 水莲的照顾：「弃牌区宝可梦（除规则盒）和基本能量合计最多3张，给对手看过后加入手牌」→ recover hand up-to + reveal
- 多龙奇 H 标侦察指令（特性）：「查看牌库上方2张，选1加入手牌，剩余放回牌库下方」→ search top_n 检视 + rest deck_bottom
- 奥琳博士的气魄：「最多2只古代宝可梦各附1张弃牌区基本能量，然后抽3张」→ attach 多目标各附1
- 猫头夜鹰 寻找宝石（特性）：「从手牌使出并进化时，若场上有太晶宝可梦可使用1次。选牌库最多2张训练家，给对手看过后加入手牌。重洗」→ own_evolve_from_hand 事件 + reveal

设计决议（随落地进 rules-reference 附录 A / STATUS 落账）：

- **D-WP3-1 多目标各附1的配对口径**：先选能量（up-to N）再选目标宝可梦（up-to N），
  按选择顺序一一配对（FIFO）；N = min（目标数， 能量数， choose) 收缩。官方规则未规定分配顺序，🔲 待核。
- **D-WP3-2 寻找宝石触发范围**（✅ 用户 2026-09-14 裁决）：判定关键 = 进化卡本身从手牌
  使出——主阶段 `_do_evolve` 与神奇糖果（skip_stage，进化卡从手牌压上）均触发；
  牌库进化（from_deck，招式学习器「进化」）不触发。DSL 手牌进化经
  pending_event_triggers 队列在外层效果完成后排水分发；排水时来源已不在场 → 离场即失效。
- **D-WP3-3 top_n 检视的选择下限**：维持检索统一 up-to 纪律（min_choose=0，
  牌库为非公开区域对手无法验证）；「选择其中1张」字面偏必选，从宽处理，🔲 待核。
- **D-WP3-4 reveal 一期口径**：仅落结构化事件流（iids + 卡名），对手 Agent 可见视图
  不引入手牌内容泄露建模（PRD 观测范围纪律）；🔲 待核。
- **备战容量**：recover/search destination=bench 受备战区 5 只上限约束（池解析即截断，
  同既有 search_deck bench 口径——若既有实现未截断，本 WP 一并补上并补测试）。

测试清单：

recover_from_discard 去向扩展（`dsl/primitives.py`）：
1. destination=bench：choose=3 + name 过滤器 → 所选入备战区为 InPlayPokemon、
   entered_play_this_turn 登记、up-to（min_choose=0）；池空 no-op 不挂起
2. destination=bench 备战区满（5 只）→ 池按剩余容量截断
3. destination=hand up-to：args.up_to=true → min_choose=0（选 0~N）；
   既有 hand 去向默认 min_choose=1 行为回归不变（夜间担架）
4. 未知 destination / bench 去向缺 choose → DslError（不猜）
5. ability_feasible / playable_feasible 支持 bench 去向与 hand up-to（弃牌区无匹配不可行）；
   未知形式仍 DslError

search_deck top_n 检视（多龙奇 侦察指令）：
6. args.top_n=2 + destination=hand + args.rest=deck_bottom：chooser 池 = 牌库顶 2 张，
   选 1 入手、剩余 1 张按原序放牌库下方、**不洗牌**（无 shuffle 节点时牌库序确定）
7. 牌库仅 1 张 → 检视 1 张尽力而为；牌库空 → no-op 不挂起
8. 参数校验：top_n 非正 int / choose > top_n / rest 非 deck_top|deck_bottom → DslError
9. top_n 检视不经 chooser 之外泄露牌库序（事件流只落选择结果，不落未选卡——观测性纪律）

attach 多目标各附1（奥琳博士）：
10. 两段 chooser：段1 选能量（own_discard 基本能量，up-to N）→ 段2 选目标
    （own_pokemon_in_play + trait:古代，up-to 等量）→ 按选择顺序配对附着（D-WP3-1）
11. 目标 1 只能量 2 张 → 收缩 1 对；目标空或能量空 → no-op 不挂起
12. 附着完成 check_knockouts 兜底（同既有 attach_energy 口径）；后续 draw 3 节点无条件执行

own_evolve_from_hand 事件 + reveal 原语：
13. 词表 events 段 +own_evolve_from_hand；`_do_evolve`（主阶段手牌进化）挂点分发，
    复用 WP2 触发分发（condition 门控 / 单卡同事件多个 → DslError / completion="ability"）
14. setup 无进化行动天然不触发；DSL evolve 原语（神奇糖果）不触发（D-WP3-2）
15. reveal 原语落地：selector 池 iids 落 `reveal` 事件（含卡名），无状态变更；
    未知 selector → DslError；词表 actions 已有 reveal 词（本期实现）

卡牌落地（三道闸，分片 `tests/test_dsl_cards_b3_wp3.py`；card_ids 以装配时池内实际印刷 +
db 同文本等价类实测为准，下列为 db 检索候选）：
16. 多龙奇 H 标（CSV8C-158 / CSV9.5C-133 / CSVM2bC-006）：ability_manual once_per_turn +
    search top_n=2 hand rest=deck_bottom；用例：正常检视 / 剩余库底不洗牌 / 限次 / 牌库不足
17. 夜巡灵 H 标渡魂（CSV8C-081 / CSV8C-210 / CSV9.5C-069 / SVP-346）：on_attack +
    recover bench up-to 3 name:夜巡灵；用例：3 只全回 / 弃牌区收缩 / 备战满截断 /
    攻击后回合正常推进
18. 奥琳博士的气魄 G 标（CSV6C-121/146/156、CSV9.5C-187、CSVH4C-046、CSVM2aC-026、SVP-238）：
    on_play + attach 多目标（trait:古代）+ draw 3；用例：2 目标 2 能量配对 / 收缩 /
    无合法目标仍抽 3
19. 猫头夜鹰 寻找宝石 H 标（CSV9.5C-142、CSV9C-155、CSV9C-214、CSVM2aC-011、SVP-291）：
    trigger_on_event own_evolve_from_hand + condition own_tera_in_play + search trainer
    up-to 2 + reveal + shuffle；用例：进化触发 / 无太晶不触发 / reveal 事件落流
20. 水莲的照顾 H 标（CSV7C-193/230/246、CSV9.5C-189、CSVH4C-049、CSVM2cC-025、SVP-199）：
    on_play + recover hand up-to 3（pokemon_no_rule_or_basic_energy）+ reveal；
    用例：选 3 / 选 0 / 池空 no-op / 过滤器负例（规则盒宝可梦不可选）

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归 +
`dsl-check --db` 全库全 OK + 词表同步（events +own_evolve_from_hand；其余词复用既有段）+
真机冒烟（含多龙奇/夜巡灵/猫头夜鹰的池内卡组镜像 20 局 0 失败）

### WP4（top_n rest=shuffle + attach bench-only/up-to + modify_retreat_cost + cost 弃置排除）——测试清单定稿（2026-09-07）

范围按「解锁卡数」排序，4 组机制 7 卡（text_raw 实测 2026-09-07）：

- 米立龙 H 标揽客（特性）：「战斗场上才可使用，每回合1次。查看牌库上方6张，选其中1张支援者，给对手看过后加入手牌。剩余放回牌库并重洗」→ top_n rest=shuffle + self_is_active（WP1 已备）+ trainer_supporter（已备）+ reveal
- 宝可装置3.0（物品）：「查看牌库上方7张，选其中1张支援者，给对手看过后加入手牌。剩余放回牌库并重洗」→ 同上 on_play 版
- 怒鹦哥ex（G 标 CSV2C-105）：特性英武重抽 = first_own_turn + once_per_turn_shared + discard all + draw 6（全既有件）；招式鼓足干劲 = 「弃牌区最多2张基本能量附着于1只备战宝可梦」→ attach 目标池 own_bench + 能量 up-to
- 飞天螳螂 G 标辅助斩（151C-123 类，招式）：「弃牌区1张基本草能量附着于备战宝可梦」→ attach bench-only + energy_草（WP1 参数化已备）
- 紧急滑板（道具 H 标 CSV7C-185 类 8 印刷）：「撤退费用-1；剩余HP≤30 则全免」→ modify_retreat_cost 声明式 + holder_hp_le:30（WP1 已备）
- 拉帝亚斯ex（特性天际线，CSV9C-078 类 3 印刷）：「这只宝可梦在场上时，自己所有基础宝可梦撤退费用全免」→ modify_retreat_cost 全体基础 scope
- 超级能量回收（G 标 CSV3C-115 类）：「只有将2张手牌弃置后才可使用。选弃牌区最多4张基本能量，给对手看过后加入手牌（无法选择因本效果弃置的能量）」→ cost discard 2 + recover hand up-to 4 + 成本弃置排除 + reveal

设计决议（随落地进 rules-reference 附录 A / STATUS 落账）：

- **D-WP4-1 撤退费修正语义**：`modify_retreat_cost` 声明式（passive_static，引擎读声明，
  仿 `_effective_hp` 建 `_effective_retreat_cost`，枚举 core.py:301 与执行 :658 两触点接入）；
  value = 非负 int（减少量）或 "all"（全免）；多条修正规约：减少量加总后 clamp 下限 0，
  "all" 直接归零（无顺序依赖，可交换）；条件式修正（紧急滑板 holder_hp_le:30）由
  effect.condition 引用 holder 有效 HP 判定。🔲 待核。
- **D-WP4-2 拉帝亚斯ex 作用域**：特性在场持续生效（passive_static + scope
  own_basic_all：自己全场 stage==0 宝可梦撤退费归零）；离场即失效（引擎读声明天然满足）。
  🔲 待核。
- **D-WP4-3 超级能量回收的成本排除**：cost 段弃置的 2 张手牌 iid 记入执行上下文，
  recover 节点 args.exclude_cost_discarded=true 时池剔除之（文本明写，忠实实现非决议，
  落账仅注实现口径）；cost 支付为使用前提（手牌 <2 张不可使用，可行性门）。
- **D-WP4-4 怒鹦哥ex 鼓足干劲能量选择**：「最多2张」= up-to（段1 min_choose=0）；
  目标「1只备战宝可梦」= 段2 own_bench 必选 1 只（选能量 0 张时不进段2，no-op）。🔲 待核。
- **top_n rest=shuffle**：「剩余放回牌库并重洗」= 未选卡与牌库其余合并后整库重洗
  （rest=shuffle 时由本节点直接洗牌，等价于 剩余归位 + shuffle_deck 节点，DSL 不再写
  shuffle 节点）；与多龙奇 rest=deck_bottom（不洗牌）按文本严格区分。

测试清单：

top_n rest=shuffle（`dsl/primitives.py` search_deck 扩展）：
1. args.rest=shuffle：检视顶 N 选 K 入手，未选卡与牌库其余合并重洗（同种子下牌库序
   与 rest=deck_bottom 路径不同；事件流只落选择结果）
2. rest=shuffle 时 DSL 不写 shuffle_deck 节点（重复洗牌 = 种子消耗差异，loader/测试纪律
   注释即可）；参数校验：rest=shuffle 以外非法词仍 DslError（WP3 已覆盖 deck_top/deck_bottom）
3. 牌库不足 N 尽力而为；池空（窗内无支援者）no-op 仍重洗？——文本「剩余放回并重洗」
   在空选时依然成立：选 0 张 → 窗内全部视为剩余，整库重洗（用例锁定）

attach bench-only + 能量 up-to（`dsl/primitives.py` attach_energy 扩展）：
4. args.target_pool=own_bench：段2 目标池改备战区（战斗场不可选）；目标空（无备战）
   no-op 不挂起
5. 段1 能量 up-to：args.energy_up_to=true → min_choose=0（怒鹦哥「最多2张」）；
   选 0 张 → 不进段2 直接完成；未指定时保持既有 min=choose 行为回归
6. 单能量单备战目标（飞天螳螂）：choose=1 + target_pool=own_bench + energy_草 过滤
7. 参数校验：target_pool 非 own_pokemon_in_play/own_bench → DslError；multi_target 与
   target_pool=own_bench 组合 → 暂不支持 DslError（不猜，需要时再扩展）
8. ability_feasible / playable_feasible 补新形式（能量池/备战池为空不可行）；未知形式 DslError

modify_retreat_cost 声明式（`engine/core.py` _effective_retreat_cost + 词表 actions +词）：
9. 紧急滑板：持有者撤退费 -1（枚举层 legal_actions 与执行层 _do_retreat 两触点生效）；
   holder_hp_le:30 满足时全免（value="all"）；道具被弃置/替换后失效
10. 拉帝亚斯ex：在场时自己全体 stage0 撤退费归零（备战/战斗场均生效），对手不受影响；
    拉帝亚斯ex 离场（昏厥/回手）后失效
11. 修正叠加：滑板(-1) + 天际线(all) 并存 → 0；双滑板不可能（道具限1）不测；
    value 非法（负 int / 未知字符串）→ DslError
12. 白板宝可梦撤退行为零回归（无声明时 = card.retreat_cost 原值）

cost 弃置排除（`dsl/interpreter.py` 上下文 + recover_from_discard args）：
13. 超级能量回收：cost discard choose=2 支付后 recover 池剔除该 2 张 iid
   （弃置能量为草/火基本能量时不可回选；弃置非能量本就不匹配过滤器，双路径覆盖）
14. cost 手牌 <2 张 → 整卡不可使用（playable_feasible 门：cost 节点 choose=2 需手牌 ≥2）
15. exclude_cost_discarded 用于非 cost 先行效果（无 cost 段）→ 空集合无影响；
   非 bool 参数 → DslError

卡牌落地（三道闸，分片 `tests/test_dsl_cards_b4_wp4.py`；card_ids 以装配池内实际印刷 +
db 同文本等价类实测为准）：
16. 米立龙 H 标揽客类（候选 CBB5C-2801 等，db 实测）：ability_manual + once_per_turn +
    self_is_active + top_n=6 trainer_supporter rest=shuffle + reveal；
    用例：战斗场发动 / 备战位不可发动（可行性门）/ 窗内无支援者重洗 / 限次
17. 宝可装置3.0（候选 CSV2C-113 类）：on_play + top_n=7 同上；用例：检视选 1 / 空选重洗 /
    牌库不足 7
18. 怒鹦哥ex（CSV2C-105 类）：特性英武重抽（first_own_turn + once_per_turn_shared +
    discard all + draw 6）+ 招式鼓足干劲（attach bench-only up-to 2）；用例：特性首回合
    可用/次回合不可用/共享限次；招式选 2 附 1 备战 / 选 0 no-op / 无备战不可宣言
19. 飞天螳螂 G 标辅助斩类（151C-123 等）：on_attack + attach bench-only choose=1
    energy_草；用例：附着备战 / 弃牌区无草能量招式效果 no-op（攻击伤害照算）/ 目标
    仅备战（战斗场不可选）
20. 紧急滑板（CSV7C-185 类 8 印刷）：passive_static modify_retreat_cost holder scope；
    用例：-1 生效 / HP≤30 全免 / HP>30 只 -1 / 道具离场失效
21. 拉帝亚斯ex（CSV9C-078 类 3 印刷）：passive_static modify_retreat_cost own_basic_all
    scope；用例：基础全免 / 进化体不免 / 对手不免 / 离场失效
22. 超级能量回收（CSV3C-115 类）：cost discard 2 + recover hand up-to 4 basic_energy +
    exclude_cost_discarded + reveal；用例：弃 2 能量不可回选 / 弃非能量正常 / 手牌不足
    不可使用 / 池不足收缩

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归 +
`dsl-check --db` 全库全 OK + 词表同步（actions +modify_retreat_cost；rest=shuffle /
target_pool / energy_up_to / exclude_cost_discarded 为 args 键先例）+ 真机冒烟
（赫普的苍响 = 米立龙 + 宝可装置3.0 + 紧急滑板 + 拉帝亚斯ex；猛雷鼓 = 怒鹦哥ex；
赛富豪 = 飞天螳螂 + 超级能量回收）

### WP5（任意数量弃置×N 伤害族 + 费用/奖赏修正 + until_tails + bounce 参数 + 变身）——测试清单定稿（2026-09-14）

范围按「解锁卡数 + 机制通用性」排序，6 组机制 8 卡（text_raw 实测 2026-09-14）：

- 赛富豪ex 淘金潮 50×（G 标 CSV4C-089 类 7 印刷）：「将自己手牌中任意数量的基本能量放于弃牌区，造成其张数×50伤害」→ discard own_hand 任意数量 + 前序弃置张数计数词
- 猛雷鼓ex 极雷轰 70×（H 标 CSV7C-154 类 7 印刷）：「将自己场上宝可梦身上附着的任意数量的基本能量放于弃牌区，造成其张数×70伤害」→ discard own_attached_energy 任意数量版；飞溅咆哮 = discard all + draw 6（既有件）
- 猛雷鼓 落雷风暴（H 标 CSV8C-161 类 2 印刷）：「给对手的1只宝可梦，造成这只宝可梦身上附着的能量数量×30伤害[备战不计算弱抗]」→ counters 词 attached_energy_on_target（备战不计算弱抗 = 引擎既有规则）
- 月月熊 赫月ex（H 标 CSV8C-172 类 8 印刷）：老练招式 = modify_attack_cost 声明式（血月费用减对手已拿奖赏数×【无】）+ opponent_taken_prizes 计数词；血月 240 + lock_attack（WP4 已备）
- 白蕾雅（H 标 CSV9.5C-197 类 6 印刷）：「对手剩余奖赏=2 时才可使用。本回合自己太晶宝可梦招式伤害致对手战斗场昏厥 → 多拿1奖赏」→ opponent_prizes_eq:2（WP1 已备）+ 回合级奖赏加成钩子（仅招式伤害路径）
- 索财灵 连掷硬币 20×（G 标 CSV4C-063 类 3 印刷）：「抛掷硬币直到出现反面，造成正面次数×20伤害」→ coin_flip until_tails 模式 + flip_heads_count 计数词
- 牡丹（G 标 CSV1C-124 类 5 印刷）：「自己场上1只基础宝可梦，将该宝可梦以及放于其身上的所有卡牌放回手牌」→ bounce args.attachments=hand（默认 discard 不变）；basic_pokemon 场上过滤器 WP1 已备
- 百变怪 变身启动（G 标 151C-132 类 4 印刷）：「战斗场上、最初回合限1次。选牌库1张基础宝可梦（除百变怪），将这只宝可梦及放于其身上的所有卡牌放于弃牌区，被选择的放于原先位置。重洗」→ transform 替换原语（self_is_active / first_own_turn WP1 已备）

设计决议（随落地进 rules-reference 附录 A / STATUS 落账）：

- **D-WP5-1 任意数量弃置**：「任意数量」= up-to all（min_choose=0）；选 0 张 → 伤害 0，
  招式仍可宣言（WP4 宣言裁决的延伸应用）。前序弃置张数经 ExecutionContext 传递
  （计数词 discarded_this_effect，仅读本效果内前序 discard 节点）。🔲 待核。
- **D-WP5-2 白蕾雅奖赏加成**：仅「招式伤害致昏厥」路径触发（效果/指示物致昏厥不触发）；
  回合级标记（turn scoped，回合结束清除）；多拿 1 张在 take_prize 触点结算。🔲 待核。
- **D-WP5-3 变身启动**：替换不触发昏厥与奖赏（非昏厥离场）；伤害/特殊状态/效果
  **不继承**（原文未写继承——与 30th 版整蛊变身「全部继承」措辞差异忠实区分）；
  新宝可梦登记 entered_play_this_turn；牌库检索 up-to（可以不找→整效 no-op，重洗仍执行）。
  🔲 待核。
- **D-WP5-4 月月熊 费用减免**：modify_attack_cost 声明式（passive_static，引擎
  _energy_satisfied 求值点读声明）；减免 = opponent_taken_prizes（=6−对手剩余奖赏）
  个【无】能量，下限 0（费用不可为负）；只减【无】部分。🔲 待核。
- **until_tails 掷币序列**：单次行动内连续掷到反面为止，逐次落 coin_flip 事件流；
  种子确定性由单一随机源保证（既有 rng 路径）。

测试清单：

discard 任意数量 + 弃置张数计数词（`dsl/primitives.py` discard/damage 扩展）：
1. discard own_hand + filters + args.any_count=true：choose 0~全部基本能量；
   弃置张数记 ctx；damage 节点计数表达式 discarded_this_effect×系数结算
2. discard own_attached_energy any_count（场上全体附着能量池，basic_energy 过滤）：
   从各宝可梦身上摘下弃置；选 0 → 伤害 0 可宣言
3. 计数词仅读前序（同一效果内 discard 之后的 damage 才得数；无 discard 前置 → 0）；
   any_count 非 bool / 未知计数词 → DslError

attached_energy_on_target 计数词（猛雷鼓）：
4. damage = 目标附着能量数×30，目标 opponent_pokemon_any choose=1；备战目标不计算
   弱抗（引擎既有规则回归）；目标无能量 → 伤害 0
5. counters 词表 +attached_energy_on_target；未知词 DslError 不猜

modify_attack_cost 声明式（月月熊ex，词表 actions +词）：
6. 老练招式：对手已拿 N 奖赏 → 血月费用减 N 个【无】（_energy_satisfied 求值点接入，
   枚举与执行共用）；N=0 无减免；减免超过【无】部分 clamp 0
7. 只减【无】不减少有色部分（血月【无】×5 全无色——构造含有色费用的合成用例锁定）；
   来源离场失效（求值点实时读声明）
8. opponent_taken_prizes = 6 − opponent_remaining_prizes（counters 词表 +词）；
   非法 value/未知计数词 → DslError

白蕾雅奖赏加成钩子：
9. condition opponent_prizes_eq:2 不满足 → 不可使用（playable_feasible 既有门）；
   使用后本回合太晶宝可梦招式昏厥对手战斗场 → 拿 2 张（1+1）
10. 非太晶宝可梦招式昏厥 / 指示物致昏厥 / 备战昏厥 → 不加成；次回合标记清除
11. 太晶判定读 CardDef.is_tera（WP1 数据管道）；多拿在 take_prize 触点、奖赏不足
    按剩余拿取（拿完即胜）

coin_flip until_tails（索财灵）：
12. 连续掷币直到反面，逐次落事件；伤害 = 正面次数 ×20；首掷即反面 → 伤害 0
13. 同种子复现（两次同种子运行掷币序列一致）；if_flip_* 门控不受 until_tails 影响
    （既有行为回归）

bounce attachments=hand（牡丹）：
14. args.attachments=hand：整叠+附着能量/道具全部回手牌（不弃置）；默认 discard
    行为回归（弗图博士等既有卡不动）
15. 战斗场目标 bounce 后换上流程回归（resume_after_promotes 机制不变式）；
    attachments 非法值 → DslError

transform 替换原语（百变怪，词表 actions +词）：
16. 战斗场百变怪 → 选牌库 1 基础（除百变怪，参数化过滤器 not_name 或等效形式）→
    百变怪整叠+附着物进弃牌区、被选宝可梦入战斗场（entered_play_this_turn 登记）→
    重洗；不触发昏厥/奖赏/换上
17. 备战位不可发动（self_is_active 条件门）；非首回合不可发动（first_own_turn）；
    牌库无合法目标 → no-op 仍重洗
18. 伤害/状态不继承（D-WP5-3）；参数校验 DslError

卡牌落地（三道闸，分片 `tests/test_dsl_cards_b5_wp5.py`；card_ids 以装配池内实际印刷 +
db 同文本等价类实测为准，上文已列候选类）：
19. 赛富豪ex：特性嘉奖硬币（once_per_turn + draw 1 + self_is_active 时额外 draw 1——
    条件式追加抽，需节点级 condition 或拆分两效果块，实现形式实现者定但保真）+
    淘金潮 50×；用例：特性战斗场/备战位两形态 / 淘金潮弃 3 张=150 / 弃 0=0 可宣言
20. 猛雷鼓ex：飞溅咆哮（discard all + draw 6）+ 极雷轰 70×（场上能量）；
    用例：弃 2 张=140 / 跨多只宝可梦摘能量 / 选 0=0
21. 猛雷鼓：落雷风暴（attached_energy_on_target×30）+ 龙之头击 130 白板；
    用例：目标 2 能=60 / 备战目标不计算弱抗 / 0 能=0
22. 月月熊 赫月ex：老练招式 + 血月 240 + lock_attack；用例：对手拿 0/2/5 奖赏三档
    费用减免 / 有色费用不减 / 血月后冷却锁
23. 白蕾雅：on_play condition opponent_prizes_eq:2 + 奖赏加成；用例：条件门 /
    太晶招式昏厥拿 2 / 非太晶不加成 / 次回合失效
24. 索财灵 连掷硬币类（3 印刷）：on_attack until_tails ×20；用例：种子锁定序列 /
    首反 0 伤害 / 多正面累计
25. 牡丹：on_play + bounce own basic attachments=hand；用例：整叠+能量道具回手 /
    战斗场 bounce 后换上 / 进化体不可选（basic_pokemon 过滤器负例）
26. 百变怪 变身启动类（4 印刷）：用例：变身替换全流 / 牌库空 no-op 重洗 /
    备战位不发动 / 非首回合不发动

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归 +
`dsl-check --db` 全库全 OK + 词表同步（actions +modify_attack_cost/+transform；
counters +attached_energy_on_target/+opponent_taken_prizes/+discarded_this_effect
/+flip_heads_count；其余 args 键先例）+ 真机冒烟（赛富豪 / 猛雷鼓 / 赫普的苍响 /
喷火龙大比鸟池内卡组）

### WP6（blocked 8 张全清：hand_disrupt + bench_size + 组合检索 + deck_top 有序 + KO 触发/撤退锁 + protection + devolve/学习器）——测试清单定稿（2026-09-14）

范围 = coverage-plan 剩余 blocked 8 张全清（池内印刷实测自 deck_cards 2026-09-14）：

- 雪童子 惊吓（H 标 CSV7C-057，玛俐雪妖女 ×2）：「不看正面选对手1张手牌，查看正面后放回对手牌库并重洗」→ hand_disrupt 原语 + damage 20
- 零之大空洞（H 标 CSV9C-207，猛雷鼓厄诡椪 ×2）：太晶在场玩家备战上限 5→8 + 失效缩减括号注 → bench_size 覆写 + 失效缩减结算
- 小刚的发掘（I 标 CSV10C-207，赛富豪 ×1）：「牌库最多2张基础**或**1张进化，给对手看后加入手牌，重洗」→ search 二选一组合约束
- 赤松（H 标 CSV9C-196，黑夜魔灵 ×1 + 猛雷鼓 ×2）：「属性各不相同的基本能量最多2张，1张入手、剩余附着自己宝可梦，重洗」→ distinct-type 约束 + 检索拆分去向（hand+attach）
- 暗码迷的解读（H 标 CSV7C-191，赛富豪 ×3）：「选任意2张，余库重洗，所选以任意顺序排列放回牌库顶」→ deck_top 有序去向
- 沙铃仙人掌（I 标 CSV10C-008，多龙巴鲁托 ×1）：炸裂针刺（战斗场受对手招式伤害昏厥 → 攻击方放 6 指示物）+ 穷追不舍 20（下个对手回合目标无法撤退）→ own_ko_by_attack 触发器 + lock_retreat
- 火恐龙两文本类（喷火龙大比鸟/多龙喷火龙 各 151C-005×1 + CSV5C-015×1，均 G 标，按同名多文本拆两文件）：151C-005 大字爆炎 90「选自身附着1能量弃置」→ own_attached_energy 扩 choose=1；CSV5C-015 闪焰之幕「不受对手招式的效果影响」→ protection 最小版
- 招式学习器 退化（G 标 CSV5C-120，玛俐雪妖女 ×1 + 赫普苍响 ×1）：学习器载体（道具即招式、持有者回合结束自弃）+ devolve 原语（对手全场进化宝可梦各退栈顶 1 张回对手手牌）

设计决议（2026-09-14 用户核对设计口径通过；随落地进附录 A 🔲，gate3 核销后翻 ✅）：

- **D-WP6-1 hand_disrupt（雪童子）**：「不看正面选择」= 均匀随机 1 张（单一随机源，
  种子确定性不变）；「查看正面」沿用 WP3 reveal 口径（仅落事件流，可见视图不建模）；
  放回并重洗的是**对手**牌库；对手手牌空 → 效果段 no-op，伤害照算（WP4 宣言裁决）。
- **D-WP6-2 零之大空洞**：bench_size 逐玩家动态求值（竞技场在场 + 该方太晶在场 → 8）；
  失效触点 = 竞技场离场或己方太晶离场，立即缩减至 5——弃哪些由**该方玩家自选**
  （choose）；缩减弃置非昏厥、无奖赏；双方同时需缩减 → 持有者先执行（括号原文明示）；
  8 只容量对一切放置路径（含 recover/search destination=bench）同步放开。
- **D-WP6-3 小刚的发掘**：「最多」覆盖整个短语——基础 up-to 2 / 进化 up-to 1；
  两分支**互斥**（不可 1 基础 + 1 进化混合，文本「或」）；选 0 → no-op 重洗仍执行。
- **D-WP6-4 赤松**：distinct（属性互异）约束作用于**选择池解析**（同属性池内互斥）；
  拆分去向 = 1 张入手（玩家选定）+ 剩余附着自己宝可梦（目标自选）；选 1 张 → 附着段
  no-op；选 0 → 全 no-op 重洗。**用户补充场景（2026-09-14）**：牌库仅单一属性能量时
  可选上限收缩为 1 → 入手 1 / 附着 0 / 重洗执行（约束在选择阶段生效，非拆分后补救）。
- **D-WP6-5 暗码迷**：「任意2张」= 任意种类的 2 张，从宽 up-to 2（牌库非公开）；
  排列顺序 = **选择顺序即牌顶顺序**（先选的在最顶，FIFO），不做二次排列交互；
  牌库不足按池收缩纪律。
- **D-WP6-6 沙铃仙人掌**：炸裂针刺触发面 = 战斗场 + 对手**招式伤害** + 昏厥三条件
  （效果/指示物致昏厥、备战昏厥不触发；复用 WP5 attack_ctx 攻击方识别）；攻击方
  此时已离场 → no-op。穷追不舍撤退锁挂目标实例——该目标的下个回合结束解除；
  进化/离场清除（既有状态清除纪律）。task 029 域最小落地。
- **D-WP6-7 火恐龙闪焰之幕**：「效果影响」= 招式附加效果（指示物/特殊状态/弃置/
  换位等），**伤害本体不免疫**；免疫在效果落点逐目标检查（passive_static 声明式，
  引擎读声明）。task 029 域最小落地。
- **D-WP6-8 招式学习器 退化**：「各移除1张」= 栈顶（最后进化上去的那张），二段进化
  只退 1 张；退化后伤害指示物**保留**、特殊状态恢复（离场口径）；新 HP 上限 <
  已有伤害 → 昏厥结算（时点对齐离场检查）；只退进化卡本身（能量/道具不动）；
  对手无进化宝可梦 → no-op。学习器载体：附着后持有者可宣言其招式（正常费用校验），
  持有者自己回合结束自弃。

测试清单：

hand_disrupt 原语（雪童子，词表 actions +词）：
1. 对手手牌均匀随机 1 张（单一随机源；同种子两次运行选中序列一致）→ reveal 事件 →
   回对手牌库 + 洗对手库；自己手牌/牌库不受影响
2. 对手手牌空 → 效果段 no-op、伤害 20 照算；参数校验未知词 DslError

bench_size 覆写 + 失效缩减（零之大空洞）：
3. 竞技场在场 + 己方太晶在场 → 己方备战上限 8（手动放置与效果放置均放开）；
   对方无太晶 → 对方仍 5
4. 失效触点①竞技场被顶/弃置 ②己方太晶离场 → 立即缩减：该方玩家自选弃置至 5
   （choose）；非昏厥无奖赏；双方同时超 → 持有者先执行
5. 无竞技场时 5 只上限回归（默认不变式不受影响）；词表 +bench_size

search 二选一组合约束（小刚的发掘）：
6. 分支 A basic_pokemon up-to 2 / 分支 B 进化 up-to 1；互斥（混合选择不可达）；
   reveal + hand + shuffle 全流
7. 选 0 → no-op 重洗仍执行；池不足收缩；参数校验 DslError

distinct-type + 拆分去向（赤松）：
8. 基本能量选择池属性互异（2+ 属性可选满 2）；拆分：1 张入手（玩家选定）+ 剩余附着
   自己宝可梦（目标自选）
9. **单属性能量牌库 → 可选上限收缩 1 → 入手 1 / 附着 0 / 重洗**（用户补充场景）；
   选 0 → 全 no-op 重洗

deck_top 有序去向（暗码迷）：
10. search any up-to 2 → 余库重洗 → 所选按选择顺序回牌顶（先选在顶 FIFO）；
    牌库不足 2 收缩；选 0 → 仅重洗

own_ko_by_attack + lock_retreat（沙铃仙人掌）：
11. 炸裂针刺：战斗场受对手招式伤害昏厥 → 攻击方放 6 指示物；效果/指示物致昏厥不触发；
    备战昏厥不触发；攻击方已离场 no-op
12. 穷追不舍：被伤害目标下个其回合撤退枚举被门控；再下回合解禁；进化/离场清除
13. 词表 events +own_ko_by_attack / actions +lock_retreat；参数校验

protection 最小版 + own_attached_energy choose=1（火恐龙两文件）：
14. 大字爆炎：damage 90 + discard own_attached_energy choose=1（any_count 之外补
    choose 形式）；自身无能量 → 效果 no-op 伤害照算
15. 闪焰之幕：对手招式附加效果（指示物/状态/弃置/换位）对持有者不适用；伤害照算；
    词表 +protection

招式学习器载体 + devolve（招式学习器 退化）：
16. 学习器附着后持有者可宣言其招式（费用校验走既有路径）；持有者回合结束自弃
17. devolve：对手全场已进化宝可梦各退栈顶 1 张回对手手牌；二段进化只退 1 张；
    未进化/对手场空 → no-op
18. 退化后伤害指示物保留、特殊状态恢复；新 HP 上限 < 已有伤害 → 昏厥结算；
    能量/道具不动

卡牌落地（三道闸，分片 `tests/test_dsl_cards_b6_wp6.py`；card_ids 以装配池内实际
印刷 + db 同文本等价类实测为准）：
19. 雪童子 惊吓类：用例——全流（随机选→reveal→回库洗对手库）/ 对手空手 no-op /
    种子复现
20. 零之大空洞：用例——太晶在场 8 上限 / 失效自选缩减 / 双方同时缩减持有者先 /
    无奖赏
21. 小刚的发掘：用例——基础 up-to 2 / 进化 up-to 1 / 互斥负例 / 空选重洗
22. 赤松：用例——双属性选满拆分 / **单属性收缩（用户场景）** / 空选重洗
23. 暗码迷的解读：用例——选 2 有序回顶（顺序断言）/ 选 0 仅重洗 / 余库重洗
24. 沙铃仙人掌：用例——炸裂针刺三条件正反 / 攻击方离场 no-op / 撤退锁门控与解除
25. 火恐龙 151C-005 类：大字爆炎 choose=1 弃能量 / 无能量 no-op；火恐龙 CSV5C-015 类：
    闪焰之幕免疫附加效果 / 伤害照算
26. 招式学习器 退化：用例——学习器宣言/回合结束自弃 / devolve 全场退化 / 二段只退 1 /
    伤害保留 + HP 超限昏厥

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归 +
`dsl-check --db` 全库全 OK + 词表同步（actions +hand_disrupt/+lock_retreat/+protection
/+devolve；bench_size / distinct / deck_top 按落点归段）+ 真机冒烟（玛俐雪妖女 /
多龙巴鲁托 / 喷火龙大比鸟 / 赛富豪 / 猛雷鼓厄诡椪 / 赫普的苍响 / 多龙黑夜魔灵池内卡组）

### WP7（B 级 15 张：宝可梦检查阶段 + 常驻伤害修正挂载面扩展 + 8 项小原语）——测试清单定稿（2026-09-19）

范围 = coverage-plan B 级 pending 15 张（池内印刷已逐卡实测 deck_cards + db text_raw，
2026-09-19；均为池内单一印刷，同文本等价类印刷随闸 1 实测挂载）：

- 化朗镇（I 标 CSV10C-218，竞技场，赫普的苍响）：双方「赫普的宝可梦」招式对对手战斗场 +30
- 古玉鱼（G 标 CSV5C-022，喷火龙大比鸟）：①闪焰生成（弃牌区最多2基本火能量附着1只）
  ②嫉妒业火 50+（上一对手回合自己宝可梦因招式伤害昏厥 → +90）
- 咕咕（H 标 CSV9C-154，猛雷鼓厄诡椪）：三刺击 10×（掷币3次×正面数）
- 喷火龙ex（G 标 CSV5C-075，喷火龙大比鸟/多龙喷火龙）：烈炎支配（手牌进化触发：
  牌库最多3基本火能量任意附着+重洗）+ 燃烧黑暗 180+（对手已拿奖赏×30）
- 大比鸟ex（G 标 CSV4C-101，喷火龙大比鸟）：音速搜索（回合1次任意检索1张，同名共享锁）
  + 狂风呼啸 120（若希望弃场上竞技场）
- 小火龙（G 标 151C-004，喷火龙大比鸟/多龙喷火龙）：烧光（弃场上竞技场）+ 吐火 30 白板
- 火箭队的惊吓炸弹（I 标 CSV10C-198，物品，赫普的苍响）：掷币——正面对手1只放2指示物，
  反面自己战斗场放2指示物
- 爬地翅（G 标 CSV6C-082，古代，猛雷鼓厄诡椪）：踏平（对手牌库顶1张→弃牌区）+
  烫伤怒涛 120（自伤90+对手战斗场灼伤）
- 空手道王的修炼（H 标 CSVH4eC-044，支援者，赫普的苍响）：本回合自己宝可梦招式
  对对手战斗场 ex +40
- 裁判（G 标 CSVH1C-051，支援者，猛雷鼓厄诡椪）：双方手牌洗回牌库，各抽4
- 谢米（I 标 CSV10C-007，多龙黑夜魔灵/多龙喷火龙/玛俐雪妖女）：花之纱幔（在场期间
  自己备战宝可梦（除规则盒）不受对手招式伤害）+ 踢飞 30 白板
- 赫普的卡比兽（I 标 CSV10C-175，赫普的苍响）：慷慨（在场期间自己赫普宝可梦 +30，
  同名不叠加）+ 强劲压制 140（自伤80）
- 赫普的讲究头带（I 标 CSV10C-201，道具，赫普的苍响）：持有者（赫普的）招式费用 -1【无】
  + 对对手战斗场 +30
- 野餐篮（G 标 CSV3C-117，物品，赛富豪）：双方所有宝可梦各回复30
- 雪妖女（H 标 CSV7C-059，玛俐雪妖女）：冻结帷幕（每当宝可梦检查时，双方所有拥有特性的
  宝可梦（除雪妖女）各放1指示物）+ 冰霜粉碎 60 白板

设计决议（主会话定稿 2026-09-19；随落地进附录 A 🔲，gate3 核销后翻 ✅）：

- **D-WP7-1 宝可梦检查阶段**（rules-manual §7.2，出处 basic_rules07）：每回合结束时
  新增检查阶段，对双方全场宝可梦结算——①中毒放1指示物 ②灼伤放2指示物后持有者掷币
  正面恢复 ③睡眠持有者掷币正面恢复 ④麻痹在**其持有者下一个自己回合结束后**的检查
  直接恢复（需记录麻痹施加方/回合标记，施加当回合结束不恢复）⑤检查触发的特性/训练家
  效果（pokemon_check 事件）。§7.2 注「处理顺序可由玩家自行决定」→ 引擎确定性暂定
  口径：回合持有者方先、状态按 中毒→灼伤→睡眠→麻痹 固定序、随后事件触发；掷币走
  单一随机源。**全部处理结束后**统一 check_knockouts + 奖赏（§7.2 末注：检查结束后、
  下一回合开始前判昏厥），再进入下一回合。
- **D-WP7-2 特殊状态结算补齐**：引擎 SpecialCondition 此前仅混乱（招式时掷币）有结算，
  本批按 §7.2/§7.3 补中毒/灼伤/睡眠/麻痹的检查阶段结算与行动限制（睡眠/麻痹不可
  撤退、麻痹/睡眠不可用招式的枚举门控若已有则接通、无则补）。现网 cards/ 无卡施加
  毒/眠/麻（grep 实证：仅 愿增猿 apply_status confused），沙奈朵镜像无状态卡——
  hash 回归预期不变；**若镜像 hash 变动 → 停下上报主会话，不擅自更新基准**。
- **D-WP7-3 常驻伤害修正挂载面泛化**：`_effective_damage_modifier` 由「仅持有者道具」
  扩为多来源求和——①持有者道具（既有口径不变）②场上竞技场卡（化朗镇：双方攻击者
  均生效，condition 对攻击方持有者求值）③自己场上宝可梦卡 aura（慷慨：
  modify_damage args.scope=own_field，condition 对攻击方持有者求值，**同名来源卡
  去重不叠加**）④回合级标记（空手道王：支援者 on_play 落 modify_damage 标记于
  PlayerState 回合字段，回合结束清除——走 prize_bonus 同模式）。目标侧过滤走
  args.target_rule_box（空手道王 ex：求值点校验对手战斗场 rule_box）。结算顺序位不变
  （§6 顺序 2：基准后、弱点抗性前）；仅「对对手战斗宝可梦」落点（备战落点不加）。
  新 condition 词 `holder_owner:X`（对持有者求值，读 CardDef.owner）。
- **D-WP7-4 攻击费用修正读道具**：`_effective_attack_cost` 增读持有者道具
  passive_static modify_attack_cost 分支（仿 _effective_retreat_cost 道具扫描），
  condition 对持有者求值（讲究头带 holder_owner：赫普，-1【无】，clamp ≥0）。
- **D-WP7-5 谢米 花之纱幔**：protection 新 scope `opponent_attack_damage_to_bench`
  ——**伤害**免疫（区别于 D-WP6-7 的效果免疫）、作用面 = 自己备战区、来源限对手招式；
  「除拥有规则的宝可梦外」= 新场上过滤器 `no_rule_box` 作用于**受保护目标**（非来源）。
  守卫落点 = 招式伤害对备战宝可梦的施加路径（含 damage 原语 bench 目标与引擎直接
  路径）；指示物放置不是伤害、不受此保护（雪妖女 vs 谢米 不互动）。
- **D-WP7-6 discard_stadium 原语**（大比鸟ex/小火龙共用）：公共场竞技场弃入其持有者
  弃牌区 + stadium 状态清理（复用 _do_play_stadium 旧场处理路径）。「若希望」的放弃
  选项不建模——满足即执行（对齐 D-WP2-3 触发式特性不建模放弃选项先例）。
- **D-WP7-7 古玉鱼 嫉妒业火**：跨回合精确口径新标记
  `own_ko_by_attack_during_opponent_turn`（仅**招式伤害**致昏厥置位，对齐 WP6
  own_ko_by_attack 精确口径；效果/指示物致昏厥不置位；置位/清除时点仿现有
  own_ko_during_opponent_turn——宽口径标记不动，既有卡不受影响）。新节点级
  condition 词 `if_own_ko_by_attack_during_opponent_turn` 门控追加 90 节点
  （基准 50 无条件照打）。
- **D-WP7-8 喷火龙ex 烈炎支配**：attach_energy 新 selector `own_deck`（牌库来源
  附着）：filters basic_energy + energy_火，up-to 3（min 0），multi_target 任意分配
  （目标自己场上宝可梦，每只张数自由），结算后重洗牌库。触发 own_evolve_from_hand
  既有（猫头夜鹰先例）。「以任意方式」= 张数在目标间自由分配。
- **D-WP7-9 裁判**：新原语 `shuffle_hand_into_deck`（selector own_hand /
  opponent_hand 各一节点实现「双方」，手牌回库+重洗——**不是库底**，
  hand_to_deck_bottom 语义不动），随后 draw 4 + draw opponent_deck 4
  （奇树结构先例）。
- **D-WP7-10 小件四项**：①place_damage_counters selector +own_active（惊吓炸弹
  反面）；②damage selector +self（爬地翅 90 / 卡比兽 80 自伤——效果文伤害：
  固定值直接放置，**不吃弱点/抗性/增伤修正**（§6 伤害计算仅适用于招式基准值链路），
  致昏厥走正常 check_knockouts）；③heal selector +all_pokemon_both（野餐篮：
  双方全场各 30，无 choose，满血 no-op 照常）；④新原语 `mill`（对手牌库顶 N 张
  → 对手弃牌区，牌库不足收缩，牌库空 no-op）。
- **D-WP7-11 雪妖女 冻结帷幕**：新事件词 `pokemon_check`（D-WP7-1 第⑤步触发，
  双方回合结束均触发）；CardDef 新字段 `has_ability`←db abilities JSON 非空
  （WP1 数据管道同路径）；场上过滤器 +has_ability / +not_name:X；放置 selector
  +all_pokemon_both（filters 收敛目标池）。多只雪妖女在场各触发各结算（无同名锁，
  原文无「不重复」注——对照慷慨有注，从字面）。

测试清单：

宝可梦检查阶段 + 特殊状态（D-WP7-1/2，`tests/test_primitives_wp7.py` 或新分片）：
1. 中毒：检查阶段放 1 指示物（双方在场中毒宝可梦各结算）；持续多回合累计
2. 灼伤：放 2 指示物 + 掷币——正面恢复（不再放下一轮）/ 反面保持下轮再放；
   种子确定性（同种子两次运行序列一致）
3. 睡眠：掷币正面恢复反面保持；睡眠/麻痹 撤退枚举门控与不可用招式门控接通
4. 麻痹：施加当回合结束**不恢复**；持有者下一个自己回合结束后的检查恢复
5. 检查全部结束后统一判昏厥 + 拿奖赏（灼伤指示物致昏厥：对方拿奖赏、换上流程）；
   检查阶段昏厥的战斗场宝可梦换下后再进入下一回合
6. 处理顺序确定性：回合持有者方先、毒→灼→眠→麻→事件触发（同种子重放一致）；
   混乱不在检查阶段结算（§7.3）
7. 词表同步 + 参数校验未知词 DslError；**沙奈朵镜像同种子 hash 回归不变**

常驻伤害修正泛化（D-WP7-3/4）：
8. 道具来源回归：不服输头带既有用例全绿（挂载面重构不回归）
9. 竞技场来源：化朗镇在场，双方「赫普的宝可梦」攻击 +30；非赫普宝可梦不加；
   竞技场离场即失效；备战落点不加
10. 宝可梦 aura 来源：卡比兽在场，自己赫普宝可梦（含卡比兽自身）+30；两只卡比兽
    同名去重只加一次；卡比兽离场即失效；非赫普不加
11. 回合级标记：空手道王打出后本回合对对手战斗场 ex +40、对非 ex 不加；
    回合结束清除（下回合不加）；多来源求和叠加（道具+竞技场+回合标记）
12. target_rule_box 求值点校验 + holder_owner 条件词注册/未知词 DslError
13. 费用读道具：讲究头带持有者（赫普）招式费用 -1【无】（clamp ≥0）；非赫普持有者
    不减；道具离场即失效；月月熊自身卡来源 modify_attack_cost 回归绿

protection 伤害免疫（D-WP7-5）：
14. 谢米在场：对手招式对自己备战宝可梦的伤害归零；战斗场不保护；规则盒备战宝可梦
    （如 ex）不保护；对手招式的**效果**（指示物/状态）不受此 scope 影响
    （D-WP6-7 各管各的）；谢米离场即失效；己方招式误伤不保护（来源限对手）
15. no_rule_box 场上过滤器注册 + 未知词 DslError；闪焰之幕既有用例回归绿

小原语（D-WP7-6/7/8/9/10）：
16. discard_stadium：公共场弃置入持有者弃牌区 + 状态清理；无竞技场 no-op；
    词表 +discard_stadium
17. 古玉鱼标记：自己宝可梦在对手回合因招式伤害昏厥 → 次回合标记生效；
    效果/指示物致昏厥不置位；自己回合结束清除；宽口径 own_ko_during_opponent_turn
    既有用例回归绿
18. attach_energy own_deck：牌库选 up-to 3 基本火能量任意分配附着 + 重洗；
    牌库不足收缩；选 0 仅重洗；目标满场自由分配（可全给 1 只）
19. shuffle_hand_into_deck：双方手牌各回库重洗 + 各抽 4（裁判全流）；手牌空
    照常抽 4；种子确定性
20. place_damage_counters own_active / damage self（固定值不吃弱点抗性增伤）/
    heal all_pokemon_both（满血 no-op）/ mill（牌库不足收缩、空库 no-op）——
    各正例 + 边界 + 词表注册 + DslError
21. 咕咕 三刺击：coin_flip times:3 × flip_heads_count（既有原语组合，卡测试覆盖）
22. 大比鸟ex 音速搜索：once_per_turn_shared 同名锁（两只大比鸟ex 当回合只能用 1 次）
    ——同名锁机制既有（WP 前已落地），卡测试覆盖
23. 雪妖女 冻结帷幕：每次宝可梦检查双方拥有特性的宝可梦（除雪妖女）各 +1 指示物；
    无特性宝可梦不放；多只雪妖女各触发；雪妖女离场不触发；has_ability 数据管道
    映射单测（db abilities 非空 → True）+ not_name/has_ability 场上过滤器注册

卡牌落地（三道闸，分片 `tests/test_dsl_cards_b7_wp7.py`；card_ids 以装配池内实际
印刷 + db 同文本等价类实测为准）：
24. 15 卡逐卡单测（效果正例 + 关键边界 + 事件流锚点），引用 text_raw 原文注释；
    闸 1  schema + 同文本归一校验，闸 2 单卡测试，gate3 攒批待核销
25. 装配校验：故意取错印刷用例被闸 1 拦下（防回归）

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归（预期不变，
变动即停）+ `dsl-check --db` 全库全 OK + 词表同步（actions +mill/+discard_stadium/
+shuffle_hand_into_deck；selectors +self/+own_active（place_damage_counters）/
+all_pokemon_both/+own_deck（attach_energy）；events +pokemon_check；conditions
+holder_owner:/+if_own_ko_by_attack_during_opponent_turn；filters +has_ability/
+not_name（场上）/+no_rule_box（场上）；protection scope +opponent_attack_damage_to_bench；
modify_damage scope +own_field + target_rule_box）+ 真机冒烟（赫普的苍响 / 喷火龙大比鸟 /
猛雷鼓厄诡椪 / 玛俐雪妖女 / 多龙黑夜魔灵 / 赛富豪 池内卡组）

### WP8（特殊能量被动框架 + 喷射/夜光/薄雾 3 卡）——测试清单定稿（2026-09-20）

范围 = coverage-plan C 级「特殊能量被动框架」3 张（池内印刷已实测 2026-09-20，均 G/H 标）：

- 喷射能量（G 标 CSV4C-129，喷火龙大比鸟/赫普的苍响）：视作 1 个【无】；
  当从手牌附着于备战宝可梦时，该宝可梦与战斗宝可梦互换
- 夜光能量（G 标 CSV1C-127，多龙喷火龙/多龙巴鲁托）：视作 1 个**所有属性**能量；
  若持有者还附着其他特殊能量，则视作 1 个【无】
- 薄雾能量（H 标 CSV7C-204，喷火龙大比鸟）：视作 1 个【无】；持有者不受对手
  宝可梦招式的效果影响（已经受到的效果不会消失）

**背景实测**（2026-09-20）：db 特殊能量 `types`/`provides` 均 null → CardDef.energy_type
为 None，现行 `_energy_satisfied`（core.py:64，自由函数）只把它们当【无】计数——
喷射/薄雾恰好等价、夜光应为彩虹是错误口径；且提供值硬读字段、无 DSL 声明面。
调用点：core.py:349（攻击枚举）+ agent/heuristic.py 三处（启发式估值用）。

设计决议（主会话定稿 2026-09-20；随落地进附录 A 🔲，gate3 核销后翻 ✅）：

- **D-WP8-1 provide_energy 声明式框架**：特殊能量的提供值走 DSL 声明
  （引擎零硬编码）——能量卡文档 passive_static + `provide_energy` 原语：
  args.types=[无]（单属性）/ args.types=all（彩虹：1 个能量单元可抵**任意 1 个**
  需求符号，含有色）。求值点：`_energy_satisfied` 改引擎方法，逐附着能量读 DSL
  文档——无文档 → 既有行为（card.energy_type，None 计入无色）；有文档 → 收集
  condition 通过的 provide_energy 声明，恰 1 条取其提供值，0 条回退默认，
  ≥2 条 DslError（不猜）。匹配算法：有色需求先精确匹配非彩虹单元、再以彩虹
  单元抵，余下单元抵无色（ rainbow 全程只算 1 个单元）。
- **D-WP8-2 夜光降级条件**：「除这张卡牌以外的特殊能量」= 持有者附着的特殊能量
  （card_type=energy 且非 is_basic_energy）**计数 ≥2**（含夜光自身——两张夜光
  互相使对方降级，忠实文本）；基本能量不计。condition 新词
  `holder_special_energy_count_ge:2`（参数化先例 holder_has_energy:）。
  夜光 DSL = 两 passive_static 块：有条件块提供 [无]、无条件块提供 all
  （互斥，恰 1 条通过）。
- **D-WP8-3 喷射换位触发**：新事件词 `own_attach_from_hand_to_bench`——手动
  能量附着行动（每回合 1 次权）完成后，目标是备战区时分发；能量卡文档
  trigger_on_event + switch 原语（self 与战斗场互换）。附着到战斗场不触发；
  效果附着（attach_energy 原语：discard/deck 来源）不触发——现网无从手牌的
  效果附着，文本「从手牌附着」在一期=手动附着口径（附录 A 记）。当回合附着权
  消耗、换位后撤退锁/状态等按既有换位口径。
- **D-WP8-4 薄雾 protection 能量来源**：`_protected_from_attack_effects`
  （D-WP6-7 守卫落点不变：apply_status/place_damage_counters/lock_retreat/
  devolve）增读持有者**附着能量卡**文档的 protection scope=opponent_attack_effects
  声明（与宝可梦卡自身声明并集）。「已经受到的效果不会消失」= 落点守卫设计
  天然满足（不做回顾性清除），注释记明。
- **D-WP8-5 Agent 侧保持近似**：heuristic 三处 `_energy_satisfied` 调用走自由
  函数旧口径（energy_type/None→无，不含 DSL provide/彩虹）——Agent 只做估值
  排序，合法性由引擎枚举门控，近似不产生非法操作；夜光彩虹在 Agent 眼里退化为
  无色（可能低估攻击可用性，不影响正确性）。附录 A 记为已知近似。

测试清单：

provide_energy 框架（D-WP8-1/2，`tests/test_primitives_wp8.py`）：
1. 无 DSL 文档能量行为回归（既有攻击枚举/费用测试全绿不动）
2. types=[无]：计入无色、不抵有色；types=all：抵任意 1 个有色符号（【火】可满足）、
   1 张彩虹只抵 1 个符号（【火】【火】需 2 单元）、彩虹+普通混合抵费
3. 多声明：0 条通过回退默认 / ≥2 条通过 DslError；词表注册 + 未知词 DslError
4. 夜光降级：单独附着=彩虹；+任意 1 张其他特殊能量 → 【无】（holder_special_energy_count_ge:2
   条件词注册）；2 张夜光互相降级；基本能量不影响计数
5. 求值点一致性：攻击枚举与执行共用（同种子对局不发散）

喷射换位（D-WP8-3）：
6. 手动附着备战 → 该宝可梦与战斗场互换（含事件流锚点）；附着战斗场不触发；
   附着权正常消耗；换位后特殊状态按既有口径（回备战恢复——睡眠/麻痹/混乱清除）
7. 效果附着（attach_energy discard/deck 来源）不触发；事件词注册

薄雾 protection（D-WP8-4）：
8. 持有者不受对手招式附加效果（指示物/特殊状态/撤退锁/退化四落点抽查）；
   伤害照算；已受效果不消失（附着前已中的特殊状态保留）；能量离场（devolve/
   弃置）即失效；闪焰之幕既有用例回归绿

卡牌落地（三道闸，分片并入 `tests/test_dsl_cards_b7_wp7.py` 或新 b8 分片）：
9. 3 卡逐卡单测（效果正例+边界，text_raw 原文注释；card_ids 同文本等价类实测
   挂载）+ 闸 1 防回归用例

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归 +
`dsl-check --db` 全库全 OK + 词表同步（actions +provide_energy；events
+own_attach_from_hand_to_bench；conditions +holder_special_energy_count_ge:）+
真机冒烟（喷火龙大比鸟 / 赫普的苍响 / 多龙喷火龙 / 多龙巴鲁托池内卡组）

### WP6+（pending 33 张 B/C 级）

启动时按同流程细化；批次级验收口径：

- 每个新 filter/condition/原语：注册词单测 + 未知词 DslError 不猜 + 词表 vocabularies.yml 同步
- 每张落地卡走三道闸（schema → 单卡单元测试 → 人工核销），日志落 `cards/authoring-log.jsonl`
- 装配校验：故意取错印刷的用例必须被闸 1 拦下（防回归测试）
- 全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归
- 批末落账：coverage-plan 状态全量更新 + authoring-log 质量数据（first_pass / 人工修改量）
- WP6 后 blocked 清零；剩余 pending 33 张（B/C 级）按「解锁卡数 + 机制通用性」排序
  续批推进（C 级含 TERA 规则盒核对 task 027 / ACE SPEC task 027 / 持续 lock 体系
  task 029 依赖项）

## 实现要点

- 严守不猜纪律：装配发现清单外机制缺口 → blocked 上报，不顺手扩展范围
- 词表一律开放字符串 + vocabularies.yml 注册，不写死代码
- 规则语义存疑 → ptcg-rules skill 查 rules-manual → rules-reference → 附录 A 决议日志
- 归组口径（2026-09-06 用户决议）：DSL 按（卡名 + 文本）等价类组织、严格拆分（同语义异措辞不合并）；
  装载键 name_group → card_id 精确挂载；闸 1 校验文件内 card_ids 归一化 text_raw 一致

## 结果与遗留

### WP0（2026-09-06 完成）：harness 装配校验 + card_id 挂载 + 审计拆分

**落地**：
- `dsl/loader.py` 新增 `CardLibrary`（dict 子类，键 = card_id）：`from_docs` 校验挂载键必填 +
  card_id 跨文件查重（含文件名上下文）；`by_name(name)` 按文档去重返回；`load_card_dir` 返回 CardLibrary。
- `engine/core.py` 新增 `effect_doc` / `effect_doc_by_ref` 解析助手，全部 17 处查询点 +
  `dsl/primitives.py`（copy_attack）改走助手：CardLibrary 仅按 card_id（无名字兜底），
  朴素 dict 按卡名（存量测试兼容路径保留）。`GameEngine.__init__` 保 CardLibrary 类型。
  copy_attack 嵌套帧 inner 改三元组（card_id, 卡名, 招式名）。
- `runner/experiment.py` 新增 `assemble_card_effects`（按 card_id 过滤 + 覆盖告警）；
  prepare / prepare_variant 改走之；worker 载荷改为去重文档列表，worker 内重建 CardLibrary。
- `cli.py` dsl-check 新增 `--db`：① card_id 存在性 ② 文件内归一化 text_raw 一致
  ③ 最新 standard 合法性快照（SDK `legal_at` LegalityPool，含再录合法口径）。无 --db 行为不变。

**审计拆分实测**（只读 SQL + SDK 复核）：全库仅 2 个文件异文本混挂——
- 不服输头带：10 → 9（剔除 CSVH1aC-016「宝可梦使用的招式」异文本类；池内印刷 CSV1C-117 保留）
- 朋友手册：20 → 11（剔除「2张」类 9 个 id：CSM1DC-246/CSM1bC-121/CSM2.1C-006/CSM2DC-255/
  CSMPkC-010/CSMPoC-007/SSP-NaN48~50；池内印刷 CSV1C-111 所在「最多2张」类保留）
- 出库 3 文件（全印刷退环境 + 池内零使用）：彷徨夜灵.yml（D 标 CS2.5C-018，任务指定）、
  **交替推车.yml / 捕获香氛.yml（全印刷 F 标退环境，同口径出库——超出任务清单的实测发现，
  单卡测试分片同步移除；若回归环境再按 WP2 管线重写）**
- 其余候选（厉害钓竿/反击捕捉器/巢穴球/高级球/神奇糖果/能量转移/夜光能量/波波/皮宝宝）
  实测单文本类且全印刷在合法性快照内（旧标经再录合法），无需收窄。

**验收**：pytest 404 全绿；ruff 零告警；`dsl-check --db` 全库 33 文件全 OK；
沙奈朵镜像同种子 hash 回归（test_deckload::test_loaded_deck_plays_game，真实卡组 +
CardLibrary 直通）通过；池内 9 套卡组印刷覆盖回归：唯一未覆盖且同名有文档的印刷 =
波波 CSV4C-099（「起风」白板异文本，合法走覆盖告警，断言豁免）。

**遗留**：
- 波波 CSV4C-099 式覆盖告警目前仅 prepare 透传打印，report 层未聚合（不影响结果口径）。
- 交替推车/捕获香氛出库后，coin_flip 节点门控 / heal+switch own_bench / own_active_is_basic
  条件失去真实卡测试载体（机制仍在 chooser/原语注册）；WP1+ 落地同机制新卡时回补。
- m5-coverage-plan / authoring-log 的彷徨夜灵已有 blocked 记录；交替推车/捕获香氛原为
  gate3 通过卡，出库落账（状态改「出库：退环境」）由主会话统一处理。
- 彷徨夜灵 H 标 CSV8C-082（咒怨炸弹）归 WP2：place_damage_counters + 自我昏厥原语落地后新写。

### WP1（2026-09-07 完成）：filters/conditions 高频解锁项 + CardDef 数据管道 + 3 卡落地

**数据管道**：CardDef 新增 `is_tera` / `owner` / `labels`（`engine/state.py`）；
`carddef_from_db` 映射 is_tera←db is_tera、owner←db owner、labels←effect_tags.labels
（db PRD v1.23 契约键，mik 机制标签「古代/未来」等——db 无独立特质列，labels 键即特质事实源）。
单测落 `tests/test_deckload.py`（含缺省空值不猜用例）。

**filters 注册**（`dsl/chooser.py`，未知词仍 DslError）：
- 卡维度：`name:<卡名>`、`owner_pokemon:<名>`（宝可梦且 owner 命中；db 未覆盖主人组恒不匹配，
  不回落卡名硬推）、`energy_<属性>` 参数化（原字面词 energy_超 泛化并入，行为回归测试保持）、
  `pokemon_no_rule_or_basic_energy`、`trait:<特质>`（CardDef.labels）
- 场上维度：`basic_pokemon`（与卡维度同词同义复用，栈顶 stage==0）、`trait:<特质>`

**conditions 注册**（`condition_met`）：`self_is_active`/`holder_is_active`（栈顶 iid 比对）、
`first_own_turn`（turn==1，turn 仅在先攻方回合开始递增）、`own_tera_in_play`、
参数化 `opponent_prizes_eq:N` / `opponent_prizes_in:[...]` / `holder_hp_le:N`
（有效 HP − 已受伤害；畸形参数 DslError 不猜）。
单测落 `tests/test_filters_conditions_wp1.py`（14 用例）。

**引擎钩子**：`_do_attack` 支持 on_attack 效果级 condition——不满足则招式失败
（不结算伤害/效果、回合照常结束、attack 事件落 failed 标记），「则这个招式失败」语义
（赫普的古月鸟）。既有卡无 on_attack condition，行为零回归。

**落地 3 卡**（三道闸前两闸全过，gate3=false 待用户核销；authoring-log 已落 first_pass=true）：
- 老大的指令（CSVH1aC-023）：gust 无门控版；38 个印刷归一化 text_raw 实测全一致、全挂载。
- 尖钉镇道馆（CSV10C-216）：stadium_grant + `owner_pokemon:玛俐`。
- 赫普的古月鸟（CSV10C-188）：`opponent_prizes_in:[4,3]` + 招式失败钩子。
- 分片测试 `tests/test_dsl_cards_b2_wp1.py`（7 用例，含老大的指令无备战不可用门、
  尖钉镇道馆过滤负例、古月鸟奖赏 4/3/5 三分支）。

**词表同步**：本批未新增 actions/selectors/counters/destinations/triggers/limits 六段词
（gust 用既有 switch、检索用既有 search_deck/shuffle_deck）；filters/conditions 按既定架构
注册于代码求值点（vocabularies.yml 无对应段，闸 1 不校验，闸 2 兜底），vocabularies.yml 无变更。

**验收**：pytest 427 全绿（基线 404 + WP1 新增 23）；ruff 零告警；`dsl-check --db`
全库 36 文件全 OK；沙奈朵镜像同种子 hash 回归（test_loaded_deck_plays_game）在套件内绿。

**遗留**：
- **db 数据缺口：cards.owner 未覆盖赫普组**（实测 DISTINCT owner = 玛俐/竹兰/莉莉艾/N/火箭队）——
  赫普的包包 blocked，需 db 侧补数（不回落卡名前缀硬推）。化朗镇/赫普的讲究头带/赫普的卡比兽
  等其余赫普机制卡届时同受其益。
- 多龙奇原 blocked 原因失真（装配复核）：实测为「牌库顶2检视选1、剩余放下方」，缺
  search_deck top_n 检视 + 剩余卡 deck_bottom 去向，归 WP2+ 原语批。
- 水莲的照顾：过滤器已备，缺 recover_from_discard hand up-to（min_choose=0，同 超级能量回收）。
- 奥琳博士的气魄：trait：古代 已备，缺 attach 多目标各附1。
- coverage-plan 已更新 13 行 blocked 原因（标注 WP1 已备项）+ 3 行 done。

### WP2（2026-09-07 完成）：trigger_on_event 分发 + place_damage_counters + ko_self + 2 卡落地

**换上队列与结算顺序**（`engine/state.py` / `engine/core.py`）：
- 删 `promote_to_main`，新增 `promote_queue: list[PromoteReq]` + `resume_after_promotes` 挂起恢复
- 效果内昏厥（ko_self 等）：弃牌/奖赏按文本语序立即结算，换上推迟到效果完成后按
  `promote_queue` 统一进行并回效果方主阶段（D-WP2-1）。行为修正：亢奋脑力 KO 对手战斗场
  旧实现错进对手回合，现正确回我方主阶段
- 多昏厥换上按扫描序（玩家0→1、备战→战斗场）FIFO（D-WP2-2）；
  双方同时无宝可梦 → 平局 is_draw（D-WP2-4）
- 解释器 `_run_or_suspend` 完成路径翻 promote；game_over 守卫（终局后效果不再结算）

**新原语**（`dsl/primitives.py`）：
- `ko_self`：自我昏厥入队列（彷徨夜灵咒怨炸弹）
- `place_damage_counters`：选择器池放置 N×10 伤害指示物（counters:N 参数化），
  池不足 min 收缩；bounce 迁移同构
- chooser `ability_feasible` 补两原语可行性门

**trigger_on_event 分发**：`Effect.event` 字段（schema + loader 校验，vocabularies.yml
新段 `events:` + `own_play_from_hand_to_bench`）；`_do_place_bench` 主阶段触发点
（拍备战完成时检索挂该事件的特性卡并逐个结算）。触发式特性「可使用」放弃选项不建模
（自动发动 + 尽力而为，D-WP2-3）；池空 no-op、池不足 min 收缩。

**落地 2 卡**（闸 1/2 全过，first_pass 2/2，gate3 已核销 2026-09-07）：
- 彷徨夜灵 H 标（CSV8C-082 咒怨炸弹，card_ids 4 印刷）：ability_manual + once_per_turn +
  ko_self + place_damage_counters opponent_pokemon_any counters:5——WP0 核销不过的缺口卡回库，
  全库唯一卡测试载体恢复，test_loader_cardid 出库断言同步更新
- 摔角鹰人（CSV1C-079，card_ids 8 印刷）：trigger_on_event own_play_from_hand_to_bench +
  place_damage_counters opponent_bench choose:2 counters:1
- 分片测试 `tests/test_dsl_cards_b2_wp2.py`（7 用例）

**词表同步**：actions +ko_self；新段 events: [own_play_from_hand_to_bench]（PRD §5.1 同步
「事件触发」段）。

**测试**：新 44 条——test_promote_queue 8 / test_primitives_wp2 17 / test_trigger_on_event 8 /
test_dsl_schema +4 / 卡分片 7；全量 474 绿（基线 430）+ ruff 零告警 +
`dsl-check --db` 全库 39 文件全 OK + 沙奈朵镜像同种子 hash 回归绿（主会话独立复验 diff 一致）。

**真机冒烟**：多龙黑夜魔灵（655545）vs 喷火龙大比鸟（650353）20 局 heuristic 镜像 0 失败，
ko_self 真实触发 27 次；摔角鹰人 trigger 真实对局未自然出现（启发式 Agent 主阶段不铺备战，
既有口径），由单卡测试覆盖。

**规则决议 4 条落 rules-reference 附录 A（🔲 待核）**：D-WP2-1~4（同上）。
沙铃仙人掌维持 blocked：撤退锁归 task 029、KO 来源追踪未建——无落地卡的原语不先行。

**遗留**：
- 彷徨夜灵 / 摔角鹰人 gate3 已核销（2026-09-14 用户核对通过，authoring-log human 行 +
  coverage-plan「已核销」已落账）
- 附录 A 4 条决议 ✅ 已核（2026-09-14 用户核对通过）
- WP3 = 多龙奇（search_deck top_n 检视 + deck_bottom 去向）/ 夜巡灵（recover bench）/
  奥琳博士的气魄（attach 多目标各附1）；猫头夜鹰需 own_evolve_from_hand 事件 + reveal 原语

### WP3（2026-09-14 完成）：recover 去向扩展 + top_n 检视 + attach 多目标 + own_evolve_from_hand + reveal + 5 卡落地

**机制落地**（`dsl/primitives.py` / `dsl/chooser.py` / `engine/core.py`）：
- `recover_from_discard`：destination=bench（up-to、entered_play_this_turn 登记、备战区
  5 只容量在池解析即截断）+ hand 去向 args.up_to=true（min_choose=0，既有 hand 默认
  min=1 行为回归不变）
- `search_deck`：args.top_n=N 检视牌库顶 N 张为选择池 + args.rest=deck_top/deck_bottom
  未选卡按原序归位不洗牌；私密检视观测纪律（事件流只落选择结果，不落未选卡）；
  既有 bench 去向未做容量截断的问题随本 WP 一并补上
- `attach_energy`：args.multi_target=true 多目标各附1（段1 选能量 up-to N → 段2 选等量
  目标 args.target_filters → FIFO 配对，D-WP3-1；任一侧空 no-op；check_knockouts 兜底）
- `own_evolve_from_hand` 事件：`_do_evolve` 挂点；WP2 触发分发抽公共函数
  `_fire_trigger_on_event`（_do_place_bench 行为不变回归）；神奇糖果等手牌来源的
  DSL 效果进化经 pending_event_triggers 队列在外层效果完成后排水触发，
  牌库来源（招式学习器「进化」）不触发（D-WP3-2，✅ 用户 2026-09-14 裁决）
- `reveal` 原语落地（词表既有词）：selector 池 iids+卡名落 reveal 事件，无状态变更
  （D-WP3-4；已知近似：池按 selector+filters 执行时重解析，可能宽于实际移动卡）
- chooser 双可行性门补 recover/search 新形式（池空 / bench 满不可行；未知形式 DslError）

**落地 5 卡**（闸 1/2 全过，first_pass 5/5，gate3 已核销 2026-09-14）：
- 多龙奇 H 标侦察指令（CSV8C-158 / CSV9.5C-133 / CSVM2bC-006）：ability_manual +
  once_per_turn + search top_n=2 hand rest=deck_bottom
- 夜巡灵 H 标渡魂（CSV8C-081 / CSV8C-210 / CSV9.5C-069 / SVP-346）：**on_attack 招式** +
  recover bench choose=3 name:夜巡灵
- 奥琳博士的气魄 G 标（7 印刷单文本类全收）：on_play + attach multi_target trait:古代
  choose=2 + draw 3
- 猫头夜鹰 寻找宝石 H 标（CSV9.5C-142 / CSV9C-155 / CSV9C-214 / CSVM2aC-011 / SVP-291）：
  trigger_on_event own_evolve_from_hand + own_tera_in_play + search trainer choose=2 +
  reveal + shuffle_deck
- 水莲的照顾 H 标（7 印刷单文本类全收）：on_play + recover hand choose=3 up_to +
  pokemon_no_rule_or_basic_energy + reveal
- 分片测试 `tests/test_dsl_cards_b3_wp3.py`（14 用例）；池内实际印刷全覆盖（实测自
  deck_cards：多龙奇 CSV8C-158 / 夜巡灵 CSV8C-081 / 奥琳 CSV6C-121 / 猫头夜鹰 CSV9C-155 /
  水莲 CSV7C-193）

**词表同步**：events 段 +own_evolve_from_hand；reveal 为 actions 既有词本期实现；
rest / up_to / multi_target 为 args 键（闸 1 不校验 args，同 target_filters 先例）。

**测试**：新 48 条（test_primitives_wp3 28 + test_trigger_evolve_from_hand 5 +
卡分片 14 + test_dsl_schema +1）；全量 522 绿（基线 474）+ ruff 零告警 +
`dsl-check --db` 全库 44 文件全 OK + 沙奈朵镜像同种子 hash 回归绿（主会话独立复验
diff 一致）。first_pass 披露：卡 YAML 与卡分片首跑全过；机制测试分片 2 处测试侧笔误
返工（能力门 doc 漏过滤器 / up_to 测试误用 stub），DSL 零修改。

**真机冒烟 40 局 0 失败**：猛雷鼓厄诡椪（652967）vs 多龙黑夜魔灵（655545）20 局 11/9 +
赛富豪（655513）vs 喷火龙大比鸟（650353）20 局 9/11；机制真实触发：侦察指令
use_ability 122 次、奥琳博士打出 36 次、水莲 reveal 10 次、渡魂相关选择 64 次、
猫头夜鹰 own_evolve_from_hand 真实触发 1 次。

**规则决议 5 条落 rules-reference 附录 A**：D-WP3-1 FIFO 配对 🔲 /
D-WP3-2 触发范围 ✅（用户 2026-09-07 裁决：神奇糖果手牌进化触发、牌库进化不触发，
已修正确认为队列排水分发机制）/ D-WP3-3 检视 up-to 🔲 / D-WP3-4 reveal 口径 🔲 +
效果直放备战区容量截断 🔲。

**裁决修正（2026-09-14）**：D-WP3-2 用户裁决后实现修正——`GameState.pending_event_triggers`
队列 + `_run_or_suspend` 完成路径排水（先于 promote 翻阶段；来源离场即失效跳过）；
测试净增 3 条（525 绿），1 条 WP3 初版「神奇糖果不触发」测试被裁决推翻改写为触发用例。

**偏差披露**：test_dsl_interpreter.py 1 条存量测试锁定词由 reveal 改 put_into_play
（reveal 本期实现，断言语义不变）。

**遗留**：
- 5 张新卡 gate3 已核销（2026-09-14 用户核对通过，authoring-log human 行 +
  coverage-plan「已核销」已落账）；猫头夜鹰核销含 D-WP3-2 裁决修正后确认
- 附录 A 5 条决议 ✅ 已核（2026-09-14 用户核对通过）
- WP4 = 暗码迷的解读（deck_top 去向 + 有序排列选择）/ 怒鹦哥ex（attach up-to-N +
  bench-only 目标池）/ gust 门控版 / devolve 等 blocked 项按解锁卡数排序

### WP4（2026-09-14 完成）：top_n rest=shuffle + attach bench-only/up-to + modify_retreat_cost + cost 弃置排除 + lock_attack + 7 卡落地

**机制落地**：
- `search_deck` args.rest=shuffle：未选卡与牌库其余合并整库重洗（本节点直接洗牌，
  空选/窗内空池也洗——文本「剩余放回牌库并重洗」；与多龙奇 rest=deck_bottom 不洗牌
  按文本严格区分）
- `attach_energy` args.target_pool=own_bench（段2 目标限备战区）+ args.energy_up_to
  （段1 min_choose=0，选 0 张不进段2 no-op）；multi_target × own_bench 组合 DslError
- `modify_retreat_cost` 声明式（D-WP4-1/2）：`_effective_retreat_cost` 仿
  `_effective_hp`，撤退枚举（_main_actions）与执行（_do_retreat）两触点接入；
  减少量加总 clamp 0、"all" 归零、可交换；紧急滑板 holder 条件式（holder_hp_le:30）、
  拉帝亚斯ex scope=own_basic_all（stage==0 全场）；词表 actions +modify_retreat_cost
- cost 弃置排除（D-WP4-3）：cost 段 discard iids 记 ExecutionContext 并随挂起冻结
  （PendingChoice.cost_discarded 穿透），recover args.exclude_cost_discarded 剔除；
  playable_feasible 门 cost choose=2 需手牌 ≥2
- **lock_attack 冷却（用户 2026-09-14 裁决补建）**：InPlayPokemon.attack_locks +
  attack_lock_turn；turn N 使用 → N+1 锁生效 → N+2 回合开始解禁；撤退/离场清除、
  进化继承（🔲 待核）；枚举层跳过被锁招式

**裁决修正 2 条（2026-09-14 用户裁决）**：
- 招式附加效果落点空**不阻却宣言**（伤害照算、效果 no-op）——WP4 清单 18 原口径
  「无备战不可宣言」被推翻，attack_feasible 门移除，怒鹦哥/飞天螳螂用例翻转；
  落附录 A ✅ 已核
- 拉帝亚斯ex 无限之刃冷却机制补建（上同）；已知近似：原文「无法使用招式」（全部），
  lock_attack 现锁绑定本招式名——单招式卡等价，多招式卡需要时再扩 scope
  （附录 A D-WP4-5 🔲 待核）

**落地 7 卡**（闸 1/2 全过，gate3 已核销 2026-09-14；first_pass 5/7）：
- 米立龙揽客（H 标 10 印刷全收）：ability_manual + once_per_turn + self_is_active +
  top_n=6 trainer_supporter rest=shuffle + reveal；first_pass=false（ability_feasible
  缺 reveal 分支的机制门缺口，引擎侧补齐后全绿，DSL 零修改）
- 宝可装置3.0（G 标 5 印刷）：on_play + top_n=7 同上；first_pass=true
- 怒鹦哥ex（G 标 7 印刷）：英武重抽（first_own_turn + once_per_turn_shared +
  discard all + draw 6）+ 鼓足干劲（attach bench-only up-to 2）；first_pass=true
- 飞天螳螂辅助斩（151C-123 单印刷）：on_attack damage 20 + attach bench-only
  energy_草 choose=1；first_pass=true
- 紧急滑板（H 标 8 印刷）：passive_static modify_retreat_cost 双块（-1 无条件 +
  all 条件 holder_hp_le:30）；first_pass=true
- 拉帝亚斯ex（H 标 3 印刷）：天际线 own_basic_all + 无限之刃 damage 200 +
  lock_attack；first_pass=false（测试夹具 retreat_cost=0 笔误 + 冷却裁决后补全）
- 超级能量回收（G 标 8 印刷）：cost discard 2 + recover hand up-to 4
  exclude_cost_discarded + reveal；first_pass=true
- 分片测试 `tests/test_dsl_cards_b4_wp4.py`（27 用例）

**词表同步**：actions +modify_retreat_cost、+lock_attack；rest=shuffle / target_pool /
energy_up_to / exclude_cost_discarded / scope 为 args 键（闸 1 不校验 args，先例保持）。

**测试**：新 64 条（test_primitives_wp4 32 + 卡分片 27 + test_attack_cooldown 4 +
schema；含 2 条宣言门翻转替换）；全量 589 绿（基线 525）+ ruff 零告警 +
`dsl-check --db` 全库 51 文件全 OK + 沙奈朵镜像同种子 hash 回归绿（主会话独立复验）。

**真机冒烟 40 局 0 失败**：赫普的苍响（655512）vs 猛雷鼓厄诡椪（652967）20 局 5/15 +
赛富豪（655513）vs 喷火龙大比鸟（650353）20 局 10/10。

**偏差披露**：`_effective_hp` 加前置过滤（仅对含 modify_hp 声明的效果求 condition，
修 holder_hp_le→_effective_hp 递归；语义等价零回归）；米立龙 CBB5C 七印刷过快照
未收窄。

**遗留**：
- 7 张新卡 gate3 已核销（2026-09-14 用户核对通过，authoring-log human 行 + coverage-plan「已核销」已落账）
- 附录 A 冷却语义决议 ✅ 已核（2026-09-14 用户核对通过）
- WP5 = 暗码迷的解读（deck_top 有序排列选择）/ 小刚的发掘（二选一组合约束）/
  月月熊ex（modify_attack_cost + opponent_taken_prizes 计数词）/ devolve /
  手牌干扰（雪童子）等 blocked 18 项按解锁卡数排序

### WP5（2026-09-14 完成）：any_count 弃置×N + attached_energy_on_target + modify_attack_cost + prize_bonus + until_tails + bounce 附着回手 + transform + 8 卡落地

**机制落地**：
- discard `args.any_count=true`（「任意数量」= up-to all，min_choose=0，与 count/choose
  互斥）+ selector `own_attached_energy`（自己全场宝可梦附着能量池，摘下弃置，
  仅 any_count 形式）+ 计数词 `discarded_this_effect`（ExecutionContext 累计本效果
  前序 discard 张数，供 damage ×N 读取；选 0 张 → 伤害 0 仍可宣言，WP4 宣言裁决延伸）
- 计数词 `attached_energy_on_target`（choose 挂起后求值的目标宝可梦附着能量数）
- `modify_attack_cost` 声明式（D-WP5-4）：passive_static，引擎
  `_effective_attack_cost` 求值点实时读声明（离场即失效），枚举与执行共用；
  只减【无】色部分、下限 clamp 0；计数词 `opponent_taken_prizes`（=6−对手剩余奖赏）
- `prize_bonus` 原语（D-WP5-2）：回合级标记 PlayerState.extra_prize_tera_ko
  （_on_turn_end 清除）；core._knockout_one 触点——active_ko + 拿取方太晶宝可梦
  招式伤害（attack_ctx）→ 从**己**奖赏堆多拿 1，不足按剩余拿取（拿完即胜）；
  args.amount 暂仅 1、scope 暂仅 tera_attack_ko
- coin_flip `args.until_tails=true`（与 times 互斥）：连续掷至反面为止，逐次走单一
  随机源、逐条落事件流；正面次数存 ExecutionContext.flip_heads_count 供计数词
  `flip_heads_count` 读取（常规 times 路径同写）
- bounce `args.attachments=hand`（默认 discard 不变）：整叠+附着能量/道具全回手；
  **顺带修 bounce 不传 filters 的既有 bug**（filters 转发缺失）
- `transform` 替换原语（D-WP5-3）：selector=self + choose=1；来源整叠+附着物进
  弃牌区，牌库匹配宝可梦（filters 如 basic_pokemon + not_name:百变怪）入原位置——
  非昏厥离场（不触发昏厥/奖赏/换上）；伤害/特殊状态/效果不继承（全新
  InPlayPokemon，与 30th 版「全部继承」措辞差异忠实区分）；新宝可梦登记
  entered_play_this_turn；检索 up-to（可空找 → no-op，重洗由后续 shuffle_deck
  节点表达仍执行）；牌库无合法目标 → 不挂起 no-op；不被 ability_feasible 池空
  门控（门控由 effect.condition self_is_active_and_first_own_turn 承担）

**落地 8 卡**（闸 1/2 全过，first_pass 8/8，gate3 待核销）：
- 赛富豪ex（G 标 CSV4C-089 类 7 印刷全收）：嘉奖硬币 draw 1 + 节点门控
  if_self_active 追加 draw 1；淘金潮 discard own_hand basic_energy any_count +
  discarded_this_effect×50
- 猛雷鼓ex（H 标 CSV7C-154 类 7 印刷）：飞溅咆哮 discard all+draw 6；极雷轰
  own_attached_energy any_count + discarded_this_effect×70
- 猛雷鼓（H 标 CSV8C-161 类 2 印刷）：落雷风暴 attached_energy_on_target×30
  （目标含备战；备战弱抗不结算=引擎贯穿规则）；龙之头击 130 白板
- 月月熊 赫月ex（H 标 CSV8C-172 类 8 印刷）：老练招式 modify_attack_cost
  （opponent_taken_prizes 减【无】）+ 血月 240 + lock_attack（沿用 D-WP4-5 近似：
  单招式卡锁本招式名等价全锁）
- 白蕾雅（CSV9C-202 类 6 印刷）：使用条件 opponent_prizes_eq:2 + prize_bonus
  amount:1 scope:tera_attack_ko
- 索财灵-连掷硬币（G 标 CSV4C-063 类 3 印刷，同名多文本拆分独立文件）：
  coin_flip until_tails + flip_heads_count×20
- 牡丹（G 标 CSV1C-124 类 5 印刷）：bounce own_pokemon_in_play basic_pokemon
  attachments=hand
- 百变怪-变身启动（G 标 151C-132 类 4 印刷，同名多文本拆分独立文件）：
  ability_manual + once_per_turn + self_is_active_and_first_own_turn + transform
  （not_name:百变怪）+ shuffle_deck；粘粑粑 10 白板
- 分片测试 `tests/test_dsl_cards_b5_wp5.py` + `tests/test_primitives_wp5.py`

**词表同步**：actions +prize_bonus / +transform / +modify_attack_cost（WP5 段）；
counters +attached_energy_on_target / +opponent_taken_prizes /
+discarded_this_effect / +flip_heads_count；not_name 过滤器 /
self_is_active_and_first_own_turn condition / if_self_active 节点门控为代码注册
（非词表段）。

**测试**：新 62 条；全量 651 绿（基线 589）+ ruff 零告警 + `dsl-check --db` 全库
59 文件全 OK（主会话独立复验）。

**真机冒烟 40 局 0 失败**：赛富豪（655513）vs 猛雷鼓厄诡椪（652967）20 局 6/14 +
赫普的苍响（655512）vs 喷火龙大比鸟（650353）20 局 5/15。机制真实触发：
淘金潮 26 次（含梦幻ex copy:淘金潮 路径）、极雷轰 6 次、连掷硬币 until_tails
8 次（最长 3 连正）、牡丹 attachments=hand 真实回手、白蕾雅 prize_bonus 标记
真实设置；血月/变身启动 40 局未自然出现（月月熊ex 登场 13 次未攒够费用、百变怪
未首发上场），由单卡测试覆盖。

**偏差披露**：词表 actions +prize_bonus 为任务书外必要新增；bounce filters 转发
bug 修正；月月熊 lock_attack 沿用 D-WP4-5 近似；transform 不被 ability_feasible
池空门控；test_loader_cardid 白名单 +CSV9C-096（索财灵同名异文本印刷，波波先例）。

**落账对账修正**：coverage-plan 8 行 blocked→done 后实测缺口 done 40 / blocked 8 /
pending 33（共 81）——WP4 落账口径 done 29 与文件实测差 3（早期 vanilla/WP1 行
记账漂移），以文件实测为准；authoring-log 批 4 八条；附录 A 5 条决议 🔲 待核；
PRD §5.1 WP5 补充段已定稿。

**遗留**：
- 8 张新卡 gate3 已核销（2026-09-14 用户核对通过，authoring-log human 行 +
  coverage-plan「已核销」已落账）
- 附录 A D-WP5-1~4 + until_tails 口径 5 条 ✅ 已核（2026-09-14 用户核对通过）
- WP6 = 雪童子（对手手牌盲选回库）/ 零之大空洞（bench_size 覆写 + 失效缩减结算）/
  小刚的发掘（二选一组合约束）/ 赤松（distinct-type + 检索拆分去向）/ 暗码迷的解读
  （deck_top 有序排列）/ 招式学习器 退化（devolve）/ 沙铃仙人掌 / 火恐龙（blocked 8）

### WP6（2026-09-19 完成）：blocked 8 张全清——hand_disrupt + bench_size + choose_groups + distinct 拆分 + deck_top 有序 + own_ko_by_attack/lock_retreat + protection + devolve

**前情**：上一会话完成 TDD 红阶段（`tests/test_primitives_wp6.py` 49 用例 + 9 个卡 YAML +
词表 WP6 新词 + PRD §5.1 WP6 段），机制实现为零；本会话接手：子代理实现 → 主会话独立复验 →
规格复核子代理 → 质量复核子代理 → 返工 → 复核批准（双闸流程）。

**机制落地**（`dsl/primitives.py` / `dsl/chooser.py` / `engine/core.py` / `engine/state.py` /
`dsl/interpreter.py`）：
- `hand_disrupt`：对手手牌 rng.randbelow 均匀随机 1 张 → reveal 事件 → 回对手库 + rng.shuffle；
  空手 no-op（`{"disrupted":0,"reason":"empty_hand"}`）伤害照算（D-WP6-1）
- `bench_size` 声明式覆写（D-WP6-2）：`_bench_size` 读竞技场 passive_static 声明逐玩家求值
  （condition own_tera_in_play），value 限 5..8 否则 DslError；一切放置路径（手动/search/
  recover bench）走动态上限；PlayerState 构造守卫放宽至 8（规则层 5 只由引擎强制）
- `bench_shrink` 失效缩减阶段：超容方逐只自选弃置至 5（非昏厥无奖赏），双方同缩旧竞技场
  持有者先；战斗场太晶昏厥先换上再缩减；触点 = play_stadium / _do_promote / 效果完成路径
  （质量返工补全：备战太晶指示物昏厥、transform、bounce 均触发）
- `search_deck` `args.choose_groups` 二选一互斥（小刚的发掘：基础 up-to 2 / 进化 up-to 1，
  chooser 组并集枚举使混合不可达；选 0 no-op 重洗仍执行）（D-WP6-3）
- `distinct=energy_type` 分桶互斥（chooser pool_buckets，同属性互斥、桶数<choose 收缩——
  单属性牌库收缩为 1，用户补充场景）+ split 三段流（选能量→选 1 入手→剩余附着）（D-WP6-4）
- deck_top 有序去向（暗码迷）：chooser ordered 排列枚举，选择顺序即牌顶 FIFO，
  余库本节点内重洗（D-WP6-5）
- `own_ko_by_attack` 事件 + selector `opponent_attacker`（D-WP6-6）：`pending_ko_triggers`
  队列（仅战斗场+招式伤害致昏厥入队，attack_ctx 三元组带攻击方 iid）+ `_drain_event_triggers`
  共享排水（来源从弃牌堆找回）；攻击方已离场 no-op；`lock_retreat`（目标实例撤退锁，
  其回合结束/进化/离场解除，退化保留）
- `protection` 声明式最小版（D-WP6-7）：`_protected_from_attack_effects`，一期守卫落点 =
  apply_status / place_damage_counters / lock_retreat / devolve（质量返工扩面，池内可达冲突
  穷追不舍 vs 闪焰之幕已覆盖）；伤害本体不免疫、训练家效果不受保护
- `devolve`（D-WP6-8）：对手全场各退栈顶 1 张回其手牌（战斗场先），伤害保留/状态恢复/
  能量道具不动/撤退锁保留，HP 超限走 check_knockouts；discard own_attached_energy 补
  choose=1 形式（池收窄为来源宝可梦）
- `attacker_iid` 挂起穿透：PendingChoice 第四字段（照 flip_result/cost_discarded/
  discarded_count 先例），触发效果先挂起选择再反伤可达

**落地 8 卡 9 文件**（闸 1/2 全过，first_pass 9/9，gate3 待用户核销）：
- 雪童子 惊吓类（CSV7C-057/CSV9.5C-043）/ 零之大空洞（5 印刷）/ 小刚的发掘（5 印刷）/
  赤松（6 印刷）/ 暗码迷的解读（6 印刷）/ 沙铃仙人掌（CSV10C-008/CSV10C-224）/
  火恐龙-大字爆炎（151C-005 类 3 印刷）/ 火恐龙-闪焰之幕（CSV5C-015 类 4 印刷，
  同名多文本严格拆分）/ 招式学习器 退化（4 印刷）
- 分片 `tests/test_dsl_cards_b6_wp6.py`（27 用例）；闪焰之幕正例以沙铃仙人掌真实卡文档
  互验（两卡均从 cards/ 装载）

**词表同步**（红阶段已就位）：actions +hand_disrupt/+bench_size/+lock_retreat/+protection/
+devolve；selectors +opponent_attacker/+opponent_pokemon_all；destinations +deck_top；
events +own_ko_by_attack。

**测试**：WP6 新 76 条（primitives_wp6 49 含质量返工补测 6 + 卡分片 27）；全量 **727 绿**
（基线 651）+ ruff 零告警 + `dsl-check --db` 全库 68 文件全 OK + 沙奈朵镜像同种子 hash 回归绿。

**真机冒烟 80 局 0 失败**（heuristic 4×20，`results/wp6-smoke/`）：玛俐雪妖女（643572）vs
赫普的苍响（655512）9/11；赛富豪（655513）vs 猛雷鼓厄诡椪（652967）8/12；多龙巴鲁托（648346）
vs 多龙黑夜魔灵（655545）9/11；喷火龙大比鸟（650353）vs 猛雷鼓厄诡椪 9/11。机制真实触发：
lock_retreat 14 次、bench_shrink 真实缩减 1 次、reveal 250+ 次；hand_disrupt/devolve/transform
未自然出现（启发式路径未达），由单卡测试覆盖；装载告警仅波波/索财灵两例既有白名单。

**双闸复核与返工**：规格复核证实红阶段 5 条断言为测试编写错误（3 条忘回合开始抽牌、
2 条忘所打训练家卡离手），主会话裁决修断言（机制零修改；:215 脆弱种子巧合断言改全集
不变式）；质量复核 I-1/I-2/I-3 + Minor 8 项全修后批准。

**偏差披露**：`test_state.py::test_bench_limit_five` 构造守卫 5→8；`tests/helpers.py`
effects_by_name 加 KNOWN_MULTI_TEXT_GROUPS 白名单（火恐龙拆分）；interpreter.py 一次 CRLF
编辑事故已修复（探针定位）。

**落账**：coverage-plan 8 行 blocked→done——**blocked 清零，缺口 done 48 / blocked 0 /
pending 33（共 81）**；authoring-log 批 5 九条；附录 A D-WP6-1~8 八条 🔲 待核；PRD §5.1
WP6 段红阶段已定稿。

**遗留**：
- 9 个卡文件 gate3 待用户核销 + 附录 A D-WP6-1~8 待核
- WP6+ = pending 33 张 B/C 级按「解锁卡数 + 机制通用性」排序续批（C 级含 TERA 规则盒核对
  task 027 / ACE SPEC task 027 / 持续 lock 体系 task 029 依赖项）

### WP7（2026-09-20 完成）：B 级 15 张全清——宝可梦检查阶段 + 伤害修正四来源泛化 + 8 项小原语

**流程**：主会话逐卡实测 db text_raw（15 卡池内均单一印刷，初判复核：直写 1 / 小扩展 8 /
新机制 5）→ 测试清单定稿（D-WP7-1~11 + 清单 25 条）→ WP7a 机制批（子代理 TDD 红→绿，
31 测）→ 规格复核 + 质量复核双闸 → 返工 → WP7b 卡牌批（零机制新增）→ 卡牌规格复核
批准 → F1 返工 → 冒烟 → 落账。

**机制落地**：
- 宝可梦检查阶段（D-WP7-1/2，rules-manual §7.2）：`core._start_pokemon_check` /
  `_settle_conditions` / `_advance_pokemon_check`——毒 1 / 灼 2+掷币 / 眠掷币 /
  麻按 paralyzed_mark 持有者回合窗口恢复，固定序（回合持有者方先、毒→灼→眠→麻→事件），
  全部结束后统一 check_knockouts + 奖赏；接入 _do_end_turn / _do_attack / _do_promote /
  _run_or_suspend 全路径；睡眠/麻痹撤退与招式门控接通
- `_effective_damage_modifier` 四来源泛化（D-WP7-3）：道具 / 竞技场 / 宝可梦 aura
  （scope=own_field 强制否则 DslError、同名来源卡去重）/ 回合标记 turn_damage_mods
  （modify_damage on_play 解释执行形态，回合结束清除）；condition 对攻击方持有者求值
  （新词 holder_owner:X）；args.target_rule_box 求值点校验
- `_effective_attack_cost` 读道具分支（D-WP7-4，clamp 0）
- protection 新 scope opponent_attack_damage_to_bench + 场上过滤器 no_rule_box
  （D-WP7-5，no_rule_box 作用于受保护目标）
- 小原语：discard_stadium（D-WP7-6「若希望」不建模放弃）/ shuffle_hand_into_deck
  （D-WP7-9 非库底）/ mill / attach_energy own_deck（up-to 任意分配+重洗，D-WP7-8）/
  damage self（固定值不吃弱点抗性增伤，D-WP7-10②）/ heal+place_damage_counters
  all_pokemon_both / place_damage_counters own_active / attach_energy own_deck
  事件载荷全量 iids
- 古玉鱼精确标记 own_ko_by_attack_during_opponent_turn（D-WP7-7 + F1：战斗场与备战
  狙击均置位；指示物/检查阶段灼伤不置位）+ 节点门控 if_own_ko_by_attack_during_opponent_turn
- CardDef.has_ability ← db abilities 非空 + 场上过滤器 has_ability/not_name:X +
  事件 pokemon_check（D-WP7-11）

**双闸复核与返工**：规格复核 D-WP7-1~11 逐条符合、自主裁决①（攻击方自爆/自伤昏厥
换上后回合权归对手）规则正确批准；质量复核 M1（攻击致昏厥→换上路径漏 _on_turn_end
完整清理的既存结构洞——_start_pokemon_check 入口统一调 _on_turn_end，幂等 + 回归
测试）/ M2（检查阶段×挂起选择测试 + 连锁修 choice 恢复后阶段拨回 + _advance 防卫）；
Minor 9 项全修。**backlog 待核**：aura 去重键粒度（同名异特性文本场景，当前池安全）/
§7.1 睡眠-麻痹-混乱互替未实现（WP7 池不可达）。

**落地 15 卡 15 文件**（闸 1/2 全过，first_pass 15/15，gate3 待核销）：
化朗镇 / 古玉鱼-嫉妒业火（4 印刷）/ 咕咕-三刺击（2）/ 喷火龙ex-烈炎支配（10）/
大比鸟ex（6）/ 小火龙-烧光（5）/ 火箭队的惊吓炸弹 / 爬地翅-烫伤怒涛（3）/
空手道王的修炼（7）/ 裁判-4张（31）/ 谢米-花之纱幔（2）/ 赫普的卡比兽 /
赫普的讲究头带 / 野餐篮（4）/ 雪妖女-冻结帷幕（10）；同名多文本全按等价类拆分/收窄；
分片 `tests/test_dsl_cards_b7_wp7.py`（42 用例，含闸 1 防回归）。

**词表同步**：actions +mill/+discard_stadium/+shuffle_hand_into_deck；selectors
+all_pokemon_both；events +pokemon_check（conditions/filters 按既定架构代码注册）。

**测试**：WP7 新 78 条；全量 **805 绿**（基线 727）+ ruff 零告警 + `dsl-check --db`
全库 83 文件全 OK + 沙奈朵镜像同种子 hash 回归绿。

**真机冒烟 80 局 0 失败**（heuristic 4×20，`results/wp7-smoke/`）：赫普的苍响 vs
喷火龙大比鸟 13/7；玛俐雪妖女 vs 猛雷鼓厄诡椪 15/5；喷火龙大比鸟 vs 多龙黑夜魔灵 9/11；
赛富豪 vs 多龙喷火龙 6/14。机制真实触发：pokemon_check 303–1092 次/库、discard_stadium
4–31 次、mill 15、burned 6、shuffle_hand 14、heal all_pokemon_both 17。

**仓库卫生**：`.gitignore` 顶层 `data/` 误吞 `battlefrontier/data/` 源码包（WP1 数据
管道从未进版本控制）——加 `!battlefrontier/data/` 反忽略一并纳入（存量 ruff TRY004 已修）。

**落账**：coverage-plan 15 行 pending→done——**缺口 done 63 / blocked 0 / pending 18
（共 81，余全 C 级）**；authoring-log 批 6 十五条；附录 A D-WP7-1~11 共 11 条 🔲 待核；
PRD §5.1 WP7 段定稿。

**遗留**：
- 15 个卡文件 gate3 待用户核销 + 附录 A 11 条决议 🔲 待核（连同 WP6 攒批）
- 下一步 WP8（特殊能量被动框架 + 3 卡，框架零设计）→ task 027（ACE SPEC + TERA + 7 卡，
  需立项）→ task 029（持续 lock/protection 体系 + 8 卡，需立项）

### WP8（2026-09-20 完成）：特殊能量被动框架 + 喷射/夜光/薄雾 3 卡

**流程**：主会话实测 3 卡 text_raw + 背景勘察（db 特殊能量 types/provides 均 null →
旧口径把夜光彩虹错误当【无】计数）→ 测试清单定稿（D-WP8-1~5 + 清单 9 条）→
子代理实现（机制+3 卡一批，17 测）→ 规格复核批准 → 质量复核主会话自做
（429 限流降本，用户裁决）→ 冒烟 → 落账。

**机制落地**：
- provide_energy 声明式框架（D-WP8-1）：`core._attached_energy_units`（逐附着能量
  读 DSL 声明；分层求值=有条件块覆盖无条件块、同层 ≥2 条 DslError、零条回退
  energy_type 旧口径）+ `_units_cover_cost`（有色先精确、再彩虹、余抵无色，彩虹
  全程 1 单元）；攻击枚举走新求值点 `_energy_units_satisfied`，与执行共用；
  自由函数 `_energy_satisfied` 与 agent/heuristic.py 三处未动（D-WP8-5）
- 夜光降级条件 holder_special_energy_count_ge:N（D-WP8-2，chooser 参数化词，
  特殊能量=supertype ENERGY 非 basic 含自身计数）
- 喷射换位（D-WP8-3）：`_do_attach_energy` bench 落点直发 own_attach_from_hand_to_bench
  + `_find_source_mon` 增 attached_energy 匹配 + switch 新 selector self
  （回备战方状态清除同既有换位口径）
- 薄雾 protection（D-WP8-4）：`_protected_from_attack_effects` 声明来源 =
  宝可梦卡 ∪ 附着能量卡并集，四落点守卫不变

**落地 3 卡 3 文件**（闸 1/2 全过，first_pass 3/3，gate3 待核销）：
喷射能量（5 印刷全挂）/ 夜光能量（池内文本类单挂 CSV1C-127，另 7 印刷异文本类
未落地）/ 薄雾能量（3 印刷全挂）；分片 `tests/test_dsl_cards_b8_wp8.py`（6 用例，
含闸 1 防回归：夜光混异文本印刷必拦）+ `tests/test_primitives_wp8.py`（11 用例）。

**词表同步**：actions +provide_energy；events +own_attach_from_hand_to_bench
（condition 词按既定架构代码注册）。

**测试**：WP8 新 17 条；全量 **822 绿**（基线 805）+ ruff 零告警 + `dsl-check --db`
全库 86 文件全 OK + 沙奈朵镜像同种子 hash 回归绿（规格复核附带验证镜像 100 局
串/并行 events_hash 逐局一致）。

**真机冒烟 80 局 0 失败**（heuristic 4×20，`results/wp8-smoke/`）：喷火龙大比鸟 vs
赫普的苍响 6/14；多龙喷火龙 vs 喷火龙大比鸟 7/13；多龙巴鲁托 vs 赫普的苍响 6/14；
多龙喷火龙 vs 多龙黑夜魔灵 9/11。机制真实触发：own_attach_from_hand_to_bench
3/6 次（喷射换位真实发生）、switch 43–85 次/库、protected 10–57 次/库。

**过程纪要**：当日 API 反复 429（网关限流）——用户裁决降本：质量复核主会话自做
（core.py/chooser.py/primitives.py/词表/测试/卡 YAML diff 全量审读，无必修项）、
后续子代理串行不并行、小批次双复核可合并。

**落账**：coverage-plan 3 行 pending→done——**缺口 done 66 / blocked 0 / pending 15
（共 81，余 C 级：task 027 域 7 + task 029 域 8）**；authoring-log 批 7 三条；
附录 A D-WP8-1~5 共 5 条 🔲 待核；PRD §5.1 WP8 段定稿。

**遗留**：
- 3 个卡文件 gate3 待用户核销 + 附录 A 5 条决议 🔲 待核（连同 WP6/WP7 攒批）
- 夜光能量异文本类 7 印刷（「还附着了」措辞）未落地——若回归池内需另文新写
- 下一步 task 027（ACE SPEC + TERA 规则盒核对 + 7 卡，需立项）→ task 029
  （持续 lock/protection 体系 + 8 卡，需立项）
