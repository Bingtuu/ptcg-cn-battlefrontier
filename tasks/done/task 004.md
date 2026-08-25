# task 004 · 白板对局端到端与 M1 确定性验收

- 状态：完成（2026-08-25）
- 关联：PRD §11 M1 验收（同种子复现；阶段机单测）、§8.4（确定性）；里程碑 M1 收口

## 目标

用随机合法行动 Agent 打完整场白板对局，验证引擎端到端可运行，并完成 M1 的确定性硬验收。

## 验收标准（测试清单）

- [x] 随机 Agent（均匀随机选合法行动）可对白板卡组打完整局，产出胜负结果，不抛异常（100 局不同种子冒烟）
- [x] **确定性硬验收**：同实验配置 + 同种子重跑，对局事件流逐事件一致（比对序列化事件序列 hash）
- [x] 串行与多进程并行执行同批种子，结果逐局一致（并行可用 2 进程最小验证）
- [x] 单局事件流可渲染为人类可读回合记录（§5.4 人工 check 模式的最小版）
- [x] 对局无死循环保护：回合数/行动数超上限强制判平并记录（上限值进配置，不硬编码散落各处）
- [x] 异常对局（如卡组无基础宝可梦）有明确错误而非崩溃

## 实现要点

- 本 task 的 runner 是最小测试驱动器，不是 M3 的正式实验 Runner（不落库、无实验定义 YAML）
- 白板卡组 fixture：60 张 stub 卡（基础宝可梦 + 能量），进 `tests/fixtures/`
- 完工后更新 `STATUS.md`（M1 ✅），本文件归档 `tasks/done/`

## 结果与遗留

- **结果**：54 测试全绿 + ruff 零告警。新增 `agent/random_agent.py`（均匀随机 Agent）、`runner/play.py`（play_game / run_games_parallel spawn 池 / GameResult 含事件流 sha256 / DeckConfigError / DEFAULT_MAX_TURNS=200 配置）、`report/render.py`（事件流 → 中文回合记录渲染）。**M1 硬验收达成**：同种子事件流 hash 逐局一致；12 种子串行 vs 2 进程并行逐局一致；100 局随机对局零异常；回合上限强制判平 + turn_cap 事件；无基础宝可梦/张数不足卡组抛 DeckConfigError。
- **TDD 记录**：test_play.py 8 测先 RED（模块不存在）；rng.randbelow 小循环同样先 RED。
- **遗留**：①play.py 是验证驱动器，M3 正式 Runner 才接实验定义 YAML + 结果库；②渲染模板词表随事件 kind 增长维护；③白板随机局存在较高平局率（回合上限），启发式 Agent（M3）落地后观察是否需调整 DEFAULT_MAX_TURNS。
