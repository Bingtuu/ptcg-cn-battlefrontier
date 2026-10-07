# task 042：MCTS 决策分析——根节点访问分布导出

设计文档：`docs/superpowers/specs/2026-10-07-mcts-decision-analysis-design.md`
（D-042-1~5 与验收标准以它为准）。

## 范围

- 采集：MCTSAgent.last_consideration + play.py 追加 mcts_consider 事件
- 口径：events_hash 排除该 kind；render 显式跳过
- 报告：report/mcts_analysis.py（新模块）+ cli report --mcts-consider 三件套
- 不做：heuristic 分歧对照、局面聚类（D-042-5）

## 验收

1. 事件流含 mcts_consider 字段完整；2. events_hash 排除 + 对拍回归绿；
3. 三件套单测；4. 端到端小预算实验出表；5. 全量 pytest + ruff。
