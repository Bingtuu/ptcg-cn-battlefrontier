# task 096 · M13 端到端复算与里程碑验收

- 状态：**已完成（2026-10-31，Asia/Shanghai）**
- 关联：M13；task 094/095；`docs/superpowers/specs/2026-10-31-phase4-accuracy-validity-design.md` §5
- 边界：复用 task 095 报告实现，不修改 Agent、DSL、引擎规则或对局行为
- 完成 loop：Task 096-L1/L2/L3，详见 `docs/superpowers/plans/2026-10-31-m13-lint-acceptance.md`；分支 `task/m13-lint-acceptance`
- lint 口径：锁定 Ruff 0.16.4 及其新版默认规则；不归档已跟踪文件、不新增排除或告警抑制；本地临时脚本只移动留档、不删除不改内容

## 目标

用锁定实验、模拟结果库和真实数据版本复算 full / development / validation 报告与 manifest，验证真实口径一致、模拟零失败、串并确定性和全项目回归，完成 M13。

## 验收标准（测试清单）

- [x] `results/m13-baseline/` 含三份双轨偏差包和 manifest，72 格 `sim_failed=0`。
- [x] raw full 与既有 SDK 偏差包 real_n / real_wr 72/72 全等。
- [x] 100 局 workers=1 / workers=4 events_hash 逐种子全等、失败 0，并与 post-086 行为基线一致。
- [x] full / development / validation 均含加权/未加权 |Δ|、高残差格数、行级残差和不确定性信息。
- [x] 全量 pytest 最终复跑 **1674 passed**；`git diff --check` 通过。
- [x] 全仓 Ruff 0.16.4 `ruff check .` **零告警**。
- [x] STATUS、规格、计划与 task 记录同步。

## 实现要点

- 基线：`experiments/v2-calibration.example.yml` + `results/v2-calibration-post086.db` + `config/m13-validation-v1.yml`。
- 确定性：`experiments/m13-determinism.yml`，种子 208000..208099。
- 运行 manifest 记录实验、结果库和真实 DB 的 SHA-256；结果产物留本机 `results/`。

## 结果

- full：409 场 / 24315 决定局，加权 |Δ| 18.065%、未加权 18.065%、高残差 16；development：286 场 / 15430 局，19.195% / 18.279% / 20；validation：123 场 / 8885 局，16.270% / 17.986% / 14；三份均为 9 行 archetype 行级指标。
- raw/SDK 72/72 real_n 与 real_wr 全等；100/100 串行=并行=post-086 winner/is_draw/events_hash/error，失败 0。
- manifest 记录 report code `224de6f+dirty`、sim code `1405d2f+dirty`、数据 `2026-09-16 (user_version=13)` 及输入资产 SHA-256。
- 独立代码审查无 Critical；2 Important 与 3 Minor 均已先红测后修复。最终真实产物重新生成并再次 72/72 对拍通过。
- lint loop 起始为全仓 415 / 跟踪文件 37。125 个未跟踪本地脚本经 SHA-256 校验移至 `results/m13-scratch/`，清单为 `results/m13-scratch-manifest.json`；移动后全仓与跟踪文件均为同一组 37 项。6 个已跟踪历史实验脚本经 21 项自动安全修复和剩余 15 项人工清理后，6/6 AST 解析通过、全仓 Ruff 零告警。未新增规则排除、`noqa` 或 Ruff 抑制注释。
- 最终验收：全量 pytest **1674 passed in 590.69s**；真实复算三份报告指标与冻结值完全相等；全仓 Ruff 零告警；变更范围无 Agent、DSL 或引擎规则修改。M13 完成。
