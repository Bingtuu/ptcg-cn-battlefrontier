# task 018 · 通用启发式 Agent（M3 启动）

- 状态：完成
- 关联：PRD §7 决策层（§7.2 通用启发式、D10 不做单卡组定制）/ 里程碑 M3

## 目标

实现 PRD §7.2 的通用启发式 Agent：局面评估函数 + 决策规则（布阵优先级、行动排序、
斩杀检测），参数全暴露可配置。这是 Runner 落库实验（task 019）的前置——没有它，
M3 的「百局实验」只有 RandomAgent 对 RandomAgent，报告层无意义。

本 task 只交付 Agent 本体与单测；正式 Runner / 结果库 / CLI 实验子命令属 task 019。

## 验收标准（测试清单）

文件：`battlefrontier/agent/heuristic.py` + `tests/test_heuristic_agent.py`。

1. **协议合规**：HeuristicAgent 实现 `Agent` 协议（`observe(view, legal_actions) -> Action`），
   返回的 Action 必定来自传入的 legal_actions。
2. **可见性纪律**：只读 `VisibleGameState`——构造两个仅对手手牌/牌库内容不同的视图，
   决策必须一致（测试锁定：不碰隐藏信息）。
3. **开局布阵优先级**（setup 阶段）：
   - `place_active`：按确定性规则选 active（如 HP×性价比/进化潜力综合分最高），tie-break 确定性。
   - `place_bench`：按优先级填满备战区后再 `confirm_setup`。
   - 无合法布阵选择时行为正确（单基础宝可梦直接 active）。
4. **行动排序**（主阶段，PRD §7.2「特性→进化→能量→物品→支援者→攻击」）各一条测试：
   - 有可用 `use_ability` 时优先于其他主阶段行动。
   - 有 `evolve` 时优先于能量/物品/攻击。
   - `attach_energy`：目标选择有启发式（优先战斗场/斩杀目标），每回合只附着一次后不再选。
   - `play_trainer`（物品）优先于支援者，支援者优先于攻击（无斩杀时）。
   - `attach_tool` / `retreat` / `play_stadium` / `use_stadium` 有明确默认策略（可保守，但确定性）。
   - `attack`：存在能直接昏厥对手战斗场宝可梦的招式时必选该招式（斩杀检测）。
   - 无斩杀且无事可做时 `end_turn` 兜底。
5. **昏厥后推备**（`promote`）：按布阵同一套评分选备战区宝可梦，确定性 tie-break。
6. **chooser 选择策略**（`choose` 行动）：有确定性启发式（如检索按评分取最高），
   不取随机。
7. **确定性**：同视图同 legal_actions 调用两次结果一致；Agent 不消费引擎随机源
   （tie-break 用确定性规则，如 iid 排序，而非随机）。
8. **参数对象**：权重与开关收敛为一个配置对象（如 `HeuristicParams`），默认值=PRD
   通用启发式；改参数能改变决策（至少一条测试：调权重后选择变化）。
9. **集成冒烟**：用 `runner/play.py` 现有 `play_game` 让 HeuristicAgent 对 RandomAgent
   跑若干局不同种子，不崩溃、对局正常结束（胜率统计实验留 task 019）。
10. `pytest -q` 全绿 + `ruff check .` 零告警。

## 实现要点

- 评估函数按 PRD §7.2 五因子：奖赏差 / 场面战力 / 手牌质量 / 能量就绪度 / 牌库资源，
  线性加权，权重进 `HeuristicParams`；布阵与斩杀检测可用规则式（不强制走评估函数）。
- D10：不写任何针对特定卡组的定制逻辑；所有知识来自卡片数据与 DSL 暴露的通用字段
  （HP、招式伤害/能量需求、进化链、卡片类别等），不按卡名分支。
- 不改动引擎与 DSL；Agent 层只消费 `VisibleGameState` + `legal_actions`。
- MCTS 预留（§7.3）：评估函数与决策规则拆成可复用的纯函数，不挡后续 MCTS 接入。

## 后续（task 019 范围，本 task 不做）

实验定义 YAML + 正式 Runner（Agent 配置注入，替代/包装 `runner/play.py` 的硬编码）+
结果库三层表（experiments/games/game_events，独立 SQLite WAL）+ `bfsim` 实验子命令 +
百局端到端落库验收 + HeuristicAgent vs RandomAgent 对照胜率实验。

## 结果与遗留

**完成**（2026-08-29）：`battlefrontier/agent/heuristic.py`（HeuristicAgent + HeuristicParams +
evaluate/pokemon_score 纯函数）+ `tests/test_heuristic_agent.py` 24 条；`play_game` 增
`agents` 可选注入。全量 243 绿 + ruff 零告警。

实现中两处口径修正（TDD 过程中收敛）：

- 能量附着从「战斗场不能支付任何招式才补」收敛为「仍有付不起的招式才补，全就绪跳过」
  ——多招式宝可梦向大招式蓄能算 needs，全就绪不浪费每回合 1 次附着；
- 斩杀检测在行动排序中凌驾物品/支援者（能直接昏厥对手战斗场必先出手），
  无斩杀时才走「物品→支援者→最高伤害攻击」。

遗留：胜率对照实验与参数进实验定义 YAML 归 task 019；评估函数暂只用于报告/测试，
未参与逐手决策（PRD §7.2 允许规则式决策）。
