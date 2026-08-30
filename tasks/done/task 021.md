# task 021 · 胜率报告 + bfsim report（M4 启动）

- 状态：完成
- 关联：PRD §9 报告层（胜率报告口径）/ 里程碑 M4；task 019 结果库（games 层字段已齐）

## 目标

`report/winrate.py` + `bfsim report <experiment_id>`：从结果库聚合胜率报告——
A/B 胜率 + Wilson 95% CI、先后手拆分、平均回合数、平局率、失败局显式计数，
meta 回显实验 id / 名称 / 种子区间 / 代码+数据版本 / 局数（可复算纪律）。

统计量手写实现（不引 scipy/statsmodels——公式简单，依赖保持轻；
正确性用已知参考值对拍锁定，见验收 2）。

## 口径定义（写死在 docstring，报告页同步标注）

- **完成局** = error IS NULL；**决定局** = 完成局且非平局；
- **胜率** = 胜场 / 决定局（平局不计入分母，平局率单独报告）；
- **平均回合数** = 完成局（含平局）平均；
- **先后手拆分** = games.first_player（0 = A 先攻）分组，各组内 A 胜率 + CI；
- Wilson 95% CI（z=1.96）；决定局为 0 时胜率/CI 记 0（不除零不猜）。

## 验收标准（测试清单）

文件：`battlefrontier/report/winrate.py`、`tests/test_winrate.py`、cli 加 report 子命令。

1. `ResultsDB.experiment(experiment_id)` 访问器（报告 meta 数据源）。
2. `wilson_ci` 对拍参考值：x=63/n=100 → ≈(0.532, 0.718)；x=40/n=100 → ≈(0.310, 0.498)
   （±1e-3）；n=0 → (0.0, 0.0)。
3. 合成结果库对账：11 局（A胜6/B胜3/平1/失败1，先攻后攻各半已知分布）→
   各聚合计数、胜率、先后手拆分、平均回合数逐项精确断言。
4. 边界：零局实验不崩溃（胜率 0、CI (0,0)、meta 仍完整）；全平局 decided=0 不除零。
5. `format_report` 文本含 meta 全要素（实验 id/名称/种子区间/版本/局数）+
   胜率/CI/先后手/平局/失败各行。
6. CLI：`bfsim report <id> --results <path>` 退出码 0，stdout 含实验名与胜率行；
   不存在的实验 id 明确报错（退出码非 0 或明确错误信息）。
7. `pytest -q` 全绿 + `ruff check .` 零告警。

## 实现要点

- 纯查询层：只读结果库，不动引擎/Runner；聚合在 Python 侧（千局规模无压力）。
- 决策聚合（observe 锚点 + choose 决策事件）归 task 022；换卡敏感性归 task 023。

## 结果与遗留

**完成**（2026-08-29）：`report/winrate.py`（wilson_ci / winrate_report / format_report）+
`ResultsDB.experiment()` + `bfsim report` 子命令。TDD 13 新测试；全量 286 绿 + ruff 零告警。

真实库首跑（M3 百局）：A(启发式) 65.0%（CI 55.3..73.6），先攻 70.7% / 后攻 61.0%，
平均 10.4 回合，失败 0。

实现中两处小修：Wilson 全负参考值 0.037（非 0.038）；argparse help 含 `%` 需 `%%`。

遗留：决策事件 + observe 锚点聚合归 task 022（注意：补 choose 决策事件会改变事件流
hash 基线，需重记）；换卡敏感性归 task 023。
