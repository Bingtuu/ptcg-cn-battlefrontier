# task 126 · 价值网进搜索（MCTS value_guide）

- 状态：已收官（2026-11-17）——**净效应门 FAIL，按 PRD 条款 4 no-go 留档关闭**（判决 dig：`docs/digs/2026-11-17-t126-value-guide-net-effect.md`）
- 关联：四期 PRD `docs/superpowers/specs/2026-11-14-phase4-prd-design.md` §3 M15 任务拆分；M11 评估器资产 `models/eval-linear-v1.json`；M15 gate（spec §3：过门 = B2 立项依据 +1，不过门 = 价值网路线留档关闭、B2 改 BC 主入口）

## 目标

把 M11 学得评估器接入 MCTS 树策略：value-informed 子节点选择（rollout 深度截断 `eval_cutoff_turns` 已有，本任务接树内 value）。动机 = Pass 2 盲点 B1：评估器从未接入搜索引导，先小步验证再决定是否开 M16 主注。numpy runtime 纪律不破（引擎/agent runtime 零 torch import，D3-3 核销口径延续）。

## 设计段（实现期定项落笔，2026-11-16 预注册）

- **接入点（PRD 指定）**：UCT 子节点选择公式加 value 项——`_ucb_select` 增 `w_v · V(child)`，V = 展开时刻子节点状态的评估器估值（**root 视角**，与 wins 同向存储，对手节点翻边口径与 mean 一致）。
- **V 的计算时点**：节点展开（expansion）时一次性求值缓存（`_Node.v_raw`），选择/回传阶段零评估器调用；V 从 determinized 克隆的 `visible_state(该节点行动方)` 纯函数求值（D-M11-4 同款纪律：信息纪律不破、零随机源消耗）。V 只影响树内分布，决策外行为零变化。
- **加权**：`value_guide_weight`（默认 0.5，预注册验收跑批钉死 0.5）；`value_guide: true` 必填 `evaluator_path`（复用 `load_model` 强校验装载，与 `eval_cutoff_turns` 共用同一资产，不猜）。value_guide 默认关（行为零变化纪律）。
- **词表**：`MCTS_PARAMS` 增 `value_guide`（bool）/`value_guide_weight`（float），yaml schema 白名单同步；未知参数照旧显式报错。
- **行为门口径（预注册）**：value_guide 内部分布可变、观测事件流零变化——验收 = 同种子 `value_guide=on, weight=0` vs `off` 一批对局 events_hash 逐局全等（评估器永不触发路径之外，唯一差异源被钉零；评估器调用本身只读可见视图纯函数，无事件/随机源副作用）。既有 MCTS 测试零改动（只加不改）。
- **已知限制（task 145 拍板输入折扣项）**：评估器 eval-linear-v1 在 v2.x 漂移实证（AUC 0.676 vs v1 0.972，非坍塌）——净效应判读按漂移折扣；蒸馏 policy v2 不可用与本任务无关（不接入）。
- **净效应门格选择（预注册，MCTS 固定执 沙奈朵 711854 = t141/t146 目标卡表）**：
  - C1 vs 676344 多龙黑夜（field 头部 23.9%、决胜格、base 52.6% 最难格）
  - C2 vs 677291 电电虫（12.4%）
  - C3 vs 711855 玛俐（11.6%）
  - 深档加评：C1 4×100（价值引导预期优势区间，PRD 条款 1）
  - 理由：三对手 = field-snap-2026-11 前三份额且为 t141 深挖格（基线读数在档）；同卡表 = t146 标签集同底板，机制结论可与门槛实验互参。
- **跑批口径**：CRN 逐种子配对（on/off 同 seed 区间 700000..，与 t141/t146 种子域 470000/600000-630000、t145 500000+ 不重叠）；每格 400 局 × 2 臂（判读功效 ±~3.5pp 半宽级），深档 200 局 × 2 臂；预算门 = 单格墙钟超 task 097 先例 2 倍即按部分交付判决（不得续命加跑）。
- **成本门**：同格同局数 on/off 墙钟比 ≤ ×3（task 126 预注册）。
- **预注册脚本**：`.kimi-code/t126_net_effect.py`（CRN 配对 McNemar + CI 下界判读 + 墙钟比），判据数值可原样重放。

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

**判决（2026-11-17）：三门槛 1/3 过——净效应门 FAIL → PRD 条款 4 no-go 留档关闭。** 完整判读见 `docs/digs/2026-11-17-t126-value-guide-net-effect.md`，可重放（结果库 `results/t126-net-effect.db` + 判读脚本 + 两份判读 JSON）。

| 门槛 | 判据 | 实测 | 判定 |
|---|---|---|---|
| 净效应门 | ≥3 标准格 CI95 下界 > 0 | 1/3（仅 C2 电电虫 +6.75pp [+1.68, +11.82]；C1 +1.25pp [−4.27, +6.77]；C3 −1.0pp） | **FAIL** |
| 成本门 | on/off 墙钟比 ≤ ×3 | 1.31 / 1.03 / 0.99（深档 0.91） | PASS |
| 行为门 | weight-0 臂 vs off events_hash 全等 | 15 单测覆盖 | PASS |

- **处置（条款 4）**：价值网路线留档关闭；**task 127 不激活**；value_guide 维持默认关（代码保留，行为零变化纪律不破）；B2 改以 BC 为主入口。
- **加评**：深档 C1（4×100）+4.0pp [−2.48, +10.48]——方向正但不显著，作机制存在性的弱信号留档，不构成翻案依据。
- **限定语**：① 功效——n=400 下 CI 半宽 ±5.5pp，「不显著 ≠ 机制无效」，C2 显著正向说明评估器校准良好的格内机制有真实信号；② 评估器漂移折扣（task 145：eval-linear-v1 v2.x AUC 0.676）——FAIL 不可区分「机制不行」vs「评估器 v2.x 上不行」；③ 全部读数为启发式自对局口径。
- **留档资产**：实现（commit `144b2f5`）+ 预注册判据 + 全量跑批数据 + 本判决；若未来评估器在 v2.x 重训（AUC 回升），value_guide 重验是低成本候选（换 evaluator_path 即可），但须重新预注册。
