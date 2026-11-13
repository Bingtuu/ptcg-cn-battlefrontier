# task 114 · format_sensitivity 补 sim 解释限定语（task 106 收口遗留）

- 状态：完成（待提交合 main）
- 关联：task 106（报告层诚实化）/ task 113 gate 2 发现 / claims register 使用守则 1
- 日期：2026-11-13 立项并执行

## 目标

task 113 验收发现：`bfsim sensitivity` 产品输出（`format_sensitivity`）未携带 `SIM_INTERPRETATION_NOTE`，违反 claims register 守则 1「sim 胜率必带『自对局结果』限定语」——`format_report`（winrate.py）与 `format_calibration` 在 task 106 已钉，敏感性输出是同一守则的遗留缺口。本任务按 task 106 先例红测先行补齐。

## 验收标准（测试清单）

1. 红测：`format_sensitivity` 输出末行 = `SIM_INTERPRETATION_NOTE`（新增断言，先红）。
2. 实现：sensitivity.py 引入并追加该常量为报告末行（与 winrate.py:131 同构）。
3. 局部测试绿 + 全量 pytest 绿 + `ruff check .` 零告警。
4. 重新导出 task 113 报告包（`bfsim sensitivity 1 2 3 4 --out results/v2-swap-dragapult`），swap.md 内嵌限定语 → task 113 gate 2 转 PASS。

## 实现要点

- 只动 `battlefrontier/report/sensitivity.py`（import + 一行）与 `tests/test_sensitivity.py`（新断言）。
- 限定语位置 = 整个敏感性报告块末行（format_report 末行先例；meta 告警行维持原相对位置逻辑——告警行在限定语之后追加与 winrate 同构）。

## 结果与遗留

- **红→绿（验收 1–2 ✅）**：`tests/test_sensitivity.py` 新增末行断言先红（1 failed / 11 passed）→ sensitivity.py 引入常量并追加为报告末行 → 12 passed + ruff 净。
- **产物复验（验收 4 ✅）**：重新导出后 swap.md 末行内嵌「声明：sim 数字为自对局模拟结果，不构成真实胜率预测（见 docs/claims-register.md）」，task 113 gate 2 转 PASS。
- **遗留**：验收 3 全量回归 ✅ 1704 passed（311s，新增断言挂在既有测试上、测试数不变）；提交合 main 待授权（与 task 111/113 变更一批）。
