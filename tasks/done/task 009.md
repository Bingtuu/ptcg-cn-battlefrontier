# task 009 · chooser 机制 + 检索/回收/选择式弃牌原语

- 状态：完成
- 关联：PRD §5.2（运行时选择由 Agent 决策）/§5.4/§6.2，里程碑 M2；输入 = task 005 原语清单、task 007/008 遗留（chooser 机制）

## 目标

落地「效果执行中途挂起 → 引擎枚举选择项 → Agent 选择 → 恢复执行」的 chooser 机制（挂起状态可序列化、确定性、不消耗随机源），并注册首批选择类原语：`discard`（选择式成本）、`search_deck`（入手牌/直放备战区）、`shuffle_deck`、`recover_from_discard`（入手牌）。以三张真实卡端到端验收：高级球（选弃 2 → 检索宝可梦入手 → 洗牌）、巢穴球（检索基础宝可梦直放备战区 → 洗牌）、夜间担架（弃牌区选 1 张宝可梦或基本能量入手）。

## 验收标准（测试清单）

- [ ] 高级球 e2e：play → 挂起（手牌选弃 2）→ 选择 → 再挂起（牌库检索 1 宝可梦）→ 选择 → 洗牌 → 状态逐项断言（手牌/弃牌区/牌库/phase 回 main）
- [ ] 巢穴球 e2e：检索基础宝可梦**直放备战区**（+1，记入 `entered_play_this_turn` 联动当回合不可进化）；备战区满（5 只）时该卡不可使用（枚举例外）
- [ ] 夜间担架 e2e：弃牌区过滤器（宝可梦或基本能量）正确排除训练家/特殊能量
- [ ] 检索可不找（up-to 语义：空选择是合法行动）；牌库无匹配时不挂起、效果空结算且**仍洗牌**（规则：检索后必洗）
- [ ] 回收无合法目标时不挂起、效果 no-op（有事件记录）
- [ ] 成本可行性门：手牌不足 2 张（除高级球本体）时 `play_trainer` 不枚举高级球；未知成本形式 → DslError 不猜
- [ ] 选择合法性：不在枚举内的 choose 行动（iid 不在池 / 数量不符 min~max）→ IllegalActionError
- [ ] 隐藏信息纪律：牌库检索挂起时，选择方可见检索池内容、对手不可见；挂起状态可 JSON 序列化往返
- [ ] 确定性：选择不消耗随机源；含高级球的对局同种子事件流 hash 一致
- [ ] 未知 filter 词 / 不支持 choose 的原语 → DslError 明确报错
- [ ] pytest 全绿 + ruff 零告警

## 实现要点

- `schema.py`：`ActionNode.choose: int ≥1 | None`（运行时选择数量，与 count 区分：count=自动量，choose=Agent 选）
- `state.py`：`PendingChoice`（player / source 卡实例 / effect_index / cursor 步骤游标 / pool / filters / min~max / destination）+ `GameState.pending_choice`；`visible_state` 对自己揭示 deck 检索池内容
- `actions.py`：`Action.choices: tuple[int, ...] = ()`（多选 iid 集合）
- `dsl/chooser.py`：`NeedChoice` 哨兵、池计算（own_hand/own_deck/own_discard + filter 求值，未知 filter 报错）、选择枚举（min~max 子集，iid 排序保确定序）、成本可行性检查
- `interpreter.py`：扁平步骤游标（cost 段在前）；原语签名加 `choice` 参数；返回 `NeedChoice` 即挂起，恢复时从 card_effects 重取 Effect 续跑（Effect 树不入状态，单一事实源 = DSL 文档）
- `core.py`：phase `"choice"`；`_do_play_trainer` 改挂起式（支援者标记在打出时置位、本体在效果完成后进弃牌区）；`_do_choose`；`play_trainer` 枚举加成本可行性门
- 撤退弃能量选择式、奖赏任意顺序拿取：复用本机制的候选，本 task 不做（引擎层行动，归后续）

## 结果与遗留

- 交付：`dsl/chooser.py`（NeedChoice 哨兵 / filter 求值唯一入口 / 池解析冻结 / min~max 子集枚举 / 成本可行性门）；解释器挂起-恢复协议（扁平步骤游标，Effect 树不入状态，恢复时从 card_effects 重取）；`PendingChoice` + `GameState.pending_choice`（可序列化）+ `visible_state` 向选择方揭示牌库检索池（对手不可见，rules-manual §3）；`Action.choose`/`ActionNode.choose` 字段
- 原语四件：`discard`（choose=N 选择式成本 + 保留 count=all）、`search_deck`（filters + up-to 可不找 + destination hand/bench，bench 联动 entered_play_this_turn）、`shuffle_deck`、`recover_from_discard`（池空 no-op 不挂起）
- 引擎：phase `"choice"`、`_do_choose` 恢复、`_do_play_trainer` 挂起式重构（支援者标记打出时置位、本体效果完成后进弃牌区）、`play_trainer` 枚举成本可行性门（高级球手牌不足 2 张不枚举；巢穴球备战满不枚举；未知成本形式 DslError 不猜）
- 三卡 e2e：高级球（弃 2 → 检索宝可梦入手 → 洗牌）、巢穴球（检索直放备战区）、夜间担架（弃牌区过滤宝可梦/基本能量回收）
- TDD 红→绿：14 新测试 + 1 旧测试改约（search_deck 已实现，未实现断言改到 copy_attack；新增 search_deck 必须 choose 的契约测试）；全量 116 绿 + ruff 零告警；含高级球整局同种子 hash 一致
- 设计要点：池在挂起瞬间解析冻结进 `pool_iids`（choice 阶段状态不变，池不漂移）；Effect 树不序列化，单一事实源 = DSL 文档；选择不消耗随机源
- 遗留（task 010+）：撤退弃能量选择式与奖赏任意顺序拿取可复用本机制（引擎层行动，未接）；特性触发器（ability_manual/once_per_turn）、道具/竞技场骨架、计数表达式求值、伤害类原语（铺伤/变量伤害）、特殊状态（混乱）+ 宝可梦检查阶段、跨回合 flag；卡组装载层（db → CardDef + DSL 定义库落盘，含 38 张跨源待核销卡的前置核对）
