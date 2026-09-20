# task 027 · ACE SPEC 核对 + TERA 规则盒 + C 级 7 卡

- 状态：完成（2026-09-20）
- 关联：PRD §5.1 / 里程碑 M5；coverage-plan C 级「ACE SPEC 机制」「TERA 规则盒结算核对」两组

## 目标

卡池缺口 C 级 7 张落地（闸 1/2 + 落账 done）：

| 卡 | 池内 card_id | 组别 | 机制判定（db text_raw 实测 2026-09-20） |
|---|---|---|---|
| 不公印章 | CSV8C-173（H，ACE 物品，多龙黑夜魔灵/多龙喷火龙） | ACE | **直写**：条件 own_ko_during_opponent_turn（宽口径——卡面「自己的宝可梦昏厥」不限招式伤害，与古玉鱼精确口径区分）+ shuffle_hand_into_deck 双方 + 自抽 5 / 对手抽 2 |
| 极限腰带 | CSV7C-189（H，ACE 道具，喷火龙大比鸟） | ACE | **直写**：WP7 道具 modify_damage amount=50 + target_rule_box:ex |
| 顶尖捕捉器 | CSV7C-180（H，ACE 物品，猛雷鼓厄诡椪/赫普的苍响） | ACE | **直写**：switch opponent_bench choose=1 → switch own_bench choose=1（顺序两节点） |
| 能量输送PRO | CSV9C-176（H，ACE 物品，赛富豪） | ACE | 小扩展：search_deck 任意数量（up-to all，D-WP5-1 口径）+ distinct=energy_type（WP6 赤松机制）+ reveal + hand + shuffle |
| 新冲天能量 | CSV7C-203（H，ACE 能量，多龙巴鲁托） | ACE | 小扩展：provide_energy 加 args.count（2 单元）+ 条件词 holder_stage:2（2阶进化持有者 → 2 个所有属性能量） |
| 厄诡椪 碧草面具ex | CSV8C-028（H，TERA 基础 210HP，猛雷鼓厄诡椪） | TERA | 小扩展：特性 attach_energy selector own_hand 目标=self（手牌 1 基本草能量附自身）+ 抽 1；招式 30+ 新计数词 attached_energy_on_both_actives ×30 |
| 多龙巴鲁托ex | CSV8C-159（H，TERA 2阶 320HP，多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托） | TERA | 小扩展：place_damage_counters opponent_bench 任意分配（6 个指示物自由分布）；喷射头击 70 白板 |

配套机制骨架：

1. **ACE SPEC 每卡组限 1**：构筑校验已由 db 侧 `validate_deck` 承担（`battlefrontier/data/deck.py:4` 契约，本项目不重复实现）——本任务补**测试钉住**（含 2 张 ACE 的卡组装载必抛错）+ 文档核对，引擎侧零新增。
2. **TERA 规则盒结算**：卡面规则盒原文「只要这只宝可梦，处于备战区，就不会受到招式的伤害。」（52poke 太乐巴戈斯ex/米立龙ex/皮卡丘ex 词条 + EN 规则书交叉一致，2026-09-20 核对）——**备战区太晶宝可梦不受招式伤害（双方招式均含，卡面无对手限定）；仅伤害，招式效果/指示物放置不受影响**。引擎规则骨架落点（对齐 PRIZE_BY_RULE_BOX 先例），非 DSL 声明。

## 验收标准（测试清单）

设计决议（主会话定稿 2026-09-20；随落地进附录 A 🔲，gate3 核销后翻 ✅）：

- **D-027-1 TERA 备战免伤**：备战区 is_tera 宝可梦受招式伤害 → 伤害归零（双方招式；守卫落点 = 招式伤害对备战的施加路径，与 D-WP7-5 谢米守卫同点不同源——太晶是规则骨架非 DSL）。指示物放置（雪妖女/惊吓炸弹）不受免伤影响；战斗场太晶正常受伤；「已经受到的伤害」无追溯。
- **D-027-2 ACE SPEC 校验钉住**：load_deck 对含 2 张 ACE SPEC 的构筑抛错（db validate_deck 口径，含 is_ace_spec 字段断言）；池内 9 套卡组各 ≤1 ACE 实测回归。
- **D-027-3 不公印章条件**：宽口径 own_ko_during_opponent_turn（效果/指示物致昏厥也算——卡面无「招式的伤害」限定，与 D-WP7-7 精确口径区分）；条件不满足 → 整卡不可使用（训练家卡条件门既有机制）。
- **D-027-4 新冲天能量 2 单元**：provide_energy args.count（缺省 1；count=2 + types=all = 2 个彩虹单元，可抵 2 个任意符号）；条件词 holder_stage:N（holder stage==N，读栈顶 CardDef.stage）。非 2 阶持有者 → 1 个【无】（无条件块回退）。
- **D-027-5 厄诡椪 碧草之舞**：attach_energy selector own_hand（filters basic_energy+energy_草，choose=1）目标固定 self（无 choose）；目标池空（手牌无草能量）→ 特性不可用（ability_feasible 既有门控）；随后抽 1。计数词 `attached_energy_on_both_actives` = 双方战斗场附着能量总数。
- **D-027-6 多龙巴鲁托 幻影潜袭**：place_damage_counters opponent_bench + args.distribute（N 个指示物逐只挂起分配，可集中可分散——「以任意方式」）；备战空 → 效果段 no-op 伤害照算（WP4 宣言裁决）；分配致昏厥走正常 check_knockouts；**备战太晶不挡指示物**（指示物非伤害，D-027-1 反面）。
- **D-027-7 能量输送PRO**：「任意数量」= up-to all（min_choose=0，D-WP5-1 延伸）；distinct=energy_type 选择池属性互斥（D-WP6-4 机制）；reveal → 手牌 → 重洗；选 0 → no-op 重洗仍执行。

测试清单（`tests/test_primitives_t27.py` + 卡分片 `tests/test_dsl_cards_t27.py`）：

TERA 规则盒（D-027-1）：
1. 备战太晶受对手招式伤害 → 0（战斗场太晶正常受伤）；备战太晶受**己方**招式伤害 → 0
   （卡面无对手限定）；指示物放置/特殊状态等效果不受影响；备战非太晶正常受伤
2. rules-manual §1.4 补太晶条目（文档同步）+ 附录 A 决议落账

ACE SPEC（D-027-2）：
3. 含 2 张 ACE SPEC 的构筑装载抛错（violations 明细含 ACE）；含 1 张通过；
   池内 9 套装载回归全过

不公印章（D-027-3）：
4. 上一对手回合有昏厥（含效果致昏厥）→ 可打出：双方手牌回库重洗 + 自抽 5 对手抽 2；
   无昏厥 → 不可使用（行动枚举不含）

新冲天能量（D-027-4）：
5. 附着 2 阶 → 2 彩虹单元（单卡满足【火】【水】双符号费用）；附着非 2 阶 → 1【无】；
   count 缺省回归（WP8 三卡不受影响）；holder_stage 词注册/畸形 DslError

厄诡椪（D-027-5）：
6. 特性：手牌草能量 → 附着自身 + 抽 1（回合 1 次）；手牌无草能量 → 特性不可用；
   招式 30+双方战斗场能量总数×30（含 0 基准断言）

多龙巴鲁托（D-027-6）：
7. 幻影潜袭 200 + 6 指示物任意分配（集中 1 只 / 分散多只 / 致昏厥结算）；
   备战空 no-op 伤害照算；备战太晶照常收指示物（不挡）

直写 3 卡（极限腰带 / 顶尖捕捉器 / 不公印章效果段）：
8. 极限腰带 +50 仅对 ex（非 ex 不加；道具离场失效——WP7 机制卡级钉住）；
   顶尖捕捉器 gust + 自换顺序两节点全流；词表/装配校验

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归 +
`dsl-check --db` 全库全 OK + 词表同步（conditions +holder_stage:；计数词
+attached_energy_on_both_actives；provide_energy args +count；place_damage_counters
args +distribute）+ 真机冒烟（多龙黑夜魔灵/多龙喷火龙/多龙巴鲁托/喷火龙大比鸟/
猛雷鼓厄诡椪/赛富豪/赫普的苍响池内卡组）

## 实现要点

- 严守不猜纪律；词表开放字符串注册；db 只读；不改既有测试（发现断言错→报主会话）
- TERA 免伤是规则骨架（引擎），不做成 DSL 声明（对齐 PRIZE_BY_RULE_BOX 先例）
- 同名多文本严格拆分；card_ids 以装配池内印刷 + db 同文本等价类实测为准
- 规则出处标注：TERA 规则盒 = 卡面规则盒原文（52poke 词条 + EN 规则书交叉）

## 结果与遗留

- **测试**：新 30 条（primitives_t27 13 + dsl_cards_t27 17）；全量 852 绿（基线 822）
  + ruff 零告警 + dsl-check --db 全库 93 文件全 OK
- **真机冒烟 80 局 0 失败**（heuristic 4×20，`results/t27-smoke/`）：多龙巴鲁托 vs
  猛雷鼓厄诡椪 15/5；多龙喷火龙 vs 喷火龙大比鸟 10/8/平2；赛富豪 vs 多龙喷火龙 2/18；
  赫普的苍响 vs 猛雷鼓厄诡椪 13/7；幻影潜袭 distribute / 不公印章 / 顶尖捕捉器 /
  protected 落点均真实触发
- **合并复核（主会话自做，降本裁决）**：必修项 0 遗留；D-WP8-3 归正返工完成；
  顶尖捕捉器双侧备战门裁决维持现状（附录 A 候选条目）；既有测试唯一修改 =
  test_primitives_wp6.py distinct-no-split 断言演进（规格正名，主会话批准）
- **落账**：coverage-plan 7 行 pending→done（缺口 done 73 / pending 8）；
  authoring-log 批 8 七条（first_pass 7/7，gate3 待核销）；附录 A D-027-1~7 +
  顶尖捕捉器候选共 8 条 🔲 待核（D-WP8-3 条目同步修订）；PRD §5.1 task 027 段
- **遗留**：7 个卡文件 gate3 待用户核销（攒批 34 个）；附录 A 待核决议攒批；
  下一步 task 029（持续 lock/protection 体系 + 8 卡，需立项）
