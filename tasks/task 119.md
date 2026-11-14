# task 119 · `bfsim check-deck` 卡表预检

- 状态：进行中
- 关联：task 118（印刷级 decklist）/ task 073（入口模板）；使用便利性 P0
- 日期：2026-11-14 立项（四层优化拍板 P0）

## 目标

跑前预检：写错卡表不用等 run 装载才发现。`bfsim check-deck <decklist.txt>` 秒级体检，零跑批。

## 验收标准（TDD）

1. 红测 → 绿：合法 60 张卡表 → 退出码 0 + 体检报告（张数、宝可梦/训练家/能量构成、每卡 DSL 状态：覆盖/vanilla 告警/无文档）。
2. 红测 → 绿：格式错误（带行号）/卡名未命中/印刷未命中/卡名不一致/张数≠60 → 退出码 1 + 明确错误行。
3. 全量 pytest 绿 + ruff 零告警；README §5.5 场景 1 补一句预检命令。

## 实现要点

- 新模块 `battlefrontier/runner/deck_check.py`：`check_decklist(db_path, path) -> DeckCheckReport`（结构化）+ `format_deck_check(report) -> str`；CLI 子命令薄壳（`--db` 缺省走 config，与现有一致）。
- 复用 `_load_decklist_file` 的解析/校验（错误类型一致，不猜）；DSL 状态经 `load_card_dir` + card_id 精确挂载口径。
- 真实 db 测试跟随 test_deckload.py 先例（本机 db）。

## 结果与遗留

- **实现 ✅**：`battlefrontier/runner/deck_check.py`（`check_decklist` 结构化 + `format_deck_check` 人读）+ CLI `bfsim check-deck`（`--db`/`--cards-dir` 与现有一致）；experiment.py 抽 `_resolve_decklist_entry` 公共解析助手（run 装载与预检同口径，零行为变化）。
- **测试（验收 1–3 ✅）**：6 测（合法卡表体检 / 张数不足 / 卡名未命中 / 格式错误带行号 / 构成与 DSL 状态 / CLI 退出码）；真实 db 跟随 test_deckload 先例；ruff 零告警。
- **实证 ✅**：模板示例（7 张）正确拒绝：`[预检失败] decklist 展开后为 7 张，应为 60`。README §5.5 场景 1 补预检命令。
- **遗留**：全量回归随 120/121 同批。
