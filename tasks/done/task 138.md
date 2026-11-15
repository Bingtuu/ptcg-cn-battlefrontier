# task 138 · 太乐巴戈斯ex 引擎扩展批（task 132 backlog 核销）

- 状态：完成
- 关联：task 132（太乐巴戈斯ex blocked 转引擎扩展 backlog）；task 069/071 引擎扩展批惯例（TDD 只加不改）；备赛 P1 goal loop 并行线（与 135/136/137 无依赖）

## 目标

核销太乐巴戈斯ex（CSV9C-175）DSL 所需的三项引擎表达力缺口，并交付该卡 DSL 过三闸。该卡在真实冠军表（1 张，特性减伤影响存活结论），task 131 判为阻断卡——vanilla 有损，特性减伤缺失会使存活/奖赏结论系统性偏离。

## 三项引擎扩展（红测先行，逐项核销）

1. **招式使用门**：特性/效果级「每只宝可梦每回合限用 N 招」的枚举点使用门（具体语义实现期按 text_raw + ptcg-rules skill 定案，争议进附录 A）；
2. **`bench_count_own` 选择器/条件**：效果按己方后备区宝可梦数量取值（伤害/抽牌等参数化场景）；
3. **防御侧时效减伤**：受攻击结算时的时效性减伤落点（参照 `own_turn_end` 先例 D-069-1 的时序落点纪律）。

## 验收标准（测试清单）

1. **TDD 只加不改**：每扩展红→绿闭环；全部落地后既有引擎/DSL 测试零改动（零改动即只加不改证明）；新词表进 `vocabularies.yml`（开放字符串纪律），schema args 键名白名单同步；
2. **太乐巴戈斯ex DSL 三闸**：闸 1 `dsl-check --db` 全过；闸 2 单卡单元测试断言特性减伤关键行为（含减伤截顶/时效边界）；闸 3 核销清单交付 Owner（text_raw 逐条对照）；
3. `experiments/t1114-*.yml` 跑前 strict-coverage 对太乐巴戈斯ex 通过（阻断解除实证）；
4. 事件序纪律：新落点不违背 task 108 双关口冲刷口径（若有触发原语，昏厥结算事件时序抽查）；
5. 全量 pytest 绿 + ruff 零告警；DSL 库份数按当时 `cards/` 实测基线 +1（收官记录实测值）；
6. 记录一次通过率与人工修改量（管线记账纪律）；
7. CHANGELOG.md Unreleased 段记账（Added：新引擎原语 + 新定义）。

## 实现要点

- 引擎层零硬编码纪律不破：扩展是通用原语/门，太乐巴戈斯ex 语义全在 DSL
- 子代理 TDD + 主会话独立复验（dsl-check rc=0 + 新测绿 + 全量零回归逐项亲验）
- 与 task 137 的接口：若本任务先于矩阵跑批完成，太乐巴戈斯ex 所在表（若有）按 DSL 覆盖计；晚完成则不阻塞 137（vanilla 有损表已在 task 131 口径中显式存在）

## 结果与遗留

（2026-11-15 收官；闸 3 已核销同日——主会话逐条 text_raw 对照，Owner 指令代核，4 行全 ✅，零改动）

### 三扩展清单（红→绿 TDD；既有测试零改动）

| D 编号 | 扩展 | 落点 | 动机卡 | 测试证据 |
|---|---|---|---|---|
| D-138-1 | Effect 级 `usage_gate` 开放词（词表新段 `usage_gates:`，首词 `second_player_first_turn`）——招式枚举点使用门（禁用条件真 → 该招式不枚举、攻击机会不消耗；区别于古月鸟 condition「招式失败」语义）；枚举与执行共用求值点 `core._usage_gate_banned`（turn 计数仅在先攻方回合开始递增 → turn==1 且行动方 != first_player = 后攻最初回合），`_do_attack` 执行双保险（IllegalActionError，对齐 suppress_tool 口径） | dsl/schema.py（Effect.usage_gate 字段）+ loader（仅 on_attack + 词表校验）+ vocabularies.yml（usage_gates 段）+ core（_usage_gate_banned / _main_actions 攻击环 / _do_attack） | 太乐巴戈斯ex 同盟打击「这个招式，在后攻玩家的最初回合无法使用。」 | test_primitives_t138 7 测（含四象限求值、装载负例 2、执行双保险） |
| D-138-2 | 计数词 `bench_count_own`（己方备战宝可梦数量；既有 bench_count_both 己方半边，求值走 interpreter._eval_counter 单一点；Agent 侧伤害估算镜像 dsl_estimate._visible_counter 同步登记——己方备战全可见） | vocabularies.yml（counters 段）+ primitives._eval_counter + agent/dsl_estimate._visible_counter | 太乐巴戈斯ex 同盟打击「造成自己备战宝可梦数量×30伤害。」 | test_primitives_t138 3 测（3 备 ×30=90 / 零备 0 / 词表负例） |
| D-138-3 | `prevent_attack_damage` 原语（selector=self，args：timing=opponent_next_turn 必填 / attacker_stage=basic 可选 / except_attacker_type 单值或列表可选）——写 `InPlayPokemon.attack_shield` = (施加 turn, 施加方, 失效 turn, 阶段限定, 属性排除)；失效 turn = 施加 turn + (0 if 施加方==first_player else 1)，生效 iff s.turn==失效turn 且 current_player != 施加方——(player, turn) 对唯一，「下一个对手的回合」窗口精确圈定不漂移；对手回合结束 `_on_turn_end` 跨侧清除（对齐 D-069-1 时点纪律 + task 017 旧竞技场跨侧先例）；守卫 `_attack_damage_shielded` 接招式伤害三路径（_do_attack 白板 / DSL damage 原语 / copy_attack 白板复制，对齐 _survival_cap 三落点纪律）；仅免疫「招式的伤害」——指示物与招式效果不经（比 protection 窄，卡面仅「伤害」）；战斗场/备战落点同守；撤退/进化随宝可梦保留，昏厥/离场即消失 | state.py（attack_shield 字段）+ primitives（PRIMITIVE_ARGS + 实现）+ core（_attack_damage_shielded + 三接入点 + _on_turn_end 清除）+ vocabularies.yml（actions 段） | 太乐巴戈斯ex 皇冠蛋白石「在下一个对手的回合，这只宝可梦不会受到【基础】宝可梦（除【无】宝可梦外）的招式的伤害。」 | test_primitives_t138 10 测（基础非无归零 / 无属性照伤 / 一阶照伤 / DSL 路径 / 备战落点 / 白板复制路径 / 回合末清除 / 过期照伤 / 后攻施加 parity 分支 / args 负例 2） |

### 闸 1

`cards/太乐巴戈斯ex.yml`（7 印刷等价类：CSV9C-175/232/251/262 + CSV9.5C-156/248/259，db 归一化 text_raw 实测一致）`dsl-check --db` rc=0；全库 dsl-check 155/155 [OK] rc=0（基线 154 → +1）。

### 闸 2（亲跑）

- `tests/test_primitives_t138.py` **20/20 绿**（D-138-1 七测 + D-138-2 三测 + D-138-3 十测）；
- `tests/test_dsl_cards_b138_terapagos.py` **8/8 绿**（等价类挂载 / 后攻首回合同盟打击不枚举而皇冠蛋白石枚举 / 次回合起枚举 / 直接驱动报非法 / 备战×30 伤害 / 180+盾施加 / 对手回合基础雷免疫+回合末清除 / 无属性照伤）。

### 闸 3 核销清单（交付 Owner，逐条对照 + 裁定栏）

**太乐巴戈斯ex（CSV9C-175 档，7 印刷）**

| text_raw 原文 | DSL 落点 | 说明 | 人工裁定 |
|---|---|---|---|
| 【无】【无】 同盟打击 30× | on_attack 同盟打击 + damage count=bench_count_own args={op:×, per:30} | D-138-2 计数词；招式绑定名命中卡面；伤害由 DSL 结算（AttackDef.damage 不重复结算） | ✅ |
| 这个招式，在后攻玩家的最初回合无法使用。 | usage_gate: second_player_first_turn | D-138-1 枚举点使用门——禁用时不可宣言、攻击机会不消耗（区别于古月鸟「招式失败」；附录 A 已登记 🔲 待核，Owner 若裁失败语义改挂 condition 即可，两路径引擎并存） | ✅ |
| 【草】【水】【雷】 皇冠蛋白石 180 | damage amount=180 | 招式绑定名命中卡面 | ✅ |
| 在下一个对手的回合，这只宝可梦不会受到【基础】宝可梦（除【无】宝可梦外）的招式的伤害。 | prevent_attack_damage selector=self args={timing: opponent_next_turn, attacker_stage: basic, except_attacker_type: 无} | D-138-3 时效减伤：窗口精确 = 下一个对手的回合（(player,turn) 对唯一）；仅「招式的伤害」——招式附加效果/伤害指示物不免疫（卡面仅「伤害」，比 protection 窄）；战斗场/备战同守（「这只宝可梦」不限位置） | ✅ |

### gate 收口

`tests/test_coverage_gate.py`：**11 passed**——task 139 残留的唯一红（火伊布表「太乐巴戈斯ex CSV9C-175 无文档」）解除，全绿收官。

### 验收数字

- 份数：cards/ 实测 155（基线 154 → +1）；
- 存量零改动证明：未改任何既有测试文件（git diff tests/ 仅含 task 139 先行改动，本批只新增 2 个测试文件）；
- 全量 pytest / ruff：全量 **1949 passed in 779.59s**（exit 0；跑批期间仅两处等价 ruff 改写——core `_attack_damage_shielded` SIM103 与 primitives `_holder` 哑变量——这两个 hunks 在跑批启动后落地，其行为等价性由跑后终态代码的定向复跑覆盖：t138 原语 20/20 + 单卡 8/8 + coverage gate 11/11 全部在终态代码上重跑通过）；ruff check . 零告警；
- 一次通过率：原语扩展 + 卡档闸 1+2 首次提交即过（测试侧构造笔误 3 处——KO 后 active 为 None、p1 行动未置 current=1、朴素 dict 按卡名键——均测试侧修正，非实现返工）；**first_pass=true**；人工修改量已核销落账（2026-11-15：human_edit_lines=0，零改动核销）。

### authoring-log 行（交主会话集中落账）

```json
{"date":"2026-11-15","card":"太乐巴戈斯ex","card_id":"CSV9C-175","author":"llm","batch":138,"gate1":true,"gate2":true,"gate3":false,"first_pass":true,"human_edit_lines":null,"notes":"task 138 引擎扩展批核销（task 132 blocked）：usage_gate=second_player_first_turn（D-138-1）+ bench_count_own（D-138-2）+ prevent_attack_damage 时效减伤（D-138-3）；7 印刷等价类；gate 收口"}
```

> 注：以上 JSON 为交付快照；正式日志已由主会话落账并置 gate3=true（2026-11-15 核销，human_edit_lines=0）。

### 遗留

- **① 闸 3 人工核销**：上表 4 行待 Owner；附录 A 新增 3 行决议（D-138-1/2/3）全部 🔲 待核，与 task 139 七行一并核销。
- **② dsl_estimate 未镜像 usage_gate**：Agent 伤害估算器在后攻首回合仍把同盟打击当作可用斩杀候选（引擎枚举保护合法性，Agent 不可能真选它）——仅首回合斩杀排序的一处启发式噪声，量小不立项。
- **③ timing=opponent_next_turn 的非 on_attack 施用**：原语未限制触发器——若未来训练家卡效果写盾，「下一个对手的回合」从效果结算时点起算，语义自洽（本卡 on_attack 无此问题）。
