# task 111 · 核验勘误与 lint 修复收口

- 状态：进行中（勘误与修复已落盘；待提交合 main 后归档）
- 关联：task 102（报告层校准证据）/ task 109（M12 盲区证据）；零行为变更线
- 日期：2026-11-13 立项并执行（独立核验评估会话的建议 ①②）

## 目标

2026-11-13 独立核验（pytest 全量 + ruff + 证据资产复算）发现两处与宣称不符的瑕疵，本任务做文档勘误与 hygiene 修复收口，恢复「全量测试绿 + Ruff 零告警 + 数字可复算」三项纪律的一致性。不改任何对局行为、不改 Agent/DSL/引擎。

## 背景（核验事实）

1. **task 102 无向预检数不可复现**：`tasks/task 102.md` §2 与 STATUS 引用的「val 无向 36 对 +0.142/+0.167、dev 无向 −0.064/−0.053」在当前 `results/m13-baseline/` 包下重算不成立（无向口径对侧边选择反射不变，Pearson/Spearman 数学上唯一）：val 重算 −0.078/−0.099（未加权）/ −0.016/+0.010（real_n 加权），dev 重算负值更大。原预检计算方法未存档。正式预注册判决（有向 72 格 + G1/G3 + verdict FAIL，`.kimi-code/t102_calibrate.py` 重跑）**数值级复现**，「格级 sim↔real 相关 ≈ 0」结论不变（重算值全负，更保守）。
2. **t109 证据脚本 F841**：`.kimi-code/t109_blindspot_precheck.py:84` 未使用变量 `games_any`，`ruff check .` 报 1 error，与「Ruff 零告警」宣称不符。评估会话已现场删除该两行赋值，删后 `All checks passed`（纯死代码删除，行为零变化）。

## 验收标准（测试清单）

1. `tasks/task 102.md` §2 预检节追加勘误段：声明无向口径未存档、该两点估计不再引用；以有向 72 格数值与 `results/t102-calibration.json` 为权威口径。
2. `STATUS.md` task 102 焦点段同步：删去或标注 val 无向 +0.142/+0.167 引用，只保留可复现的有向 72 格数与判决结论。
3. `.venv/Scripts/ruff.exe check .` 全仓零告警。
4. `pytest -q` 全量 1704 passed（零行为变更回归护栏）。
5. 提交 `task(111)` 合 main；t109 修复随本 task 入库。

## 实现要点

- 只动：`tasks/task 102.md`（勘误段）、`STATUS.md`（一处引用）、`.kimi-code/t109_blindspot_precheck.py`（已删死代码，本 task 入库）。
- 不重算任何判决、不碰 m13 包、不碰 `t102_calibrate.py`、不碰 heuristic/引擎/DSL。
- 勘误措辞按项目诚实性文化：写明「重算值全负、结论不变甚至更强」，不掩饰原始数字出处。

## 结果与遗留

- **勘误落盘（验收 1–2 ✅）**：`tasks/task 102.md` §2 预检节追加勘误段（口径未存档、重算值全负、权威口径 = 有向 72 格 + `results/t102-calibration.json`）；`STATUS.md` task 102 焦点段引用同步改为可复现的有向数（val 72 格 −0.016/−0.010），原 +0.142/+0.167 标注勘误不再引用。
- **lint 修复（验收 3 ✅）**：`.kimi-code/t109_blindspot_precheck.py` 删除未使用变量 `games_any` 两行死代码；`ruff check .` → `All checks passed`。
- **回归护栏（验收 4 ✅）**：修复后全量 pytest **1704 passed**（308.73s）；删除为证据脚本死代码，tests 不 import 该脚本，绿结果对当前树有效。
- **遗留**：验收 5（`task(111)` 提交合 main）待执行——本次会话未获 git 提交授权，变更留在工作区。

