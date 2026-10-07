# MCTS 决策分析设计（task 042）

2026-10-07 立项。来源：二期候选「MCTS 决策分析」——根节点访问分布是强 Agent 的
策略信号，当前 `mcts.py` 的 `counts` 用完即弃；decisions 报告（task 022）只聚合
DSL chooser 的 choose 事件，覆盖不到主阶段行动（攻击/撤退/打牌）这一 MCTS 主要
决策面。

## 架构

```
MCTSAgent.observe ──记──> last_consideration（根统计）
                                │
runner/play.py 驱动循环 ──读──┘（observe 返回后）──> 追加 mcts_consider 事件进引擎事件流
                                │
                game_events 落库（现有表，零 schema 变更）
                                │
                bfsim report <id> --mcts-consider（report/mcts_analysis.py）
```

## 设计决议

- **D-042-1（采集）**：`MCTSAgent.observe` 末尾把根统计存 `self.last_consideration`
  ——turn / phase / player / 各合法行动 visits / total_visits / 选中行动。
  `runner/play.py` 在 `agent.observe(...)` 返回后检查该属性，非 None 则向引擎
  事件流追加 `mcts_consider` 事件（随后清空，防重复记账）。heuristic/random
  无此属性 → 零开销零行为变化。
- **D-042-2（观测性事件口径）**：`mcts_consider` 是观测事件（Agent 搜索内部状态
  的外化），**不影响对局行为**——events_hash 计算排除该 kind（play.py 的
  payload 过滤），保持行为校验跨版本可比；render.py 回放跳过该类（未知 kind
  回退已存在，此处显式跳过更干净）。
- **D-042-3（事件载荷）**：`{turn, phase, chosen, total_visits, considered:
  [{action, visits}...]}`；action 标签 = kind + 可读参数（attack → 招式名、
  play_trainer/retreat 等 → 卡名），emit 点在 play.py 持引擎引用可经状态解析，
  解析失败回退 kind 原文（不猜）。
- **D-042-4（报告三件套，最小可用）**：
  ① 按 action kind 聚合的访问份额分布（sum(visits)/sum(total)——强 Agent 注意力
  分布）；② 高熵决策点 top N（归一化熵 H/Hmax——访问最分散 = 关键抉择点，
  列 turn/phase/分布）；③ 选中行动访问份额分桶（果断 >80% / 50-80% / 纠结 <50%）
  × 最终胜率（访问置信是否兑现）。
- **D-042-5（YAGNI）**：不做 heuristic 分歧对照、不做局面聚类、不做逐决策点
  胜率关联（choose 事件已有该口径）——后续 task 按需。

## 验收标准

1. 小预算 MCTS 对局事件流含 mcts_consider，字段完整（turn/phase/considered/
   chosen/total）。
2. events_hash 排除该 kind：同种子两局 hash 相等；既有串并对拍回归全绿。
3. 报告三件套单测（合成事件流）：份额/熵排序/分桶胜率各断言。
4. 端到端：真实卡组小预算 MCTS 实验（games=4）+ `report --mcts-consider` 出表。
5. 全量 pytest 绿 + ruff 零告警。
