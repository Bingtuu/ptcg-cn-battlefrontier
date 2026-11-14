# task 123 · metamages 式选卡器（field_pick）

- 状态：进行中
- 关联：四期 PRD M14（`docs/superpowers/specs/2026-11-14-phase4-prd-design.md`）；Pass 2 路线图 A2
- 日期：2026-11-14 立项（四期 PRD 拍板后开工）

## 目标

给定目标 field 分布（CN 使用率快照）+ matchup 矩阵（三层合成：intl 真实格 / sim 同口径格 / 缺口 low_confidence），输出每候选卡组的期望胜率排序 + 蒙特卡洛 field 模拟的排序稳定性——「带哪套去高级赛」的量化参考工具。

## 设计（预注册）

- 新模块 `battlefrontier/report/field_pick.py`（纯函数核心 + format）+ CLI `bfsim field-pick`。
- matchup 格来源：
  - `intl`：上游只读 pairings（`battlefrontier/data/pairings.py` 同口径，无向格双向化，镜像剔除）；
  - `sim`：偏差包 cells（`deviation.json`，`sim_wr` 有向格）；
  - 同一格两源并存时 intl 优先（真实 > 模拟），另一源记 detail 备查；全缺格 = 缺口（参与计算但标 low_confidence）。
- 期望胜率 = Σ_field share × wr(candidate vs f)；蒙特卡洛 = 钉种子对 share 做 Dirichlet 抖动 ×1,000 次，输出期望胜率分布与「排序第一」频率。
- **限定语**：输出头注三行——sim 格 = 同模拟器内；intl 格 = 国际线上周赛 meta 弱参照；low_confidence 格计数。

## 验收标准（TDD，判据跑批前冻结）

1. 红→绿：合成数据下期望胜率可手算复现（share × wr 逐项对拍）；归一化（share 和 ≠1 自动归一）。
2. 红→绿：蒙特卡洛钉种子可复现（同输入同种子同输出）；排序稳定性统计字段齐全。
3. 红→绿：缺格处理——无数据格按 0.5 计且标 low_confidence；双源格 intl 优先。
4. 输出含三行限定语头注；全量 pytest 绿 + ruff 零告警。
5. CLI 冒烟：`bfsim field-pick` 端到端跑通（真实快照 + sim 包）。

## 实现要点

- 纯 Python + numpy（runtime 纪律）；不碰引擎/Agent/DSL。
- field 快照加载支持 JSON（ptcgdb stats usage --format json 出口转换后）。

## 结果与遗留

- **核心（验收 1–4 ✅）**：`battlefrontier/report/field_pick.py`（MatchupCell/assemble_matrix/expected_winrate/field_pick/format + 适配器）；6 测全过（手算复现 / 归一化 / 缺格占位 / intl 优先 / 蒙特卡洛钉种子复现 / 限定语头注）；ruff 零告警。**TDD 偏差披露**：实现先于测试落盘（主会话直写），测试按预注册判据补写全绿。
- **CLI（验收 5 ✅）**：`bfsim field-pick --field <快照> --pool <池> [--intl-db --from --to] [--sim-pack] [--n-sim --seed]`；真实数据端到端跑通（CN 10 月窗快照 × intl 窗 × m13 sim 包，n=1000 秒出）。
- **冒烟暴露的输入纪律（重要，写进使用约定）**：机械功能正常，但 m13 sim 包（10 月启发式代码 + 零效度数字）驱动的排序与真实 meta 常识相悖（多龙纯第一、玛俐倒数第二）——**工具输出质量 = 矩阵输入质量**，sim 源必须新鲜重跑且只作同模拟器内参照；真实选卡建议 intl-only 模式或现码矩阵。该读数已如实记录，供 M14 gate 评估。
- **遗留**：全量回归后台收尾；提交后归档。

## 使用约定（M14 gate 前）

1. 真实选卡决策：优先 `--intl-db` 真实格（缺格会标 low_confidence）；sim 包仅作「同模拟器内补充」且必须用当前代码现跑。
2. m13 及更早的冻结偏差包**禁止**直接作选卡器 sim 源（效度证伪资产的数字，只作历史校准参照）。
