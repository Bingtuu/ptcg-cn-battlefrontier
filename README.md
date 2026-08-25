# BattleFrontier（对战开拓区）

> AI 宝可梦卡牌（PTCG 简中环境）对战模拟与卡组强度测试引擎

**BattleFrontier** 是 [ptcg-cn-db](https://github.com/Bingtuu/ptcg-cn-db)（数据基建层）之上的应用层项目：构建完整的 PTCG 规则模拟引擎与 AI 智能体，通过大规模模拟对局回答三类问题——

- **强度**：卡组 A 对抗卡组 B 的胜率是多少？
- **策略**：某卡组在某对阵下的最优策略是什么？（以决策数据聚合报告形式产出）
- **敏感性**：调整卡组中的卡牌（宝可梦、物品、支援者）对胜率是否有显著影响？新比赛标准环境下各卡组/主轴强度如何变化？

## 核心设计

- **效果 DSL 优先**：卡牌效果数据化（结构化 YAML + 原语节点树 + Pydantic 强校验），引擎对卡牌内容零硬编码，解释器执行 DSL
- **分层 AI**：通用启发式 Agent 打底 → MCTS（后续）→ RL（远期）；接口统一，双方可用不同实现做对照实验
- **种子确定性**：单一可注入随机源，同种子同局完全复现（硬验收项）
- **可复算实验**：实验定义（YAML）+ 代码版本 + 数据版本三者锁定；结果落独立 SQLite（遵守 db 项目 FR-10 sim 库契约，主库只读）
- **校准目标**：模拟 matchup 矩阵 vs 数据层真实赛事 matchup 矩阵的偏差持续跟踪

## 状态

🚧 设计阶段完成，实现未开始。权威设计文档见 [PRD v1.0](docs/superpowers/specs/2026-08-25-battlefrontier-prd-design.md)（含 12 条决策记录、一期里程碑 M1–M6）。

## 数据依赖

本项目不自带卡牌数据，消费 [ptcg-cn-db](https://github.com/Bingtuu/ptcg-cn-db) 的 SDK（`ptcgdb.sdk`）与导出件（`dist/`）。

## ⚖️ 合规声明

本项目与 Nintendo、The Pokémon Company、宝可梦（上海）**无任何隶属或背书关系**。卡面文本与卡牌数据版权归宝可梦（上海）/ The Pokémon Company 所有；本项目不采集、不存储、不分发卡图与卡牌数据，仅限本地研究与工具自用。

## 📄 License

代码与文档基于 MIT License 发布（卡牌数据版权见上方声明，不在许可范围内）。
