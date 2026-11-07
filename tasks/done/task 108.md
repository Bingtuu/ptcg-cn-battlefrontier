# task 108 · 事件序观感债修复（昏厥/拿奖事件滞后冲刷）

日期：2026-11-07 · 类型：引擎观测层（零对局行为变更）· 分支：`task/t108-event-order`

## 问题（实测坐实）

`results/m13-followup-gard-zoro.db` 事件流抽查（3/3 同型）：**招式带追加效果且造成昏厥**时序为

```
attack → effect_start → knockout → take_prize → effect_primitive ×n → effect_end → promote
```

同一招式的文本效果（`effect_primitive`，如老大搬伤害指示物）在事件流里排在 `knockout`/`take_prize` **之后**，回放/报告阅读顺序违背因果（先看到昏厥再看到造成昏厥的效果）。此即 task 063/064 单列的「事件排序观感债：knockout/game_over 先于触发原语的 effect_primitive 事件」。

成因：`check_knockouts` 在招式效果执行中（`_in_effect=True`）被伤害步骤内联调用，昏厥/拿奖事件当场入 `self.events`；追加效果的 `effect_primitive` 在 DSL 后续节点才发射。

## 方案（只动事件发射层，状态结算时点一律不动）

1. 招式效果窗口内（attack completion 的效果链执行期间，`self._in_effect` 且当前链根为招式），`knockout` / `take_prize` / `game_over` 三类事件先入引擎实例级缓冲 `_ko_event_buffer`，不直接 `self.events`。
2. 冲刷点：attack completion 收尾路径（`effect_end` 之后、推进 promote/回合前）统一 flush 缓冲。
3. 挂起-恢复安全：缓冲存引擎实例（非 state），跨 NeedChoice 挂起天然保持；`_run_or_suspend` 完成路径保证冲刷（含异常完成）。
4. 终局保底：窗口内若 `_game_over` 触发（拿完奖/全场空判负），先 flush 缓冲再发 `game_over` 事件，保持因果序。
5. 窗口外一切路径（训练家/特性/场馆/排水触发器等）发射行为零变化。

## 硬门（预注册）

1. **零对局行为变更**：状态轨迹等价——除缓冲三 kind 的 seq 重排外，事件多重集不变；规则语义零变化（拿奖/换上/胜负判定时点维持 task 026 WP2、D-WP2-1、task 064 定案）。
2. **确定性保持**：新序下 events_hash 串行=并行（抽查 100 局）；同种子重放逐局一致。
3. 不动 DSL / Agent / 启发式；不加词表。
4. TDD 红先行：新测试断言新序（`effect_primitive` 先于 `knockout`）；存量断言旧序的测试按「语义评估」更新并逐条注明。
5. 不回改历史结果包（m13 哈希为历史 artifact）；replay render 无需改（读序即新序）。

## 开发期实证修正（2026-11-07）

- **排水内层帧漏洞**：初版只在 impl 完成段（effect_end 后、排水前）设一个冲刷点；replay 抽查（gard-zoro 种子 300003）实证**排水内层帧**（仙人掌式反伤等以 `completion="attack"` 发动的触发帧，深度 2）产生的昏厥事件两块全丢——外层完成段冲刷点在其之前已过，内层完成段深度 2 不冲。存量 1703 测试全绿但无覆盖（该路径靠 replay 抽查才暴露）。
- **修复**：双关口——(a) impl 完成段深度 1 冲刷（排水前，本帧窗口昏厥块）；(b) 包装层 finally 深度 0 且未挂起（`pending_choice is None`）冲刷（补冲排水内层帧）。挂起两关口都不冲，缓冲跨挂起保持。
- **回归测试**：`test_drain_inner_frame_ko_events_not_lost`（沙铃仙人掌反伤双昏厥）；变异检查（去掉关口 b）测试如期 FAIL。
- **replay 抽查 PASS**（`.kimi-code/t108_replay_check.py`，gard-zoro 种子 300000..300019）：事件多重集 20/20、终局 20/20、重排生效 20/20、串行 events_hash 20/20。

## 验收

- 红测先行（至少：窗口内昏厥新序测试、窗口外不变测试、挂起-恢复冲刷测试、game_over 保底顺序测试）。
- 全量 pytest 绿 + ruff 零告警。
- 指定 replay 抽查：gard-zoro 同种子 20 局，逐局事件多重集与 main 基线一致、仅 seq 重排符合规格。

## 明确不做

不改拿奖/换上/胜负判定的状态时点；不动 `pending_ko_triggers` 排水语义；不碰报告层；不重跑 m13 矩阵（非完成条件）。
