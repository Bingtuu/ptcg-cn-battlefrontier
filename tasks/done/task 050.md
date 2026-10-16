# task 050 · M11 WP1：特征层 + 采集钩子 + 数据产线

- 状态：进行中
- 关联：M11 设计文档 `docs/superpowers/specs/2026-10-16-m11-learned-evaluator-design.md`（D-M11-1/2 数据产线与特征清单）；三期 PRD M11

## 目标

实施 M11 WP1：`agent/features.py` 特征层（A+B 组）+ `play_game` collector 钩子 +
`bfsim collect-features` 数据产线 CLI + 正式跑批（36 对 × 2800 局 @seed 300000，
≈10.08 万局，产物 `results/m11-data/`）。C 组特征（dsl_estimate 衍生）顺延后续 WP
（主会话裁决：WP1 保持聚焦）。

## 验收标准（测试清单）

1. **特征层**：`features.py` 纯函数 `feature_vector(view) -> dict[str, float]`，A 组
   （五因子原值——heuristic.evaluate 拆分为共享因子函数，重构零行为变化：现有测试
   全绿 + 新增「拆分后 evaluate 输出逐值对拍」回归）+ B 组（结构量，清单对齐
   D-M11-2）；特征名键序钉死（tuple 常量），全确定性
2. **collector**：`play_game(..., collector=None)` 默认零变化（既有 events_hash
   回归测试全绿）；采集模式逐 main 阶段决策点记录（pair/seed/turn/player/特征/action
   结构）；同种子重跑产物逐行一致；collector 不消费随机源
3. **产线**：CLI `bfsim collect-features`（pool/games/seed-start/out/workers 参数）；
   端到端小预算冒烟（2 对 × 20 局，产物 schema 校验）；worker 复用
   `_run_one_experiment` 同路径（串并一致）
4. **正式跑批**：36 对 × 2800 局产物 36 个 JSONL，行数/字段/标签分布校验
   （失败局剔除并计数报告）
5. 全量 pytest 绿 + ruff 零告警

## 实现要点

- 子代理 TDD + 主会话独立复验（task 026 以来惯例）
- 冻结面：tune 五模块零改动；mcts.py 不动（WP3 域）；collector=None 路径性能无感
- worker 传输：特征行随 worker 返回（pickle），按配对聚合落盘

## 结果与遗留

- **交付**：`agent/features.py`（FEATURE_NAMES 30 键序钉死：A 组五因子原值 + B 组 25
  结构量，对手侧仅 count 特征守信息纪律；`agent/heuristic.py` evaluate 拆因子零行为
  变化对拍回归）；`agent/collect.py` FeatureCollector（仅 main 阶段决策点入缓冲）；
  `runner/collect.py` + CLI `bfsim collect-features`（worker 复用 `_run_one_experiment`
  同路径，种子 = pair i → [seed_start+i×N, +N) matrix 惯例）；`runner/play.py`
  collector 钩子（默认 None 零变化）；tests/test_features.py + test_collect.py
- **正式跑批（2026-10-16）**：36 对 × 2800 局 = 100,800 局 @seed_start 300000
  @16 workers ~21min；产物 `results/m11-data/` 36 个 JSONL 共 **7,440,861 行**
  （6.7GB，results/ 已 gitignore 不落库），失败剔除 8 局（pair-1 沙奈朵×猛雷鼓
  厄诡椪）并计数报告；装载告警 16 条（波波 CSV4C-099 / 索财灵 CSV9C-096 异文本
  印刷未覆盖按 vanilla 结算——既有口径）；抽样 schema + 标签分布校验通过
- **复验**：pytest 1178 绿（主会话亲自复跑）+ ruff 零告警；冻结面（tune/、mcts.py、
  experiment.py）git diff 实证干净
- **遗留**：每局实际决策点 ~74 个远超设计估算 ~15–20 → 训练侧按局行数上限裁决
  归 task 051（D-051-1）；C 组特征（dsl_estimate 衍生）顺延 WP3 前增量评估；
  8 失败局明细未逐局归因（量级 0.008%，不阻塞）
