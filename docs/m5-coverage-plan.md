# M5 覆盖计划：目标卡组池缺口全表（v1，2026-08-30 生成）

> 生成口径：`config/target-pool.v1.yml` 锁定池（WUR 窗口 2026-05-30~08-28 /
> master·cn / 6 场 / 快照 standard-2026-07-16；代表卡组均过当前快照合法性校验，
> 替补口径见 pool 文件头注）。缺口 = 9 套代表卡组并集 − 已有 cards/ DSL − 基本能量
>（引擎原生）。级别为 effect_tags 归并的**初判**，逐卡落地以 db `text_raw` 原文为准；
> 状态随 task 025–030 核销（pending / blocked:<原因> / done）。

缺口合计 **81 张**（A 46 / B 17 / C 18）。
V-UNION 缺口 0（一期不做，无冲突）。

## 批次划分（按级别 = 原语依赖递增）

- 批 1（task 025）：A 级——现有原语可写 + 小原语（coin_flip/gust/heal/伤害修饰）顺路补
- 批 2（task 026）：B 级——铺伤/手牌干扰/mill/ko/特殊能量被动框架先行
- 批 3（task 027–030）：C 级——VSTAR 力量 / ACE SPEC / TERA / 放逐区 / lock 体系

| 卡名 | 卡种 | effect_tags | 所属卡组 | 级别 | 依赖 | 状态 |
|------|------|-------------|----------|------|------|------|
| 友好宝芬 | trainer | search | 喷火龙大比鸟/多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女/赛富豪/多龙巴鲁托 | A | 现有原语（hp_max 过滤器已随 task 024 注册） | done（task 024 自验卡，gate3 已核销） |
| 吉尼亚 | trainer | search | 喷火龙大比鸟/多龙黑夜魔灵/多龙巴鲁托 | A | 现有原语 | done（task 025 闸1/2 过，gate3 已核销 2026-09-06） |
| 多龙奇 | pokemon | search | 多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托 | A | 现有原语 | done（task 026 WP3：H 标侦察指令等价类 3 印刷，search_deck top_n=2 检视 + rest=deck_bottom 不洗牌；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 多龙梅西亚 | pokemon | damage_boost | 多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托 | A | vanilla（无需 DSL，装载即可） | done（vanilla 核验：目标印刷无效果句，无需 DSL） |
| 夜巡灵 | pokemon | bounce | 喷火龙大比鸟/多龙黑夜魔灵 | A | 现有原语 | done（task 026 WP3：H 标渡魂等价类 4 印刷，recover_from_discard bench 去向 up-to 3 + name 过滤器 + 备战容量截断；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 奥琳博士的气魄 | trainer | draw,energy_accel | 猛雷鼓厄诡椪 | A | 现有原语 | done（task 026 WP3：G 标 7 印刷全收，attach_energy 多目标各附1（trait:古代，FIFO 配对决议）+ draw 3；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 宝可梦交替 | trainer | switch | 多龙黑夜魔灵/赛富豪/赫普的苍响 | A | 现有原语 | done（task 025 闸1/2 过，gate3 已核销 2026-09-06） |
| 宝可装置3.0 | trainer | search,bounce | 赫普的苍响 | A | 现有原语 | done（task 026 WP4：G 标类 5 印刷，top_n=7 trainer_supporter rest=shuffle + reveal；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 小刚的发掘 | trainer | search | 赛富豪 | A | 现有原语 | done（task 026 WP6：I 标等价类 5 印刷，search choose_groups 二选一互斥（基础 up-to 2 / 进化 up-to 1）+ reveal + 空选仍重洗；闸1/2 过，first_pass=true，gate3 待核销） |
| 尖钉镇道馆 | trainer | search | 玛俐长毛巨魔雪妖女 | A | 现有原语 | done（task 026 WP1 闸1/2 过，gate3 已核销 2026-09-07；owner_pokemon:玛俐 过滤器） |
| 弗图博士的剧本 | trainer | bounce | 喷火龙大比鸟/猛雷鼓厄诡椪/赛富豪/多龙巴鲁托 | A | bounce 原语（task 025 已注册） | done（task 025 代表卡，gate3 已核销 2026-09-06） |
| 彷徨夜灵 | pokemon | status | 喷火龙大比鸟/多龙黑夜魔灵 | A | 现有原语 | done（task 026 WP2：H 标 CSV8C-082 咒怨炸弹新写入库，ko_self + place_damage_counters + promote_queue 机制件落地，同文本等价类 4 印刷全挂载；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 怒鹦哥ex | pokemon | draw,energy_accel | 猛雷鼓厄诡椪 | A | 现有原语 | done（task 026 WP4：G 标 CSV2C-105 类 7 印刷，英武重抽 first_own_turn+once_per_turn_shared+discard all+draw 6 / 鼓足干劲 attach bench-only up-to 2；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 拉帝亚斯ex | pokemon | modifier,cooldown | 猛雷鼓厄诡椪/多龙巴鲁托/赫普的苍响 | A | 现有原语 | done（task 026 WP4：H 标 CSV9C-078 类 3 印刷，天际线 modify_retreat_cost 全体基础 + 无限之刃 lock_attack 冷却（裁决后补全）；闸1/2 过，first_pass=false（测试侧笔误+机制门缺口），gate3 已核销 2026-09-14） |
| 拉鲁拉丝 | pokemon | status | 沙奈朵 | A | vanilla（无需 DSL，装载即可） | done（vanilla 核验：目标印刷无效果句，无需 DSL） |
| 招式学习器 退化 | trainer | bounce,evolution,special_behavior | 玛俐长毛巨魔雪妖女/赫普的苍响 | A | 现有原语 | done（task 026 WP6：G 标 4 印刷，学习器载体（授予招式+回合结束自弃）+ devolve 全场退栈顶 1 张回手、伤害保留状态恢复、HP 超限昏厥；闸1/2 过，first_pass=true，gate3 待核销） |
| 摔角鹰人 | pokemon | draw,bounce | 多龙黑夜魔灵/多龙巴鲁托 | A | 现有原语 | done（task 026 WP2：trigger_on_event 分发 + place_damage_counters 落地，飞身入场 G 标 CSV1C-079 同文本等价类 8 印刷全挂载；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 暗码迷的解读 | trainer | search,bounce | 赛富豪 | A | 现有原语 | done（task 026 WP6：H 标等价类 6 印刷，search any up-to 2 + deck_top 有序去向（选择顺序即牌顶 FIFO）+ 余库本节点重洗；闸1/2 过，first_pass=true，gate3 待核销） |
| 月月熊 赫月ex | pokemon | modifier,cooldown | 猛雷鼓厄诡椪/多龙黑夜魔灵/多龙巴鲁托/赫普的苍响 | A | 现有原语 | done（task 026 WP5：H 标 CSV8C-172 类 8 印刷，老练招式 modify_attack_cost 声明式（opponent_taken_prizes 减【无】、clamp 0）+ 血月 240 + lock_attack 冷却（沿用 D-WP4-5）；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 朋友手册 | trainer | discard_recover,bounce | 赫普的苍响 | A | 现有原语 | done（task 025 闸1/2 过，gate3 已核销 2026-09-06） |
| 比比鸟 | pokemon | - | 喷火龙大比鸟 | A | vanilla（无需 DSL，装载即可） | done（vanilla 核验：目标印刷无效果句，无需 DSL） |
| 水莲的照顾 | trainer | discard_recover | 赛富豪 | A | 现有原语 | done（task 026 WP3：H 标 7 印刷全收，recover_from_discard hand up-to（args.up_to）+ pokemon_no_rule_or_basic_energy + reveal；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 沙铃仙人掌 | pokemon | - | 多龙巴鲁托 | A | 现有原语 | done（task 026 WP6：I 标 2 印刷，own_ko_by_attack 触发（战斗场+对手招式伤害+昏厥三条件）+ place_damage_counters opponent_attacker 6 + lock_retreat 撤退锁；闸1/2 过，first_pass=true，gate3 待核销） |
| 波波 | pokemon | search | 喷火龙大比鸟 | A | 现有原语 | done（task 025 闸1/2 过，gate3 已核销 2026-09-06） |
| 火恐龙 | pokemon | - | 喷火龙大比鸟/多龙喷火龙 | A | 现有原语 | done（task 026 WP6：同名多文本严格拆分两文件——151C-005 类 3 印刷（大字爆炎 discard own_attached_energy choose=1）+ CSV5C-015 类 4 印刷（闪焰之幕 protection 最小版）；闸1/2 过，first_pass=true，gate3 待核销） |
| 牡丹 | trainer | bounce | 赫普的苍响 | A | 现有原语 | done（task 026 WP5：G 标 CSV1C-124 类 5 印刷，bounce args.attachments=hand（整叠+附着能量/道具全回手）；顺带修 bounce 不传 filters 的既有 bug；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 猛雷鼓 | pokemon | draw | 猛雷鼓厄诡椪 | A | 现有原语 | done（task 026 WP5：H 标 CSV8C-161 类 2 印刷，落雷风暴 attached_energy_on_target×30（目标含备战，备战弱抗不结算=引擎贯穿规则）；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 猛雷鼓ex | pokemon | draw | 猛雷鼓厄诡椪 | A | 现有原语 | done（task 026 WP5：H 标 CSV7C-154 类 7 印刷，飞溅咆哮 discard all+draw 6 / 极雷轰 discard own_attached_energy any_count + discarded_this_effect×70；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 猫头夜鹰 | pokemon | bounce | 猛雷鼓厄诡椪 | A | 现有原语 | done（task 026 WP3：H 标寻找宝石等价类 5 印刷，own_evolve_from_hand 事件 + own_tera_in_play + search trainer up-to 2 + reveal；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 玛俐的捣蛋小妖 | pokemon | draw | 玛俐长毛巨魔雪妖女 | A | 现有原语 | done（task 025 闸1/2 过，gate3 已核销 2026-09-06） |
| 玛俐的诈唬魔 | pokemon | - | 玛俐长毛巨魔雪妖女 | A | 现有原语 | done（vanilla 核验：目标印刷无效果句，无需 DSL） |
| 白蕾雅 | trainer | modifier | 喷火龙大比鸟 | A | 现有原语 | done（task 026 WP5：CSV9C-202 类 6 印刷，使用条件 opponent_prizes_eq:2 + prize_bonus 回合级标记（太晶招式伤害致对手战斗场昏厥多拿 1，从己奖赏堆拿）；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 百变怪 | pokemon | search | 猛雷鼓厄诡椪 | A | 现有原语 | done（task 026 WP5：「变身启动」G 标 151C-132 类 4 印刷（同名多文本拆分独立文件 cards/百变怪-变身启动.yml），transform 替换原语（非昏厥离场/伤害状态不继承/可空找仍重洗）+ self_is_active_and_first_own_turn 门控；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 皮宝宝 | pokemon | bounce | 喷火龙大比鸟 | A | 现有原语 | done（task 025 闸1/2 过，gate3 已核销 2026-09-06） |
| 米立龙 | pokemon | search,bounce | 赫普的苍响 | A | 现有原语 | done（task 026 WP4：揽客 H 标类 10 印刷全收，top_n=6 trainer_supporter rest=shuffle + reveal + self_is_active；闸1/2 过，first_pass=false（ability_feasible 缺 reveal 分支，机制门补齐后全绿），gate3 已核销 2026-09-14） |
| 索财灵 | pokemon | - | 赛富豪 | A | 现有原语 | done（task 026 WP5：「连掷硬币」G 标 CSV4C-063 类 3 印刷（同名多文本拆分独立文件 cards/索财灵-连掷硬币.yml），coin_flip until_tails + flip_heads_count×20；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 紧急滑板 | trainer | modifier | 喷火龙大比鸟/多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女/赫普的苍响 | A | 现有原语 | done（task 026 WP4：H 标 CSV7C-185 类 8 印刷，modify_retreat_cost -1 + holder_hp_le:30 全免双块；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 能量输送 | trainer | search | 玛俐长毛巨魔雪妖女 | A | 现有原语 | done（task 025 闸1/2 过，gate3 已核销 2026-09-06） |
| 赛富豪ex | pokemon | draw | 赛富豪 | A | 现有原语 | done（task 026 WP5：G 标 CSV4C-089 类 7 印刷，嘉奖硬币 draw 1 + if_self_active 追加 draw 1 / 淘金潮 discard own_hand basic_energy any_count + discarded_this_effect×50；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 赤松 | trainer | search,energy_accel | 猛雷鼓厄诡椪/多龙黑夜魔灵 | A | 现有原语 | done（task 026 WP6：H 标等价类 6 印刷，distinct=energy_type 选择池互斥（单属性收缩为 1）+ 拆分去向 hand+attach + 空选仍重洗；闸1/2 过，first_pass=true，gate3 待核销） |
| 赫普的包包 | trainer | search | 赫普的苍响 | A | 现有原语 | done（2026-09-07：db owner 赫普组补数后解锁，task 026 闸1/2 过，first_pass=false（测试夹具笔误，DSL 零修改），gate3 已核销 2026-09-07） |
| 赫普的古月鸟 | pokemon | - | 赫普的苍响 | A | 现有原语 | done（task 026 WP1 闸1/2 过，gate3 已核销 2026-09-07；opponent_prizes_in:[4,3] + on_attack 招式失败钩子） |
| 超级能量回收 | trainer | discard_recover | 赛富豪 | A | 现有原语 | done（task 026 WP4：G 标 CSV3C-115 类 8 印刷，cost discard 2 + recover hand up-to 4 exclude_cost_discarded + reveal；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 雪童子 | pokemon | - | 玛俐长毛巨魔雪妖女 | A | 现有原语 | done（task 026 WP6：H 标「惊吓」等价类 2 印刷，hand_disrupt 对手手牌均匀随机 1 张 reveal 后回库重洗 + damage 20；闸1/2 过，first_pass=true，gate3 待核销） |
| 零之大空洞 | trainer | modifier | 猛雷鼓厄诡椪 | A | 现有原语 | done（task 026 WP6：全赛制合法 5 印刷，bench_size 声明式覆写 5→8（own_tera_in_play 逐玩家求值）+ bench_shrink 失效缩减自选弃置（非昏厥无奖赏、双方同缩持有者先）；闸1/2 过，first_pass=true，gate3 待核销） |
| 飞天螳螂 | pokemon | energy_accel | 赛富豪 | A | 现有原语 | done（task 026 WP4：辅助斩 G 标 151C-123 类，attach bench-only choose=1 energy_草；闸1/2 过，first_pass=true，gate3 已核销 2026-09-14） |
| 不服输头带 | trainer | damage_boost | 玛俐长毛巨魔雪妖女 | B | modify_damage 结算（task 025 已接入） | done（task 025 代表卡，gate3 已核销 2026-09-06） |
| 化朗镇 | trainer | damage_boost | 赫普的苍响 | B | 小原语批（task 025/026） | done（task 026 WP7：I 标 CSV10C-218 唯一印刷，竞技场来源常驻 modify_damage（挂载面泛化四来源之一）+ holder_owner：赫普 对攻击方求值、双方生效；闸1/2 过，first_pass=true，gate3 待核销） |
| 古玉鱼 | pokemon | mill,energy_accel | 喷火龙大比鸟 | B | 小原语批（task 025/026） | done（task 026 WP7：G 标「嫉妒业火」等价类 4 印刷，attach own_discard 火能 up-to 2 + 节点门控 if_own_ko_by_attack_during_opponent_turn 追加 90（精确标记含备战狙击 F1 归正）；闸1/2 过，first_pass=true，gate3 待核销） |
| 咕咕 | pokemon | gust | 猛雷鼓厄诡椪 | B | 小原语批（task 025/026） | done（task 026 WP7：H 标「三刺击」等价类 2 印刷，coin_flip times:3 × flip_heads_count 既有原语组合直写；闸1/2 过，first_pass=true，gate3 待核销） |
| 喷火龙ex | pokemon | damage_boost | 喷火龙大比鸟/多龙喷火龙 | B | 小原语批（task 025/026） | done（task 026 WP7：G 标「烈炎支配」等价类 10 印刷，own_evolve_from_hand + attach_energy own_deck（up-to 3 基本火任意分配+重洗）+ opponent_taken_prizes×30；闸1/2 过，first_pass=true，gate3 待核销） |
| 大比鸟ex | pokemon | search,removal | 喷火龙大比鸟 | B | 小原语批（task 025/026） | done（task 026 WP7：G 标 6 印刷全收，音速搜索 once_per_turn_shared 同名锁 + discard_stadium 新原语（「若希望」不建模放弃，D-WP7-6）；闸1/2 过，first_pass=true，gate3 待核销） |
| 小火龙 | pokemon | removal | 喷火龙大比鸟/多龙喷火龙 | B | 小原语批（task 025/026） | done（task 026 WP7：G 标「烧光」等价类 5 印刷，discard_stadium + 吐火白板；闸1/2 过，first_pass=true，gate3 待核销） |
| 火箭队的惊吓炸弹 | trainer | spread | 赫普的苍响 | B | 小原语批（task 025/026） | done（task 026 WP7：I 标 CSV10C-198 唯一印刷，掷币正反分支 + place_damage_counters 新 selector own_active；闸1/2 过，first_pass=true，gate3 待核销） |
| 爬地翅 | pokemon | mill,status | 猛雷鼓厄诡椪 | B | 小原语批（task 025/026） | done（task 026 WP7：G 标「烫伤怒涛」等价类 3 印刷，mill 新原语 + damage self 90（固定值不吃修正）+ apply_status burned（宝可梦检查阶段灼伤结算）；闸1/2 过，first_pass=true，gate3 待核销） |
| 空手道王的修炼 | trainer | damage_boost | 赫普的苍响 | B | 小原语批（task 025/026） | done（task 026 WP7：H 标 7 印刷全收，on_play modify_damage 回合级标记 + target_rule_box:ex（求值点校验）；闸1/2 过，first_pass=true，gate3 待核销） |
| 老大的指令 | trainer | gust | 喷火龙大比鸟/猛雷鼓厄诡椪/多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女/赛富豪/多龙巴鲁托/赫普的苍响 | B | 小原语批（task 025/026） | done（task 026 WP1 闸1/2 过，gate3 已核销 2026-09-07；gust 无门控版，38 印刷同文本全挂载） |
| 裁判 | trainer | draw,hand_disrupt,bounce | 猛雷鼓厄诡椪 | B | 小原语批（task 025/026） | done（task 026 WP7：G 标「4张」等价类 31 印刷，shuffle_hand_into_deck 新原语（双方手牌回库重洗非库底）+ 各抽 4；闸1/2 过，first_pass=true，gate3 待核销） |
| 谢米 | pokemon | heal,bounce | 多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女 | B | 小原语批（task 025/026） | done（task 026 WP7：I 标「花之纱幔」等价类 2 印刷，protection 新 scope opponent_attack_damage_to_bench（伤害免疫备战面）+ no_rule_box 作用于受保护目标；闸1/2 过，first_pass=true，gate3 待核销） |
| 赫普的卡比兽 | pokemon | damage_boost | 赫普的苍响 | B | 小原语批（task 025/026） | done（task 026 WP7：I 标 CSV10C-175 唯一印刷，宝可梦 aura 来源 modify_damage scope=own_field（同名去重不叠加）+ holder_owner：赫普 + damage self 80；闸1/2 过，first_pass=true，gate3 待核销） |
| 赫普的讲究头带 | trainer | damage_boost,modifier | 赫普的苍响 | B | 小原语批（task 025/026） | done（task 026 WP7：I 标 CSV10C-201 唯一印刷，道具 modify_damage +30 + modify_attack_cost -1【无】（_effective_attack_cost 新增道具分支）+ holder_owner：赫普；闸1/2 过，first_pass=true，gate3 待核销） |
| 野餐篮 | trainer | heal | 赛富豪 | B | 小原语批（task 025/026） | done（task 026 WP7：G 标 4 印刷，heal 新 selector all_pokemon_both 双方全场各 30；闸1/2 过，first_pass=true，gate3 待核销） |
| 雪妖女 | pokemon | spread | 玛俐长毛巨魔雪妖女 | B | 小原语批（task 025/026） | done（task 026 WP7：H 标「冻结帷幕」等价类 10 印刷，宝可梦检查阶段 + pokemon_check 事件 + has_ability 数据管道/场上过滤器 + not_name + all_pokemon_both；闸1/2 过，first_pass=true，gate3 待核销） |
| 不公印章 | trainer | draw,hand_disrupt,bounce | 多龙黑夜魔灵/多龙喷火龙 | C | ACE SPEC 机制（task 027） | done（task 027：ACE 物品 2 印刷，宽口径 own_ko_during_opponent_turn 条件门 + 双方手牌回库重洗 + 自抽5/对手抽2（D-027-3）；闸1/2 过，first_pass=true，gate3 待核销） |
| 厄诡椪 碧草面具ex | pokemon | draw,energy_accel | 猛雷鼓厄诡椪 | C | TERA 规则盒结算核对（task 027） | done（task 027：TERA 10 印刷，碧草之舞 attach_energy own_hand→self + 抽1（D-027-5，D-WP8-3 归正触发喷射换位）+ 30+双方战斗场能量总数×30；闸1/2 过，first_pass=true，gate3 待核销） |
| 含羞苞 | pokemon | lock | 多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女/多龙巴鲁托 | C | 持续 lock/protection 体系（task 029） | pending |
| 喷射能量 | energy | modifier | 喷火龙大比鸟/赫普的苍响 | C | 特殊能量被动框架（task 026） | done（task 026 WP8：G 标等价类 5 印刷全挂，provide_energy [无] 声明式框架 + own_attach_from_hand_to_bench 手动附着备战触发 + switch self 换位（D-WP8-1/3）；闸1/2 过，first_pass=true，gate3 待核销） |
| 多龙巴鲁托ex | pokemon | spread | 多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托 | C | TERA 规则盒结算核对（task 027） | done（task 027：TERA 2阶 5 印刷，幻影潜袭 200 + place_damage_counters distribute 6 指示物任意分配（D-027-6，备战太晶不挡指示物）+ 喷射头击 70；闸1/2 过，first_pass=true，gate3 待核销） |
| 夜光能量 | energy | modifier | 多龙喷火龙/多龙巴鲁托 | C | 特殊能量被动框架（task 026） | done（task 026 WP8：池内文本类单挂 CSV1C-127（另 7 印刷异文本类按严格拆分未落地），provide_energy all 彩虹 + holder_special_energy_count_ge:2 降级【无】（D-WP8-1/2）；闸1/2 过，first_pass=true，gate3 待核销） |
| 巨钳螳螂 | pokemon | damage_boost,protection,evolution | 赛富豪 | C | 持续 lock/protection 体系（task 029） | pending |
| 新冲天能量 | energy | modifier | 多龙巴鲁托 | C | ACE SPEC 机制（task 027） | done（task 027：ACE 能量 2 印刷，provide_energy args.count=2 + types=all 彩虹双单元 + holder_stage:2 条件（D-027-4，非 2 阶回退 1【无】）；闸1/2 过，first_pass=true，gate3 待核销） |
| 旋转洛托姆 | pokemon | spread,lock,modifier | 猛雷鼓厄诡椪 | C | 持续 lock/protection 体系（task 029） | pending |
| 极限腰带 | trainer | damage_boost | 喷火龙大比鸟 | C | ACE SPEC 机制（task 027） | done（task 027：ACE 道具 2 印刷，道具 modify_damage +50 + target_rule_box:ex（WP7 机制复用，离场失效）；闸1/2 过，first_pass=true，gate3 待核销） |
| 火箭队的监视塔 | trainer | lock | 多龙巴鲁托 | C | 持续 lock/protection 体系（task 029） | pending |
| 玛俐的长毛巨魔ex | pokemon | search,spread,energy_accel,lock,evolution | 玛俐长毛巨魔雪妖女 | C | 持续 lock/protection 体系（task 029） | pending |
| 能量输送PRO | trainer | search | 赛富豪 | C | ACE SPEC 机制（task 027） | done（task 027：ACE 物品 1 印刷，search_deck any_count up-to all + distinct=energy_type 属性互斥 + reveal→手牌→重洗（D-027-7）；闸1/2 过，first_pass=true，gate3 待核销） |
| 薄雾能量 | energy | protection,modifier | 喷火龙大比鸟 | C | 特殊能量被动框架（task 026） | done（task 026 WP8：H 标等价类 3 印刷全挂，provide_energy [无] + protection opponent_attack_effects 能量来源并集（D-WP8-4，「已经受到的效果不会消失」=落点守卫天然满足）；闸1/2 过，first_pass=true，gate3 待核销） |
| 赫普的苍响ex | pokemon | spread,lock,cooldown | 赫普的苍响 | C | 持续 lock/protection 体系（task 029） | pending |
| 阻碍之塔 | trainer | lock | 喷火龙大比鸟/猛雷鼓厄诡椪/多龙喷火龙/多龙巴鲁托 | C | 持续 lock/protection 体系（task 029） | pending |
| 顶尖捕捉器 | trainer | gust,switch | 猛雷鼓厄诡椪/赫普的苍响 | C | ACE SPEC 机制（task 027） | done（task 027：ACE 物品 4 印刷，switch opponent_bench → switch own_bench 顺序两节点；双侧备战门维持现状进附录 A 候选条目；闸1/2 过，first_pass=true，gate3 待核销） |
| 黑夜魔灵 | pokemon | lock,modifier | 喷火龙大比鸟/多龙黑夜魔灵 | C | 持续 lock/protection 体系（task 029） | pending |
