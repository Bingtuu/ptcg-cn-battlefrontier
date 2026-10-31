# task 094 · M13 测量协议、基线资产与实施计划

- 状态：完成（2026-10-31；文档复核通过；未修改运行时代码或 Agent 行为）
- 关联：M13；`docs/superpowers/specs/2026-10-31-phase4-accuracy-validity-design.md`；goal「校准与验证地基」
- 停止线：本 task 只写设计、计划和任务文档，不修改运行时代码、测试或 Agent 行为

## 目标

把 M13 的开发/验证划分、基线资产、统计口径、报告兼容性和端到端验收钉成可执行文档，为 task 095 的 TDD 与 task 096 的复算提供唯一事实源。

## 验收标准（测试清单）

- [x] 真实 409 场按 `(date, tournament_id)` 排序，前 286 场开发、后 123 场验证；分界两边同日，明确禁止纯日期切分。
- [x] 明确 full / development / validation 三份报告的加权与未加权 |Δ|、高残差格数、行级残差、Wilson CI 与低置信口径。
- [x] 既有 calibration 命令默认行为不变；只有显式传新参数才启用切分。
- [x] 明确 raw 全量与 SDK 72/72 对拍、模拟失败 0、确定性、全量 pytest 与 ruff 的验收要求。
- [x] 实施计划覆盖 task 095 / 096，逐文件、逐红测、逐命令，无 TBD/TODO 或“稍后实现”。
- [x] 主会话独立复核规格和计划：范围只含 M13；类型与命令一致；没有要求修改 Agent 行为。
- [x] 复核通过后才进入 task 095。

## 实现要点

- 协议：`config/m13-validation-v1.yml`。
- 运行 manifest：`results/m13-baseline/manifest.json`。
- 数据侧复用只读 `v_pairing_players` / `v_tournament_weights`，报告侧复用 `CalibrationReport` 与双轨偏差包。
- 本 task 不创建上述运行时资产；它们属于后续 task 的 TDD 交付。

## 结果与遗留

- 已写四期设计与 M13 实施计划；主会话复核通过。复核修正：扩展汇总仅限显式 split 模式，旧 stdout 与 JSON 字段不变。
- 验证：占位符扫描零匹配，`git diff --check` 通过。文档任务无运行时代码，TDD 不适用；未进入 task 095，未修改 Agent 行为。
