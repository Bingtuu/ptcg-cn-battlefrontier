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
| 友好宝芬 | trainer | search | 喷火龙大比鸟/多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女/赛富豪/多龙巴鲁托 | A | 现有原语（hp_max 过滤器已随 task 024 注册） | done（task 024 自验卡，gate3 待核销） |
| 吉尼亚 | trainer | search | 喷火龙大比鸟/多龙黑夜魔灵/多龙巴鲁托 | A | 现有原语 | done（task 025 闸1/2 过，gate3 待核销） |
| 多龙奇 | pokemon | search | 多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托 | A | 现有原语 | blocked:缺 name:<卡名> 过滤器 |
| 多龙梅西亚 | pokemon | damage_boost | 多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托 | A | vanilla（无需 DSL，装载即可） | done（vanilla 核验：目标印刷无效果句，无需 DSL） |
| 夜巡灵 | pokemon | bounce | 喷火龙大比鸟/多龙黑夜魔灵 | A | 现有原语 | blocked:缺 recover_from_discard bench 去向 + name 过滤器 |
| 奥琳博士的气魄 | trainer | draw,energy_accel | 猛雷鼓厄诡椪 | A | 现有原语 | blocked:缺古代特质过滤（CardDef labels）+ attach 多目标各附1 |
| 宝可梦交替 | trainer | switch | 多龙黑夜魔灵/赛富豪/赫普的苍响 | A | 现有原语 | done（task 025 闸1/2 过，gate3 待核销） |
| 宝可装置3.0 | trainer | search,bounce | 赫普的苍响 | A | 现有原语 | blocked:缺 search_deck top_n 限定池 |
| 小刚的发掘 | trainer | search | 赛富豪 | A | 现有原语 | blocked:缺二选一组合约束选择 |
| 尖钉镇道馆 | trainer | search | 玛俐长毛巨魔雪妖女 | A | 现有原语 | blocked:缺 owner_pokemon:<名> 过滤器 |
| 弗图博士的剧本 | trainer | bounce | 喷火龙大比鸟/猛雷鼓厄诡椪/赛富豪/多龙巴鲁托 | A | bounce 原语（task 025 已注册） | done（task 025 代表卡，gate3 待核销） |
| 彷徨夜灵 | pokemon | status | 喷火龙大比鸟/多龙黑夜魔灵 | A | 现有原语 | done（task 025 闸1/2 过，gate3 待核销） |
| 怒鹦哥ex | pokemon | draw,energy_accel | 猛雷鼓厄诡椪 | A | 现有原语 | blocked:缺 first_own_turn + attach_energy up-to-N + bench-only 目标池 |
| 拉帝亚斯ex | pokemon | modifier,cooldown | 猛雷鼓厄诡椪/多龙巴鲁托/赫普的苍响 | A | 现有原语 | blocked:缺 modify_retreat_cost（全体基础）+ 招式冷却机制 |
| 拉鲁拉丝 | pokemon | status | 沙奈朵 | A | vanilla（无需 DSL，装载即可） | done（vanilla 核验：目标印刷无效果句，无需 DSL） |
| 招式学习器 退化 | trainer | bounce,evolution,special_behavior | 玛俐长毛巨魔雪妖女/赫普的苍响 | A | 现有原语 | blocked:缺 devolve 原语（退化回对手手牌） |
| 摔角鹰人 | pokemon | draw,bounce | 多龙黑夜魔灵/多龙巴鲁托 | A | 现有原语 | blocked:缺 trigger_on_event 分发 + place_damage_counters（task 026 域） |
| 暗码迷的解读 | trainer | search,bounce | 赛富豪 | A | 现有原语 | blocked:缺 deck_top 去向 + 有序排列选择 |
| 月月熊 赫月ex | pokemon | modifier,cooldown | 猛雷鼓厄诡椪/多龙黑夜魔灵/多龙巴鲁托/赫普的苍响 | A | 现有原语 | blocked:缺 modify_attack_cost + opponent_taken_prizes 计数词 + 冷却机制 |
| 朋友手册 | trainer | discard_recover,bounce | 赫普的苍响 | A | 现有原语 | done（task 025 闸1/2 过，gate3 待核销） |
| 比比鸟 | pokemon | - | 喷火龙大比鸟 | A | vanilla（无需 DSL，装载即可） | done（vanilla 核验：目标印刷无效果句，无需 DSL） |
| 水莲的照顾 | trainer | discard_recover | 赛富豪 | A | 现有原语 | blocked:缺 pokemon_no_rule_or_basic_energy 过滤器 |
| 沙铃仙人掌 | pokemon | - | 多龙巴鲁托 | A | 现有原语 | blocked:缺 place_damage_counters + KO 事件触发 + 撤退锁（task 026/029 域） |
| 波波 | pokemon | search | 喷火龙大比鸟 | A | 现有原语 | done（task 025 闸1/2 过，gate3 待核销） |
| 火恐龙 | pokemon | - | 喷火龙大比鸟/多龙喷火龙 | A | 现有原语 | blocked:缺 discard own_attached_energy + 招式效果免疫 passive（task 029 域） |
| 牡丹 | trainer | bounce | 赫普的苍响 | A | 现有原语 | blocked:缺 bounce 附着物回手参数 + in-play 基础宝可梦过滤器 |
| 猛雷鼓 | pokemon | draw | 猛雷鼓厄诡椪 | A | 现有原语 | blocked:缺 counters 词 attached_energy_on_target |
| 猛雷鼓ex | pokemon | draw | 猛雷鼓厄诡椪 | A | 现有原语 | blocked:缺弃置场上附着能量原语 + 前节点选择数计数词 |
| 猫头夜鹰 | pokemon | bounce | 猛雷鼓厄诡椪 | A | 现有原语 | blocked:缺 trigger_on_event 引擎分发 + own_tera_in_play |
| 玛俐的捣蛋小妖 | pokemon | draw | 玛俐长毛巨魔雪妖女 | A | 现有原语 | done（task 025 闸1/2 过，gate3 待核销） |
| 玛俐的诈唬魔 | pokemon | - | 玛俐长毛巨魔雪妖女 | A | 现有原语 | done（vanilla 核验：目标印刷无效果句，无需 DSL） |
| 白蕾雅 | trainer | modifier | 喷火龙大比鸟 | A | 现有原语 | blocked:缺 opponent_prizes_eq:2 + CardDef.is_tera + 奖赏修正钩子 |
| 百变怪 | pokemon | search | 猛雷鼓厄诡椪 | A | 现有原语 | blocked:缺 first_own_turn/self_is_active + 变身替换原语 |
| 皮宝宝 | pokemon | bounce | 喷火龙大比鸟 | A | 现有原语 | done（task 025 闸1/2 过，gate3 待核销） |
| 米立龙 | pokemon | search,bounce | 赫普的苍响 | A | 现有原语 | blocked:缺牌库顶N检视 + self_is_active |
| 索财灵 | pokemon | - | 赛富豪 | A | 现有原语 | blocked:缺 coin_flip until_tails + 正面次数×N 伤害 |
| 紧急滑板 | trainer | modifier | 喷火龙大比鸟/多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女/赫普的苍响 | A | 现有原语 | blocked:缺 modify_retreat_cost + holder_hp_le:N |
| 能量输送 | trainer | search | 玛俐长毛巨魔雪妖女 | A | 现有原语 | done（task 025 闸1/2 过，gate3 待核销） |
| 赛富豪ex | pokemon | draw | 赛富豪 | A | 现有原语 | blocked:缺 holder_is_active + discard 区间弃置 + 弃置张数计数词 |
| 赤松 | trainer | search,energy_accel | 猛雷鼓厄诡椪/多龙黑夜魔灵 | A | 现有原语 | blocked:缺 distinct-type 约束 + 检索拆分去向(hand+attach) |
| 赫普的包包 | trainer | search | 赫普的苍响 | A | 现有原语 | blocked:缺 owner_pokemon:<名> 过滤器 |
| 赫普的古月鸟 | pokemon | - | 赫普的苍响 | A | 现有原语 | blocked:缺 condition opponent_prizes_in:[4,3] |
| 超级能量回收 | trainer | discard_recover | 赛富豪 | A | 现有原语 | blocked:缺 recover_from_discard hand up-to(min_choose=0) |
| 雪童子 | pokemon | - | 玛俐长毛巨魔雪妖女 | A | 现有原语 | blocked:缺对手手牌随机单张回牌库原语（hand_disrupt） |
| 零之大空洞 | trainer | modifier | 猛雷鼓厄诡椪 | A | 现有原语 | blocked:缺 bench_size 覆写 + CardDef.is_tera + 失效缩减结算 |
| 飞天螳螂 | pokemon | energy_accel | 赛富豪 | A | 现有原语 | blocked:缺 energy_type:<属性> 过滤器 + bench-only attach 目标池 |
| 不服输头带 | trainer | damage_boost | 玛俐长毛巨魔雪妖女 | B | modify_damage 结算（task 025 已接入） | done（task 025 代表卡，gate3 待核销） |
| 化朗镇 | trainer | damage_boost | 赫普的苍响 | B | 小原语批（task 025/026） | pending |
| 古玉鱼 | pokemon | mill,energy_accel | 喷火龙大比鸟 | B | 小原语批（task 025/026） | pending |
| 咕咕 | pokemon | gust | 猛雷鼓厄诡椪 | B | 小原语批（task 025/026） | pending |
| 喷火龙ex | pokemon | damage_boost | 喷火龙大比鸟/多龙喷火龙 | B | 小原语批（task 025/026） | pending |
| 大比鸟ex | pokemon | search,removal | 喷火龙大比鸟 | B | 小原语批（task 025/026） | pending |
| 小火龙 | pokemon | removal | 喷火龙大比鸟/多龙喷火龙 | B | 小原语批（task 025/026） | pending |
| 火箭队的惊吓炸弹 | trainer | spread | 赫普的苍响 | B | 小原语批（task 025/026） | pending |
| 爬地翅 | pokemon | mill,status | 猛雷鼓厄诡椪 | B | 小原语批（task 025/026） | pending |
| 空手道王的修炼 | trainer | damage_boost | 赫普的苍响 | B | 小原语批（task 025/026） | pending |
| 老大的指令 | trainer | gust | 喷火龙大比鸟/猛雷鼓厄诡椪/多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女/赛富豪/多龙巴鲁托/赫普的苍响 | B | 小原语批（task 025/026） | pending |
| 裁判 | trainer | draw,hand_disrupt,bounce | 猛雷鼓厄诡椪 | B | 小原语批（task 025/026） | pending |
| 谢米 | pokemon | heal,bounce | 多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女 | B | 小原语批（task 025/026） | pending |
| 赫普的卡比兽 | pokemon | damage_boost | 赫普的苍响 | B | 小原语批（task 025/026） | pending |
| 赫普的讲究头带 | trainer | damage_boost,modifier | 赫普的苍响 | B | 小原语批（task 025/026） | pending |
| 野餐篮 | trainer | heal | 赛富豪 | B | 小原语批（task 025/026） | pending |
| 雪妖女 | pokemon | spread | 玛俐长毛巨魔雪妖女 | B | 小原语批（task 025/026） | pending |
| 不公印章 | trainer | draw,hand_disrupt,bounce | 多龙黑夜魔灵/多龙喷火龙 | C | ACE SPEC 机制（task 027） | pending |
| 厄诡椪 碧草面具ex | pokemon | draw,energy_accel | 猛雷鼓厄诡椪 | C | TERA 规则盒结算核对（task 027） | pending |
| 含羞苞 | pokemon | lock | 多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女/多龙巴鲁托 | C | 持续 lock/protection 体系（task 029） | pending |
| 喷射能量 | energy | modifier | 喷火龙大比鸟/赫普的苍响 | C | 特殊能量被动框架（task 026） | pending |
| 多龙巴鲁托ex | pokemon | spread | 多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托 | C | TERA 规则盒结算核对（task 027） | pending |
| 夜光能量 | energy | modifier | 多龙喷火龙/多龙巴鲁托 | C | 特殊能量被动框架（task 026） | pending |
| 巨钳螳螂 | pokemon | damage_boost,protection,evolution | 赛富豪 | C | 持续 lock/protection 体系（task 029） | pending |
| 新冲天能量 | energy | modifier | 多龙巴鲁托 | C | ACE SPEC 机制（task 027） | pending |
| 旋转洛托姆 | pokemon | spread,lock,modifier | 猛雷鼓厄诡椪 | C | 持续 lock/protection 体系（task 029） | pending |
| 极限腰带 | trainer | damage_boost | 喷火龙大比鸟 | C | ACE SPEC 机制（task 027） | pending |
| 火箭队的监视塔 | trainer | lock | 多龙巴鲁托 | C | 持续 lock/protection 体系（task 029） | pending |
| 玛俐的长毛巨魔ex | pokemon | search,spread,energy_accel,lock,evolution | 玛俐长毛巨魔雪妖女 | C | 持续 lock/protection 体系（task 029） | pending |
| 能量输送PRO | trainer | search | 赛富豪 | C | ACE SPEC 机制（task 027） | pending |
| 薄雾能量 | energy | protection,modifier | 喷火龙大比鸟 | C | 特殊能量被动框架（task 026） | pending |
| 赫普的苍响ex | pokemon | spread,lock,cooldown | 赫普的苍响 | C | 持续 lock/protection 体系（task 029） | pending |
| 阻碍之塔 | trainer | lock | 喷火龙大比鸟/猛雷鼓厄诡椪/多龙喷火龙/多龙巴鲁托 | C | 持续 lock/protection 体系（task 029） | pending |
| 顶尖捕捉器 | trainer | gust,switch | 猛雷鼓厄诡椪/赫普的苍响 | C | ACE SPEC 机制（task 027） | pending |
| 黑夜魔灵 | pokemon | lock,modifier | 喷火龙大比鸟/多龙黑夜魔灵 | C | 持续 lock/protection 体系（task 029） | pending |
