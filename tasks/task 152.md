# task 152 · BC+RL 混合栈（BC 阶段，PRD §4 task 152）

- 状态：**预注册已冻结（2026-11-21）——待开工**
- 关联：四期 PRD §4 task 152 + 预注册验收标准/kill criteria（成本门已放宽）；
  task 151（数据集 `results/m16-flywheel-v1/`，质量门 5/5 过已归档）；
  task 058/062（M12 BC 设施与 v2 特征路径）；task 127（联赛设施 BT-MLE，31 测在档）；
  task 149（吞吐 spike，R2 可行）；task 126 no-go（价值网不入列，已定案）；
  task 145/150（蒸馏 v2 资产词表锚 v1 的教训——本任务以 v2.x 池重建词表）

## 目标

BC 自蒸馏（教师 = task 151 种群混合数据集）→ 联赛提升门判读。**RL 微调
（PPO/TrueSkill）不在本任务书范围**——BC 门过后另起预注册（PRD kill
criteria 以 BC 后联赛读数为第一道停损点）。

## 预注册（2026-11-21 冻结，判据跑数前不得变更）

- **数据源**：`results/m16-flywheel-v1/` 全量 147,635 行（教师 = 种群混合
  口径：mcts 46.6% + heuristic 53.4% 行全入列）；行级 `agent` 键不进特征、
  训练 meta 记录配比（消融候选，不阻塞主训练）。词表外卡名显式报错（不猜）。
- **特征路径**：task 062 v2 路径（`policy_state_features` /
  `policy_action_features`）；`card_vocab = build_card_vocab(
  config/target-pool.v2.yml, db)`——v2.x 池锚定，封堵 task 145/150 词表
  漂移教训；资产 format = `bf-distilled-policy-v2`（既有分派纪律，v1/v2 旧
  资产装载不动）。
- **训练设施**：复用 `bfsim train-policy`（torch dev-only D3-3；runtime
  numpy-only D3-4 训练非复算面延续；权重 JSON 进版本控制）。超参沿用 M12
  钉死缺省（epochs 100 等），任何偏离须在 WP2 前写进本任务书并披露。
  训练随机源种子域 **1100000+**（与采集域 1020000+ / 探针域 800000+
  不重叠，PRD v0.7 条款 c）。
- **BC 阶段质量锚（报告锚，非门槛）**：装载冒烟（v2.x 卡组跑局零错误）+
  一致率读数（task 059 口径：学生行动 vs 数据集教师行动）+ kind 级分布
  落 dig。M12 v2 参照（use_ability 20.9% / 锚 1 88.8%）仅作对照不门槛。
- **提升门（PRD 钉死，终判）**：Elo 联赛（task 127 设施，BT-MLE 主估计子，
  CRN 双向配对）——BC 学生 vs 启发式净胜 CI 下界 > 0，且相对**纯 MCTS
  2×50 教师（联赛基线锚）**中位 Elo 差 > 0。评测可加跑深预算档。
- **评估预算（2026-11-21 WP3 前冻结，预注册纪律）**：注册表
  `experiments/t152-bc-league.example.yml`——agents {heuristic-base,
  mcts-2x50-v3cut（= task 151 教师同款 2×50 cap50 + eval-linear-v3 截断 10，
  联赛基线锚可比性）, bc-student} × v2.x 池 10 decks × `games_per_cell=8`
  × ab/ba 双向 = 60 细胞 480 局（MCTS 教师参赛 320 局）。成本核算：MCTS 局
  ~9.65 min（578.9s 实测）× 320 ÷ 16 workers ≈ 200 min 独占口径，桌面争抢
  ~2.3× → 整夜档 ~8-9h。功效披露：每无序对 160 局（CRN 双向配对对冲先手
  偏差）；判读落 inconclusive 带（CI 覆盖 0 且 |点估计| ≥ 3pp）→ Owner
  预算修正案，不得临场加局。
- **Kill criteria（PRD 钉死，任一触发即停损，回 M15 水平线，管线资产留档）**：
  BC 后联赛对启发式无显著优势（CI 覆盖 0 且点估计 < +3pp）；或吞吐不达标
  且 spike 估期 > 6 周（task 149 已解除，不适用）；或训练非复算面声明
  无法维持。
- **成本门**：训练一次完整迭代单机 ≤ 21 天（BC 单轮预期分钟级——147,635
  行小数据 + row_to_sample 一次性合法行动重枚举；实测落 dig）。

## 验收标准（测试清单）

1. 数据管线：全量 147,635 行 `load_policy_samples(card_vocab=v2.x)` 转换
   零报错（教师行动不在合法列 = 0）；`agent` 键兼容（行格式扩展不破坏
   task 052/058 装载）；词表 = v2.x 池 10 套卡组并集（数量落 dig）。
2. 训练冒烟：迷你子集（如 1 对文件）端到端训练 + 资产落盘 + 装载 +
   `type: distilled` 跑局零错误（v2.x 卡组）。
3. 正式训练：全量训练落 `models/policy-m16-bc1.json`（或修订名），meta
   完整（feature_version/pool/seed/数据版本），墙钟与 loss 落 dig。
4. 联赛评估：注册表 schema 经 task 127 设施核验（复用其 31 测锚），
   BT-MLE 评级报告 + 提升门判读落 dig。
5. 全量 pytest 绿 + ruff 零告警；既有行为零变化（train-policy 缺省路径
   与联赛缺省路径）。

## WP 拆分

- **WP1 数据管线核验**：全量样本转换 + 词表构建 + 分布统计（kind/agent/
   per-pair）落 dig `docs/digs/2026-11-2X-t152-bc-data.md`。
- **WP2 BC 训练**：冒烟（迷你子集端到端）→ 正式训练（超参若偏离 M12
  缺省先修订本文档）→ 资产 + meta + 质量锚读数落 dig。
- **WP3 联赛评估面**：注册表 yml 设计（schema 核验 + MCTS 教师格成本核算）
  → 评估预算写入本文档冻结 → `bfsim league` 跑批 → BT-MLE 报告。
- **WP4 判读收口**：提升门 + kill criteria 判读 → dig 终判 → CHANGELOG /
  STATUS → 归档（RL 阶段另起任务书预注册）。

## 结果与遗留

（待填）
