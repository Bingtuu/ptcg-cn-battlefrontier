# task 066 · M12 处置 A 包：零采集重训（per-kind 重加权 + end_turn 双投票降噪）

- 状态：完成（2026-10-21 用户拍板：A 包证伪收口，整体维持 v2 基线，B 特征 v3 不立项）
- 关联：三期 PRD M12 backlog 处置——task 065 诊断 → 用户拍板（2026-10-21）选项 C：A 先行 + B（特征 v3）按残余决定

## 目标

在零新采集前提下（同 171k 教师快照、同 split_seed 20261018、同超参），训练侧引入两项样本加权，重训复测：

1. **per-kind 正例重加权**：治少数标签坍缩（play_stadium 命中率 13.46% 全 kind 最低、use_ability 正例被 end_turn 坍缩吞并）
2. **end_turn 双投票降噪**：利用既有 anchor1-ceiling 异种子重放数据（第二投票），教师标签不稳定（两票不一致）的 end_turn 点降权——天花板 33.6% 的 kind 不让噪声标签主导梯度

## 设计决议

- **D-066-1 kind 权重方案**：play_stadium ×3.0 / use_ability ×2.0 / 其余 ×1.0。依据：play_stadium 有效正例质量 13.5%×3 ≈ 对齐 attack 档命中率（31.5%→83.4% 一致率的既有对照带）；use_ability ×2 对治坍缩到 end_turn 的形态（69% 首选 end_turn）。系数钉进资产 meta
- **D-066-2 end_turn 降噪**：join key = (pair_index, 决策点序号 index)，数据源 `results/m12-anchor1-ceiling/pair-*.json`（教师异种子重放 = 第二投票）；两票不一致的 end_turn 点 w=0.25，一致点及其余 kind 点 w=1.0。零新采集
- **D-066-3 资产口径**：特征不动 → format 维持 `bf-distilled-policy-v2`（v2 装载路径复用）；新资产文件名 `models/policy-m12-v2w.json`；meta 增 weight_scheme 段（kind_weights + end_turn_unstable_weight + 双投票数据源锚点）
- **D-066-4 组织方式**：WP1 子代理 TDD + 主会话独立复验（task 026 起惯例）；WP2/WP3 主会话跑批
- **D-066-5 A2 降剂量（2026-10-21 用户拍板）**：v1 剂量锚 1 过冲 + 锚 2 恶化（见结果段）后的中间档——新方案 `kind-weights-v2`：play_stadium ×1.5 / use_ability ×1.25 / end_turn 双投票 ×0.5。amended 判据：判据 1/2/8 不变；**判据 3' = attack 一致率 ≥ 0.734（让位 ≤10pts）且 v1 分母整体 ≥ 0.305（降幅 ≤3pts）**；加监控项 play_stadium ≤ 0.60（防过冲超教师带）。甜点假设：零剂量 v2（坍缩）↔ v1 剂量 v2w（过冲）之间存在锚 1/锚 2 双不伤点

## 边界

- 特征层零改动（B 包特征 v3 不在本任务，视残余拍板）
- 训练侧改动限 `learn/` + CLI train-policy 参数面；engine/agent runtime 路径零行为变化（distilled 推理前向不动）
- 教师采集/重放不新增任何跑批（降噪用既有 ceiling 数据）

## 验收标准（终止判据先行）

WP1 实现验收：
1. 加权 masked softmax NLL 单元测试（权重进入损失/梯度的数值对拍；w 全 1 时与现状逐位全等）
2. 双投票 join 测试（pair+index 对齐、缺票点显式报错不猜）
3. 全量 pytest 绿 + ruff 零告警

WP2 重训复测（锚 1）：
4. double-run sha256 逐字节全等（训练确定性不损，D3-4 非复算面声明不破）
5. **判据 1**：play_stadium 一致率 ≥ 10%（破零且达可用信号档）
6. **判据 2**：use_ability 一致率 ≥ 25%（v2 的 20.9% 基础上 +4pts）
7. **判据 3**：整体一致率降幅 ≤ 1.5pts（加权不以全局崩塌为代价）

WP3 matrix 复测（锚 2/3 口径）：
8. 18000 局复跑：加权 |Δ| ≤ 13.2%（第一门槛不回退）；机制对拍 play_stadium > 0、use_ability 局均 ↑（v2 基线 4.05）
9. 确定性：det-check 串并 events_hash 全等

判据不达 → 如实记录，按 C 路线评估 B（特征 v3）立项，不硬凑。

## 实现要点

- WP1：`learn/train_policy.py` 样本权重进 NLL（掩码 softmax 后逐点 w×logp）；CLI `train-policy` 增 `--weight-scheme`（缺省 none = 现状逐位全等）；`learn/policy_data.py` 或新模块出权重向量（kind 映射 + ceiling join）；资产 meta 校验加 weight_scheme 可选段（v2 旧资产无此段仍可装载——不破坏 v1/v2 装载测试）
- WP2：同 split 重训（~13min）→ `bfsim agreement --policy` 分 kind 复测（沿用 task 062 by-kind 脚本口径）
- WP3：`experiments/m12-distilled-matrix-v2.example.yml` 换资产跑 matrix（~7.4min @18 workers）+ calibration 偏差表 + 机制对拍

## 结果与遗留

- **WP1 ✅（子代理 TDD + 主会话独立复验）**：新模块 `learn/sample_weights.py`（kind 权重表 + 双投票 join + 缺票显式报错族）+ `train_policy.py` 加权 NLL（缺省路径逐位全等）+ `policy_model.py` meta 可选段 + CLI `--weight-scheme`/`--ceiling-dir`；27 新测试，**全量 1402 绿 + ruff 零告警**（主会话亲跑）
- **主会话复验关键项**：①join 口径——任务书原描述「index = agreement 评估点序号」写反，子代理按实证纠正为「index = 快照文件行号」（agreement.py:118 `enumerate(snapshot.rows)`），主会话独立验证 pair-0 全量 1473 行 kind 零错位，批准；②权重-样本序对齐（`_split_by_game` 保序 + zip strict）；③ceiling join 实跑统计 = end_turn 21,649 点中 14,378（66.4%）降权，与天花板 33.6% 互洽
- **WP2 重训 ✅（判据 4 过）**：kind-weights-v1 双跑 sha256 逐字节全等（f4c27642…）；171,219 点 / 1005 局 / split_seed 20261018 同口径；holdout argmax 0.4034（v2 基线 0.4016 同量级微升）；资产 `models/policy-m12-v2w.json`（meta 含 weight_scheme 段，git dirty 标记如实落账）
- **WP2 锚 1 复测 ✅ 出数（判据 1/2 大幅过线、判据 3 崩）**：play_stadium 0.000→**0.716**（判据 ≥10% ✅）、use_ability 0.209→**0.645**（判据 ≥25% ✅）；代价面——attack 0.834→0.477（-35.7pts）、end_turn 0.073→0.002、play_trainer 0.390→0.290、retreat 0.300→0.521（意外受益）、v1 分母整体 0.335→0.211（**-12.4pts，判据 3 ❌**；全 main 口径 0.353→0.358 持平、holdout argmax 0.4016→0.4034 持平）；交叉护栏过（脚本 v1 分母子集与 CLI 逐对全等）。产物 `results/m12-anchor1-v2w/` + `.kimi-code/m12-task066-agreement-by-kind.json`
- **WP3 matrix 复测 ✅ 出数（判据 8 ❌ 恶化）**：18000 局 18 workers **8.0min**（锚 3 分钟级保持）；**加权 |Δ| 18.6%**（v2 12.5% / 启发式 13.2% / MCTS 9.7%）——第一门槛回退 ❌；CI 覆盖 13.9%；最大偏差格赛富豪×苍响 -49.2%；机制对拍——play_stadium 0→**2.54/局**（破零 ✅ 但超启发式 1.49 约 70%、超教师 2.16）、use_stadium 0→5.20（启发式 2.86）、use_ability 4.05→**14.75/局**（超启发式 9.85 约 50%、超教师 ~10.9）、局均回合 22.4→18.4 回落；**平 90→0 = task 064 修复在 matrix 口径的首次实证**；失败 4 局同一已知形态（copy_attack 嵌套）
- **口径披露**：v2w 与 v2 的 |Δ| 对比含引擎口径差（v2 的 90 平局为 task 064 修复前旧口径；影响面 0.5% 局、亚 pts 级，不改变 12.5→18.6 的结论方向）；det-check 未单跑（判据 8 已败，结论不变；推理确定性由 double-run + 既有 distilled 确定性测试覆盖）
- **WP2/WP3 总判：方向对、剂量过猛（A 包第一枪未过判据）**——目标两 kind 锚 1 大幅过线且机制量恢复（双双略超教师带），但 attack 一致性砍半 + |Δ| 恶化 6.1pts：锚 1 局部收益换锚 2 总体恶化，不划算
- **遗留（呈报拍板）**：A2 降剂量迭代（×1.5/×1.25 + end_turn 降噪 0.5，~35min/轮，有「零剂量 v2 ↔ 过猛 v2w」中间甜点假设）/ 转 B 特征 v3 / A2+B 组合 / 收口维持 v2 基线；v2w 资产存 `models/policy-m12-v2w.json`（待拍板去留，D3-4 入库口径待定）

## A2 轮（D-066-5，2026-10-21 用户拍板「先跑一轮 A2 降剂量」）

- **实现**：主会话直改 TDD——`kind-weights-v2` 方案（play_stadium ×1.5 / use_ability ×1.25 / end_turn ×0.5）进 `_SCHEME_PARAMS` 注册表 + CLI choices；2 新测试（常数钉死 + 映射/meta）；全量 **1404 绿 + ruff 零告警**
- **重训**：double-run sha256 全等（7d05d9ad…）；holdout argmax **0.4223**（v2 0.4016 / v2w 0.4034 / v1 0.4222——三版最高，整体拟合质量无损）
- **锚 1（判据 1/2 ✅、判据 3' ❌ 但大幅收窄）**：play_stadium **0.448**（≥10% 过线且 ≤0.60 未过冲）/ use_ability **0.547**（≥25% 过线）/ attack 0.655（让位 -17.9pts，超 10pts 门槛 ❌）/ play_trainer 0.378 基本恢复 / v1 分母 0.280（≥0.305 未达 ❌）/ **全 main 0.381（三版最高）**；end_turn 0.003（降噪下回不来，天花板 33.6% 口径下损失有限）
- **matrix（判据 8 ❌）**：18000 局 18 workers 7.8min；**加权 |Δ| 15.9%**（v2 12.5% ← → v2w 18.6% 之间）；最大偏差格赛富豪×苍响 -40.4%；失败 7 局同一已知形态；机制对拍——**play_stadium 1.97/局 ≈ 教师 2.16（贴带）/ use_ability 12.68/局（教师 ~10.9 / 启发式 9.85）/ 局均回合 20.3 ≈ 教师 20.9：机制量三版中最贴教师带**
- **A 包两轮总判（剂量-响应三点全单调）**：锚 1 目标 kind 单调受益（play_stadium 0→0.448→0.716；use_ability 0.209→0.547→0.645）↔ attack 单调受损（0.834→0.655→0.477）↔ **|Δ| 单调恶化（12.5%→15.9%→18.6%）——锚 2 口径零剂量（v2）即最优，甜点假设证伪**；机制量贴教师带但 |Δ| 仍恶化 → 实证锚 2 瓶颈在决策「质」（attack 让位 + 特性时机）不在机制「量」，与 task 065 根因①（特征不可分）闭环互洽
- **结论与遗留（已拍板 2026-10-21）**：**A 包（重加权路线）对锚 2 证伪收口**——两轮单调证据硬；用户拍板**整体收口维持 v2 基线，B 特征 v3 不立项**（残留盲区特性质量①/竞技场③/end_turn③ 留档 backlog）。v2w/v2w2 资产不入库：models/ 已清回正式资产三件套（eval-linear-v1 / policy-m12-v1 / policy-m12-v2），实验资产存档 results/（不入版本控制，sha256 已落账可复算）。加权训练管线（sample_weights.py + CLI --weight-scheme）作为 harness 保留入库（27+2 测试，未来处置复用）
