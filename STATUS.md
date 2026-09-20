# STATUS.md — ptcg-cn-battlefrontier

> 进展速记：每完成一步更新。规范对齐 db 项目（进展记在这里，不进 README）。

## 当前

**M5 进行中**：task 024 ✅（卡组池锁定 + LLM harness）、task 025 ✅（批 1：小原语批 + A 级处理）。**卡池 v1 = 9 套（全窗口 WUR 覆盖 53.4%，`config/target-pool.v1.yml`）**。缺口 81 张（`docs/m5-coverage-plan.md`）：**done 63 / blocked 0 / pending 18（全 C 级）**。**关键发现：A 级初判失真严重**（46 张初判「现有原语可写」实测仅 10 张可直接写）。LLM harness 质量数据：批 1 新写 DSL 12 张 first_pass 10/12、gate3 11/12 **核销完毕**（彷徨夜灵不过转 blocked——装配取错印刷，WP2 已根治落地）；批 2–4 累计 25 张全部核销通过；批 5（WP6）9 文件 first_pass 9/9、批 6（WP7）15 文件 first_pass 15/15，gate3 攒批待核销。
M1–M4 已达成。**task 026 进行中（`tasks/task 026.md`）**：WP0 ✅（CardLibrary card_id 挂载 + dsl-check --db + 审计拆分）、WP1 ✅（filters/conditions 高频项 + CardDef 数据管道 + 招式失败钩子）、WP2 ✅（trigger_on_event 分发 + place_damage_counters + ko_self + promote_queue 换上队列机制）、WP3 ✅（recover bench/hand up-to 去向 + search top_n 检视 + attach 多目标各附1 + own_evolve_from_hand 事件 + reveal 原语，2026-09-14）、**WP4 ✅（top_n rest=shuffle + attach bench-only/up-to + modify_retreat_cost + cost 弃置排除 + lock_attack 冷却，2026-09-14）**；WP4 新写 7 卡（米立龙揽客 / 宝可装置3.0 / 怒鹦哥ex / 飞天螳螂辅助斩 / 紧急滑板 / 拉帝亚斯ex / 超级能量回收），闸 1/2 全过 first_pass 5/7，gate3 已核销（2026-09-14）；**WP5 ✅（discard any_count×N + attached_energy_on_target + modify_attack_cost + prize_bonus + until_tails + bounce 附着回手 + transform，2026-09-14）**，新写 8 卡（赛富豪ex / 猛雷鼓ex / 猛雷鼓 / 月月熊 赫月ex / 白蕾雅 / 索财灵-连掷硬币 / 牡丹 / 百变怪-变身启动），闸 1/2 全过 first_pass 8/8，gate3 已核销（2026-09-14）；**WP6 ✅（blocked 8 张全清：hand_disrupt + bench_size 覆写/失效缩减 + choose_groups 二选一 + distinct 拆分去向 + deck_top 有序 + own_ko_by_attack/lock_retreat + protection + devolve，2026-09-19）**，新写 8 卡 9 文件（火恐龙同名多文本拆两文件），闸 1/2 全过 first_pass 9/9，gate3 待核销；**WP7 ✅（B 级 15 张全清：宝可梦检查阶段 + 特殊状态结算补全 + 常驻伤害修正四来源泛化 + 费用读道具 + protection 伤害免疫 scope + 8 项小原语，2026-09-20）**，新写 15 卡 15 文件，闸 1/2 全过 first_pass 15/15，gate3 待核销；定义库 83 文件；**缺口 done 63 / blocked 0 / pending 18（共 81，余全 C 级）**；下一步 WP8（特殊能量被动框架 + 喷射/夜光/薄雾 3 卡）→ task 027（ACE SPEC + TERA 规则盒核对 + 7 卡）→ task 029（持续 lock/protection 体系 + 8 卡）。
ptcgdb SDK 已接入（`C:/Vibe Project/Pokearena` 可编辑安装）。

## 里程碑

- ✅ M1 引擎骨架（白板对局 + 同种子复现）——task 001–004 全 ✅（2026-08-25）
- ✅ M2 DSL + 解释器 + 首批原语（第一套目标卡组）——task 005–008、010–017 全 ✅
- ✅ M3 启发式 Agent + Runner + 结果库（百局端到端）——task 018–020 全 ✅（2026-08-29）
- ✅ M4 报告层（胜率 / 决策聚合 / 换卡敏感性）——task 021–023 全 ✅（2026-08-30）
- ⬜ M5 覆盖扩展 + LLM 辅助编写试验
- ⬜ M6 校准基线 + 一期验收

## 工作记录

### 2026-09-20 task 026 WP7：B 级 15 张全清——宝可梦检查阶段 + 常驻伤害修正四来源泛化 + 8 项小原语 ✅

- **流程**：本会话全程 goal 驱动。主会话逐卡实测 db text_raw 复核初判（15 卡池内均单一印刷）→ 缺口分析（直写 1 / 小扩展 8 / 新机制 5）→ TDD 任务书定稿（D-WP7-1~11 + 测试清单 25 条）→ 机制批（WP7a 子代理 TDD，31 测）→ 双闸复核返工 → 卡牌批（WP7b 15 卡零机制新增）→ 卡牌规格复核批准 → F1 保真返工 → 冒烟 → 落账
- **机制层（WP7a）**：①**宝可梦检查阶段**（rules-manual §7.2 落地：回合结束对双方全场结算毒 1/灼 2+掷币/眠掷币/麻按持有者回合窗口恢复，固定序回合持有者方先、毒→灼→眠→麻→事件，全部结束后统一判昏厥+奖赏；麻痹用 paralyzed_mark 记施加回合/方；睡眠/麻痹撤退与招式门控接通）——特殊状态结算自此补全（此前仅混乱）；②`_effective_damage_modifier` 四来源泛化（道具/竞技场/宝可梦 aura scope=own_field 同名去重/回合标记 turn_damage_mods + target_rule_box 目标过滤 + condition holder_owner:X）；③`_effective_attack_cost` 读道具分支；④protection 新 scope opponent_attack_damage_to_bench + 场上过滤器 no_rule_box；⑤小原语 discard_stadium / shuffle_hand_into_deck / mill / attach_energy own_deck（up-to 任意分配+重洗）/ damage self（固定值不吃修正）/ heal+place_damage_counters all_pokemon_both / place_damage_counters own_active / 跨回合精确标记 own_ko_by_attack_during_opponent_turn + 节点门控；⑥CardDef.has_ability ← db abilities 非空 + 场上过滤器 has_ability/not_name + 事件 pokemon_check
- **双闸复核与返工**：规格复核逐条对照 D-WP7-1~11 全符合；质量复核 M1（攻击致昏厥→换上路径漏 `_on_turn_end` 完整清理——retreat_lock/extra_prize_tera_ko 等四标记陈旧泄漏的**既存结构洞**，本批接管该路径后修为 `_start_pokemon_check` 入口统一调 `_on_turn_end` + 回归测试）/ M2（检查阶段×挂起选择零覆盖，补挂起恢复测试并连锁修 choice 恢复后阶段拨回）；Minor 9 项全修（含 attach own_deck 事件载荷失真、all_pokemon_both 守卫方向、paralyzed_mark 清除补齐、注释归正）。backlog 待核：aura 去重键粒度（同名卡异特性文本场景，当前池安全）/ §7.1 睡眠-麻痹-混乱互替未实现（WP7 池不可达）
- **新卡 15 张 15 文件（闸 1/2 全过，first_pass 15/15，gate3 待核销）**：化朗镇 / 古玉鱼-嫉妒业火（4 印刷）/ 咕咕-三刺击（2）/ 喷火龙ex-烈炎支配（10）/ 大比鸟ex（6）/ 小火龙-烧光（5）/ 火箭队的惊吓炸弹 / 爬地翅-烫伤怒涛（3）/ 空手道王的修炼（7）/ 裁判-4张（31）/ 谢米-花之纱幔（2）/ 赫普的卡比兽 / 赫普的讲究头带 / 野餐篮（4）/ 雪妖女-冻结帷幕（10）；同名多文本全部按等价类拆分/收窄；分片 `tests/test_dsl_cards_b7_wp7.py` 42 用例（含闸 1 防回归：混异文本印刷必拦）
- **规格复核 F1 返工**：嫉妒业火精确标记原仅战斗场置位，卡面无战斗场限定——扩展至备战狙击招式伤害昏厥（指示物/检查阶段灼伤仍不置位，补反向断言）
- **测试**：WP7 新 78 条（primitives_wp7 37 + 卡分片 42 − 重复计 1）；**全量 805 绿（基线 727）+ ruff 零告警 + dsl-check --db 全库 83 文件全 OK + 镜像 hash 回归绿**
- **真机冒烟 80 局 0 失败**（heuristic 4×20，`results/wp7-smoke/`）：赫普的苍响 vs 喷火龙大比鸟 13/7；玛俐雪妖女 vs 猛雷鼓厄诡椪 15/5；喷火龙大比鸟 vs 多龙黑夜魔灵 9/11；赛富豪 vs 多龙喷火龙 6/14。机制真实触发：pokemon_check 303–1092 次/库、discard_stadium 4–31 次、mill 15、burned 6、shuffle_hand 14、all_pokemon_both heal 17
- **仓库卫生修复**：`.gitignore` 顶层 `data/` 模式误吞 `battlefrontier/data/` 源码包（WP1 数据管道**从未进版本控制**）——加 `!battlefrontier/data/` 反忽略，本批一并纳入（暴露的存量 ruff TRY004 已修）
- **落账**：coverage-plan 15 行 pending→done——**缺口 done 63 / blocked 0 / pending 18（共 81，全 C 级）**；authoring-log 批 6 十五条；附录 A D-WP7-1~11 共 11 条 🔲 待核；PRD §5.1 WP7 段
- **遗留**：15 个卡文件 gate3 待用户核销 + 附录 A 11 条决议 🔲 待核（连同 WP6 9 文件 8 条攒批）；下一步 WP8（特殊能量被动框架 + 3 卡，框架零设计需先出设计）→ task 027（ACE SPEC + TERA + 7 卡，需立项）→ task 029（持续 lock/protection 体系 + 8 卡，需立项）

### 2026-09-19 db 数据更新验收：新合法性快照 + 赛事数据至 09-09 ✅

- **上游更新**：db 新增 `standard-2026-09-16` / `open-2026-09-16` 快照（G/H/I+**J** 标；旧 standard-2026-07-16 落 effective_to=09-15）；data_version v20260919.3；tournaments 至 2026-09-09 共 283 场（原止于 08-05）
- **白名单变化**：44 → 26——移除项全为 30th-P 特典 PROMO 卡（妙蛙种子/小火龙等同名再录白名单条目）；博士的研究/老大的指令两条按名白名单保留
- **本项目影响核查全绿**：池内 9 套卡组在新快照下装载校验全过（60 张、零告警）；`dsl-check --db` 全库 68 文件全 OK（赛制闸自动指向最新快照）；全量 pytest 727 绿（含镜像 hash 回归——卡牌内容数据无变化）
- **退赛 4 archetype 复查**：密勒顿已有新鲜 full 卡组（最近出场 09-06）；放逐Box/洛奇亚/雷吉铎拉戈最近出场仍停在 7 月（补数后确认是环境自然消亡非数据断点）；09-16 新环境尚无赛后数据，M6 校准矩阵随数据积累受益
- **复算锚点变更**：新实验 meta 数据版本 = v20260919.3 / 快照 standard-2026-09-16；旧结果库的重放仍需对应旧版 db（FR-10 契约既有口径）
- **用户决议（2026-09-19）**：卡池 v1 维持锁定——校准基线需要池稳定；密勒顿回池评估留待 M6 后再议

### 2026-09-19 task 026 WP6：blocked 8 张全清——hand_disrupt + bench_size 覆写 + choose_groups + distinct 拆分 + deck_top 有序 + own_ko_by_attack/lock_retreat + protection + devolve ✅

- **前情**：上一会话已完成 TDD 红阶段（机制测试 `tests/test_primitives_wp6.py` 1311 行 + 9 个卡 YAML + 词表 WP6 新词 + PRD §5.1 WP6 段定稿），机制实现为零；本会话接手实现（子代理 TDD 红转绿，主会话独立复验 + 规格复核 + 质量复核双闸）
- **机制层**：①`hand_disrupt`（对手手牌 rng.randbelow 均匀随机 1 张 → reveal 事件 → 回对手库重洗，空手 no-op 伤害照算）；②`bench_size` 声明式覆写（`_bench_size` 逐玩家求值，value 限 5..8 否则 DslError）+ `bench_shrink` 失效缩减阶段（超容方逐只自选弃置至 5，非昏厥无奖赏，双方同缩旧竞技场持有者先，战斗场太晶昏厥先换上再缩减；触点在质量返工中补全至昏厥/transform/bounce 等一切离场完成路径）；③`search_deck` `choose_groups` 二选一互斥（组并集枚举，混合不可达）；④`distinct=energy_type` 分桶互斥（chooser pool_buckets，桶数<choose 收缩）+ split 三段流（选能量→选 1 入手→剩余附着）；⑤deck_top 有序去向（chooser ordered 排列枚举，选择顺序即牌顶 FIFO，余库节点内重洗）；⑥`own_ko_by_attack` 事件（`pending_ko_triggers` 队列 + `_drain_event_triggers` 共享排水，来源从弃牌堆找回；selector `opponent_attacker`，攻击方离场 no-op）+ `lock_retreat`（目标实例撤退锁，其回合结束/进化解除，退化保留）；⑦`protection` 声明式最小版（`_protected_from_attack_effects`，一期守卫落点 = apply_status / place_damage_counters / lock_retreat / devolve 四处，docstring 明示新落点须显式接入）；⑧`devolve`（对手全场各退栈顶 1 张回手，伤害保留/状态恢复/能量道具不动/HP 超限走 check_knockouts）+ discard own_attached_energy 补 choose=1 形式；`attacker_iid` 挂起穿透（PendingChoice 第四字段，照 flip_result 三件套先例）
- **规则决议 8 条落附录 A（🔲 待核）**：D-WP6-1 盲选=均匀随机 / D-WP6-2 失效缩减立即+自选+持有者先 / D-WP6-3 二选一互斥 / D-WP6-4 distinct 选择池约束+拆分去向（含单属性收缩为 1 用户补充场景）/ D-WP6-5 选择顺序即牌顶 FIFO / D-WP6-6 受击昏厥三条件+撤退锁 / D-WP6-7 protection=招式附加效果不适用（伤害不免疫、训练家不受保护、守卫落点清单）/ D-WP6-8 devolve 栈顶 1 张+伤害保留+HP 超限昏厥
- **新卡 8 张 9 文件（闸 1/2 全过，first_pass 9/9，gate3 待核销）**：雪童子（H 标惊吓类 2 印刷）/ 零之大空洞（5 印刷）/ 小刚的发掘（I 标 5 印刷）/ 赤松（H 标 6 印刷）/ 暗码迷的解读（H 标 6 印刷）/ 沙铃仙人掌（I 标 2 印刷）/ 火恐龙-大字爆炎（151C-005 类 3 印刷）+ 火恐龙-闪焰之幕（CSV5C-015 类 4 印刷，同名多文本严格拆分两文件）/ 招式学习器 退化（G 标 4 印刷）；分片 `tests/test_dsl_cards_b6_wp6.py` 27 用例
- **测试**：WP6 新 76 条（primitives_wp6 49 + 卡分片 27；红阶段 40 条 + 质量返工补测 6 条 + 既有 schema/loader 更新）；**全量 727 绿（基线 651）+ ruff 零告警 + dsl-check --db 全库 68 文件全 OK + 镜像 hash 回归绿**
- **真机冒烟 80 局 0 失败**（heuristic 镜像 4×20，`results/wp6-smoke/`）：玛俐雪妖女 vs 赫普的苍响（9/11）/ 赛富豪 vs 猛雷鼓厄诡椪（8/12）/ 多龙巴鲁托 vs 多龙黑夜魔灵（9/11）/ 喷火龙大比鸟 vs 猛雷鼓厄诡椪（9/11）；机制真实触发——lock_retreat 14 次、bench_shrink 真实缩减 1 次、reveal 250+ 次（惊吓/发掘/暗码迷）、place_damage_counters+ko_self 持续工作；hand_disrupt/devolve/transform 80 局未自然出现（启发式决策路径未达），由单卡测试覆盖；装载告警仅波波/索财灵两例既有白名单
- **质量复核返工（双闸流程）**：I-1 protection 守卫补 lock_retreat/devolve 落点（池内可达冲突：穷追不舍 vs 闪焰之幕）/ I-2 bench_shrink 触点补全（备战太晶被指示物昏厥、transform、bounce）/ I-3 attacker_iid 挂起穿透；Minor 8 项全修
- **偏差披露**：红阶段 5 条测试断言笔误经规格复核证实为测试错（3 条忘回合开始抽牌、2 条忘所打训练家卡离手，WP3 :585 先例），主会话裁决后修正断言（机制零修改）；红阶段测试 :215 脆弱断言（洗回牌被抽中的种子巧合）改全集不变式；`test_state.py::test_bench_limit_five` 构造守卫 5→8（规则层 5 只上限由引擎动态强制，回归测试在）；`tests/helpers.py` effects_by_name 加 KNOWN_MULTI_TEXT_GROUPS 白名单（火恐龙同名多文本拆分，波波/索财灵先例的泛化）；D-WP6 决议编号注释漂移已修齐
- **落账**：coverage-plan 8 行 blocked→done——**blocked 清零，缺口 done 48 / blocked 0 / pending 33（共 81）**；authoring-log 批 5 九条；附录 A 8 条 🔲 待核；PRD §5.1 WP6 段红阶段已定稿
- **遗留**：9 个卡文件 gate3 待用户核销 + 附录 A 8 条决议 🔲 待核；下一步 WP6+ = pending 33 张 B/C 级按「解锁卡数 + 机制通用性」排序续批（C 级含 TERA 规则盒核对 task 027 / ACE SPEC task 027 / 持续 lock 体系 task 029 依赖项）

### 2026-09-14 task 026 WP5：any_count 弃置×N + attached_energy_on_target + modify_attack_cost + prize_bonus + until_tails + bounce 附着回手 + transform ✅

- **机制层（子代理 TDD，主会话独立复验 651 绿 + ruff 零告警 + dsl-check 59 文件全 OK + diff 抽查一致）**：①discard `args.any_count`（「任意数量」=up-to all，min_choose=0）+ selector `own_attached_energy`（场上宝可梦附着能量池摘下弃置）+ 计数词 `discarded_this_effect`；②计数词 `attached_energy_on_target`；③`modify_attack_cost` 声明式（passive_static，引擎 `_effective_attack_cost` 枚举与执行共用求值点；只减【无】、clamp 0、计数词 `opponent_taken_prizes`）；④`prize_bonus` 回合级标记（scope=tera_attack_ko，core._knockout_one 触点从己奖赏堆多拿 1）；⑤coin_flip `args.until_tails` + 计数词 `flip_heads_count`（逐次走单一随机源）；⑥bounce `args.attachments=hand`（顺带修 bounce 不传 filters 的既有 bug）；⑦`transform` 替换原语（整叠弃置、牌库基础宝可梦接替原位、非昏厥离场不触发奖赏/换上、伤害状态不继承、可空找仍重洗）
- **规则决议 5 条落附录 A（✅ 已核 2026-09-14）**：D-WP5-1 任意数量=up-to all、选 0 伤害 0 可宣言（WP4 宣言裁决延伸）/ D-WP5-2 白蕾雅加成触发面收窄（仅太晶招式伤害致对手战斗场昏厥，从己奖赏堆拿）/ D-WP5-3 变身不触发昏厥奖赏、伤害状态不继承（与 30th 版「全部继承」措辞差异忠实区分）、空找仍重洗 / D-WP5-4 费用减免只减【无】 clamp 0 / until_tails 逐次落事件流口径
- **新卡 8 张（闸 1/2 全过，first_pass 8/8，gate3 已核销 2026-09-14）**：赛富豪ex（G 标 7 印刷，嘉奖硬币 if_self_active 追加抽 + 淘金潮 50×）/ 猛雷鼓ex（7 印刷，飞溅咆哮 + 极雷轰 70×）/ 猛雷鼓（2 印刷，落雷风暴 ×30 含备战）/ 月月熊 赫月ex（8 印刷，老练招式减费 + 血月 240 lock_attack）/ 白蕾雅（6 印刷，opponent_prizes_eq:2 + prize_bonus）/ 索财灵-连掷硬币（G 标 3 印刷，同名多文本拆分）/ 牡丹（5 印刷，attachments=hand）/ 百变怪-变身启动（G 标 4 印刷，同名多文本拆分）
- 测试：新 62 条（primitives_wp5 + 卡分片 b5_wp5 等）；**全量 651 绿（基线 589）+ ruff 零告警 + dsl-check --db 全库 59 文件全 OK**
- 真机冒烟 40 局 0 失败：赛富豪 vs 猛雷鼓厄诡椪 20 局（6/14）+ 赫普的苍响 vs 喷火龙大比鸟 20 局（5/15）；机制真实触发——淘金潮 26 次（含梦幻ex copy:淘金潮 路径）、极雷轰 6 次、连掷硬币 until_tails 8 次（最长 3 连正）、牡丹 attachments=hand 真实回手、白蕾雅 prize_bonus 标记真实设置；血月/变身启动 40 局未自然出现（月月熊ex 登场 13 次未攒够费用、百变怪未首发上场），由单卡测试覆盖
- 偏差披露：词表 actions +prize_bonus（任务书外必要新增）；bounce filters 转发 bug 修正；月月熊 lock_attack 沿用 D-WP4-5 近似（单招式卡锁本招式名等价全锁）；transform 不被 ability_feasible 池空门控（门控由 condition 承担，否则 no-op 重洗不可达）；test_loader_cardid 白名单 +CSV9C-096（索财灵同名异文本印刷，波波先例）；新增过滤器 not_name / condition self_is_active_and_first_own_turn / 节点门控 if_self_active（代码注册非词表段）
- 落账：coverage-plan 8 行 blocked→done；**对账修正缺口计数为实测 done 40 / blocked 8 / pending 33（共 81）**——WP4 落账口径 done 29 与文件实测差 3（早期 vanilla/WP1 行记账漂移），以文件实测为准；authoring-log 批 4 八条；附录 A 5 条；PRD §5.1 WP5 补充段（变量伤害与修正声明扩展）已定稿
- 遗留：8 张新卡 gate3 已核销 + 附录 A 5 条决议 ✅ 已核（均 2026-09-14 用户核对通过）；下一步 WP6 = 雪童子（对手手牌盲选回库）/ 零之大空洞（bench_size 覆写 + 失效缩减结算）/ 小刚的发掘（二选一组合约束）/ 赤松（distinct-type + 检索拆分去向）/ 暗码迷的解读（deck_top 有序排列）/ 招式学习器 退化（devolve）/ 沙铃仙人掌 / 火恐龙

### 2026-09-14 task 026 WP4：rest=shuffle + attach bench-only/up-to + modify_retreat_cost + cost 排除 + lock_attack ✅

- **机制层（子代理 TDD，主会话独立复验 diff 一致）**：①`search_deck` top_n 加 `rest=shuffle`（未选卡与牌库合并整库重洗，空选也洗——文本「剩余放回牌库并重洗」）；②`attach_energy` 加 `args.target_pool=own_bench`（段2 目标限备战）+ `args.energy_up_to`（段1 min_choose=0，选 0 张不进段2）；③`modify_retreat_cost` 声明式（`_effective_retreat_cost` 仿 `_effective_hp`，撤退枚举+执行两触点接入；减少量加总 clamp 0、"all" 归零、可交换；紧急滑板 holder 条件式 / 拉帝亚斯ex own_basic_all scope）；④cost 弃置排除（cost 段 discard iids 记 ExecutionContext 并随挂起冻结，recover `exclude_cost_discarded` 剔除；cost 手牌不足整卡不可使用）；⑤**lock_attack 冷却**（用户裁决补建：InPlayPokemon.attack_locks + turn 戳，turn N 使用 → N+1 锁 → N+2 解禁；撤退/离场清除、进化继承 🔲 待核）
- **规则裁决 2 条落附录 A**：招式附加效果落点空不阻却宣言（✅ 用户裁决，attack_feasible 门移除——WP4 清单 18 原口径「无备战不可宣言」被推翻，测试翻转）+ 攻击冷却语义（🔲 待核，含进化继承与单招式卡「无法使用招式」=锁本招式的已知等价口径）
- **新卡 7 张（闸 1/2 全过，first_pass 5/7，gate3 已核销 2026-09-14）**：米立龙揽客（H 标 10 印刷，first_pass=false：ability_feasible 缺 reveal 分支的机制门缺口，补齐后全绿）/ 宝可装置3.0（5 印刷）/ 怒鹦哥ex（7 印刷）/ 飞天螳螂辅助斩（151C-123）/ 紧急滑板（8 印刷）/ 拉帝亚斯ex（3 印刷，first_pass=false：测试夹具 retreat_cost=0 笔误 + 无限之刃冷却裁决后补全）/ 超级能量回收（8 印刷，cost 排除忠实原文括号注）
- 测试：新 64 条（primitives_wp4 32 + 卡分片 b4_wp4 27 + attack_cooldown 4 + schema；含 2 条宣言门翻转替换）；**全量 589 绿（基线 525）+ ruff 零告警 + dsl-check --db 全库 51 文件全 OK + 镜像 hash 回归绿**
- 真机冒烟 40 局 0 失败：赫普的苍响 vs 猛雷鼓厄诡椪 20 局（5/15）+ 赛富豪 vs 喷火龙大比鸟 20 局（10/10）
- 偏差披露：`_effective_hp` 加前置过滤（仅对含 modify_hp 声明的效果求 condition，修 holder_hp_le→_effective_hp 递归，语义等价零回归）；米立龙 CBB5C 七印刷过快照未收窄
- 落账：coverage-plan 7 行 blocked→done（缺口 done 29 / blocked 18 / pending 34，定义库 51 文件）；authoring-log 批 3 七条；PRD §5.1 补 WP4 段；task 026 WP4 测试清单（22 条 + D-WP4-1~4）定稿写入
- 遗留：7 张新卡 gate3 已核销 + 冷却语义决议 ✅ 已核（均 2026-09-14 用户核对通过）；下一步 WP5 = 暗码迷的解读（deck_top 有序排列）/ 小刚的发掘（二选一组合约束）/ 月月熊ex（modify_attack_cost）/ devolve / 手牌干扰等

### 2026-09-14 task 026 WP3：recover 去向扩展 + top_n 检视 + attach 多目标 + own_evolve_from_hand + reveal ✅

- **机制层（子代理 TDD，主会话独立复验 diff 一致）**：①`recover_from_discard` 去向扩展——bench（up-to、entered_play_this_turn 登记、备战区 5 只容量在选择池解析即截断）+ hand up-to（args.up_to=true → min_choose=0，既有 hand 默认 min=1 行为不变）；②`search_deck` top_n 检视（args.top_n=N 池=牌库顶 N 张 + args.rest=deck_top/deck_bottom 未选卡按原序归位不洗牌；私密检视观测纪律：事件流只落选择结果）；③`attach_energy` 多目标各附1（args.multi_target：段1 选能量 up-to N → 段2 选等量目标 → FIFO 配对，任一侧空 no-op）；④`own_evolve_from_hand` 事件挂 `_do_evolve`（触发分发抽公共函数 `_fire_trigger_on_event`）+ `reveal` 原语落地（词表既有词，落事件流无状态变更）；chooser 双可行性门补 recover/search 新形式
- **规则决议 5 条落附录 A**：D-WP3-1 多目标各附1 FIFO 配对 🔲 / **D-WP3-2 触发范围 ✅ 已核（用户 2026-09-14 裁决并修正实现）** / D-WP3-3 牌库顶检视从宽 up-to 🔲 / D-WP3-4 reveal 仅落事件流（已知近似：reveal 池按 selector+filters 重解析，可能宽于实际移动卡）🔲 + 效果直放备战区容量截断口径 🔲
- **D-WP3-2 裁决修正**：触发口径 = 进化卡本身从手牌使出——神奇糖果（skip_stage）从手牌进化**触发**、招式学习器「进化」（from_deck）不触发；实现为 `pending_event_triggers` 队列 + `_run_or_suspend` 完成路径排水（先于 promote 翻阶段；来源离场即失效跳过）；测试净增 3 条（1 条初版「不触发」用例被裁决推翻改写）
- **新卡 5 张（闸 1/2 全过，first_pass 5/5，gate3 待用户核销）**：多龙奇 H 标侦察指令（3 印刷）/ 夜巡灵 H 标渡魂（on_attack + recover bench，4 印刷）/ 奥琳博士的气魄（G 标 7 印刷，attach 多目标 + draw 3）/ 猫头夜鹰寻找宝石（H 标 5 印刷，own_evolve_from_hand + own_tera_in_play + reveal）/ 水莲的照顾（H 标 7 印刷，recover hand up-to + reveal）；池内实际印刷全覆盖（实测自 deck_cards）
- 测试：新 48 条（primitives_wp3 28 + trigger_evolve_from_hand 5 + 卡分片 b3_wp3 14 + schema +1；裁决修正后再 +3）；**全量 525 绿（基线 474）+ ruff 零告警 + dsl-check --db 全库 44 文件全 OK + 镜像 hash 回归绿**；first_pass 披露：卡 YAML 与卡分片首跑全过，机制测试分片 2 处测试侧笔误返工（DSL 零修改）
- 真机冒烟 40 局 0 失败：猛雷鼓厄诡椪 vs 多龙黑夜魔灵 20 局（11/9）+ 赛富豪 vs 喷火龙大比鸟 20 局（9/11）；机制真实触发——侦察指令 use_ability 122 次、奥琳博士 36 次打出、水莲 reveal 10 次、夜巡灵渡魂选择 64 次、猫头夜鹰 own_evolve_from_hand 真实触发 1 次
- 落账：coverage-plan 5 行 blocked→done（缺口 done 22 / blocked 25 / pending 34，定义库 44 文件）；authoring-log 批 2 追加 5 条；PRD §5.1 补「检索检视与回收扩展」段；task 026 WP3 测试清单（20 条 + D-WP3-1~4）定稿写入
- 偏差披露：test_dsl_interpreter 1 条存量测试锁定词由 reveal 改 put_into_play（reveal 本期实现，断言语义不变）；既有 search_deck bench 去向未做容量截断的问题随本 WP 一并补上
- 遗留：5 张新卡 gate3 已核销 + 附录 A 5 条决议 ✅ 已核（均 2026-09-14 用户核对通过）；下一步 WP4 = 暗码迷的解读（deck_top 去向 + 有序排列选择）/ 怒鹦哥ex（attach up-to-N + bench-only 目标池）/ gust 门控版 / devolve 等 blocked 项按解锁卡数排序

### 2026-09-07 task 026 WP2：trigger_on_event + place_damage_counters + ko_self ✅

- **机制层（子代理 TDD，主会话独立复验 diff 一致）**：①`promote_queue` 昏厥换上队列（`state.py` 删 promote_to_main、加 promote_queue / resume_after_promotes）——效果内昏厥（ko_self 等）的弃牌/奖赏按文本语序立即结算，换上推迟到效果完成后按队列统一进行并回效果方主阶段（行为修正：亢奋脑力 KO 对手战斗场旧实现错进对手回合）；多昏厥按扫描序（玩家0→1、备战→战斗场）FIFO；②新原语 `ko_self`（自我昏厥入队列）+ `place_damage_counters`（选择器池放置 N×10 伤害指示物，池不足 min 收缩），bounce 迁移同构；③trigger_on_event 分发：`Effect.event` 字段 + `_do_place_bench` 主阶段触发点 + `_run_or_suspend` 完成路径翻 promote，「可使用」放弃选项不建模（自动发动+尽力而为）；④双方同时无宝可梦 → 平局 is_draw；interpreter 加 game_over 守卫、chooser 的 ability_feasible 补两原语
- **规则决议 4 条落附录 A（✅ 已核 2026-09-07）**：D-WP2-1 换上推迟到效果完成后按队列进行 / D-WP2-2 多昏厥换上按扫描序 FIFO / D-WP2-3 触发式特性「可使用」放弃选项不建模 / D-WP2-4 双方同时无宝可梦判平局；沙铃仙人掌维持 blocked（撤退锁归 task 029、KO 来源追踪未建——无落地卡的原语不先行）
- **新卡 2 张（闸 1/2 全过，first_pass 2/2，gate3 已核销 2026-09-07）**：彷徨夜灵 H 标 CSV8C-082 咒怨炸弹（ability_manual + once_per_turn + ko_self + place_damage_counters opponent_pokemon_any counters:5，回库后全库唯一卡测试载体恢复）/ 摔角鹰人（trigger_on_event own_play_from_hand_to_bench + place_damage_counters opponent_bench choose:2 counters:1）
- 测试：新 44 条（promote_queue 8 + primitives_wp2 17 + trigger_on_event 8 + schema +4 + 卡分片 7；test_loader_cardid 退环境出库断言更新——彷徨夜灵回库）；**全量 474 绿（基线 430）+ ruff 零告警 + dsl-check --db 全库 39 文件全 OK + 镜像 hash 回归绿**
- 真机冒烟：多龙黑夜魔灵 vs 喷火龙大比鸟 20 局镜像 0 失败，ko_self 真实触发 27 次；摔角鹰人 trigger 真实对局未自然出现（启发式 Agent 主阶段不铺备战，既有口径），由单卡测试覆盖
- 落账：coverage-plan 两行 blocked→done（缺口 done 17 / blocked 30 / pending 34，定义库 39 文件）；authoring-log 批 2 追加 2 条；PRD §5.1 补「事件触发」段；task 026 WP2 测试清单（25 条 + D-WP2-1~4）定稿写入
- 遗留：2 张新卡 gate3 已核销 + 附录 A 四条决议 ✅ 已核（均 2026-09-14 用户核对通过）；下一步 WP3 = 多龙奇 top_n 检视 / 夜巡灵 recover bench / 奥琳博士 attach 多目标（猫头夜鹰需 own_evolve_from_hand 事件 + reveal 原语）

### 2026-09-07 db owner 补数验收 + 赫普的包包 ✅

- **上游补数验收**：db `cards.owner` 从 5 组扩到 12 组（新增赫普 14 / 奇树 9 / 派帕 9 / 阿响 15 / 小霞 11 / 大吾 11 / 阿渡 1），三组前缀逐张复核 owner≠前缀或 NULL 为零；池内赫普的卡 5 种抽查全对
- **赫普的包包（CSV10C-195）解锁落地**（主会话直写，TDD）：检索 ≤2 基础「赫普的宝可梦」入备战（basic_pokemon + owner_pokemon：赫普 双过滤 + bench 去向 + up-to）；闸 1（dsl-check --db）✅ 闸 2 ✅ 3 用例（full flow / 双过滤负例 / 空选仍洗牌）；first_pass=false 严格口径（首跑 2 条失败 = 测试夹具默认备战区假设错误，DSL 零修改）；gate3 待核销
- 落账：coverage-plan 赫普的包包 blocked→done（缺口 done 15 / blocked 32）；authoring-log 批 2 首条；全量 **430 绿** + ruff 零告警
- **gate3 核销批 2 全过（2026-09-07）**：老大的指令 / 尖钉镇道馆 / 赫普的古月鸟 / 赫普的包包——coverage-plan 4 行 + authoring-log 4 条落账；古月鸟核销含规则语义确认：原文否定式「不为4张、3张则招式失败」= 可宣言但失败（攻击机会消耗、回合照常结束），DSL 与引擎钩子忠实于此（非「不可宣言」）
- 上游剩余缺口：跨源对账残留 38 张人工核销 / 合法性快照与赛事数据新鲜度（M6 前置）/ group_key 暴露（已非阻塞，可选）；**Q&A 供给端（2026-09-07 用户更新）：仅官方小程序有数据、此前爬取尝试未果，后续研究其他渠道——维持搁置**

### 2026-09-06 task 026 WP1：filters/conditions 高频项 + 数据管道 ✅

- **CardDef 数据管道**：`is_tera` / `owner` ← db cards 列；`labels` ← db `effect_tags.labels`（古代/未来特质有现成来源，未按文本硬推）
- **filters 注册**：`name:<卡名>` / `owner_pokemon:<名>` / `energy_<属性>`（参数化，原字面词 `energy_超` 泛化并入）/ `pokemon_no_rule_or_basic_energy` / `trait:<特质>`（卡维度+场上维度）；未知词仍 DslError
- **conditions 注册**：`self_is_active`/`holder_is_active` / `first_own_turn` / `own_tera_in_play` / `opponent_prizes_eq:N` / `opponent_prizes_in:[...]` / `holder_hp_le:N`（有效 HP 口径，畸形参数 DslError）
- **引擎钩子**：on_attack 效果级 condition 不满足 → 招式失败（不结算、回合照常结束、attack 事件落 failed 标记）——古月鸟「则这个招式失败」语义
- **新写卡 3 张（闸 1/2 全过，first_pass 3/3，gate3 待用户核销）**：老大的指令（gust 无门控，38 印刷同文本全挂载，池内最高频缺口卡）/ 尖钉镇道馆（owner_pokemon：玛俐）/ 赫普的古月鸟（opponent_prizes_in:[4,3] + 招式失败三分支）；词表零变更（filters/conditions 按既定架构注册在代码求值点）
- **blocked 原因复核更新 13 行**：多龙奇原 blocked 失真（实测缺 top_n 检视 + deck_bottom 去向，归 WP2+）；**赫普的包包 = db 数据缺口**（cards.owner 实测仅玛俐/竹兰/莉莉艾/N/火箭队，赫普组无数据——上游 Pokearena 补数项，不猜不硬推）；水莲的照顾等 11 张标注「WP1 已备项」待 WP2/3 原语
- 测试：新 23 条（filters/conditions 14 + 卡分片 9）；**全量 427 绿 + ruff 零告警 + dsl-check --db 全库 36 文件全 OK + 镜像 hash 回归绿**（主会话独立复验一致）
- 遗留：3 张新卡 gate3 待核销；db 侧 owner 补数（赫普组）为上游立项项；WP2 = trigger_on_event 分发 + place_damage_counters

### 2026-09-06 gate3 核销批 + task 026 WP0 ✅

- **task 026 WP0 前置完成（子代理 TDD，主会话独立复验）**：CardLibrary（dict 子类，键 = card_id，card_ids 必填 + 跨文件查重 + by_name 索引）；引擎 17 处查询点改走 `effect_doc()` 助手（CardLibrary 仅 card_id 精确命中无名字兜底，朴素 dict 兼容存量测试）；`assemble_card_effects` 装配层（card_id 过滤 + 覆盖告警：印刷未覆盖且同名有文档 → warning）；dsl-check 新增 `--db`（card_id 存在性 / 文件内归一化 text_raw 一致 / 赛制标合法性——SDK legal_at，含再录合法口径）
- **审计拆分**：不服输头带 10→9、朋友手册 20→11 收窄至单文本类；其余候选（厉害钓竿/反击捕捉器/巢穴球/高级球/神奇糖果/能量转移/夜光能量/波波/皮宝宝）实测单文本类无需收窄
- **退环境出库 3 张**：彷徨夜灵 D 标（任务内）+ **捕获香氛/交替推车（子代理实测发现：全部 14 个印刷 F 标退环境、standard-2026-07-16 仅 G/H/I+白名单且两卡未入白名单、池内零使用——主会话 SQL 复核属实，按同口径确认出库）**；两卡 DSL gate3 本已通过，移除原因是赛制合法性非文本保真；coin_flip / heal+switch / own_active_is_basic 失去真实卡测试载体（原语单测仍在），WP1+ 同机制新卡落地时回补。定义库 28→25 文件
- 测试：新 21 条（test_loader_cardid 15 + cli dsl-check --db 6），迁移 10 个存量测试文件，删出库卡测试 7 条；**全量 404 绿 + ruff 零告警 + dsl-check --db 全库 33 文件全 OK + 镜像 hash 回归绿**（主会话独立复验一致）
- 遗留：池内唯一「同名有文档但印刷未覆盖」= 波波 CSV4C-099（起风白板，告警豁免已断言）；彷徨夜灵 H 标归 WP2
- **彷徨夜灵 核销不过 → 转 blocked 归 task 026**：装配阶段按 name_group 取 text_raw 取错印刷——池内两套卡组（喷火龙大比鸟 mik_moe:650353 / 多龙黑夜魔灵 mik_moe:655545）实际均为 H 标 CSV8C-082「咒怨炸弹」（自我昏厥 + 给对手 1 只宝可梦放置 5 伤害指示物，自爆多龙轴组件），现 DSL 覆盖的 D 标 CS2.5C-018（奇异之光）池内零使用。H 标版需 place_damage_counters + 自我昏厥原语，正属 task 026 re-scope 域
- 落账：coverage-plan 行改 blocked（含原因）、authoring-log 补 gate3=false 条、cards/彷徨夜灵.yml 头部加印刷口径警示；计数 done 15→14 / blocked 32→33
- **用户决议：根因是「版本检查/赛制标签」缺失**——harness 装配环节需增加 card_id/赛制标对齐卡池实际印刷的校验，列为 task 026 前置任务
- **A 组其余 11 张 gate3 全部核销通过**（含交替推车 heal 前置取舍确认）：coverage-plan 9 行状态更新、authoring-log 补 11 条 gate3=true；批 1 最终质量数据定格 first_pass 10/12、gate3 11/12
- **B1/B2 规则决议用户确认无误**：rules-reference 附录 A bounce 换上/无宝可梦判负两条 🔲 → ✅ 已核（2026-09-06）
- **C1 task 026 re-scope 用户拍板（四点全确认）**：a) 组织方式改解锁项驱动（不按已证伪的字母批）；b) 优先级 = filters/conditions 先行 → trigger_on_event + place_damage_counters → 其余按解锁卡数排序；c) harness 装配校验列为第一步；d) 老大的指令（gust 无门控版）顺带批 2 落地。已立项 `tasks/task 026.md`
- **D1 同名组归组口径用户拍板**：按（卡名 + 文本）等价类归组、**严格拆分**（同语义异措辞不合并）；装载键 name_group → card_id 精确挂载；闸 1 校验文件内 card_ids 归一化 text_raw 一致。池内实测支撑：112 卡名中 40 个全库多文本，火恐龙（特性版 vs 白板）/索财灵池内同名异效。现有 DSL 需审计拆分（朋友手册/巢穴球/高级球/神奇糖果等着异文本混挂），归 task 026 前置
- 待用户核对事项全部清零；task 026 可启动

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
| 2026-08-30 | 退赛 4 archetype 以退赛后窗口 WUR 前列替补（玛俐长毛巨魔雪妖女/赛富豪/多龙巴鲁托/赫普的苍响） | config/target-pool.v1.yml 头注；task 024 |
| 2026-09-06 | DSL 归组口径 =（卡名 + 文本）等价类，**严格拆分**：同语义异措辞也拆（朋友手册「最多2张」/「2张」级别差异不合并）；装载键 name_group → card_id 精确挂载；闸 1 校验文件内 card_ids 归一化 text_raw 一致 | 用户决议（池内实测：112 卡名中 40 个全库多文本、火恐龙/索财灵池内同名异效）；归 task 026 前置 |
| 2026-09-06 | task 026 re-scope：解锁项驱动替代字母批；顺序 = 装配校验前置 → filters/conditions → trigger_on_event + place_damage_counters → 其余按解锁卡数；老大的指令顺带 | 用户决议；tasks/task 026.md |
| 2026-09-19 | 卡池 v1 维持锁定（db 新快照 standard-2026-09-16 + 数据至 09-09 后不换池）——校准基线需要池稳定；密勒顿回池评估留待 M6 后 | 用户决议；STATUS 2026-09-19 数据更新验收节 |
