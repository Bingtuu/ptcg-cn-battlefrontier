# M6 校准基线 + 一期验收 设计文档（task 030）

- 日期：2026-10-03
- 状态：已获用户批准（组织方式 / 样本量 / 技术方案三决策，2026-10-03）
- 前置：db 项目 task 057 收官（Limitless online_open 收编），matchup 启动门槛已达成（`--basis intl_aligned --min-n 30` 实测 n_games_used=99,800，头部格 Gardevoir×Raging Bolt Ogerpon n=1,559）

## 1. 目标与范围

PRD §11 M6：校准基线 = 模拟 matchup 矩阵 vs db 真实赛事 matchup 矩阵偏差表 + 一期验收。单 task 030 一次做完，内部分 WP：

- WP1 口径决议 + archetype 映射 + matrix 实验定义 schema（TDD 任务书）
- WP2 runner matrix 展开 + 18,000 局正式跑批
- WP3 偏差表报告（report/calibration.py + CLI）
- WP4 一期验收（硬验收复核 + LLM 管线质量评估 + 二期建议）

## 2. 口径决议（开工先落 docs/rules-reference.md 附录 A，用户核销）

1. **真实侧口径**：`ptcgdb stats matchup --basis intl_aligned --from 2025-04-11 --to 2025-08-31 --division master --min-n 30`。CN 侧对阵数据不存在是硬约束，「真实赛事 matchup 矩阵」= EN 环境对齐段（CN GHI ⊆ EN 窗口对齐机制，含 task 057 收编的 online_open tier coef=0.5）。**环境差本身贡献一部分偏差——校准的是「简中卡池模拟 vs EN 同窗口真实 meta」，不设死阈值**（PRD §10.2）。
2. **镜像剔除**：两侧一致——真实矩阵同 archetype 内战本就不进矩阵（db task 041 口径）；模拟侧 9 套只跑 36 个无向配对（i<j），不打镜像。
3. **胜率口径**：分母 = 决定局（平局单列不进分母），对齐既有 `report/winrate.py` 口径；真实侧 ties 实测为 0、未上报局已由 db 排除。
4. **先后手**：由种子区间自然均摊，不做强制平衡。
5. **数据版本锚点**：偏差表 meta 回显 db data_version、name_group_rules_hash、tournament_tiers_hash（查询输出头既有），可原样重放。

## 3. Archetype 映射（CN 池 ↔ EN db，已实查验证）

`config/target-pool.v1.yml` 每 deck 加 `en_archetype` 字段（卡池事实源单点维护，loader 强校验必填）：

| CN archetype（池） | EN archetype（db） |
|---|---|
| 沙奈朵 | Gardevoir |
| 喷火龙 大比鸟 | Charizard Pidgeot |
| 猛雷鼓 厄诡椪 | Raging Bolt Ogerpon |
| 多龙巴鲁托 黑夜魔灵 | Dragapult Dusknoir |
| 多龙巴鲁托 喷火龙 | Dragapult Charizard |
| 玛俐的长毛巨魔 雪妖女 | Grimmsnarl Froslass |
| 赛富豪 | Gholdengo |
| 多龙巴鲁托 | Dragapult |
| 赫普的苍响 | Hop's Zacian |

36 格池内配对在真实矩阵实测 72 有向行全在、无缺格，最小 n=48（Charizard Pidgeot × Hop's Zacian），全部 ≥ min-n 30 门槛。

## 4. matrix 实验定义与 runner 展开

实验 YAML 新增 `matrix:` 段（与既有 `decks:`/`variants:` 互斥，Pydantic 强校验）：

```yaml
# experiments/m6-calibration.example.yml
name: m6-calibration
seed_start: 100000          # 种子基值
matrix:
  pool: config/target-pool.v1.yml
  games_per_pair: 500       # 36 格 × 500 = 18,000 局
agents:
  a: {type: heuristic}
  b: {type: heuristic}
```

- runner 展开：按池文件顺序取无向对 (i, j)（i<j），生成 36 个子实验；子实验名 `{name}::{archetypeA}×{archetypeB}`，`group_name = name`，variant 列留空。
- 种子分配确定性：`pair_index = 第 k 对（0 起）`，该对种子区间 = `[seed_start + k*games_per_pair, +(k+1)*games_per_pair)`，连续不重叠、与执行顺序无关。
- 结果库三层表零 schema 变更；失败局照常落 `games.error` 不拖垮分组。
- 每格 500 局单格 Wilson CI ≈ ±4.4%，真实侧最小 n=48（CI ≈ ±14%）——模拟侧精度高于真实侧（用户决策 2026-10-03）。

## 5. 偏差表报告（report/calibration.py + `bfsim calibration <group_name>`）

- 输入：结果库 group_name 下 36 子实验 + ptcgdb SDK `stats_matchup` 只读拉取真实矩阵（§2 口径参数）。
- 输出 72 有向格逐格：`sim_wr (+Wilson CI) ‖ real_wr, real_n ‖ Δ = sim − real`，按 |Δ| 降序；平局/失败局数单列。
- 汇总行：加权平均 |Δ|（权重 = real_n）、CI 覆盖真实 WR 的格数占比、最大偏差格。**不设死阈值**，如实呈现。
- meta 全要素回显：group_name、种子区间、代码版本、db 数据版本与口径哈希、窗口、局数。
- 缺格防御：某池格真实侧无行（低于 min-n 或不存在）→ 该行标「真实侧缺数据」不报错。

## 6. 一期验收清单（WP4）

- 全量 pytest 绿 + ruff 零告警。
- 确定性复核：matrix 子实验抽样（≥2 格）串行 vs 并行逐局 hash 一致。
- 数据契约：主库只读（calibration 经 SDK 只读路径，主库零写入）。
- 覆盖声明：池内 9 套缺口 81/81 清零、DSL 定义库 101 文件、gate3 核销完毕。
- LLM 管线质量评估（PRD §10.3，见 §7）+ **二期是否批量铺开决策建议**。

## 7. LLM 管线评估素材与 Jev 调研结论（2026-10-03）

- authoring-log 全量 157 条目统计：池内批次 first_pass 率（批 5–8 全 34/34；批 9 严格口径 0/8，YAML 零返工）、已核销卡 human_edit_lines 累计 0、gate3 核销 80/157 + 早期试验卡 77 条封存不核（2026-09-20 用户裁决）。
- **Jev 调研结论（不引入）**：TypeSafe AI「System One」决策模型（2026-09-15 发布）——不生成文本，仅对预定义选项输出类型化决策。对照本项目两个 LLM 触点均不匹配：①DSL 编写是纯生成任务，范式直接排除；②Agent 决策层（`observe -> action` 有界选项）范式虽吻合，但撞三条硬约束——种子确定性（远程概率模型输出不可钉版本、不可复算，硬验收否决）、无外部服务依赖（AGENTS.md 硬性规矩）、规模不经济（18,000 局 × 每局数百决策 ≈ 数百万次 API 调用，每次 0.1–0.5s，对比本地基线 100 局 4.4s）。另：发布仅两周，第三方实测与参考 LLM 一致率仅 ~67.8%。
- 二期建议方向：LLM 铺开维持生成式 harness 路线；Jev 类决策模型记为观察项（前提 = 可钉版本 + 可本地运行的 Jev-like 开源模型成熟后，评估点 = Agent 策略层而非引擎）。

## 8. 测试计划（TDD）

- matrix 展开：36 对枚举、种子区间连续不重叠、与 decks/variants 互斥校验、确定性（同定义两次展开一致）。
- 池 loader：en_archetype 必填校验、9 条映射完整性。
- calibration 报告：合成结果库逐项对拍（含平局分母剔除、失败局标注、真实侧缺格行、|Δ| 排序、汇总加权）；真实侧数据以固定 fixture 注入（测试不打真库）。
- CLI e2e：`bfsim run` matrix 定义小规模（games_per_pair=2）端到端 + `bfsim calibration` 合成库出表。
- 速度基准门：正式跑批前先跑 1 对 × 50 局测速，推算 18,000 局总耗时；若远超预期（>2 小时）回报用户再定并行度/局数。

## 9. 流程

沿用惯例：主会话立项 + TDD 任务书 → 子代理实现 → 主会话独立复验 + 规格/质量复核 → 正式跑批 → 落账（STATUS.md + tasks/task 030.md → done/）。口径决议（§2）与映射表（§3）先落文档请用户核销，再开工 WP2 跑批。
