# task 007 · 解释器骨架 + 结构化事件流 + play_trainer 引擎接入

- 状态：完成
- 关联：PRD §5.4 / §6.6，里程碑 M2；输入 = task 006 schema + task 005 引擎缺口

## 目标

DSL 解释器骨架：消费 `CardEffectDoc`，按「成本 → 动作序列」执行原语节点树，每节点产出结构化事件（PRD §5.4：effect_id / card / trigger / 参数 / 结果，回放/人工 check/统计共用一份数据）。引擎侧落地 `play_trainer` 行动（PRD §6.6：物品不限次、支援者每回合 1 张 + 先攻方首回合禁用），打通「真实卡真实效果进真实对局」的端到端切片。首批原语只实现 `draw` / `discard`（够跑通博士的研究），其余原语归 task 008+ 逐个注册。

## 验收标准（测试清单）

- [x] 博士的研究端到端：主阶段使用 → 手牌全弃 → 抽 7 → 本体进弃牌区；状态与事件逐项断言
- [x] 事件流字段齐备：effect_start / effect_primitive（effect_id/card/action/params/result）/ effect_observe / effect_end
- [x] play_trainer 合法行动枚举：主阶段有；setup 阶段无；无 DSL 文档的训练家卡不可使用
- [x] 支援者规则：每回合限 1 张（第二张不枚举）；先攻方第一回合禁用；标记次回合重置
- [x] 物品每回合不限次数
- [x] 词表内但未实现的原语（如 search_deck）→ DslError「未实现」（区别于未知词）
- [x] 计数表达式等未落地能力 → DslError 明确报错（不猜语义）
- [x] 牌库不足 N 张时 draw 抽完即止（效果抽空不判负；判负只在回合开始抽牌）
- [x] 含训练家卡的对局同种子事件流 hash 一致（play_game 级确定性）
- [x] pytest 全绿 + ruff 零告警

## 实现要点

- `dsl/interpreter.py`：ExecutionContext（engine 引用 / 操控玩家 / 来源卡 / effect_id）+ `PRIMITIVES` 注册表 + `run_effect`；dsl 层只 import engine.state，类型标注走 TYPE_CHECKING，避免循环导入
- `dsl/primitives.py`：draw（int count）/ discard（own_hand+all）；选择式弃牌等待 chooser 机制（task 008+）
- 引擎：`CardDef` + `trainer_subtype`（开放字符串）；`PlayerState` + `supporter_played_this_turn`（_begin_turn 重置）；`GameEngine(rng, card_effects=None)`；`_do_play_trainer` = 出手牌 → 事件 → 跑 on_play 效果 → 进弃牌区 + 支援者标记
- DSL 文档按 `card.name` 查找（name_group 对齐归数据层，task 008+ 再接）
- `play_game` 增加可选 `card_effects` 参数支撑确定性测试；render.py 补 play_trainer/effect 模板
- 宝可梦道具 / 竞技场的 play_trainer 枚举本期不做（task 008+ 随对应机制落地）

## 结果与遗留

- 交付：`dsl/interpreter.py`（ExecutionContext + PRIMITIVES 注册表 + run_effect，事件序列 effect_start → effect_primitive × N → effect_observe → effect_end）、`dsl/primitives.py`（draw / discard 首两原语）、引擎 `play_trainer` 行动（物品/支援者，PRD §6.6 规则全落地：支援者回合限 1 + 先攻首回合禁用 + 次回合重置）
- 引擎增量：`CardDef.trainer_subtype`、`PlayerState.supporter_played_this_turn`、`GameEngine(card_effects=)`、`play_game(card_effects=)`、render.py 效果事件模板
- 架构纪律：dsl 层只 import engine.state（GameEngine 走 TYPE_CHECKING），core.py 经 dsl 包入口调解释器，无循环导入；无 DSL 文档的训练家卡不可使用（引擎对内容零硬编码）
- 词表有而未实现的原语 → DslError「未实现」，与 loader 层「未知词」错误区分开
- TDD 红→绿：14 新测试（初跑 12 失败 2 过）；全量 82 绿 + ruff 零告警
- 遗留：选择式弃牌/检索等待 chooser 机制（运行时选择由 Agent 决策，PRD §5.2，task 008+）；计数表达式求值、宝可梦道具/竞技场使用骨架、特性触发器（ability_manual/passive_static 等）归 task 008+；condition/limit 本期仅记录不强制
