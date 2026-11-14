# task 124 · 败局解剖产品化（bfsim report --autopsy）

- 状态：完成
- 关联：四期 PRD v0.2（`docs/superpowers/specs/2026-11-14-phase4-prd-design.md` §2 task 124）M14 卡组评估线

## 目标

任意实验一键产出「终局类型 × 死亡回合分桶 + 每桶抽样回放链接」，进 `bfsim report` 新分节 `--autopsy`。把 2026-11-14 太晶伊布备赛研究里手工 SQL 挖败因的模式（game_events 250 万条事件流 → 败因主线）产品化，备赛用户自助可得。

复用面：task 120 盘面快照/回放导出（`bfsim report` 对局包）、task 122 agent_explain 决策理由事件。

## 验收标准（测试清单）

1. `bfsim report <id> --autopsy` 输出新分节：按败方视角（A 负 / B 负分列）的「终局类型（game_over reason：prizes / no_pokemon / deck_out / 其他）× 死亡回合分桶」计数矩阵，每桶给胜率上下文与抽样回放链接（复用 task 120 对局包导出，每桶至少 1 局、可调）；
2. **分桶与 game_over 事件一致性的自动化断言**（v0.2 预注册判据）：测试从 `game_events` 独立重算终局类型/回合分布，与报告分节输出逐项一致；
3. 死亡回合定义钉死并写进分节头注：败方最后一个宝可梦昏厥所在回合（knockout 事件 turn），deck_out 类取 game_over turn；
4. 全量 pytest 绿 + ruff 零告警；**零 Agent/DSL/引擎行为变更**（纯报告层新增）；
5. 新输出带 sim 限定语（同既有 report 分节惯例）；claims register / README 使用节按需补一行。

## 实现要点

- 数据源：结果库 `games`（winner/turns）+ `game_events`（kind=game_over / knockout）；不改事件流产生逻辑。
- CLI：`bfsim report --autopsy`，可选 `--autopsy-sample N`（每桶抽样局数，默认 1）。
- 分桶建议：≤6 / 7–9 / 10–12 / 13–15 / >15（与 2026-11-14 研究口径一致，写死进测试）。
- 回放链接：抽样 game_id 走 task 120 对局包导出路径（log.md/log.html），报告里给相对路径。

## 结果与遗留

（2026-11-14 实现收官，待主会话复核）

- **实现**：新增 `battlefrontier/report/autopsy.py`（纯报告层，零 Agent/DSL/引擎行为变更）——`autopsy_report` 只读 `games`/`game_events`，按败方视角（A 负/B 负分列）产出「终局类型（prizes/no_pokemon/deck_out/其他）× 死亡回合分桶（≤6/7–9/10–12/13–15/>15，口径常量 `DEATH_BUCKETS` 写死）」计数矩阵；死亡回合 = 败方最后一只宝可梦昏厥的 knockout 事件最大 turn，deck_out 类取 game_over turn（定义写进分节头注）；每格按 (seed, id) 升序抽 N 局（`--autopsy-sample`，默认 1）经 task 120 路径（`render_log` + `deviation_html`）导出对局包 `log.md`/`log.html`（默认 `results/report-<id>-autopsy/game-<gid>/`，`--out` 时落 `<out>/autopsy/`），报告给相对路径。CLI：`bfsim report <id> --autopsy [--autopsy-sample N]`。
- **CLI 接线**：`battlefrontier/cli.py` `_cmd_report` 增 `--autopsy`/`--autopsy-sample` 两 flag。
- **测试**：新增 `tests/test_report_autopsy.py` 4 测全过——预注册判据落地：测试从 `game_events` 原始 JSON 独立重算 (败方, 终局类型, 桶) 分布，与 `AutopsyReport.cells` 全部 40 格逐项一致（含 deck_out 取 game_over turn、无 knockout 回退、未知 reason 归「其他」、平局/失败局排除）；另有分节文本/限定语/样本路径断言、抽样按种子升序且 `--autopsy-sample` 可调、CLI 端到端（含对局包落盘）一测。
- **限定语**：分节末尾带 `SIM_INTERPRETATION_NOTE`（同既有 report 分节惯例）；README 使用节与 `docs/claims-register.md` 证据索引各补一行。
- **自检**：目标测试文件 4/4 绿；`ruff check .` 全库零告警；全量 pytest **1740 passed in 333.57s**（2026-11-14，含新增 4 测）。
- **遗留**：无已知遗留；未经真实大实验（如 m9 矩阵库）跑批验证输出观感，建议主会话抽查一次真实实验的 `--autopsy` 输出。
