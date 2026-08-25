# STATUS.md — ptcg-cn-battlefrontier

> 进展速记：每完成一步更新。规范对齐 db 项目（进展记在这里，不进 README）。

## 当前

M1 进行中。task 001 ✅，下一步：**task 002 随机源与 GameState 数据模型**。
ptcgdb SDK 已接入（`C:/Vibe Project/Pokearena` 可编辑安装）。

## 里程碑

- 🔵 M1 引擎骨架（白板对局 + 同种子复现）——task 001 ✅ / 002 ⬜ / 003 ⬜ / 004 ⬜
- ⬜ M2 DSL + 解释器 + 首批原语（第一套目标卡组）
- ⬜ M3 启发式 Agent + Runner + 结果库（百局端到端）
- ⬜ M4 报告层（胜率 / 决策聚合 / 换卡敏感性）
- ⬜ M5 覆盖扩展 + LLM 辅助编写试验
- ⬜ M6 校准基线 + 一期验收

## 工作记录

### 2026-08-25 项目初始化

- PRD v1.0 定稿（D1–D12），README / AGENTS.md / STATUS.md 建立，仓库推送完成
- M1 拆解为 4 个 task（001 脚手架 / 002 随机源+GameState / 003 阶段机+行动枚举 / 004 白板对局端到端），验收标准先行
- 开放问题见 PRD §13

### 2026-08-25 task 001 项目脚手架 ✅

- venv（Python 3.14.6）+ `pip install -e .` 成功；4 测试全绿 + ruff 零告警；`bfsim` 入口可用
- ptcgdb SDK 已接入（`C:/Vibe Project/Pokearena` 可编辑安装，`test_ptcgdb_sdk_importable` 绿）：选择器字段设计、单局性能基线、dsl-authoring skill、目标卡组池名单（M1 启动时按 WUR 锁定）

## 决策日志

| 日期 | 决策 | 出处 |
|------|------|------|
| 2026-08-25 | D1–D12 | PRD §2 |
