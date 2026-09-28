# task 029 · 持续 lock/suppression 体系 + C 级收尾 8 卡（M5 缺口清零）

- 状态：完成（2026-09-20）
- 关联：PRD §5.1 / 里程碑 M5；coverage-plan C 级「持续 lock/protection 体系」8 行（最后 pending）

## 目标

卡池缺口最后 8 张落地（闸 1/2 + 落账 done），M5 覆盖清零。db text_raw 实测
（2026-09-20，池内 card_id 取自 `config/target-pool.v1.yml` 9 套 deck_cards）：

| 卡 | 池内等价类（赛制标） | 挂载 card_ids | 机制判定 |
|---|---|---|---|
| 含羞苞 | 全库 3 印刷单类（H） | CSV9.5C-004, CSVM2bC-001, SVP-411 | 小机制：痒痒花粉 10 + **lock_play 物品锁**（「下一个对手的回合，对手无法从手牌使出物品」） |
| 巨钳螳螂 | 池内类 = 4 印刷（G）；全库 17 印刷 8 类严格拆分 | CSV4C-081, CSVL2C-045, CSVL2C-085, SVP-029 | 小扩展：惩罚巨钳 10+**对手场上拥有特性的宝可梦数×50**（新计数词）；居合劈 70 白板 |
| 旋转洛托姆 | 池内类 = 4 印刷（H）；全库 5 印刷 2 类拆分 | CSV9.5C-148, CSV9C-161, CSVM2aC-012, SVP-292 | 小扩展：特性风扇呼唤（first_own_turn + once_per_turn_shared + 检索 ≤3 张 HP≤100【无】宝可梦 + reveal）；突击登陆 70（**stadium_in_play 招式失败门**，D-029-7） |
| 火箭队的监视塔 | 全库 1 印刷单类（I） | CSV10C-219 | **新机制：suppress_ability**（竞技场：双方场上所有【无】宝可梦特性全消） |
| 玛俐的长毛巨魔ex | 全库 2 印刷单类（I） | CSV10C-148, SVP-397 | 中扩展：庞克泵感（own_evolve_from_hand 触发 + 牌库 ≤5 基本恶能量**任意分配附着**于玛俐的宝可梦）；暗影子弹 180 + **备战狙击 30** |
| 赫普的苍响ex | 全库 4 印刷单类（I） | CSV10C-161, CSV10C-247, CSV10C-274, SVP-404 | 小扩展：刹那斩 30 + **备战狙击 30**；英勇之刃 240 + lock_attack 冷却（D-WP4-5 先例，机制已有） |
| 阻碍之塔 | 全库 6 印刷单类（H） | CSV8C-203, CSV8C-262, CSV9.5C-202, CSVM2aC-030, CSVM2cC-030, SVP-287 | **新机制：suppress_tool**（竞技场：双方所有宝可梦道具效果全消） |
| 黑夜魔灵 | 池内类 = 4 印刷（H）；全库 12 印刷 5 类严格拆分 | CSV8C-083, CSV8C-212, CSV9.5C-071, SVP-348 | **直写**：咒怨炸弹（ability_manual + once_per_turn + ko_self + place_damage_counters 13，彷徨夜灵同构）；影子束缚 150 + lock_retreat（沙铃仙人掌同构） |

配套机制骨架（本任务主题 = 持续 lock/suppression 体系）：

1. **suppression 声明式框架**：竞技场 passive_static 声明 `suppress_ability` /
   `suppress_tool`（词表新词），引擎统一守卫 `_ability_suppressed(mon)` /
   `_tool_suppressed(mon)`，各读点接入（对齐 provide_energy/bench_size 声明式先例）。
2. **lock_play 物品锁**：on_attack 原语（词表新词），对手侧回合标记（turn 戳，
   对齐 lock_retreat 结构），落点 = 物品打出枚举门控。

## 验收标准（测试清单）

设计决议（主会话定稿 2026-09-20；随落地进附录 A 🔲，gate3 核销后翻 ✅）：

- **D-029-1 suppress_ability（监视塔）**：声明挂载竞技场卡（passive_static），
  目标 = 双方场上所有【无】属性宝可梦（读栈顶 types）；消除面 = ability_manual
  枚举门 + 宝可梦卡来源的被动 aura（_protected_from_attack_effects 等）+
  宝可梦卡来源的 trigger_on_event 分发（pokemon_check/own_evolve_from_hand 等）。
  竞技场离场即恢复；已结算效果无追溯。能量卡/训练家效果不受影响。
- **D-029-2 suppress_tool（阻碍之塔）**：目标 = 双方场上全部宝可梦的 attached_tool；
  消除面 = 道具全部引擎读点——_effective_hp / _effective_damage_modifier /
  _effective_retreat_cost / _effective_attack_cost 道具分支 + grant_attack 授予招式
  （枚举与执行双落点）+ 道具 on_attack 绑定。动态求值天然无追溯（如 HP 加成失效
  即按新有效 HP 判昏厥，走 check_knockouts）；能量卡（喷射/夜光/薄雾）不受影响。
- **D-029-3 lock_play 物品锁（含羞苞）**：on_attack 原语 lock_play
  args{category: item}——受击方下个自己回合无法从手牌使出**物品**（支援者/竞技场/
  道具附着不受影响）；turn 戳对齐 lock_retreat（WP6）结构；撤退/离场不解锁
  （锁作用于玩家侧回合，非宝可梦实例——卡面「对手无法」）。
- **D-029-4 备战狙击 damage（苍响/长毛巨魔）**：_damage selector 扩
  opponent_bench choose=1；备战空 → 该节点 no-op、主战伤害照算（WP4 宣言裁决
  延伸）；弱抗不结算（贯穿规则）；谢米 protection（D-WP7-5）与太晶备战免伤
  （D-027-1）既有守卫同落点生效。
- **D-029-5 庞克泵感任意分配附着（长毛巨魔）**：attach_energy selector own_deck +
  args.distribute——段 1 选能量 up-to 5（filters basic_energy + energy_恶）→ 段 2
  逐张挂起选目标（own_pokemon_in_play + target_filters owner_pokemon:玛俐，可集中
  可分散，「以任意方式」）→ 重洗；选 0 → no-op 仍重洗（D-WP5-1 口径）；
  ability_feasible 门补本形式（双侧池非空）。
- **D-029-6 风扇呼唤共享口径**：once_per_turn_shared 按卡名共享 ≈ 卡面「其他的
  风扇呼唤」——一期池内仅旋转洛托姆一种卡有此特性，按卡名 = 等价（已知近似，
  异卡同名特性再议）；condition first_own_turn（WP1 既有）。
- **D-029-7 小词**：condition `stadium_in_play`（突击登陆「如果场上没有竞技场
  的话，则这个招式失败」——WP1 钩子「condition 不满足即招式失败」的成功前提
  正向词，卡面失败子句的正向形式，对齐古月鸟 opponent_prizes_in 正向挂载先例；
  2026-09-20 主会话裁决：不注册 no_stadium_in_play 反向词——无落地卡的词不先行）；
  filter `pokemon_<属性>` 参数化泛化（既有字面词 pokemon_超 并入，
  对齐 WP1 energy_<属性> 泛化先例），解锁 pokemon_无。
- **D-029-8 计数词 `opponent_ability_pokemon_count`**（惩罚巨钳）：对手场上
  （战斗+备战）has_ability 宝可梦数量（CardDef.has_ability，WP7 数据管道既有）。

测试清单（`tests/test_primitives_t29.py` + 卡分片 `tests/test_dsl_cards_t29.py`）：

suppression 体系（D-029-1/2）：
1. 监视塔在场：双方【无】宝可梦 ability_manual 不枚举（非【无】照常；对手侧同口径）；
   被动 aura（谢米 protection）在【无】持有者身上失效；trigger_on_event
   （雪妖女 pokemon_check 类）在【无】持有者身上不触发；竞技场离场恢复
2. 阻碍之塔在场：道具 modify_hp / modify_damage / modify_retreat_cost /
   modify_attack_cost 全失效（含 HP 加成失效致昏厥走 check_knockouts）；
   授予招式不枚举不可执行；竞技场离场恢复；能量卡被动（喷射/夜光）不受影响
3. 声明求值点一致性：两竞技场叠加/替换（顶掉即恢复）回合内即时生效

lock_play（D-029-3）：
4. 含羞苞攻击后：对手下回合物品不枚举（支援者/竞技场/道具附着/能量附着照常）；
   隔一回合恢复；连续两回合攻击刷新 turn 戳

备战狙击（D-029-4）：
5. 苍响 刹那斩：主战 30 + 选 1 只备战 30（弱抗不结算；谢米保护归零；备战太晶归零）；
   备战空 no-op 主战照算；英勇之刃 lock_attack 冷却（N 用 → N+1 锁 → N+2 解禁，
   撤退清除——WP4 机制卡级钉住）

庞克泵感（D-029-5）：
6. 从手牌进化触发：选 ≤5 基本恶能量逐张分配（集中 1 只 / 分散多只 / 仅玛俐的宝可梦
   可选目标——非玛俐宝可梦在场不入选池）→ 重洗；选 0 仍重洗；牌库能量不足收缩；
   非从手牌进化（学习器 from_deck）不触发（D-WP3-2 口径）

直写/小词（D-029-6/7/8）：
7. 黑夜魔灵：咒怨炸弹 13 指示物 + ko_self（奖赏/换上队列，彷徨夜灵同构回归）；
   影子束缚 lock_retreat（目标下回合不可撤退，其回合结束解除）
8. 旋转洛托姆：风扇呼唤首回合限 1 + 同名共享锁 + 检索 ≤3 张 HP≤100【无】宝可梦
   + reveal + 重洗（超属性/HP>100 不入选池）；突击登陆无竞技场 → 招式失败
   （攻击机会消耗、回合结束，古月鸟口径）；有竞技场正常 70
9. 巨钳螳螂：对手场上特性宝可梦 0/2/3 只 → 10+0/100/150；居合劈 70 白板

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归 +
`dsl-check --db` 全库全 OK（SVP-* 印刷赛制合法性逐张过闸）+ 词表同步
（actions +lock_play/+suppress_ability/+suppress_tool；counters
+opponent_ability_pokemon_count；conditions +stadium_in_play；filters
pokemon_<属性> 泛化）+ 真机冒烟（含羞苞/监视塔/长毛巨魔/苍响/阻碍之塔/黑夜魔灵
所在池内卡组：多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托/玛俐雪妖女/赫普的苍响/
猛雷鼓厄诡椪/喷火龙大比鸟/赛富豪）

## 实现要点

- 流程对齐 task 026 惯例：机制批（TDD 红→绿）→ 双复核 → 卡牌批 → 复核 → 冒烟 →
  落账；限流期子代理串行、小批次复核主会话自做（2026-09-20 过程纪要）
- 严守不猜纪律；词表开放字符串注册；db 只读；子代理不改既有测试（断言存疑报主会话）
- suppression 守卫统一单入口（`_ability_suppressed` / `_tool_suppressed`），新读点
  必须显式接入（docstring 明示，对齐 protection 守卫落点清单先例 D-WP6-7）
- 同名多文本严格拆分（巨钳螳螂 8 类 / 旋转洛托姆 2 类 / 黑夜魔灵 5 类，仅挂池内类）
- 规则出处：suppression 类竞技场=卡面原文；lock_play「无法从手牌使出物品」=
  rules-manual 训练家卡节；备战狙击弱抗=§6 贯穿规则

## 结果与遗留

- **流程**：主会话立项（db text_raw 逐卡实测 + 缺口分析 + 任务书 D-029-1~8）→
  机制批子代理 TDD（DONE_WITH_CONCERNS：D-029-6 词义方向规格矛盾报主会话）
  → 主会话独立复验 + 规格/质量合并复核（降本裁决口径）+ 三条裁决 → 卡牌批
  子代理（8 卡一批，DONE）→ 主会话复核批准 → 冒烟 → 落账
- **机制层**：①suppression 声明式框架（suppress_ability/suppress_tool 竞技场
  passive_static，引擎统一守卫 `_ability_suppressed`/`_tool_suppressed` 单入口 +
  落点清单 docstring；`_do_play_stadium` 补 check_knockouts 判 HP 加成失效昏厥）；
  ②lock_play 物品锁（PlayerState.item_lock_mark 玩家侧回合标记 + turn 戳）；
  ③damage selector 扩 opponent_bench（备战空 no-op）；④attach_energy own_deck
  args.distribute 显式声明（执行语义与 WP7 烈炎支配存量一致——逐张挂起任意分配
  为既有行为，本批补声明校验 + ability_feasible 双侧池门 + 场上过滤器
  owner_pokemon:X）；⑤小词：stadium_in_play / pokemon_<属性> 泛化 /
  opponent_ability_pokemon_count
- **主会话裁决 3 条**：D-029-6 改 stadium_in_play 正向词（删 no_stadium_in_play——
  无落地卡的词不先行，对齐古月鸟正向挂载先例）；lock_play 不接 protection 守卫
  （玩家侧落点）；学习器自弃不接 suppress_tool（已知近似进附录 A 候选）
- **新卡 8 张（闸 1/2 全过，first_pass 0/8 严格口径——闸 2 首跑前测试脚手架
  2 处修正（导入路径/F401），8 卡 YAML 全部零返工；gate3 待核销）**：含羞苞（3 印刷
  全挂）/ 巨钳螳螂-惩罚巨钳（池内类 4 印刷，全库 8 类拆分）/ 旋转洛托姆-风扇呼唤
  （池内类 4 印刷，2 类拆分）/ 火箭队的监视塔（1 印刷）/ 玛俐的长毛巨魔ex（2 印刷）/
  赫普的苍响ex（4 印刷）/ 阻碍之塔（6 印刷全挂）/ 黑夜魔灵-咒怨炸弹（池内类 4 印刷，
  5 类拆分，直写零机制新增）——共 26 印刷
- **测试**：task 029 新 53 条（primitives_t29 34 + dsl_cards_t29 19）；
  **全量 905 绿（基线 852）+ ruff 零告警 + dsl-check --db 全库 101 文件全 OK**
- **真机冒烟 80 局 0 失败**（heuristic 4×20，`results/t29-smoke/`）：喷火龙大比鸟
  vs 赛富豪 18/2；多龙巴鲁托 vs 猛雷鼓厄诡椪 6/13/平1；多龙黑夜魔灵 vs 多龙喷火龙
  5/15；玛俐雪妖女 vs 赫普的苍响 10/9/平1。机制真实触发：lock_play 148 次、
  监视塔打出 10 次、阻碍之塔打出 44 次、黑夜魔灵咒怨炸弹 ko_self 42 次、
  旋转洛托姆特性 3 次 + attack_failed（突击登陆门）2 次；长毛巨魔 庞克泵感/
  巨钳螳螂计数 80 局未自然出现（启发式路径未达），由单卡测试覆盖
- **落账**：coverage-plan 8 行 pending→done——**缺口 done 81 / blocked 0 /
  pending 0（共 81，M5 覆盖清零）**；authoring-log 批 9 八条；附录 A D-029-1~8
  + 学习器自弃候选共 9 条 🔲 待核；PRD §5.1 task 029 段（机制批随批定稿）；
  定义库 93→101 文件
- **遗留**：8 个卡文件 gate3 待用户核销（攒批 42 个：WP6 9 + WP7 15 + WP8 3 +
  t027 7 + t029 8）+ 附录 A 待核决议攒批（WP6 8 + WP7 11 + WP8 5 + t027 8 +
  t029 9 条）；夜光能量异文本类 7 印刷未落地（回归池内需另文新写）；
  下一步 = M5 收口（gate3 攒批核销 + LLM harness 质量数据汇总）→ M6 校准基线
