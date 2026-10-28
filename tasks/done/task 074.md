# task 074 · 精简对局日志 B

- 状态：完成
- 关联：`docs/superpowers/specs/2026-10-28-post-071-roadmap-design.md` §2.2 / §3 074；计划 `docs/superpowers/plans/2026-10-28-task-074-lean-battle-log.md`

## 目标

复用已落库的 `game_events`。`bfsim report` 默认给出每局汇总、抽样人读回放、主阶段行动 × 胜率，并双轨落盘。

## 验收标准（测试清单）

- `tests/test_battle_log.py`：四局汇总；招式胜率 0.5；平局 `end_turn` 计次数不计分母；`choose` 不进主阶段；抽样只取种子最小的完成局；JSON 胜率与对象相同；报告不含「理由」
- `tests/test_winrate.py` 与 `tests/test_decisions.py` 仍通过

## 实现要点

- `battlefrontier/report/battle_log.py`
- `bfsim report --out` 缺省 `results/report-<id>-log`，`--replay-sample` 默认 3
- 回放调用 `report/render.py` 的 `render_log`

## 结果与遗留

075 换卡报告未做。不编造 AI 理由，不倾倒每步合法行动。
