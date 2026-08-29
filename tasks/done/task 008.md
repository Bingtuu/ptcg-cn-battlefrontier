# task 008 · 引擎骨架扩展：能量类型成本 + 弱点抗性 + 规则盒奖赏 + 任意时机昏厥检查

- 状态：完成
- 关联：PRD §6.2/§6.4，里程碑 M2；输入 = task 005「引擎缺口」清单、rules-manual §1.4/§6/§8

## 目标

把白板 `CardDef` 升级为可承载真实卡面骨架字段的版本，落地 rules-manual §6 的伤害计算顺序（基准 → 弱点 ×2 → 抗性 -30）与 §8 的规则盒奖赏张数（ex/V/VSTAR=2，VMAX=3），并把昏厥检查从「仅攻击后」泛化为任意伤害来源后统一入口。chooser、检索原语、特性/道具/竞技场、特殊状态归 task 009+。

## 验收标准（测试清单）

- [ ] 能量成本匹配：`cost=("超","无")` 时 2 超 ✅ / 1 超 1 恶 ✅（无色任意抵）/ 2 恶 ❌ / 仅 1 超 ❌
- [ ] 多招式枚举：每个伤害招式一条 `attack` 行动（`attack_index` 区分）；能量不够的不枚举；`damage=None`（效果招式）不枚举
- [ ] 弱点 ×2：攻方属性 = 守方弱点属性 → 基准 ×2
- [ ] 抗性 -30：守方抗性属性 = 攻方属性 → 基准 -30；结果 ≤0 不造成伤害、不触发昏厥
- [ ] 计算顺序：基准 → 弱点 → 抗性（白板期无攻/防修饰，注释标注后续插入点）
- [ ] 规则盒奖赏：ex 昏厥对手拿 2 张；映射表 ex/V/VSTAR=2、VMAX=3、默认 1；拿空即胜（复用现有判胜）
- [ ] 备战区昏厥：备战宝可梦伤害 ≥ HP → 整叠进弃牌堆 + 对手拿奖赏，无需换上（铺伤原语的前置框架）
- [ ] 任意时机入口：`check_knockouts()` 扫描双方战斗场+备战区统一结算；攻击路径改走该入口；测试直接置 damage 后调用结果一致
- [ ] 回归：既有 90 测试全绿（helpers 迁移后）；同种子 hash 确定性测试不破
- [ ] pytest 全绿 + ruff 零告警

## 实现要点

- `state.py`：新增 `AttackDef(name/cost: tuple[str,...]/damage: int|None)`；`CardDef` 增 `energy_type`（宝可梦属性/能量属性，开放字符串）、`attacks`、`weakness`、`resistance`（现行规则抗性恒 -30，引擎常量）、`rule_box`（开放字符串）；删 `attack_damage`/`attack_cost`（全仓迁移：helpers.py / test_engine_setup.py / test_state.py / core.py）
- `actions.py`：`Action.attack_index: int = 0`（默认 0 兼容既有 `Action(kind="attack")` 断言）
- `core.py`：`_energy_satisfied()`（先满足指定属性，剩余无色用任意抵）；`_attack_damage()`（顺序：基准 ≤0 终止 → 弱点 ×2 → 抗性 -30 → 下限 0；备战伤害不计算弱点抗性的贯穿规则留 `to_bench` 参数位）；`PRIZE_BY_RULE_BOX` 映射（出处 rules-manual §1.4/§8）；`check_knockouts()` 统一入口（战斗场昏厥走 promote 流程不变；备战昏厥直接结算；双方同时昏厥的结算顺序见 rules-manual 附录待核清单，本 task 不覆盖）
- 撤退费用保持整数计数（属性无关，rules-manual §5「撤退费用不限属性」）
- ACE SPEC 构筑校验归数据层/卡组装载（task 010+），引擎对局内不校验

## 结果与遗留

- 交付：`AttackDef`（name/cost 能量属性列表/damage）；`CardDef` 增 `energy_type`/`attacks`/`weakness`/`resistance`/`rule_box`，删 `attack_damage`/`attack_cost`（全仓迁移完成）；`Action.attack_index`
- 引擎：`_energy_satisfied`（指定属性先匹配、无色任意抵）；`_attack_damage`（基准 ≤0 终止 → 弱点 ×2 → 抗性 -30 → 下限 0，攻/防修饰插入点注释标注，`to_bench` 贯穿规则参数位）；`PRIZE_BY_RULE_BOX`（ex/V/VSTAR=2、VMAX=3）；`check_knockouts()` 任意时机统一入口（战斗场 promote 流程不变，备战昏厥直接结算，攻击路径改走该入口）
- TDD 红→绿：11 新测试（初跑 collection error → 全绿）；全量 101 绿 + ruff 零告警
- rules-manual §10 映射表状态已同步
- 遗留（task 009+）：chooser 机制（选择式弃牌/检索/撤退弃能量选择）；`search_deck`/`recover_from_discard` 等原语逐个注册；效果招式（damage=None）走 DSL on_attack；道具/竞技场骨架；特殊状态（混乱先行）+ 宝可梦检查阶段；跨回合 flag；双方同时昏厥结算顺序（rules-manual 附录待核清单）；ACE SPEC 构筑校验归卡组装载层
