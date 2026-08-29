# task 012 · 招式效果框架（on_attack）+ 计数表达式/变量伤害 + clear_status

- 状态：完成（2026-08-29）
- 关联：PRD §5.1（DSL schema，本次补 `Effect.attack` 绑定字段，已同步 PRD）/§5.3（原语先行）/§6.2，里程碑 M2；输入 = task 009 chooser、task 011 特性框架

## 目标

落地招式附加效果框架：`Effect.attack` 绑定具体招式，被绑定招式的伤害与效果全部经
DSL 结算（`AttackDef.damage` 退为装载/展示数据）；`damage` 原语支持固定值与变量公式
（base + 计数×per / 计数×per），计数表达式求值落地（counters 词表）；目标可选
战斗场或对手任意宝可梦（chooser）；弱点 ×2 / 抗性 -30 仅对战斗场目标生效
（rules-manual §6，备战不计算是通用规则而非卡面特例）。覆盖沙奈朵卡组 6 张
效果招式卡：残忍箭矢 / 凶暴吼叫 / 精神强念 / 满月回旋曲 / 气球炸弹 / 奇迹之力。

## 验收标准（测试清单）

- [x] 枚举：damage=None 但有 on_attack 绑定的招式可枚举（能量满足前提）；无绑定且无伤害的纯效果招式不枚举
- [x] 变量伤害：精神强念 60+对手战斗场附着能量×20；满月回旋曲 20+双方备战×20；气球炸弹 自身指示物×30（计数=伤害/10）
- [x] 弱点/抗性：变量伤害对战斗场目标照常 ×2/-30；对备战目标不计算（残忍箭矢/凶暴吼叫打备战验证）
- [x] 目标选择：selector=opponent_pokemon_any 经 chooser 选目标（战斗场+备战全枚举），选备战目标伤害落备战
- [x] damage_counters_on_target：凶暴吼叫按所选目标身上指示物×20
- [x] 奇迹之力：190 落对手战斗场 + clear_status 清自身全部特殊状态
- [x] DSL 攻击后回合正常结束；攻击致昏厥 → promote/终局不被覆盖（completion="attack"）
- [x] 计数求值：六个 counters 词（all 非数值 DslError；未知词 DslError 不猜）
- [x] 定义库：cards/ 增 吉雉鸡ex/吼叫尾/奇鲁莉安/莉莉艾的皮皮ex/飘飘球 五卡 + 沙奈朵ex 补奇迹之力（注释引用 text_raw 原文）
- [x] play_game 含效果招式卡组同种子 hash 一致
- [x] pytest 全绿 + ruff 零告警

## 实现要点

- `Effect.attack: str | None`（schema 补位，loader 不校验招式名存在性——绑定解析在引擎枚举/执行时，无匹配招式 = DslError）
- 引擎：`_main_actions` 攻击枚举条件改为「能量满足 且（damage 非空 或 有 on_attack 绑定）」；`_do_attack` 有绑定时走 `_run_or_suspend(completion="attack")`，完成且无昏厥分支时 `_begin_turn(对手)`
- 原语 `damage`：selector=opponent_active（自动目标）/ opponent_pokemon_any（choose=1 挂起）；公式 args：`{amount}` 固定 / `{base, per, op:"+"}` / `{per, op:"×"}` + count=计数词；弱抗由引擎规则骨架结算（仅战斗场目标）
- 计数求值 `_eval_counter`（primitives 内）：own/opponent_remaining_prizes、damage_counters_on_self（source 场上单体）、damage_counters_on_target、attached_energy_on_opponent_active、bench_count_both
- chooser：resolve_pool 增 `opponent` 参数支持 `opponent_pokemon_any` 池（对手场上维度，公开信息无需揭示）
- 原语 `clear_status`（selector=self：清 source 在场单体的 conditions）
-  Deferred（归 task 013+）：精神幻觉（混乱）、基因侵入（copy_attack）、愿增猿特性转伤

## 结果与遗留

**结果**（2026-08-29）：

- `Effect.attack` 绑定字段落地（PRD §5.1 已同步）：on_attack 绑定的招式伤害与效果全部
  经 DSL 结算，`AttackDef.damage` 仅作装载/展示数据（奇迹之力 190 不重复结算有测试锁定）。
- 引擎：攻击枚举 = 能量满足 且（damage 非空 或 on_attack 绑定）；`_do_attack` DSL 路径
  走 `_run_or_suspend(completion="attack")`，完成后推进对手回合，昏厥进 promote/终局不覆盖。
- 原语 `damage`（opponent_active 自动 / opponent_pokemon_any choose=1 挂起；公式
  amount 固定 / base+per×n / per×n；弱抗由引擎骨架 `_weakness_resistance` 结算、
  仅战斗场目标）+ `clear_status`（self）；计数求值 `_eval_counter` 六词
  （own/opponent_remaining_prizes、damage_counters_on_self/target、
  attached_energy_on_opponent_active、bench_count_both），非数值词 DslError。
- chooser：`resolve_pool` 增 opponent 参数，新池 `opponent_pokemon_any`（公开信息不揭示）。
- 定义库 11 卡：新增 吉雉鸡ex/吼叫尾/奇鲁莉安/莉莉艾的皮皮ex/飘飘球 + 沙奈朵ex 补
  奇迹之力（注释引用 text_raw 原文）。
- TDD：12 新测试红→绿（首红 = schema extra_forbidden）；全量 153 绿 + ruff 零告警；
  含效果招式卡组 play_game 同种子 hash 一致。

**遗留**：

- 精神幻觉（混乱状态，含 D1 决议的攻击掷币结算）、基因侵入（copy_attack）归 task 013+。
- 愿增猿特性（move_damage_counters 选择式转伤）、化危为吉（跨回合触发）、
  妖精领域（passive_static 弱点改写）归 task 013+。
- 道具 / 竞技场骨架（勇气护符 / 招式学习器 进化 / 深钵镇）归 task 014。
