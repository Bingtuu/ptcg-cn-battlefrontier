# task 062 · 蒸馏特征 v2（卡身份 + 弃牌构成）重训复测

- 状态：进行中
- 关联：task 060（锚 2 未达）/ task 061（根因诊断：特征盲区 → use_ability
  不可分）；设计 `docs/superpowers/specs/2026-10-19-distilled-features-v2-design.md`
  （D-062-1~5，用户 2026-10-19 批准）；计划
  `docs/superpowers/plans/2026-10-19-distilled-features-v2.md`
- 用户拍板（2026-10-19）：采纳诊断建议「特征补课 → 现有数据重训 → 复测」，
  替代 task 060 呈报的原 B 方案（10⁴ 采集判否：特征不可分加数据无效）

## 范围（计划 Task 1–7）

- WP1 `agent/policy_features.py`：v2 特征（状态 +6 弃牌构成 / 行动 +112 卡身份
  one-hot）+ 卡词表构建（卡池 v1 group_key 112）
- WP2 资产 `bf-distilled-policy-v2`（format 分派，v1 保持可装载）+
  训练/推理/CLI 接入（v1 路径逐位不变）
- WP3 正式重训（同 171k 试点快照 / 同超参 / 同 split_seed）+ double-run +
  分 kind 一致率复测（**终止判据：use_ability ≥18%**）
- WP4 matrix 复测（同种子锚 700000，CRN 可比）+ 机制计数复核 + 确定性 +
  M12 终判呈报

## 验收标准（设计文档§验收标准，逐条）

1. use_ability 一致率 0.009% → ≥18%；attack 类价值损失均值收敛
2. matrix 加权 |Δ| ≤ 13.2%（第一门槛）；对照 9.7% 如实落账；全局特性
   使用率 ≥5 次/局
3. 训练 double-run 逐字节全等；distilled 镜像同种子两跑逐局全等
4. 全量 pytest 绿 + ruff 零告警；M11 资产路径零变化
5. STATUS.md / 本文档落账归档 + M12 终判呈报（用户拍板点）

## 结果与遗留

（待完成填写）
