# task 106 — 报告层诚实化：sim 解释限定语

- 日期：2026-11-06
- 分支：`task/t106-report-honesty`
- 性质：小 TDD 行为变更（报告输出文本）；承接 task 104 claims register 使用守则 1/3
- 动机：claims register 把「sim 胜率必带自对局限定语」写成守则，但守则此前只存在于文档——本 task 把它钉进产品输出表面，防未来过度宣称的最后一公里。

## 改动

1. `battlefrontier/report/__init__.py`：新增两个常量（报告层单源）——
   - `SIM_INTERPRETATION_NOTE` = 「声明：sim 数字为自对局模拟结果，不构成真实胜率预测（见 docs/claims-register.md）」
   - `CALIBRATION_EXTRA_NOTE` = 「真实侧窗口与模拟卡快照可能不同代；|Δ| 是描述量，不是模拟精度指标」
2. `battlefrontier/report/winrate.py::format_report`：末行追加 `SIM_INTERPRETATION_NOTE`。
3. `battlefrontier/report/calibration.py::format_calibration`：口径行后追加两行限定语（`SIM_INTERPRETATION_NOTE + CALIBRATION_EXTRA_NOTE`）——deviation 包 md/html 内嵌 `format_calibration` 原文，自动继承。

## 验收

- 红测先行：`tests/test_report_sim_note.py` 3 测（常量语义 / format_report 含限定语 / format_calibration 含两条）。
- 局部套件 42 passed（winrate/calibration/v2-matrix/validation 相关）；全量 pytest 见合并前验证。
- ruff 零告警。
- 不改任何数字/口径/行为，仅输出文本加行。

## 不做

- 不动 `bfsim report --decisions` / `--mcts-consider` 分节（决策分析层无胜率宣称问题）。
- 不动 CSV/JSON 机器可读字段（限定语属于人读层；md/html 已覆盖）。
