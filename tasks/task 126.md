# task 126 · 价值网进搜索（MCTS value_guide）

- 状态：**待启动**——激活条件 = P1 loop 出口（M14 gate 过门，spec §2 判据）；gate 不过门则本任务保持冻结
- 关联：四期 PRD `docs/superpowers/specs/2026-11-14-phase4-prd-design.md` §3 M15 任务拆分；M11 评估器资产 `models/eval-linear-v1.json`；M15 gate（spec §3：过门 = B2 立项依据 +1，不过门 = 价值网路线留档关闭、B2 改 BC 主入口）

## 目标

把 M11 学得评估器接入 MCTS 树策略：value-informed 子节点选择（rollout 深度截断 `eval_cutoff_turns` 已有，本任务接树内 value）。动机 = Pass 2 盲点 B1：评估器从未接入搜索引导，先小步验证再决定是否开 M16 主注。numpy runtime 纪律不破（引擎/agent runtime 零 torch import，D3-3 核销口径延续）。

## 验收标准（预注册判据，跑批前冻结；成本门为 Owner 2026-11-14 拍板放宽口径）

1. **净效应门**：`value_guide=on` 的 MCTS（2×50 同预算）对启发式 agent 池，在 ≥3 个指定格上 CRN 成对净胜率 CI 下界 > 0；**加评一档 4×100 深预算格**（价值引导的预期优势区间）；判据冻结前显式列出格选择与理由；
2. **成本门（放宽后）**：单局墙钟 ≤ 基线 MCTS ×3（原 ×1.5）；深预算档另计、不设倍数门；
3. **行为门**：同种子开/关 `value_guide` 的 events_hash 等价（观测事件口径，task 122 纪律——观测事件流零变化，决策内部分布可变）；
4. **开关纪律**：`value_guide` 默认关，实验定义显式开；yaml 词表/schema 白名单同步（开放字符串纪律）；
5. 全量 pytest 绿 + ruff 零告警；既有 MCTS 测试零改动（只加不改）；CHANGELOG Unreleased 记账。

## 实现要点

- 评估器装载复用 M11/M12 资产分派惯例（JSON 权重 + format 校验）；输入特征层 = VisibleGameState 30 维（信息纪律不破：树内 value 只用可见视图特征）
- 接点：UCT 子节点选择公式加 value 项（具体加权方式实现期定，写入设计段）；克隆 determinize 路径不动（task 039 冻结集纪律）
- 预注册脚本留档（`.kimi-code/` 惯例），判据数值可原样重放

## 结果与遗留

（待填）
