# task 095 · M13 赛事切分、校准汇总与双轨报告

- 状态：完成（2026-10-31；TDD 与相关验证通过；未修改 Agent 行为）
- 关联：M13；`docs/superpowers/specs/2026-10-31-phase4-accuracy-validity-design.md` D-M13-2/4/5；计划 Task 095
- 边界：只改数据读取、报告与 CLI；不修改 Agent、DSL、引擎规则或对局行为

## 目标

实现显式 `time-70-30` 赛事切分，在同一份模拟矩阵上输出 full / development / validation 三份可复算偏差包和运行 manifest；未传新参数时旧 stdout、JSON 字段与真实 SDK 查询路径保持不变。

## 验收标准（测试清单）

- [x] 同日分界按 `(date, tournament_id)` 有序 ID 集切分；空赛事/非法比例明确报错。
- [x] 协议配置锁定 409→286/123 与两个分界 ID。
- [x] `pairing_contrast` 可按精确赛事 ID 集过滤；缺省调用结果不变。
- [x] 汇总含加权/未加权 |Δ|、|Δ|≥25% 格数、行级指标与最大残差格。
- [x] split 报告追加扩展汇总；旧报告无 `summary` 字段且 stdout 不变。
- [x] CLI split 模式输出三份双轨包与 manifest；旧 CLI 测试不改断言且全绿。
- [x] 相关 pytest 全绿、ruff 零告警。
- [x] 文档复核和每个红→绿分片通过后才进入下一分片。

## 实现要点

- `battlefrontier/data/validation.py`：只读、确定性赛事切分。
- `battlefrontier/data/pairings.py`：可选赛事 ID 过滤，不复制真实胜率口径。
- `battlefrontier/report/validation.py`：纯汇总与 manifest 写出。
- `battlefrontier/cli.py`：显式 split 编排；旧 SDK 路径不变。
- `config/m13-validation-v1.yml`：冻结协议；运行产物落 `results/m13-baseline/`。

## 结果与遗留

- 红→绿分片：切分/过滤 10 tests；汇总/manifest 3 tests；报告兼容与回归 22 tests；CLI 端到端 2 tests。
- 最终相关回归：**49 passed**；ruff 零告警。测试夹具两次修正（配对行数与池定义合法性），未改实现口径迁就测试。
- 未修改 Agent、DSL、引擎规则或对局行为。真实数据全量对拍、串并确定性与 M13 总验收归 task 096。
