# task 017 · M2 收口批：三特性 + 基因侵入 copy + 竞技场骨架 + 支援者两枚

- 状态：已完成（2026-08-29）
- 关联：PRD §5.3/§6.2，里程碑 M2 收口（沙奈朵卡组 mik_moe:644634 全覆盖）
- 输入：task 011 特性框架、task 013 混乱、task 014 物品批、task 015/016 道具与进化；
  `GameState.stadium` 字段 task 003 已预留

## 目标

沙奈朵卡组剩余全部机制落地，M2 覆盖收口：

1. **化危为吉**（吉雉鸡ex 特性，CSV8C-135）：「在上一个对手的回合，如果自己的宝可梦
   【昏厥】的话，则在自己的回合可以使用1次。抽3张。这个回合已使用其他「化危为吉」
   则无法使用。」→ 跨回合 KO 标记 `PlayerState.own_ko_during_opponent_turn`
   （对手回合内我方宝可梦昏厥置位，我方回合结束清除）+ condition 词
   `own_ko_during_opponent_turn`；限次复用 once_per_turn_shared（task 011 已有）。
2. **亢奋脑力**（愿增猿 特性，CSV8C-094）：「附着了【恶】能量则可用1次。选自己场上
   1只宝可梦身上最多3个伤害指示物，转放于对手场上1只宝可梦。」→ 参数化 condition
   前缀 `holder_has_energy:<属性>` + `move_damage_counters` 原语（词表已有词）。
   **降级决策（记 rules-reference 附录 A）**：转放数量 = min(3, 来源指示物数) 全转——
   chooser 协议只支持 iid 集合选择，数值选择暂不建模；「最多3个」的少转分支对 AI
   几乎无收益，语义偏差已记录。
3. **妖精领域**（莉莉艾的皮皮ex 特性，CSV10C-082）：「只要在场上，对手场上所有【龙】
   宝可梦的弱点全部变为【超】。」→ 声明式词 `modify_weakness`（词表 actions 补，
   引擎读声明）+ `GameEngine._effective_weakness(attacker, defender)`：攻方场上有
   领域声明且防守栈顶属性命中 target_type → 弱点视为 becomes（含龙本无弱点的赋予
   情形）。弱点抗性仍仅战斗场结算（贯穿规则不变）。
4. **基因侵入**（梦幻ex 招式，151C-151，cost 无×3）：「选择对手战斗宝可梦所拥有的
   1个招式，作为这个招式使用。」→ `copy_attack` 原语（词表已有词）：chooser 池
   `opponent_active_attack`（selectors 词表 task 005 预留词；池元素 = 招式，pool_iids
   语义为该池内 = 招式索引）。复制结算：对手卡有该招式 on_attack DSL 绑定 → 以我方
   视角跑该效果块；无绑定且有伤害 → 白板伤害（弱点抗性按我方属性结算）；两者皆无
   的招式不进池。被复制招式不需再付能量（原文「作为这个招式使用」）。
5. **竞技场骨架 + 深钵镇**（CSV2C-127）：`play_stadium` 行动（手牌竞技场每回合限 1 张
   `stadium_played_this_turn`；与场上同名不可打出；旧竞技场进其主人弃牌区）+
   `use_stadium` 行动（stadium_grant 触发器赋予的每方每回合 1 次行动，
   `stadium_used_this_turn`；效果以当前玩家为 ctx 跑 DSL）。深钵镇：检索【基础】
   宝可梦（除拥有规则的宝可梦外）放备战区 + 洗牌 → 新过滤器 `basic_pokemon_no_rule`。
6. **奇树**（CSV3C-123，支援者）：「双方各将手牌反面朝上重洗放回牌库下方，各抽与
   自身剩余奖赏卡相同数量。」→ `hand_to_deck_bottom` 原语（词表已有词，手牌
   rng.shuffle 后放库底，支持 own_hand/opponent_hand）+ `draw` 原语扩展
   （str 计数表达式经 _eval_counter 求值 + selector opponent_deck）。
7. **派帕**（CSV1C-123，支援者）：检索「物品」「宝可梦道具」各 1 张入手 + 洗牌——
   现有原语组合（两段 search_deck + shuffle_deck），纯 YAML 落库。
8. **特性枚举补 condition 判定**：ability_manual 枚举增加 condition_met（mon=持有者）
   ——化危为吉/亢奋脑力的前置（task 011 枚举只查 limit + 可行性门）。

拉鲁拉丝（CSV2C-053）精神射击为白板伤害招式（装载层已有），无需 DSL 入库。

## 验收标准（测试清单）

- [x] 化危为吉：对手回合内我方宝可梦昏厥 → 我方回合特性可枚举（抽 3）；未昏厥/
  昏厥发生在自己回合 → 不可枚举；我方回合结束后标记清除（隔回合不可用）；
  once_per_turn_shared 共享限次生效
- [x] 亢奋脑力：附着恶能量才枚举；两段选择（己方有指示物的宝可梦 → 对手场上 1 只）；
  转放 min(3, 来源) 个指示物（伤害 -30/+30 刻度）；无指示物来源不枚举
- [x] 妖精领域：皮皮在场时攻方打对手龙 active 按弱点超 ×2（龙卡面无弱点也生效）；
  皮皮不在场/防守非龙 → 原逻辑；DSL damage 原语与白板攻击两处一致
- [x] 基因侵入：枚举对手 active 可复制招式（有 DSL 绑定或有伤害）；复制白板伤害按
  梦幻属性结算弱点；复制 DSL 招式以我方视角结算；被复制招式不付能量
- [x] 深钵镇：play_stadium 枚举/流程/每回合限 1/同名不可/旧场进原主人弃牌区；
  use_stadium 双方每回合各 1 次、检索基础（除规则盒）放备战区 + 洗牌、
  备战满不枚举
- [x] 奇树：双方手牌洗回库底 + 各抽=剩余奖赏数；牌库不足抽完即止
- [x] 派帕：两段检索（物品/道具各 ≤1）入手 + 洗牌
- [x] 特性 condition 门：ability_manual 枚举过 condition_met（未知词 DslError 不猜）
- [x] 定义库 23 卡；沙奈朵卡组真实装载零告警 + play_game 同种子 hash 一致
- [x] pytest 全绿 + ruff 零告警

## 实现要点

- state：`PlayerState.own_ko_during_opponent_turn` / `stadium_played_this_turn` /
  `stadium_used_this_turn`；VisibleSelfState 同步三个标记；`_begin_turn` 重置回合标记
- core：`_knockout_one` 置位 KO 标记（owner != current_player）；回合结束四条路径
  合并为 `_on_turn_end(player)`（道具弃置 + KO 标记清除）；`play_stadium` /
  `use_stadium` 枚举与 `_do_play_stadium` / `_do_use_stadium`；`_effective_weakness`
  供 `_attack_damage` 与 damage 原语共用；ability 枚举过 condition_met
- chooser：`holder_has_energy:<属性>` 参数化 condition；`own_ko_during_opponent_turn`
  注册；`basic_pokemon_no_rule` 卡过滤器；`has_damage_counters` 场上过滤器；
  `opponent_active_attack` 池（pool_iids = 招式索引，build_pending 分支处理）
- primitives：`move_damage_counters`（两段式，全转 min(max_counters, 来源)）；
  `copy_attack`（选招式 → 我方视角结算）；`hand_to_deck_bottom`（own/opponent）；
  `draw` 扩展 str 计数表达式 + opponent_deck
- 词表：actions 补 `modify_weakness`（声明式）；selectors 补 `opponent_hand` /
  `opponent_deck`（如缺）；filters 不校验（开放字符串纪律不变）
- DSL 六卡入库/补全：吉雉鸡ex +化危为吉、愿增猿 +亢奋脑力、莉莉艾的皮皮ex +妖精领域、
  梦幻ex +基因侵入、深钵镇.yml、奇树.yml、派帕.yml（20 → 23 卡）

## 结果与遗留

- 结果：24 个新测试（20 首红）；全量 219 通过、ruff 零告警；定义库 23 卡，
  沙奈朵卡组（mik_moe:644634）DSL 全覆盖（白板与能量无需 DSL）
- 真实数据冒烟：60 张装载零告警；两 seeds 整局同种子 hash 一致；
  seed 7 中 use_stadium 实际发动（深钵镇检索）
- 实现落点：
  - `state.py`：own_ko_during_opponent_turn / stadium_played/used_this_turn +
    GameState.stadium_owner + VisibleSelfState 同步
  - `core.py`：`_on_turn_end` 合并四条回合结束路径（道具弃置 + KO 标记清除）；
    `_knockout_one` 置位跨回合标记；`_effective_weakness`（妖精领域声明式弱点
    改写，白板与 DSL damage 两路径共用）；play_stadium/use_stadium 行动；
    ability_manual 枚举过 condition_met
  - `chooser.py`：condition 参数化前缀 holder_has_energy:<属性> + 注册词
    own_ko_during_opponent_turn；过滤器 basic_pokemon_no_rule / has_damage_counters；
    opponent_active_attack 招式维度池（pool_iids = 招式索引，build_pending 兼容 int）；
    ability_feasible 增 move_damage_counters 门
  - `primitives.py`：move_damage_counters / copy_attack / hand_to_deck_bottom 注册；
    draw 扩展 str 计数表达式 + opponent_deck
- 决策记录（进 rules-reference 附录 A 候选）：
  - 亢奋脑力「最多3个」→ min(3, 来源) 全转（chooser 不建模数值选择）
  - copy_attack 嵌套挂起（被复制招式自身含运行时选择）= 显式 DslError 不猜
  - 旧竞技场进 stadium_owner 弃牌区（GameState 增放置方标记）
- 既有测试口径修正 4 处（实现推进引起，非让步）：愿增猿 effects[0] 变特性
  （按 attack 查找替代位置索引）；「未实现原语」测试改用 reveal 锁定；
  draw 计数表达式测试从「不支持」翻转为支持断言；库总数断言移交最新任务
- 遗留：chooser 嵌套游标（copy 含选择招式）/ 数值选择建模（最多 N 个）/
  宝可梦检查（中毒灼伤回合间）/ 同时昏厥结算顺序 等归 M3+ 或按目标卡组需要
