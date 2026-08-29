# task 011 · 特性框架（ability_manual）+ 沙奈朵ex/梦幻ex 特性落地

- 状态：完成（2026-08-29）
- 关联：PRD §5.2（chooser）/§5.3（原语先行）/§6.2（合法行动枚举），里程碑 M2；输入 = task 009 chooser 机制、task 010 定义库

## 目标

落地特性（Ability）主动发动框架：引擎枚举 `use_ability` 合法行动、三种限次
（once_per_turn / once_per_turn_shared / unlimited）强制、可行性门（不猜）；
chooser 协议扩展为**同节点两段式选择**（carry 传递中间结果），落地沙奈朵卡组
核心引擎特性——沙奈朵ex「精神拥抱」（弃牌区基本超能量 → 附着自己场上超宝可梦
+ 放 2 伤害指示物，会昏厥的目标不可选）与梦幻ex「再起动」（抽牌至手牌 3 张）。

## 验收标准（测试清单）

- [x] 枚举：场上宝可梦有 ability_manual DSL 文档 → main 阶段枚举 `use_ability`（iid=栈顶）；无文档不枚举；非当前方/非 main 不枚举；非法 use_ability 抛 IllegalActionError
- [x] 限次：once_per_turn 用后本回合不再枚举、下回合恢复；once_per_turn_shared 同名共享（stub 卡验证）；unlimited 不限制
- [x] 梦幻ex「再起动」e2e：手牌 <3 抽至 3；手牌 ≥3 合法空结算；事件流 effect_start/primitive/end 完整
- [x] 沙奈朵ex「精神拥抱」e2e：选弃牌区基本超能量 → 选自己场上超宝可梦（两段挂起）→ 附着 + 目标 damage+20；会昏厥目标（damage+20≥hp）不入目标池
- [x] 可行性门：弃牌区无基本超能量 / 无合法目标 → 不枚举；门未覆盖的原语形式 → DslError（不猜）
- [x] 可见视图：abilities_used 回合标记入 VisibleSelfState（PRD §6.3 纪律）；回合开始重置
- [x] 定义库：`cards/沙奈朵ex.yml` / `cards/梦幻ex.yml` 入库（注释引用 text_raw 原文），load_card_dir 覆盖六卡
- [x] play_game 含特性卡组同种子 hash 一致（选择不消耗随机源纪律回归）
- [x] pytest 全绿 + ruff 零告警

## 实现要点

- `Action(kind="use_ability", iid=栈顶 iid)`；`_do_use_ability` 复用 `_run_or_suspend`（完成不收尾弃置——加完成模式参数，trainer 才进弃牌区）
- `PlayerState` 增 `abilities_used_this_turn: frozenset[int]`（iid）+ `shared_abilities_used_this_turn: frozenset[str]`（name_group），`_begin_turn` 每回合重置；VisibleSelfState 同步
- chooser 协议扩展：`NeedChoice.carry` / `PendingChoice.payload`（中间选择随挂起冻结，恢复时经 ctx 传回原语）；新增池 `own_pokemon_in_play`（InPlayPokemon 维度，iid=栈顶）+ 过滤器 `energy_超` / `pokemon_超` / `would_survive_20`（未知词 DslError 不变）
- 新原语 `attach_energy`（selector=own_discard、destination=attach、args.target_filters / args.damage_counters；两段挂起：先选能量后选目标；完成后 check_knockouts）
- `draw` 原语扩展 `args.until_hand=N`（抽至手牌 N 张，超出空结算）
- `ability_feasible(effect, p)` 可行性门（attach_energy 双侧池非空；draw 恒可行；未知原语 DslError）
- 条件（condition）本期仍只记录不强制（两特性无需前置条件；精神拥抱的「会昏厥不可选」落在目标过滤器）

## 结果与遗留

**结果**（2026-08-29）：

- 特性框架：`use_ability` 行动（iid=栈顶）枚举 + `_do_use_ability`；三种限次强制
  （once_per_turn 按 iid / once_per_turn_shared 按卡名 / unlimited），未声明 limit 的
  ability_manual 文档 DslError（不猜）；`PlayerState.abilities_used_this_turn` /
  `shared_abilities_used_this_turn` 回合开始重置、VisibleSelfState 同步。
- chooser 协议扩展：同节点两段式选择（`NeedChoice.carry` / `PendingChoice.payload` /
  `ctx.carry` 链）；新增池 `own_pokemon_in_play`（InPlayPokemon 维度）+ 过滤器
  `energy_超` / `pokemon_超` / `would_survive_20`；`ability_feasible` 可行性门。
- 新原语 `attach_energy`（own_discard → 场上宝可梦，args.target_filters /
  damage_counters，完成后 check_knockouts）；`draw` 扩展 `args.until_hand=N`。
- `_run_or_suspend` 完成模式（trainer 收尾弃置 / ability 不弃置），效果内触发
  换上/终局时不覆盖其阶段；`PendingChoice.completion` 随挂起冻结。
- `cards/沙奈朵ex.yml`（精神拥抱）/ `cards/梦幻ex.yml`（再起动）入库，定义库六卡。
- TDD：14 新测试红→绿（11 首红，3 条非法行动类即时通过）；全量 141 绿 + ruff 零告警；
  含特性卡组 play_game 同种子 hash 一致。

**遗留**：

- 化危为吉（跨回合「上回合自己宝可梦昏厥」触发条件）、亢奋脑力（move_damage_counters
  选择式转伤）、妖精领域（passive_static 弱点改写）归 task 012+；特性 condition
  字段本期仍只记录不强制（两落地特性无前置条件）。
- 招式附加效果（on_attack：奇迹之力恢复状态 / 混乱 / 变量伤害公式 / 基因侵入 copy）
  归 task 012+；道具 / 竞技场骨架归 task 012+。
