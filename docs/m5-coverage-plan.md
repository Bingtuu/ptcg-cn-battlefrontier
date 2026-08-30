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
| 吉尼亚 | trainer | search | 喷火龙大比鸟/多龙黑夜魔灵/多龙巴鲁托 | A | 现有原语 | pending |
| 多龙奇 | pokemon | search | 多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托 | A | 现有原语 | pending |
| 多龙梅西亚 | pokemon | damage_boost | 多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托 | A | vanilla（无需 DSL，装载即可） | pending |
| 夜巡灵 | pokemon | bounce | 喷火龙大比鸟/多龙黑夜魔灵 | A | 现有原语 | pending |
| 奥琳博士的气魄 | trainer | draw,energy_accel | 猛雷鼓厄诡椪 | A | 现有原语 | pending |
| 宝可梦交替 | trainer | switch | 多龙黑夜魔灵/赛富豪/赫普的苍响 | A | 现有原语 | pending |
| 宝可装置3.0 | trainer | search,bounce | 赫普的苍响 | A | 现有原语 | pending |
| 小刚的发掘 | trainer | search | 赛富豪 | A | 现有原语 | pending |
| 尖钉镇道馆 | trainer | search | 玛俐长毛巨魔雪妖女 | A | 现有原语 | pending |
| 弗图博士的剧本 | trainer | bounce | 喷火龙大比鸟/猛雷鼓厄诡椪/赛富豪/多龙巴鲁托 | A | 现有原语 | pending |
| 彷徨夜灵 | pokemon | status | 喷火龙大比鸟/多龙黑夜魔灵 | A | 现有原语 | pending |
| 怒鹦哥ex | pokemon | draw,energy_accel | 猛雷鼓厄诡椪 | A | 现有原语 | pending |
| 拉帝亚斯ex | pokemon | modifier,cooldown | 猛雷鼓厄诡椪/多龙巴鲁托/赫普的苍响 | A | 现有原语 | pending |
| 拉鲁拉丝 | pokemon | status | 沙奈朵 | A | vanilla（无需 DSL，装载即可） | pending |
| 招式学习器 退化 | trainer | bounce,evolution,special_behavior | 玛俐长毛巨魔雪妖女/赫普的苍响 | A | 现有原语 | pending |
| 摔角鹰人 | pokemon | draw,bounce | 多龙黑夜魔灵/多龙巴鲁托 | A | 现有原语 | pending |
| 暗码迷的解读 | trainer | search,bounce | 赛富豪 | A | 现有原语 | pending |
| 月月熊 赫月ex | pokemon | modifier,cooldown | 猛雷鼓厄诡椪/多龙黑夜魔灵/多龙巴鲁托/赫普的苍响 | A | 现有原语 | pending |
| 朋友手册 | trainer | discard_recover,bounce | 赫普的苍响 | A | 现有原语 | pending |
| 比比鸟 | pokemon | - | 喷火龙大比鸟 | A | vanilla（无需 DSL，装载即可） | pending |
| 水莲的照顾 | trainer | discard_recover | 赛富豪 | A | 现有原语 | pending |
| 沙铃仙人掌 | pokemon | - | 多龙巴鲁托 | A | 现有原语 | pending |
| 波波 | pokemon | search | 喷火龙大比鸟 | A | 现有原语 | pending |
| 火恐龙 | pokemon | - | 喷火龙大比鸟/多龙喷火龙 | A | 现有原语 | pending |
| 牡丹 | trainer | bounce | 赫普的苍响 | A | 现有原语 | pending |
| 猛雷鼓 | pokemon | draw | 猛雷鼓厄诡椪 | A | 现有原语 | pending |
| 猛雷鼓ex | pokemon | draw | 猛雷鼓厄诡椪 | A | 现有原语 | pending |
| 猫头夜鹰 | pokemon | bounce | 猛雷鼓厄诡椪 | A | 现有原语 | pending |
| 玛俐的捣蛋小妖 | pokemon | draw | 玛俐长毛巨魔雪妖女 | A | 现有原语 | pending |
| 玛俐的诈唬魔 | pokemon | - | 玛俐长毛巨魔雪妖女 | A | 现有原语 | pending |
| 白蕾雅 | trainer | modifier | 喷火龙大比鸟 | A | 现有原语 | pending |
| 百变怪 | pokemon | search | 猛雷鼓厄诡椪 | A | 现有原语 | pending |
| 皮宝宝 | pokemon | bounce | 喷火龙大比鸟 | A | 现有原语 | pending |
| 米立龙 | pokemon | search,bounce | 赫普的苍响 | A | 现有原语 | pending |
| 索财灵 | pokemon | - | 赛富豪 | A | 现有原语 | pending |
| 紧急滑板 | trainer | modifier | 喷火龙大比鸟/多龙黑夜魔灵/多龙喷火龙/玛俐长毛巨魔雪妖女/赫普的苍响 | A | 现有原语 | pending |
| 能量输送 | trainer | search | 玛俐长毛巨魔雪妖女 | A | 现有原语 | pending |
| 赛富豪ex | pokemon | draw | 赛富豪 | A | 现有原语 | pending |
| 赤松 | trainer | search,energy_accel | 猛雷鼓厄诡椪/多龙黑夜魔灵 | A | 现有原语 | pending |
| 赫普的包包 | trainer | search | 赫普的苍响 | A | 现有原语 | pending |
| 赫普的古月鸟 | pokemon | - | 赫普的苍响 | A | 现有原语 | pending |
| 超级能量回收 | trainer | discard_recover | 赛富豪 | A | 现有原语 | pending |
| 雪童子 | pokemon | - | 玛俐长毛巨魔雪妖女 | A | 现有原语 | pending |
| 零之大空洞 | trainer | modifier | 猛雷鼓厄诡椪 | A | 现有原语 | pending |
| 飞天螳螂 | pokemon | energy_accel | 赛富豪 | A | 现有原语 | pending |
| 不服输头带 | trainer | damage_boost | 玛俐长毛巨魔雪妖女 | B | 小原语批（task 025/026） | pending |
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
