# STATUS.md — ptcg-cn-battlefrontier

> 进展速记：每完成一步更新。规范对齐 db 项目（进展记在这里，不进 README）。

## 当前

**M1 引擎骨架达成**（task 001–004 全 ✅）。下一步：M2 拆解（DSL schema + 解释器 + 首批原语，先按 db WUR 锁定第一套目标卡组）。
ptcgdb SDK 已接入（`C:/Vibe Project/Pokearena` 可编辑安装）。

## 里程碑

- ✅ M1 引擎骨架（白板对局 + 同种子复现）——task 001–004 全 ✅（2026-08-25）
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
- ptcgdb SDK 已接入（`C:/Vibe Project/Pokearena` 可编辑安装，`test_ptcgdb_sdk_importable` 绿）

### 2026-08-25 task 002 随机源与 GameState ✅

- `engine/rng.py` RandomSource（同种子序列一致 / 快照恢复）+ `engine/state.py` GameState（区域完整 / 不可变 / 序列化往返 / 可见视图过滤）
- 17 测试全绿 + ruff 零告警；遗留：牌库实际抽洗操作归 task 003

### 2026-08-25 task 004 白板对局端到端与 M1 确定性验收 ✅（M1 达成）

- `runner/play.py`（play_game / 2 进程并行 / 事件流 sha256）+ `agent/random_agent.py` + `report/render.py` 人类可读回合记录
- M1 硬验收全过：同种子 hash 一致 / 串行与并行逐局一致 / 100 局零异常 / 回合上限判平 / 异常卡组 DeckConfigError
- 54 测试全绿 + ruff 零告警；遗留：play.py 非正式 Runner（M3 接管）

### 2026-08-25 task 003 阶段机与合法行动枚举 ✅

- `engine/core.py` GameEngine（开局+mulligan / 阶段机 / 主阶段四行动 / 昏厥奖赏换上 / 三种胜负）+ `actions.py` / `events.py` / `agent/base.py` Agent 协议
- 45 测试全绿 + ruff 零告警；规则出处逐条注释在 core.py
- 术语修正：knockout 统一为官方用词「昏厥」（全仓替换，规则决议日志首条）
- 新增 `docs/rules-reference.md` 规则事实源（官方规则梳理 + 术语表 + 决议日志附录 A）；PRD 补 §6.6 训练家卡与 ACE SPEC 骨架规划
- 遗留：特殊状态回合间结算（M2 随效果落地）、mulligan 抽牌与让先选择权 Agent 化

## 决策日志

| 日期 | 决策 | 出处 |
|------|------|------|
| 2026-08-25 | D1–D12 | PRD §2 |
