# CHANGELOG

> 四段式：Added / Changed / Deprecated / Removed（AGENTS.md 规矩）。
> 粒度 = 里程碑/任务级，逐日流水见 `STATUS.md` 与 `docs/status-archive.md`。

## Unreleased（2026-11）

### Added

- 换卡敏感性首个正式资产（task 113）：多龙黑夜魔灵 1×3 扫描，预注册 5 门（含阴性对照 CI 覆盖 0）；`experiments/v2-swap-dragapult-dusknoir.example.yml`
- swap `in_id` 印刷级换卡支持（task 115）：`SwapCfg.in_id` 可选字段 + 存在性/同名校验，换入卡印刷可控、防 vanilla 静默退化；覆盖印刷重跑实验定义 `experiments/v2-swap-dragapult-dusknoir-printswap.example.yml`
- 对齐窗判决值守线（task 112）：WAIT 态周期维护 + 触线按 task 105 §2 出判决
- claims register（task 104）：产品宣称两层（可宣称/不可宣称）+ 使用守则

### Changed

- `format_sensitivity` 末行补 `SIM_INTERPRETATION_NOTE`（task 114）：敏感性输出纳入 claims register 守则 1
- task 102 文档勘误（task 111）：「无向 36 对」预检点估计口径未存档不可复现，权威口径 = 有向 72 格 + `results/t102-calibration.json`
- 报告层/校准输出内嵌 sim 解释限定语（task 106）；事件序观感债修复——昏厥/拿奖事件滞后到招式效果链收尾（task 108）

### Deprecated

- 格级胜率预测与强度排序宣称（task 102/103 定量关闭，claims register 禁句区）

### Removed

- M12 三残留盲区（task 109 预注册预检全部关闭，backlog 清零）

## 2026-10

### Added

- 卡池 v2（task 068，`config/target-pool.v2.yml`，WUR 覆盖 80.5%）+ 引擎扩展两批（069/071）+ DSL 缺口清零 134 份（070/071）
- M13 校准地基（094–096）：full/development/validation 三份双轨偏差包
- MCTS 决策分析（task 042）：`bfsim report --mcts-consider` 三件套
- M11 学得评估器（049–055，`models/eval-linear-v1.json`）/ M12 蒸馏学生（056–062，`models/policy-m12-v1/v2.json`，定位分钟级粗筛）

### Changed

- MCTS 信息泄漏修复（task 039，带冻结集部分 determinize）
- promote 空场判平引擎修复（task 064，时序语义定案 + 附录 A 决议）
- MCTS 成本优化（task 037–042 期，−38.5%，行为零变化 events_hash 逐局全等）

## 2026-08 ~ 2026-09

一期 M1–M6 全段（引擎骨架 / DSL+解释器 / 启发式 Agent / 报告层 / 覆盖扩展 / 校准基线）——逐日记录见 `docs/status-archive.md`。
