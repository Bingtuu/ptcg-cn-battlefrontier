# task 052 · M11 WP3：MCTS rollout 截断接入 + 决策一致率 harness

- 状态：进行中
- 关联：M11 设计文档 D-M11-4（截断接入 + 视角映射）/ D-M11-5（一致率测量）；
  task 051 WP2（`battlefrontier/learn/` 推理接口 + `models/eval-linear-v1.json`）

## 目标

1. 学得评估器接入 MCTS rollout 浅截断：`turn >= root_turn + K` 时返回 V 估值
   （默认禁用 = 行为零变化，events_hash 回归纪律）。
2. 决策一致率 harness：教师（2×50 纯搜索）跑局落决策点快照（序列化 GameState +
   教师结构化 Action），离线重放受测配置（降预算 + 评估器）比对 argmax。

## 验收标准（测试清单）

1. **默认路径零变化**：`eval_cutoff_turns` 默认 0（禁用）时全量确定性回归绿
   （既有 events_hash / 逐局一致测试不动通过）
2. **截断语义**：K > 0 且评估器已装载时，`turn >= root_turn + K` 返回评估值；
   `rollout_turn_cap=50` 的 0.5 兜底保留——K ≥ cap 时评估器永不触发（行为与
   纯 cap 一致，测试对拍）
3. **视角映射**（D-M11-4）：V 恒从截断时刻行动方视角求值；root_player == 行动方
   → V，否则 → 1−V（单测两种情形）
4. **不猜纪律**：评估器资产路径配置了但加载失败 / 特征清单不符 → 显式报错
   （复用 `learn.model.load_model` 既有校验）
5. **快照采集**：教师配置跑局时在符合条件的决策点落快照 JSONL（序列化 GameState
   往返 + 教师结构化 Action 往返，既有序列化先例对齐），落 `results/m11-eval/`
   （不落结果库，D-T4 先例）；采集开关默认关 = 行为零变化
6. **一致率统计**：离线载入快照 → 同状态跑受测配置 → 结构化 Action argmax 比对；
   分母口径 v1 = main 阶段教师选定行动 kind ∈ {attack, play_trainer, end_turn}
   的决策点，剔除唯一合法行动早退点（mcts.py:127-130 不产生考虑）；
   choose/promote/setup 类及其余 main 行动类（retreat / evolve / use_ability /
   attach_energy 等）不进分母，计数记附录字段
7. **确定性**：同快照文件 + 同受测配置两跑一致率逐一致（学生搜索种子协议钉死，
   如按快照序号派生）
8. 全量 pytest 绿 + ruff 零告警

## 实现要点

- 子代理 TDD + 主会话独立复验
- 插入点：`agent/mcts.py` `_rollout`（cap 判定 ~237-239 行）；`MCTSAgent` params 增
  `eval_cutoff_turns`（默认 0）+ 评估器资产路径（experiment.py 透传模式对齐
  card_effects）
- 评估调用在 determinized 克隆上对截断时刻行动方构造可见视图（隐藏信息已重采样，
  信息纪律）；`learn.model.predict` 双入口（view 或特征 dict）按开销选用
- 一致率 harness CLI 形状按 cli.py 既有惯例自定，但采集 / 评估两步须可独立调用
  （快照是数据资产，评估可换配置重放）
- 冻结面：tune/ 全模块；learn/ 只读复用（缺能力报主会话，不自改）；其余 task 050/051
  已交付文件只读复用

## 结果与遗留

- **截断接入（D-M11-4）**：`agent/mcts.py` —— `MCTSAgent` 增 `eval_cutoff_turns`
  （默认 0 = 禁用，行为零变化）+ `evaluator_path`（装载即走 `learn.model.load_model`
  全量校验：format / 特征清单 / 维度 / std，不符显式报错不猜；K>0 无路径报错）。
  `_rollout` cap 判定后插截断分支：`turn >= root_turn + K` → 对截断时刻行动方
  `visible_state` 求 V（纯函数零随机源），root==行动方 → V，否则 → 1−V；cap 判定
  在前，K ≥ cap 时 0.5 兜底先行、评估器永不触发（与纯 cap 对拍一致）。注意：
  `state.turn` 是**轮计数**（双方各行动完一轮 +1），K 语义 = 行过 K 轮。
  `runner/experiment.py`：MCTS_PARAMS 增两键，AgentCfg params 值域放宽 str。
- **快照采集（D-M11-5）**：`agent/snapshot.py` SnapshotCollector（只落教师实际搜索
  的决策点——consideration 非 None，早退口径天然剔除）；`runner/play.py` 增
  `snapshot_collector` 钩子（默认 None 零变化，GameResult.snapshot_rows）；
  `runner/snapshot.py` 产线（worker + 批量驱动，配对装载/种子区间/失败局剔除全复用
  task 050 口径）。落盘 `<out>/pair-*.jsonl`：首行 header（pair/种子区间/卡组/
  card_effects/教师预算——评估侧自包含，无需 db），其后每行 record=snapshot
  （序列化 GameState + asdict(Action) + turn/phase/player/action_kind/n_legal/seed）。
- **一致率评估（D-M11-5）**：`runner/agreement.py` —— 重建 GameState 置引擎 →
  受测配置 MCTSAgent bind_engine 重放 → 结构化 Action dataclass 值比对（不用
  字符串标签）。分母 v1 = main 阶段 attack/play_trainer/end_turn；非 main 与
  其余 main 行动类进 appendix 计数；教师行动不合法单列计数（对拍安全网）。
  种子协议：学生种子 = sha256(config_fingerprint:快照序号)[:8] LE，
  fingerprint = 受测配置规范 JSON sha256 前 16 hex，两者钉死进报告。
- **CLI**：`bfsim collect-snapshots`（pool/局数/种子锚点/教师预算）与
  `bfsim agreement <快照> --worlds --iterations [--eval-cutoff-turns K --evaluator P]
  [--output]`（两步独立，评估可换配置重放同一份快照）。
- **验收**：新测试 36 条（test_mcts_eval_cutoff 11 / test_snapshot 12 /
  test_agreement 13）；全量 pytest 绿（1216 → 1252）+ ruff 零告警；
  真实池 CLI 冒烟（沙奈朵×喷火龙大比鸟 1 局 1×1 教师 → 178 快照 → 重放评估）。
- **主会话复验**：mcts.py `_rollout` 截断分支亲读核实（cap 判定在前 / 视角映射
  正确 / 纯函数零随机源）；`state.turn` 轮计数口径确认（core.py:2309 仅先手方回合
  开始 +1）→ 设计文档 D-M11-4 加口径补注（K ≈ 2K 单方回合，扫描网格不变，措辞
  澄清非口径变更）；turn_norm 训练/推理同计数源无分布失真；冻结面 git diff 实证
  干净；主会话亲自复跑全量 pytest + ruff 见下（复验通过后归档）
- **遗留（WP4，task 053 域）**：K×预算扫描 + 双锚验收跑批（一致率 ≥0.85 +
  定点格 CI 覆盖）；快照行含完整 GameState 体积较大（每行几十 KB），WP4 定点格
  小规模采集无碍，全池规模化时需留意
