# task 015 · 宝可梦道具骨架 + 勇气护符（passive HP）+ 招式学习器框架

- 状态：已完成（2026-08-29）
- 关联：PRD §5.3/§6.2，里程碑 M2；rules-manual §5（道具：每只宝可梦限 1 个）/§8（昏厥判定 HP）
- 输入：task 011 特性框架、task 012 on_attack、task 014 物品批

## 目标

落地宝可梦道具（Pokémon Tool）骨架：`attach_tool` 主阶段行动（每只限 1 个、
不限次）、`InPlayPokemon.attached_tool` 状态位、昏厥随叠进弃牌区；
passive_static 首个常驻修正——勇气护符「基础宝可梦最大 HP+50」，effective_hp
贯穿 check_knockouts 与 would_survive_20 过滤器；招式学习器 进化的
「回合结束弃置」机制落地（授予招式的 on_attack 效果归 task 016，与神奇糖果
同属 evolve 原语主题）。

## 验收标准（测试清单）

- [x] `attach_tool` 枚举：手牌道具 × 场上无道具宝可梦各一条；已持有道具的宝可梦不可再挂；非法 attach_tool 抛 IllegalActionError
- [x] attach 流程：手牌 → attached_tool；事件可回放
- [x] 勇气护符：基础宝可梦 HP+50 生效于 KO 判定（110 伤对 70+50 存活；120 昏厥）；进化后（顶栈非基础）加成立即失效
- [x] 精神拥抱 would_survive_20 守卫按 effective_hp 判定（护符持有人不再被误排）
- [x] 昏厥整叠：attached_tool 随进化链+能量一起进弃牌区
- [x] 招式学习器：自己回合结束（end_turn / 攻击后）弃置入弃牌区；对手回合结束不弃
- [x] 授予招式枚举纪律：无 on_attack 绑定的授予招式不枚举（本期锁定 defer，task 016 解锁）
- [x] 定义库：cards/ 勇气护符.yml + 招式学习器 进化.yml 入库（注释引用 text_raw 原文），共 19 卡
- [x] play_game 含道具卡组同种子 hash 一致
- [x] pytest 全绿 + ruff 零告警

## 实现要点

- `InPlayPokemon.attached_tool: CardInstance | None = None`；`_knockout_one` 整叠含道具
- `_main_actions` / `_do_attach_tool`：trainer_subtype == "宝可梦道具"，无 DSL 文档也可挂（attach 是规则行动）
- `GameEngine._effective_hp(mon, player)`：base hp + 道具 passive_static 的 modify_hp 求和；
  condition 注册表增 `holder_is_basic`（顶栈 stage==0），`condition_met` 增 mon 参数
- check_knockouts 与 chooser in-play 过滤器（would_survive_20）改走 effective_hp
  （resolve_pool/build_pending/ability_feasible 透传 hp_of；ability_feasible 签名改 (effect, engine, player)）
- `_discard_turn_end_tools(player)`：grant_attack args.discard_at_turn_end 的道具在
  自己回合结束的所有路径（end_turn / 白板攻击 / DSL 攻击 / 混乱反面）统一弃置
- DSL：`{action: modify_hp, args: {amount: 50}}`（condition holder_is_basic）；
  `{action: grant_attack, args: {attack: 进化, discard_at_turn_end: true}}`
  （vocab actions 段补两词； modify_hp/grant_attack 为声明式修饰，解释器不执行、引擎读声明）

## 结果与遗留

- 结果：11 个新测试全绿；全量 183 通过、ruff 零告警；定义库 19 卡
- 测试修正两处（规则口径，非实现让步）：①精神拥抱守卫测试目标改用超属性基础
  （拉鲁拉丝）——护符限【基础】，沙奈朵ex（stage 2）本就不加成；②学习器攻击
  路径测试补 1 能量——「打击」cost=(无,) 无色需实卡抵
- 实现落点：
  - `state.py`：`InPlayPokemon.attached_tool`
  - `core.py`：`_effective_hp` / `_do_attach_tool` / `_discard_turn_end_tools`；
    check_knockouts 两处 HP 判定走有效 HP；回合末弃置覆盖 end_turn / 白板攻击 /
    DSL 攻击（_run_or_suspend completion="attack"）/ 混乱反面四条路径
  - `chooser.py`：`condition_met` 增 mon 参数（注册表增 holder_is_basic）；
    resolve_pool / build_pending / ability_feasible 透传 hp_of（ability_feasible
    签名改 (effect, engine, player)）；would_survive_20 按有效 HP
  - 词表：actions 补 modify_hp / grant_attack（声明式，引擎读声明，解释器不执行）
- 遗留：
  - 学习器「进化」招式 on_attack（evolve 原语：从牌库进化最多 2 只备战）归 task 016，
    与神奇糖果（跳阶进化）同批；本期无绑定的授予招式不枚举（测试锁定）
  - 竞技场骨架（深钵镇 stadium_grant）、剩余特性三枚（化危为吉跨回合 / 亢奋脑力
    转伤 / 妖精领域弱点改写）、基因侵入 copy 归 task 016/017
