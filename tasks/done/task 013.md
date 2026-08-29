# task 013 · 混乱状态（D1 决议落地）+ apply_status 原语 + 愿增猿「精神幻觉」

- 状态：完成（2026-08-29）
- 关联：rules-reference 附录 A（D1 混乱决议，2026-08-28 用户核定）/ rules-manual §4 特殊状态，里程碑 M2

## 目标

落地混乱状态全链路：施加（`apply_status` 原语）→ 攻击时掷币判定（D1 决议：
正面招式正常发动且混乱不解除；反面招式完全失败 + 自身 3 个伤害指示物）→
自我昏厥的回合权归属（攻击方换上后回合权给对手，攻击已消耗）。
愿增猿「精神幻觉」（60 伤 + 令对手战斗宝可梦混乱）入库。

## 验收标准（测试清单）

- [x] 愿增猿「精神幻觉」e2e：60 伤害落对手战斗场 + 对手战斗宝可梦陷入混乱（apply_status）
- [x] 混乱攻击掷币正面：招式正常结算（伤害/DSL 效果照常），混乱状态**不解除**
- [x] 掷币反面：招式完全失败（无伤害、DSL 效果一个不执行，无 effect_primitive 事件）+ 自身 +30 伤害（3 指示物），回合正常结束
- [x] 反面自我昏厥：攻击方进 promote 换上，换上后**回合权给对手**（`GameState.turn_after_promote`；普通昏厥换上维持换上方回合不变）
- [x] 混乱置于 `_do_attack` 入口：白板招式与 DSL 招式同等受检；能量不满足的招式本就不可枚举（无退款语义）
- [x] 撤退/进化清除混乱（复用既有 conditions 清除，回归测试锁定）
- [x] `apply_status`：status 词对齐 SpecialCondition 枚举，未知词 DslError（不猜）；selector 本期仅 opponent_active
- [x] 定义库：`cards/愿增猿.yml`（精神幻觉；特性亢奋脑力注释标注归 task 014+）
- [x] play_game 含混乱卡组同种子 hash 一致（掷币走统一随机源）
- [x] pytest 全绿 + ruff 零告警

## 实现要点

- `_do_attack` 入口：攻击方战斗宝可梦 `conditions` 含 CONFUSED → `rng.flip_coin()`，发
  `confusion_check` 事件（result=heads/tails）；tails → 自身 +30 → check_knockouts →
  按阶段收尾（game_over / promote+turn_after_promote / _begin_turn(对手)）
- `GameState.turn_after_promote: int | None = None`：自我昏厥时攻击方换上后回合权给对手；
  `_do_promote` 读后清零，缺省维持换上方回合（既有行为不变）
- `apply_status` 原语：args.status → SpecialCondition 枚举校验；opponent_active 施加
- 混乱掷币消耗统一随机源（种子确定性硬规矩）

## 结果与遗留

**结果**（2026-08-29）：

- 混乱全链路：`_do_attack` 入口掷币（`confusion_check` 事件 heads/tails）——正面正常
  结算不解除；反面招式完全失败（白板/DSL 同等，无 effect_primitive）+ 自身 +30 →
  check_knockouts；白板与 DSL 招式同检。
- 自我昏厥回合权：`GameState.turn_after_promote`（默认 None = 换上方回合，既有行为
  不变；混乱反面自我昏厥置为对手，`_do_promote` 读后清零）。
- `apply_status` 原语：args.status 对齐 SpecialCondition 枚举（未知词 DslError）；
  opponent_active 施加；效果序列中前序节点已致昏厥时空结算（目标随昏厥进弃牌区）。
- `cards/愿增猿.yml`（精神幻觉 = 60 伤 + 混乱）入库，定义库 12 卡。
- TDD：9 新测试（7 首红；撤退清混乱等 2 条即时通过=既有机制回归锁定）；
  全量 162 绿 + ruff 零告警；含混乱卡组 play_game 同种子 hash 一致。

**遗留**：

- 宝可梦检查（中毒/灼伤回合间结算）与睡眠/麻痹——卡组无来源卡，随覆盖扩展落地。
- 愿增猿特性「亢奋脑力」（move_damage_counters 选择式转伤）、化危为吉（跨回合触发）、
  妖精领域（弱点改写）、基因侵入（copy_attack）归 task 014+；道具/竞技场骨架同。
