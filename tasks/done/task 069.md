# task 069 · 卡池 v2 引擎扩展批（5 机制 + 3 原语小扩，DSL 批次前置）

- 状态：完成（2026-10-21；判据 1–5 全 ✅）
- 关联：task 068 机制处置定案（判据 4）；卡池 v2 线第二棒（068 池锁定 → 069 引擎扩展 → 070+ DSL 批次 → 07x matrix+校准）

## 目标

把 task 068 定案的 5 项引擎扩展 + 3 项 DSL 原语小扩全部落地（TDD），为 34 张缺口卡的 DSL 编写备齐表达力。本任务只动引擎/DSL 框架，不写任何卡面 DSL 文件（DSL 批次进 task 070）。

## 设计决议

- **D-069-1 力之沙漏时点口径（2026-10-21 用户拍板）**：「回合结束时」触发落点 = 检查阶段内、状态结算之后（`_start_pokemon_check` 入队点）；对本卡结果等价，与官方「先于宝可梦检查」名义偏差记附录 A 决议
- **D-069-2 ACE 锁覆盖面（2026-10-21 用户拍板）**：广义五门类——物品/支援者/竞技场打出 + 道具附着 + 能量附着（对齐官方 "play a card from hand" 广义口径），记附录 A 决议
- **D-069-3 组织方式**：子代理 TDD 分组并行 + 主会话独立复验（task 026 起惯例）：组 A = WP1+WP3+WP5（`_main_actions` 邻近面同组防冲突）、组 B = WP2（伤害路径）、组 C = WP4+WP6（回合末路径 + 原语小扩）
- **D-069-4 纪律**：引擎零卡名硬编码（新机制全部 DSL 声明驱动）；存量测试行为零变化（不改断言迁就实现）；附录 A 决议由主会话落 rules-reference.md

## 工作包（落点全部经 explore 评估定位）

- **WP1 虹色因子（伊布ex）**：新原语 `modify_evolution`（passive_static 声明，args `{match_evolves_from, rule_box}`）；`_main_actions` 进化枚举（core.py:352-361）加声明分支 + `_ability_suppressed` 守卫（core.py:1797-1815 落点清单）；`_do_evolve` 零改复用；词表 + PRIMITIVE_ARGS 登记；附录 A 决议（进化合法性从纯名字链扩为 DSL 声明可加宽）
- **WP2 顽强之心（皮卡丘ex）**：新原语 `prevent_ko`（passive_static，args `{remaining_hp: 10, when: full_hp}`）；新助手 `_survival_cap` 在三处伤害施加点统一接入（core.py:1166-1174 白板 / primitives.py:1189-1191 DSL damage / primitives.py:1676-1678 copy_attack）；满 HP 判定 = 伤害施加瞬间 + `damage==0`（有效 HP 经 `_effective_hp`）；`_ability_suppressed` 守卫；不碰 check_knockouts 扫描结构（task 064 纪律）；附录 A 决议
- **WP3 璀璨结晶（ACE）**：`modify_attack_cost` args 加 `types: all`（减免取法钉口径：优先【无】再按 cost 序首个有色符号，注释钉死）；chooser 加 `holder_is_tera`；附录 A 补记 D-WP5-4 口径扩展（存量 DSL 不写该键行为零变化）
- **WP4 力之沙漏**：词表 events 加 `own_turn_end`；`_start_pokemon_check`（core.py:941）状态结算后入队回合结束方场上 attached_tool 声明的触发；`_drain_event_triggers` 寻源扩 attached_tool + `_tool_suppressed` 守卫；`attach_energy` own_discard 扩 `target_pool: self`；可放弃用既有 min_choose=0 形态
- **WP5 ACE 锁（盖诺赛克特）**：`lock_play` 改可挂 passive_static + category 扩 `ace_spec`；chooser 加 `holder_has_tool`；新守卫 `_ace_spec_play_locked(player)`（扫对手场上声明 + condition + `_ability_suppressed`）；`_main_actions` 四处手牌使出枚举（core.py:364-370 能量 / 374-380 道具 / 444-472 物品支援者 / 475-482 竞技场）对 `is_ace_spec` 卡加过滤；附录 A 决议（D-069-2 五门类）
- **WP6 原语小扩 ×3**：`discard` own_attached_energy 扩 `choose: 3`（皮卡丘ex 黄晶伏特）；计数词加 opponent 全场附着能量版（叶伊布ex 绿叶风暴，对照 `attached_energy_on_opponent_active` primitives.py:1004）；`heal` 扩「自己备战全体」形态（叶伊布ex 苔纹玛瑙）

## 边界

- 不写卡面 DSL 文件（task 070）；不动 v1 池与既有结果；不改 runner/report 层
- 附录 A 决议文本主会话定稿；WP 内遇规则歧义报主会话，不自行猜

## 验收标准（终止判据先行）

1. 每 WP 单测覆盖：正向枚举/结算 + 抑制交互（监视塔/阻碍之塔）+ 边界（登场当回合 / 已受伤 / 侧别 / 放弃选项）；存量测试零改动
2. 全量 pytest 绿 + ruff 零告警（主会话亲跑）
3. 附录 A 4 条决议落 `docs/rules-reference.md`（虹色因子声明驱动进化 / 顽强之心满 HP 判定时点 / 力之沙漏时点口径 D-069-1 / ACE 锁覆盖面 D-069-2 + D-WP5-4 补记）
4. 主会话独立复验通过（改动点逐一对照本任务书落点清单）
5. STATUS.md 落账 + 本档归档

## 结果与遗留

**三組子代理 TDD 全部收官 + 主会话独立复验通过**（2026-10-21）：全量 **1454 绿**（1404 + 50 新增）+ ruff 零告警（主会话亲跑 8m14s）；存量测试零改动；diff 抽核与任务书落点清单一一对应。

- **WP1 虹色因子**：`modify_evolution` 声明原语 + `_main_actions` 进化枚举声明分支（declared_pairs 去重、登场/已进化门同口径、`_ability_suppressed` 守卫）+ `_modify_evolution_args` 不猜校验；`_do_evolve` 零改复用。8 测
- **WP2 顽强之心**：`prevent_ko` 声明原语 + `_survival_cap` 助手三落点接入（白板 `_do_attack` / DSL damage on_attack / copy_attack 白板）；满 HP=伤害施加瞬间 `damage==0`；指示物/效果伤害/自伤不经守卫。12 测
- **WP3 璀璨结晶**：`modify_attack_cost` args 加 `types: all`（取法钉死：优先【无】再首个有色）+ chooser `holder_is_tera`。6 测
- **WP4 力之沙漏**：词表 `own_turn_end` + `_start_pokemon_check` 状态结算后入队（D-069-1）+ `_drain_event_triggers` attached_tool 寻源 + `_tool_suppressed` 守卫 + `attach_energy` own_discard `target_pool: self` 段 2 免选。8 测
- **WP5 ACE 锁**：`lock_play` passive_static + category `ace_spec` + chooser `holder_has_tool` + `_ace_spec_play_locked` 实时扫场守卫 + 四处手牌使出枚举过滤（D-069-2 广义五门类，惰性求值省 MCTS 热路径）。8 测
- **WP6 原语小扩**：discard own_attached_energy `choose=N` 正 int 泛化；计数词 `attached_energy_on_opponent_all`；heal `own_bench` 形态。9 测
- **附录 A 决议 5 行落 rules-reference.md**：力之沙漏时点口径 + ACE 锁覆盖面 = ✅ 已核（2026-10-21 用户拍板 D-069-1/2）；虹色因子声明驱动进化 / 顽强之心判定时点 / D-WP5-4 types:all 扩展 = 🔲 待核攒批

**子代理自主决策（主会话复核认可）**：lock_play 两类误挂判 DslError（item 锁仅 on_attack / ace_spec 仅 passive_static）；`_ace_spec_play_locked` 惰性求值（手牌无 ACE 不扫场）；discard choose=N 池不足 no-op 不挂起；heal 可行门只查备战非空；`playable_feasible` 不扩 target_pool=self（trainer 无持有者语义，既有 DslError 拦截正确）。

**遗留**：34 张缺口卡 DSL 编写 → task 070（引擎表达力已备齐：5 扩展 + 3 小扩 + 逆转能量 chooser 组合词待写）；附录 A 3 条待核决议攒批待用户核销；v2 matrix + 校准 → task 07x。

**判据 1–5 全 ✅**。
