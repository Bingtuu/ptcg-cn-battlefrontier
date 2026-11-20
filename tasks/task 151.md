# task 151 · 自对弈数据飞轮（BC 数据面，PRD §4 原预占 128）

- 状态：**数据集已交付（2026-11-21）——质量门 4/5 过，门 ② 字面未过（147,635/150,000），待 Owner 裁决**
- 关联：四期 PRD §4 task 151 + v0.5/v0.7；task 155/155a（BC 开工门 PASS 解冻本任务）；task 149（吞吐实测纪律）；task 155 采集产线三修复（内存纪律沿用）；task 052（快照产线基座）；task 152（消费方——本任务只产数据集）

## 目标

批量种群自对弈产出**决策点数据集 v2**（快照 JSONL，复用 task 052 `bf-m11-snapshot-v1` 格式）：PRD B3 盲点的动作级数据源，供 task 152 BC 自蒸馏消费。本任务只产数据 + 质量报告，不训练策略。

## 预注册（2026-11-20 冻结，判据跑数前不得变更）

- **种群**（PRD v0.5 口径）：{启发式, 纯 MCTS 2×50}——价值网成员 task 126 no-go 不入列；蒸馏学生词表锚定 v1（task 149 实证）不入列。
- **教师配置**（MCTS 侧钉死）：`worlds=2, iterations=50, rollout_turn_cap=50, eval_cutoff_turns=10, evaluator_path=models/eval-linear-v3.json`（M11 锚 2 同款截断配置；v3 资产格式分派已兼容 MCTS 装载）。
- **混编规则**（确定性）：每局 side0/side1 按 `(seed − 该对种子起点) % 2` 交替指派 {MCTS, 启发式}；覆盖 v2.x 池全部 45 无向对（`pool_assignments` 序）。
- **快照行扩展**：每行加 `"agent"` 字段（行动方标签 `"mcts"` / `"heuristic"`，152 过滤用）；其余格式与 `bf-m11-snapshot-v1` 逐字兼容（task 052 评估器不破坏）。
- **预算（速度实测钉死）**：实测 cutoff=10 单局 **578.9s**（约 10 min/局；rollout_turn_cap=50 全展开成本结构）→ **45 对 × 22 局 = 990 局**，16 workers ≈ 96 局/h → 中位墙钟 ~10.5h，**上限 14h**（`pair_start` 断点续采兜底）；种子域 **1020000..1020989**（与训练域 960000+ / 探针域 800000+ 不重叠）。预期决策点 ~170k（M12 试点 171k/千局同构）。
- **质量门（数据集验收，跑批后判读）**：① 失败局 = 0；② 决策点总数 ≥ **150k**；③ action-kind 分布无零坍缩（各可行 kind 占比 > 0.1%——task 061 教训）；④ MCTS:heuristic 决策点比例 ∈ [40%, 60%]（混编规则自检）；⑤ 串并一致（workers=1 vs 2 冒烟对逐字节全等）。
- **内存/环境纪律**（task 155 教训沿用）：`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` 必配（MCTS worker 经 learn.model 传递性载 numpy+OpenBLAS）；snapshot runner 的 Pool 增 `maxtasksperchild`（MCTS 大对象 churn 棘轮同 task 155 机理）；主进程 per-pair 增量落盘已在 task 052 就位（本任务核验 per-pair 缓冲上界：22 局 × ~180 行 × ~15KB ≈ 60MB，安全）。

## 验收标准（测试清单）

1. `tests/test_snapshot_population.py`（新）：混编规则确定性（同 seed 同指派、%2 交替平衡）；`agent` 标签与行动方一致（MCTS 侧行 = mcts）；教师参数透传（evaluator_path/eval_cutoff_turns 到 MCTSAgent）；既有 task 052 评估器对本任务产物全绿（格式兼容）。
2. `tests/test_snapshot_population.py`：maxtasksperchild 存在性锚（Pool 构造参数）；CLI 新 flags 缺省 = 现状零变化（双侧同 MCTS 2×50 回归锚）。
3. 冒烟：1 对 × 4 局串/并产物逐字节全等 + 速度复测落 dig（正式跑批前最后校验）。
4. 正式跑批：45 对 × 22 局，质量门五条件全过，统计报告（决策点/局、action-kind 分布、双种群占比、各对完成度）落 dig `docs/digs/2026-11-2X-t151-flywheel-data.md`。
5. 全量 pytest 绿 + ruff 零告警；既有行为零变化（collect-snapshots 缺省路径）。

## 实现要点

- WP1 工程：`runner/snapshot.py` `_run_one_snapshot` 增种群分支（payload 带 `mix: true` + 教师 dict 全量键）+ `run_collect_snapshots` 混编参数透传 + Pool `maxtasksperchild`；`cli.py` `collect-snapshots` 增 `--mix-population`、`--evaluator-path`、`--eval-cutoff-turns`（缺省 None = 现状）。
- WP2 冒烟 + 速度复测。
- WP3 正式跑批（后台 + 日志 + pair_start 续采预案）。
- WP4 质量门判读 + dig + 收尾（CHANGELOG/STATUS/归档）。

## 结果与遗留

**数据集已交付**：`results/m16-flywheel-v1/`（45 pair-*.jsonl，990 局零失败，
147,635 决策点，行级 agent 标签，header `mix:true` 教师五键钉死）。dig：
`docs/digs/2026-11-20-t151-flywheel-data.md`（WP2 冒烟 + WP3 跑批 + 门判读全记录）。

**质量门判读：4/5 过，门 ② 字面未过（147,635 < 150,000，缺 1.6%）**——根因 =
预注册 ~170k 估计锚双侧 MCTS 口径（M12 试点），混编密度不可移植（WP2 预警 +
实测 149.1/局证实）；数据面健康（45 对全覆盖零失败、配比 46.6/53.4、各对
≥2,169 行）。**待 Owner 裁决**：(a) 接受 + 修订门 ②（附根因披露）；(b) 补采
修正案（新种子域，新预注册）。推荐 (a)。

工程面：混编采集分支（`--mix-population` + 教师 `--evaluator-path`/
`--eval-cutoff-turns`）+ `SnapshotCollector.record_players` + Pool
`maxtasksperchild=500`；10 新测；全量 pytest 2100 绿 + ruff 零告警。
速度实测：混编局 3.7 min/局（独占口径），16 workers 产线节奏 ~12 min/对。

遗留：门 ② 裁决（上）→ 之后 task 152（BC 自蒸馏，消费本数据集）按 PRD
排程开工；task 154（v3 池评估）并行线不受本任务影响。
