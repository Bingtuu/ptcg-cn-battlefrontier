# task 059 · M12 WP3 distilled Agent 接入（type: distilled）

- 状态：进行中
- 关联：task 056 拍板定案（numpy runtime 推理）；task 058 WP2（特征化 +
  训练管线 + `bf-distilled-policy-v1` 资产格式——本任务以 058 交付的
  装载/特征 API 为准）；接入面摸底 `.kimi-code/m12-decision-prep.md` §4
- 前置：task 058 完成并复验（模型资产 save/load 往返、CLI 冒烟训练产物）

## 设计（D-M12-x，本任务书定稿）

- **新 Agent**：`battlefrontier/agent/distilled.py` `DistilledAgent`
  （遵守统一接口 `observe(visible_state, legal_actions) -> action`）：
  state 30 维特征（复用 `agent/features.py`）⊕ 每合法行动的行动侧特征
  （复用 task 058 特征抽取函数）→ numpy 前向打分 → **合法行动掩码 argmax**
  （ties 取首索引，全程无随机源——蒸馏学生天然确定性）
- **注册三处**（缺任一处即静默错，验收须逐项实证）：
  1. `runner/experiment.py:38` `AGENT_TYPES` 元组加 `"distilled"`
  2. `_build_one`（:226）加显式分支——**不得落 RandomAgent 兜底**
     （摸底已标坑）；`policy_path` 缺失/资产装载失败显式报错
  3. `AgentCfg._check_agent`（:75-87）加 distilled 专属 params 白名单
     （`policy_path`，str），不被 HeuristicParams 校验误杀
  4. `runner/agreement.py` `replay_student`（:71-85）加 distilled 学生分支
     （现状硬编码 MCTSAgent；cfg 带 `type: distilled` 时建 DistilledAgent，
     observe 只吃 visible_state 天然守信息纪律，无需 determinize）——
     锚 1 离线重放（task 060）直接复用 `run_agreement` 基建
  5. `cli.py` `_cmd_agreement`（:434）加 `--policy <path>` 开关（与 MCTS
     预算 flags 互斥），student dict 切 `{type: distilled, policy_path}`——
     否则锚 1 只能靠 Python 驱动，CLI 面不全
- **资产装载**：模型 JSON（`bf-distilled-policy-v1`，task 058 格式）经
  params 路径装载；worker 内每局重建 Agent = 每局装载一次（与现状同例，
  模型体量须小——MLP 权重嵌套列表，资产 < 1MB 量级）
- **分层纪律**：`agent/distilled.py` 推理前向只准 numpy（task 056 防回流
  基准：runtime 路径零 torch import）
- **默认路径零变化**：不带 `type: distilled` 的既有实验定义行为零变化，
  events_hash 回归全等

## 验收标准

1. TDD：DistilledAgent 单测（掩码 argmax 正确性：非法行动永不被选；
   ties 确定性；同模型同 visible_state 重复 observe 结果一致）、
   注册三处单测（未知 type 报错 / distilled params 白名单过验 /
   `_build_one` 显式分支命中）、agreement 重放分支单测（distilled 学生
   走 `run_agreement` 出报告，分母口径与 M11 v1 一致）、CLI 端到端
   （单实验定义 `agents: {a: {type: distilled, params: {policy_path: ...}}}`
   跑通落库）
2. events_hash 零变化回归：既有确定性测试套件全绿（默认路径未动）+
   新增 distilled 自身确定性测试（同种子区间两跑 events_hash 全等）
3. runtime 零 torch import 复核（grep battlefrontier/ 排除 learn/train_policy.py）
4. 全量 pytest 绿 + ruff 零告警
5. STATUS.md 落账 + 归档

## 结果与遗留

（待完成填写）
