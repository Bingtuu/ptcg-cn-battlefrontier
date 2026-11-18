# task 155 · 评估器特征 v3（BC 开工门修复候选，v0.6 新增）

- 状态：**进行中（2026-11-18 立项，Owner 裁决 task 150 停损评审选项 A）**
- 关联：四期 PRD §4 v0.6 修订（task 155）；task 150（FAIL 归因 = 特征层失明，dig：`docs/digs/2026-11-18-t150-eval-v2x-retrain.md`）；task 062（policy-v2 +112 维卡身份特征把 use_ability 从 0.009% 救到 20.9%——本任务移植思路）；task 145/t150（探针协议与冻结 gate 脚本 `.kimi-code/t150_eval_gate.py`）；D-062-1（不动钉死清单、独立成册先例）

## 目标

task 150 已干净归因：v2.x 对决 AUC 0.6743 ≈ v1 资产 0.6755（in-distribution 重训零提升）→ 瓶颈是 30 维特征层对 v2.x 新机制状态（lock_play / status_immunity / 工具交互 / 赛场阻断等）失明，不是数据分布。本任务把评估器特征扩维到 v3（弃牌构成 + 卡身份分区计数），重训 + 同探针重判，争取过 task 150 门（v2.x AUC ≥ 0.90），解除 BC 教师种群信号源折扣。

## 预注册（2026-11-18 立项时判据冻结——跑数前不得变更）

- **特征层 v3（新模块 `battlefrontier/agent/eval_features.py`；M11 `FEATURE_NAMES` 30 维与 `policy_features` 既有常量只读复用、绝不修改——D-062-1 纪律）**：
  - 基座 36 维 = M11 原序 30 维 + 弃牌构成 6 维（复用 `DISCARD_FEATURE_NAMES` 口径：双方弃牌 count/能量数/宝可梦数）；
  - 卡身份分区计数 4 区 × 词表：区 = `own_hand`（己方手牌卡名计数）/ `own_board` / `opp_board`（active+bench 的进化栈 + 附着能量 + 附着道具卡名计数，复用 policy_features 的 `_pokemon_cards` 口径）/ `stadium`（在场竞技场 one-hot，无场全零）；键名 `cid_<区>_<卡名>`；
  - 词表 = `build_card_vocab(pool_path, db)`（卡池全部卡组卡名去重 + 字典序；v2.x 池实测 **131 词**：66 宝可梦 / 52 训练家 / 13 能量）→ v3 维度 = 36 + 4×131 = **560**；词表外卡名显式 ValueError（不猜）；
  - 信息纪律：全部只读 `VisibleGameState` 可见区域（与 features.py 同口径）；对手侧只有盘面/弃牌（公开）+ 手牌 count——对手手牌身份不进任何特征。
- **数据行紧凑格式**（v1 dict 行与采集默认行为零变化）：v3 数据文件首行 header `{"type":"header","format":"bf-collect-v3","feature_names":[...]}`（词表随池钉进文件，自包含）；数据行 `features` 为位置对齐 float list。动机：560 维 × ~400 万行若 dict 键名重复落盘 ≈ 50GB+，位置格式压到 ~1/4（JSONL 文本锚点纪律不变）。
- **数据（与 task 150 同分布同种子，单变量 = 特征层）**：`bfsim collect-features --pool config/target-pool.v2.yml --games-per-pair 1200 --seed-start 960000 --out results/m11-v2x-v3data --workers 16 --feature-set v3`（45 对 × 1200 = 54,000 局，种子域/对局流与 results/m11-v2x-data 完全一致，仅特征行不同）。
- **训练（numpy float64 路径，PRD v0.6 背书）**：`bfsim train-eval --data results/m11-v2x-v3data --pool config/target-pool.v2.yml --out models/eval-linear-v3.json --feature-set v3`——分块（chunk=50,000 行钉死）两遍流式（pass 1 mean/std，pass 2 XᵀX/Xᵀy 分块 np.dot）；按局划分 / split_seed / 按局抽样 / 死维度警戒全沿用 v1 钉死口径；**λ 候选扩为 {0.1, 1, 10, 100, 1000, 10000}**（预注册声明：维数 30→560 改变 XᵀX 尺度、λ 语义漂移；选择规则不变 = 验证 MSE 最小、并列取小 λ）；确定性声明 = 同环境同输入逐位确定，训练非复算面（D3-4 延续）。
- **资产格式 `bf-linear-eval-v3`**：meta 必含 `card_vocab` / `zones` / 全量训练落账；`load_model` 分派（v1 format 校验路径逐字不动，eval-linear-v1/v2 保持可装载）；`predict(view)` 对 v3 资产走 `feature_vector_v3(view, vocab, zones)`——**冻结 gate 脚本 `.kimi-code/t150_eval_gate.py` 不动**，其 `load_model`+`predict` 调用面必须原样工作。
- **过线判据（钉死）**：主门 = 冻结脚本 v2.x 对决（mik_moe:711854 沙奈朵 × 676344 多龙巴鲁托黑夜魔灵，20 局 seed 800000..800019）**AUC ≥ 0.90**；健康门 = 验证 MSE < 常数基线（无死维度警戒）；对照臂（非门，落账）= v1 对决读数（v2 资产参照 0.9659）+ v1 资产 v2.x 读数 0.6755（不变）。
- **FAIL 处置**：不回滚 v1/v2 资产（保持可装载）；回 M16 BC 停损评审（Owner 裁决），task 151/152 维持冻结；**不自动续命**（不得「再采一批数据重试」——数据分布已被 task 150 排除）。

## 验收标准（测试清单）

1. `tests/test_eval_features_v3.py`（新）：36 基座维键序与 M11 原序逐一相等；4 区卡身份计数正确（手牌/双方盘面含进化栈+能量+道具/竞技场 one-hot）；词表外卡名 ValueError；对手手牌身份零泄漏（构造视图断言无对手手牌卡名贡献）；零随机零引擎调用。
2. `tests/test_collect_v3.py`（新）：header 行格式校验（feature_names 与行宽度不符显式报错）；位置对齐 round-trip（v3 特征 dict → list → dict 逐位一致）；`--feature-set` 缺省 v1 行为逐位不变（v1 回归锚）。
3. `tests/test_train_eval_v3.py`（新）：分块两遍流式与全量矩阵参考实现 XᵀX/Xᵀy 对拍（np.allclose  tight 容差，固定小数据）；λ 候选扩展后选择规则（最小验证 MSE、并列小 λ）；v3 资产 round-trip（save/load/predict）；v1 数据喂 v3 训练显式报错、反之亦然。
4. `tests/test_model_v3_dispatch.py`（新，`learn/model` 扩展）：v1 format 装载校验逐字不变（v1/v2 资产回归测试绿）；v3 format 装载 + meta 缺 card_vocab/zones 显式报错；`predict(VisibleGameState)` 对 v3 资产走 v3 特征层且输出 ∈ [0,1]。
5. 全量 pytest 绿 + ruff 零告警；既有行为零变化（采集/训练默认 v1 路径逐位不变）。
6. 跑批三连：采集 54,000 局零失败 → 训练健康（验证 MSE < 基线）→ gate 判读落账（PASS/FAIL + 对照臂读数）。

## 实现要点

- WP1 特征层：`battlefrontier/agent/eval_features.py`（`EVAL_V3_ZONES` / `eval_v3_names(vocab)` / `feature_vector_v3(view, vocab, zones)`；`_pokemon_cards` 从 policy_features 导入复用）。
- WP2 采集：`FeatureCollector` 增可选 `feature_set`/`vocab`（默认 None = v1 逐位不变）；`runner/collect.py` 写 header + 位置行；CLI `--feature-set`。
- WP3 训练：`battlefrontier/learn/train_v3.py`（分块流式 loader + numpy 岭回归 + 同口径 split/警戒/meta）；`train-eval` CLI `--feature-set` 分派。
- WP4 资产分派：`learn/model.py` 增 `MODEL_FORMAT_V3` + 装载/预测分派（v1 路径不动）。
- WP5 跑批 + 判读 + dig 报告 + 收尾（CHANGELOG / STATUS / 归档）。

## 结果与遗留

（待填）
