# task 014 · 物品批：大地容器 / 秘密箱 / 厉害钓竿 / 反击捕捉器 / 能量转移

- 状态：完成（2026-08-29）
- 关联：PRD §5.2/§5.3，里程碑 M2；输入 = task 009 chooser、task 011 carry 两段式、task 012 on_attack

## 目标

沙奈朵卡组剩余五张物品卡全部落 DSL 定义库并 e2e 可用。四张复用/扩展现有原语，
两张各带一个新原语：`switch`（反击捕捉器 gust）与 `move_energy`（能量转移两段式）。
配套框架扩展：trainer 子类过滤器四词、condition 条件门首个求值（奖赏比多才可使用）、
recover 去向 deck + up-to、chooser exclude_iids（转附目标排除来源）。

## 验收标准（测试清单）

- [x] 大地容器 e2e：cost 弃 1 手牌 → 检索 ≤2 张基本能量入手（可不找）→ 洗牌
- [x] 秘密箱（ACE SPEC）e2e：cost 弃 3 手牌 → 物品/道具/支援者/竞技场各 ≤1 张顺序检索入手 → 洗牌；子类过滤器互不混淆
- [x] 厉害钓竿 e2e：弃牌区宝可梦+基本能量合计 ≤3 张（可选更少）回牌库 → 洗牌；训练家被过滤
- [x] 反击捕捉器：condition `own_prizes_more_than_opponent` 求值——不满足不枚举（「只有…才可使用」）；满足时选对手备战 1 只与其战斗场互换；被换下的战斗宝可梦特殊状态清除（回备战区规则）；对手无备战不枚举（无效果不可使用）
- [x] 能量转移 e2e：两段式——选自己场上附着的 1 个基本能量 → 转附自己其他宝可梦（目标池排除来源）；伤害/其他能量不受影响；无已附着基本能量不枚举
- [x] condition 未知词 / 可行性门未覆盖形式 → DslError（不猜）
- [x] 定义库：cards/ 五卡入库（注释引用 text_raw 原文），load_card_dir 共 17 卡
- [x] play_game 含本批物品卡组同种子 hash 一致
- [x] pytest 全绿 + ruff 零告警

## 实现要点

- chooser：`_match_one` 增 `trainer_item/trainer_tool/trainer_supporter/trainer_stadium`；
  新池 `own_attached_energy`（自己场上附着能量维度）与 `opponent_bench`（对手备战维度）；
  `NeedChoice.exclude_iids`（build_pending 冻结时剔除）；`condition_met(condition, engine, player)`
  注册表求值（None→True，未知词 DslError）；`playable_feasible` 增 opponent 参数 +
  switch（对手备战空不可用）/ move_energy（无已附着基本能量不可用）落点门
- 原语：`switch`（selector=opponent_bench choose=1，换下战斗场清状态）；
  `move_energy`（两段式 carry；目标排除来源）；`recover_from_discard` 增
  destination=deck（up-to，min_choose=0）
- 引擎：训练家卡枚举在可行性门前先过 `condition_met`
- 神奇糖果（evolve 跳阶原语）归 task 015+；道具/竞技场骨架归 task 015/016

## 结果与遗留

**结果**（2026-08-29）：

- 五物品全部 e2e 落地：大地容器（弃 1 → 检索 ≤2 基本能量）、秘密箱（弃 3 → 四类
  训练家各 ≤1 顺序检索，只洗一次）、厉害钓竿（≤3 回牌库 up-to）、反击捕捉器
  （condition 门 + gust 互换 + 换下清状态）、能量转移（两段式转附，目标排除来源）。
- chooser 扩展：trainer 子类过滤器四词（trainer_item/tool/supporter/stadium）；
  新池 own_attached_energy / opponent_bench；`NeedChoice.exclude_iids`；
  `condition_met` 注册表（首个词 own_prizes_more_than_opponent，未知词 DslError）；
  `playable_feasible` 增 opponent 参数与 switch/move_energy 落点门（无效果不可使用）。
- 原语：`switch`（opponent_bench gust）/ `move_energy`（两段式 carry + exclude）/
  `recover_from_discard` 增 destination=deck（up-to min=0）。
- 词表：selectors 段补 `own_attached_energy`（开放词表纪律，零代码新词）。
- 定义库 17 卡。TDD：10 新测试（8 首红；大地容器纯复用即时通过；测试期修正一处
  附着能量 iid 公式笔误 9000→9010）；全量 172 绿 + ruff 零告警；含物品卡组
  play_game 同种子 hash 一致。

**遗留**：

- 神奇糖果（evolve 跳阶原语）、道具骨架（勇气护符 passive HP+50 / 招式学习器 进化
  授予招式+回合末弃置）、竞技场骨架（深钵镇 stadium_grant）归 task 015/016。
- 剩余特性三枚（化危为吉跨回合触发 / 亢奋脑力选择式转伤 / 妖精领域弱点改写）与
  基因侵入（copy_attack）归 task 016+。
