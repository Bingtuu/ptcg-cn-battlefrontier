# task 025 — 批 1：小原语批 + A 级 46 张（M5 覆盖扩展第一波）

来源：M5 拆解（STATUS.md 当前段）+ `docs/m5-coverage-plan.md` 批 1 定义（A 级 = 现有原语可写 + 顺路补小原语）。卡池事实源 `config/target-pool.v1.yml`。

## 设计

### A. 小原语批（引擎/解释器，TDD 先行，各配代表卡走三道闸）

| 原语/机制 | 代表卡 | 设计要点 |
|---|---|---|
| `coin_flip` + 节点级门控 | 捕获香氛 | `coin_flip` 原语掷币置 ctx 结果；`ActionNode` 增 `condition: str \| None` 字段，运行时词 `if_flip_heads` / `if_flip_tails`（不满足跳过该节点，事件流标注 skipped）；多掷计数（正面数×N）本期不做，遇卡标 blocked |
| `heal` | 交替推车 | 去 N×10 伤害（指示物 N 个），selector own_active/choose 目标；不超过现有伤害（floor 0） |
| `switch` 扩展 own 侧 | 交替推车 | 现仅 opponent_bench gust；增 `own_bench`（自己战斗场↔备战互换，回备战清状态，与撤退同规则） |
| `bounce`（回手牌） | 弗图博士的剧本 | 场上宝可梦回手牌，附着物（能量/道具/进化链）按规则进弃牌区；selector own/opponent 按卡面 |
| 伤害修饰结算接入 | 不服输头带 | 仿 task 015 `_effective_hp` 模式：道具 passive 的 `modify_damage` 声明式求和接入 `_attack_damage`；白板与 DSL damage 两路径共用 |

### B. A 级 46 张批量编写（harness 全量投产）

- 子代理 swarm 并行（每子代理 4–6 张，独立工作），严格走 dsl-authoring skill：装配 → 草稿 → 闸 1 → 闸 2 → 日志。
- 每张卡日志落 `cards/authoring-log.jsonl`；blocked 卡标 `docs/m5-coverage-plan.md` 并记原因（解锁归后续 task）。
- 闸 3 人工核销：批量提交用户，抽样 + 关键卡逐张（用户定抽查口径）。
- 质量数据：批末统计一次通过率 / 人工修改量（task 031 素材）。

### C. 复验

- 定义库计数测试同步；批 1 完成后沙奈朵 + 多龙系等部分卡组可跑近似镜像（缺 B/C 卡的按白板降级运行，仅作 smoke，不作验收）。
- 全量 pytest 绿 + ruff 零告警；同种子 hash 回归（既有卡组不受影响）。

## 验收标准

- [x] 5 个小原语/机制各自单测 + 代表卡过闸 1/2（捕获香氛/交替推车/弗图博士的剧本/不服输头带）。老大的指令确认无需新原语（既有 gust），其在覆盖计划中归 B 级行，留待批 2 随批编写。
- [x] A 级 46 张全部处理：done 10（池内 DSL 卡）+ vanilla 4 + blocked 32（覆盖计划逐卡标注原因）。
- [x] `cards/authoring-log.jsonl` 每卡一条，字段完整（批 1 合计 49 条：5 既有 + 44 本次）。
- [x] 批 1 质量小结写入本文档记录节（见下「批 1 质量小结」）。
- [x] 全量 pytest 388 绿 + ruff 零告警；含沙奈朵镜像同种子 hash 回归（无回归）。
- [x] STATUS.md 更新 + 本文档归档。

## 记录

- 2026-08-30 开工。gust 已存在（`switch` selector=opponent_bench，反击捕捉器在用），老大的指令预计无需新原语；bounce（回手）为新增第五项——调研初判 A 级低估了 bounce，在此更正。
- 2026-08-30 A 节小原语批完成（子代理执行）：5 项全部落地，TDD 先行（每项 RED→GREEN）。
  - `coin_flip` + 节点级门控：`ActionNode.condition` 字段（schema.py）；解释器 `_NODE_CONDITIONS`（if_flip_heads/if_flip_tails，无前置掷币/未知词 = DslError）；掷币结果经 `PendingChoice.flip_result` 穿透挂起恢复（choice 阶段不消耗随机源，值稳定），跳过节点落 `effect_primitive` 且 result.skipped=true、不占选择游标。
  - `heal`：selector own_active / own_pokemon_in_play（choose=1 + filters），floor 0。
  - `switch` 增 own_bench：回备战清特殊状态（§7.1）、伤害/能量保留（§5 撤退条目）、不占撤退次数；可行性门加无备战拦截。
  - `bounce`：整叠回手 + 附着物进弃牌区；战斗场放回 → promote_to_main 主阶段内换上；无宝可梦判负（rules-reference 附录 A 2026-08-30 三条决议，含 🔲 待核项）。
  - `modify_damage`：声明式（不服输头带），引擎 `_effective_damage_modifier` 仿 `_effective_hp` 求和，接入 `_attack_damage`（§6 顺序 2）；白板 / DSL damage / copy_attack 白板三路径接入；仅对手战斗场落点。
  - 代码注册新词：filters `evolved_pokemon`、condition `own_active_is_basic`（chooser.py）；词表 vocabularies.yml actions +4（coin_flip/heal/bounce/modify_damage）、selectors +1（own_active）。
  - 代表卡 4 张（捕获香氛/交替推车/弗图博士的剧本/不服输头带）闸 1/2 全过、一次通过率 4/4，日志已落（gate3=false 待人工核销）。老大的指令确认可直接写（gust 无门控版），留待 B 节批量一并。
  - 交替推车机制取舍：heal 前置（与原文「互换后回复被换入备战区的宝可梦」终态等价，伤害指示物随宝可梦移动）——已在卡片实现注记与测试记录。
  - 定义库计数测试同步 24→28；全量 pytest 365 绿（含沙奈朵镜像 hash 回归）+ ruff 零告警。

### 批 1 质量小结（2026-08-30 落账后）

**A 级 44 张处理结果**（另 2 张 A 级=友好宝芬 task 024 已 done + 老大指令确认无需新原语转 B 行）：

- done 8（吉尼亚/波波/能量输送/宝可梦交替/皮宝宝/朋友手册/彷徨夜灵/玛俐的捣蛋小妖）+ vanilla 4（多龙梅西亚/比比鸟/玛俐的诈唬魔/拉鲁拉丝，目标印刷核验无效果句）+ blocked 32。
- 加上小原语批代表卡 4 张，本 task 新写 DSL 卡 12 张，闸 1/2 全过。**first_pass 10/12**：能量输送（gate2 测试断言手牌数算错）、玛俐的捣蛋小妖（测试常量名笔误 NameError）——两例均为测试侧笔误、DSL 草稿零修改，严格口径仍记 false。12 张 gate3 全待人工核销。
- **关键发现：A 级初判（effect_tags 归判 vs text_raw 实测）失真严重**——初判「现有原语可写」的 46 张实际仅 10 张可直接写（约 22%），32 张卡在装配阶段发现机制缺口。失真主因：effect_tags 只标效果大类，不体现选择器约束、条件门控、计数来源等实现级需求。

**blocked 32 张的解锁需求归并**（task 026+ re-scope 输入）：

- filters（chooser 注册）：`name:<卡名>`、`owner_pokemon:<名>`（db cards.owner 可供数据）、`energy_<属性>`（参数化属性能量）、`pokemon_no_rule_or_basic_energy`、in-play 基础宝可梦、古代特质（**需 CardDef.labels 数据管道**）。
- conditions：`self_is_active`/`holder_is_active`、`first_own_turn`、`own_tera_in_play`（需 CardDef.is_tera）、`opponent_prizes_eq:N`/`opponent_prizes_in:[...]`、`holder_hp_le:N`。
- 原语/机制扩展：search_deck top_n 限定池（牌库顶 N 检视）、deck_top 去向+有序排列、recover_from_discard bench 去向 + up-to（min_choose=0）、attach_energy up-to-N / bench-only / 多目标各附 1、discard 附着能量 + 区间弃置、counters 词 attached_energy_on_target + 前节点选择数计数、modify_retreat_cost、modify_attack_cost、招式冷却、devolve、变身替换、trigger_on_event 引擎分发、place_damage_counters、coin_flip until_tails 模式、对手手牌随机回库、二选一组合约束、distinct-type 检索+拆分去向、bounce 附着物回手参数、bench_size 覆写（零之大空洞）、奖赏修正。
- 数据管道（db 侧已有或需接）：CardDef.is_tera / labels（古代/未来特质）/ owner。

**结论**：task 026（B 级批）需 re-scope——先补上述高频解锁项（filters/conditions 成本低、解锁面大），trigger_on_event 分发与 place_damage_counters 为 B 级域核心。同名组多文本印刷归组口径（彷徨夜灵/波波/皮宝宝只覆盖池内实际印刷）待用户决策。
