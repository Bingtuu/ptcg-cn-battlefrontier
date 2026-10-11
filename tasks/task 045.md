# task 045：tune 子包 + 坐标下降搜索器 + bfsim tune CLI

设计文档：`docs/superpowers/specs/2026-10-11-heuristic-tuning-design.md`
（D-T1~T4 与总体验收标准以它为准）。

- 状态：进行中（2026-10-11 立项）

## 范围

- `battlefrontier/tune/` 四模块：`space.py`（参数空间声明）/ `fitness.py`（评估协议：配对分层划分 + CRN 种子派生 + 批量跑局聚合）/ `search.py`（坐标下降：乘法网格 + 噪声门槛采纳 + 3 轮上限）/ `trajectory.py`（JSONL 轨迹）
- TuneDef（Pydantic 强校验）+ `bfsim tune <定义.yml> [--workers N]`
- 不做：ES 精修（task 047 条件立项）、正式跑批（task 046）、结果库落库（搜索过程走轨迹 JSONL）

## 验收标准

1. **单测覆盖**：
   - space：8 连续维乘法网格（{0, ×0.25, ×0.5, ×2, ×4}）+ 2 整数维枚举网格生成正确（默认值不在网格点重复评估）
   - fitness：配对分层划分确定性（同种子同划分、9 archetype 双侧覆盖）+ CRN 种子派生（pair i → 200000+i×1000，跨候选同区间）+ 胜率聚合口径（分母=决定局，对齐既有 winrate 口径）
   - search：采纳规则（Δ>噪声门槛才采纳）/ 单维全不采纳则跳过 / 整轮无改进停止 / 3 轮上限
   - trajectory：每评估一行 JSONL（参数向量 + 种子区间 + 得分 + 各配对明细），可重放
   - TuneDef：未知字段/未知算法名/非法划分比例显式报错（不猜）
2. **确定性**：同调优定义同种子重跑，轨迹逐行一致（参数 + 得分 + 种子区间）；workers 4 vs 1 轨迹一致
3. **小预算冒烟**：2 对 × 20 局、单轮坐标下降端到端跑通，轨迹行数 = 预期评估次数
4. **全量 pytest 绿 + ruff 零告警**

## 遗留（归 task 046）

- 正式粗扫跑批（~36 万局，16 workers ~2h）+ 维度敏感性报告 + holdout 验证 + 复校准 + 默认参数回写裁决
- holdout 门槛是否同时要求训练集提升——跑批前用户拍板（设计文档 §8 开放项）
