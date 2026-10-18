# task 056 · M12 任务书立项 + 依赖开口（torch dev-only + numpy runtime）

- 状态：进行中
- 关联：三期 PRD §3.2（M12 主线）+ §7 第二组开放问题；D3-3（torch 开口
  推迟项，本任务核销）；D3-4（训练非复算面声明）；M11 达成（task 049–055，
  2026-10-18 用户确认）；实现接入面摸底 `.kimi-code/m12-decision-prep.md` §4

## 拍板定案（2026-10-18 用户「开工」口径）

1. **M11 里程碑终判确认**（STATUS 里程碑段已补 ✅ M11 行）
2. **依赖开口选项 A**：torch dev-only（训练侧，入 dev extras）+ numpy 升
   runtime 依赖（推理侧前向）——D3-3 原口径核销
3. **训练非复算面声明（D3-4 连带）**：torch 训练含不可锁随机源（BLAS/
   cudnn 非确定性）→ 训练过程不要求复算；模型权重 JSON 进版本控制即锁定，
   推理侧（numpy 前向 + 合法行动掩码）确定性不受损，events_hash 纪律延续
4. **教师预算档 2×50**（预研估算 10⁴ 局 ≈ 23.4h；task 055 实测 2×50 K=10
   单局 ~9.2min@16workers，教师 K=0 纯搜索更慢——试点先校准实测速率）
5. **采集规模 10³ 试点先行**（~5.5 万决策点 @55 点/局，task 042 实测）；
   试点验收后再定是否扩 10⁴ 全量

## M12 工作分解（WP 预告，后续 task 逐段立项）

- WP1 教师数据采集：复用 task 052 快照产线（bf-m11-snapshot-v1 = 教师实际
  搜索决策点 + 结构化 chosen Action + 完整 GameState，硬标签行为克隆够用）；
  试点 = 卡池 v1 定点配对 × 10³ 局 2×50 K=0 纯搜索教师
  （软标签/分布蒸馏缺口 = SnapshotCollector 丢弃 consideration.considered，
  试点不堵，扩量前评估）
- WP2 状态-行动特征化 + torch 训练管线：状态 30 维（features.py
  FEATURE_NAMES 复用）+ 行动侧特征（action kind + 关键牌计数）→
  per-action 打分 + 合法行动掩码 softmax；torch 训练脚本（dev-only）→
  导出权重 JSON（新 format `bf-distilled-policy-v1`，D3-4 进版本控制）
- WP3 `type: distilled` Agent 接入：AGENT_TYPES + _build_one 显式分支 +
  AgentCfg 专属 params 白名单（防静默落 RandomAgent）；推理 = numpy 前向 +
  掩码 argmax；默认路径零变化 events_hash 回归
- WP4 双锚验收：①matrix 复校准（学生双侧）加权 |Δ| ≤ 9.7%；②学生 vs 教师
  决策一致率（阈值按 M11 相对口径先例定——教师异种子自一致率天花板
  0.40–0.46，绝对阈值不可达）；③全 matrix 学生口径跑批墙钟分钟级

## 本任务范围（立项 + 依赖开口落地）

1. pyproject.toml：runtime 加 `numpy>=2`；dev extras 加 `torch`（CPU wheel）
2. `.venv` 实装 numpy + torch（CPU 版），冒烟：import + 前向小算例
3. 确定性纪律复核：torch 仅训练侧 import（learn/ 训练脚本），engine/agent
   runtime 路径零 torch import（ruff/测试层防回流）
4. AGENTS.md 技术栈段更新（依赖变化落账）

## 验收标准

1. pyproject.toml 依赖开口落地 + `.venv` 实装冒烟通过（torch CPU 可用）
2. runtime 路径（battlefrontier/ 非 learn 训练侧）零 torch import 实证
   （grep + 全量 pytest 绿——测试环境含 torch 但引擎路径不引用）
3. 全量 pytest 绿 + ruff 零告警
4. STATUS.md（M11 ✅ 行 + 当前段）+ AGENTS.md 落账；本任务档归档 done/

## 结果与遗留

- **依赖开口落地**：pyproject.toml runtime +`numpy>=2`（推理前向）、dev extras
  +`torch>=2`（训练侧 dev-only）；`.venv` 实装 numpy 2.5.4 + torch 2.14.1+cpu
  （CPU-only 版，PyPI Windows 轮即 CPU 构建；直连源过慢切清华镜像，68s 装完）
- **冒烟通过**：import + MLP 前向小算例 + numpy 矩阵算例；torch CPU-only
  确认（cuda False）
- **runtime 路径零 torch/numpy import 实证**：grep battlefrontier/ 零命中
  （防回流基准；后续 WP 的 torch 仅限 learn/ 训练脚本）
- **验收复核**：1252 pytest 全绿 + ruff 零告警（装依赖后基线不变）
- **落账**：STATUS.md（✅ M11 里程碑行 + 当前段 M12 拍板口径）+ AGENTS.md
  （当前状态段 M11 收官 + 技术栈段 numpy/torch 开口 + 训练非复算面声明）
- **遗留**：M12 WP1 教师数据采集立项（task 057）：collect-snapshots 接口
  已备查（--pool --games-per-pair --seed-start --out --workers，教师双侧
  MCTS 2×50，pair i → 种子 [S+iN,+N)）；试点配对选择与种子区间（避开
  300000–400799 训练段与既有锚点段，候选 600000 起）在 task 057 定稿
