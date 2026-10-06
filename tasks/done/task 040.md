# task 040：code review 遗留小包——flip_heads_count 穿透 + DSL 确定性对拍

来源：全库 code review 11 条 Important 的最后两条遗留。

## F1 flip_heads_count 挂起穿透缺环（review #4）

`dsl/interpreter.py:78-80` `ExecutionContext.flip_heads_count`（coin_flip until_tails
正面计数，primitives.py:1751 写入 / 977-983 `_eval_counter` 读取）未进挂起/恢复
穿透协议：挂起冻结块（interpreter.py:204-216 五件：flip/cost_discarded/
discarded_count/attacker_iid/step_phase）与恢复重建（164-168 四件）都没有它。
触发形态 `coin_flip(until_tails) → 任一 chooser 节点 → damage count=flip_heads_count`
恢复后 ctx.flip_heads_count=None → DslError 中断整场。当前库 2 张用卡（咕咕-
三刺击/索财灵-连掷硬币）均不可达，属潜伏崩溃点。

- **D-040-1**：flip_heads_count 进穿透协议第六件——PendingChoice 增字段
  （`flip_heads_count: int | None = None`），挂起冻结 + 恢复重建，口径与
  last_flip 完全一致（沿既有五件套的 NeedChoice→PendingChoice→run_effect
  恢复链路 plumbing）。

## F2 DSL 路径串并一致性对拍测试（review #11）

「多进程并行与串行结果逐局一致」硬规矩现有两个护栏（test_play.py:37-42 /
test_experiment.py:128-137）都跑白板局（card_effects={}），DSL 解释器参与的
路径零自动化覆盖。

- **D-040-2**：新增对拍测试——`execute_experiment` 喂真实 DSL 库（从 cards/
  选含检索+掷币+昏厥效果的卡组建测试卡组，如能量输送PRO/咕咕/索财灵），
  workers=1 vs workers=2 逐局比对 (seed, winner, is_draw, turns, events_hash)，
  口径仿 test_experiment.py:128。局数小到秒级（2-4 局）。

## 验收标准

1. F1 触发形态测试（合成 DSL：until_tails → chooser → flip_heads_count 伤害）
   修复前红、修复后绿；穿透后伤害结算正确。
2. F2 对拍测试绿，且故意引入 dict 序依赖时应能捕获（审查过测试有效性）。
3. 全量 pytest 绿 + ruff 零告警 + 闸 1 dsl-check --db 101/101 回归。
