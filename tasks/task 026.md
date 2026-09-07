# task 026 · 批 2 re-scope：解锁项驱动 + harness 装配校验

- 状态：进行中
- 关联：PRD §5.5（LLM 辅助编写）/ 里程碑 M5；输入 = task 025 批 1 质量小结（blocked 32 张解锁需求归并）

## 目标

批 1 实测证伪 A/B/C 初判（46 张 A 级仅 10 张可直接写，约 22%），批 2 不再按字母批组织，
改为**解锁项驱动**：先建 filter/condition/原语/数据管道，能解锁的卡（无论原标 A/B）随解锁落地。

范围经用户 2026-09-06 拍板（C1 四点全确认）：

0. **前置：harness 装配校验（版本检查/赛制标签）**——dsl-authoring 装配环节强制以卡池代表卡组的
   card_id 取 text_raw（不得按 name_group 任取印刷），并校验赛制标在当前 standard 快照内合法；
   防彷徨夜灵事故（D 标文本顶替 H 标池内印刷）重演。落点：`.kimi-code/skills/dsl-authoring` +
   `bfsim dsl-check` 工具化校验。含三项子工作：
   - 闸 1 新增「文本等价类一致性」校验：DSL 文件内所有 card_ids 的归一化 text_raw 必须一致
   - 装载键 name_group → card_id 精确挂载（loader 改造，同名多文本文件共存，命名约定 `<名>-<区分词>.yml`）
   - 现有 DSL 审计拆分：朋友手册（「最多2张」/「2张」混挂）、巢穴球、高级球、神奇糖果等着
     异文本印刷收窄或拆文件（池内实测清单见 STATUS 2026-09-06 记录）
1. **filters/conditions 高频项先行**（成本低、解锁面大）：
   - filters（chooser 注册）：`name:<卡名>`、`owner_pokemon:<名>`（db cards.owner 可供数）、
     `energy_<属性>`（参数化）、`pokemon_no_rule_or_basic_energy`、in-play 基础宝可梦、
     古代特质（依赖 CardDef.labels 数据管道）
   - conditions：`self_is_active`/`holder_is_active`、`first_own_turn`、`own_tera_in_play`
     （依赖 CardDef.is_tera）、`opponent_prizes_eq:N`/`opponent_prizes_in:[...]`、`holder_hp_le:N`
2. **B 级域核心机制**：`trigger_on_event` 引擎分发 + `place_damage_counters` 原语
   （彷徨夜灵 H 标咒怨炸弹/摔角鹰人/沙铃仙人掌等多卡在等；自我昏厥原语随咒怨炸弹落地）
3. **其余原语按解锁卡数排序**：search_deck top_n 检视、deck_top 去向+有序排列、
   recover_from_discard bench 去向、attach_energy up-to-N/bench-only/多目标各附1、
   discard 附着能量+区间弃置、counters 词（attached_energy_on_target 等）、
   modify_retreat_cost、modify_attack_cost、招式冷却、devolve、coin_flip until_tails、
   bounce 附着物回手参数、bench_size 覆写、奖赏修正、对手手牌随机回库、二选一组合约束、
   distinct-type 检索+拆分去向
4. **老大的指令顺带落地**（gust 无门控版，用户已确认可直接写；池内 9 套中 8 套使用，最高频卡）

数据管道（随解锁项需要接入）：CardDef.is_tera / labels（古代·未来特质）/ owner。

## 验收标准（测试清单）

开发启动时按 TDD 细化逐条测试清单；批次级验收口径：

### WP0 前置（harness 装配校验 + card_id 挂载 + 审计拆分）——测试清单已定稿

loader / CardLibrary（`dsl/loader.py`）：
1. `load_card_dir` 返回 CardLibrary（dict 子类，键 = card_id），按 card_id 精确取文档
2. 同名两文件（card_ids 不相交）共存不报错；`by_name(name)` 返回全部文档
3. card_id 跨文件重复 → DslError（含文件名上下文）
4. card_ids 为空 → DslError（挂载键必填，2026-09-06 决议）

引擎解析（`engine/core.py` `effect_doc()` 助手，~16 处调用点 + `dsl/primitives.py:687`）：
5. 同名两文本合成对局：两只同名不同 card_id 的宝可梦各自结算各自 DSL 文档（事件断言）
6. card_id 未覆盖但同名有文档 → 返回 None（不兜底、不错挂——彷徨夜灵事故回归测试）
7. 朴素 dict 注入（存量测试兼容路径）仍按 name 键工作

Runner 装配（`runner/experiment.py` prepare / prepare_variant）：
8. prepare 按 card_id 过滤 card_effects；同名两文本分属两套卡组时各挂各的
9. 印刷未覆盖 + 同名有效果文档 → warnings 透传（不硬报错：波波式 vanilla 印刷合法）
10. prepare_variant 换入卡按 card_id 补入 DSL 文档，缺失带告警

dsl-check 闸 1 增强（`cli.py`，`--db PATH` 可选旗标）：
11. 无 --db 行为不变（schema + 词表）
12. 未知 card_id → FAIL
13. 文件内 card_ids 归一化 text_raw 不一致 → FAIL（列出分歧 card_id）
14. 赛制标不在最新 standard 快照（退环境印刷）→ FAIL
15. 全绿 → OK 并回显卡名/效果数（现状保持）

审计拆分（cards/ 现有定义库）：
16. 异文本混挂文件收窄 card_ids 至单一文本等价类：不服输头带 / 厉害钓竿 / 反击捕捉器 /
    巢穴球 / 朋友手册 / 高级球 / 神奇糖果 / 能量转移 / 夜光能量（池内实测清单）；
    被收窄印刷均非池内使用（池内同名异效两例——火恐龙/索财灵——均本就 blocked/vanilla）
17. D 标彷徨夜灵.yml（CS2.5C-018，退环境 + 池内零使用）移出库，分片测试同步删除；
    H 标 CSV8C-082 待 WP2（place_damage_counters）落地时新写
18. 审计后 `dsl-check --db` 全库扫全 OK；已核销卡的池内印刷 card_id 断言被覆盖

收尾硬验：全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归一致
同步纪律：PRD 若有 name_group 主键/挂载表述与新口径冲突，先改 PRD 再落代码

### WP1（filters/conditions 高频解锁项 + CardDef 数据管道 + 随之解锁卡）——测试清单定稿

数据管道（`engine/state.py` CardDef + `data/cards.py::carddef_from_db` + tests/test_deckload.py）：
1. CardDef 新增 `is_tera: bool` / `owner: str | None` / `labels: tuple[str, ...]`，默认空值兼容存量构造
2. carddef_from_db 映射：is_tera←cards.is_tera；owner←cards.owner；labels←effect_tags.labels
   （db 无独立特质列，labels = mik 机制标签「古代/未来」等，db PRD v1.23 契约键）；缺 effect_tags → 空组
3. 映射不猜：db 无赫普组 owner 数据（实测 DISTINCT owner = 玛俐/竹兰/莉莉艾/N/火箭队）——
   不回落卡名前缀硬推，赫普的包包随之记 blocked

filters（`dsl/chooser.py::_match_one` 卡维度 / `_match_in_play` 场上维度，参数化前缀风格）：
4. `name:<卡名>`（卡维度）；未知名不报错（开放字符串，匹配不上即空池）
5. `owner_pokemon:<名>`（卡维度：宝可梦且 owner 命中）
6. `energy_<属性>` 参数化（原字面词 energy_超 泛化为前缀机制，行为不变回归）
7. `pokemon_no_rule_or_basic_energy`（无规则盒宝可梦 或 基本能量）
8. `trait:<特质>`（卡维度 + 场上维度双注册：CardDef.labels 含该特质，如 trait：古代）
9. in-play 基础宝可梦：`basic_pokemon` 在场上维度同词注册（栈顶 stage==0；与卡维度同义复用）
10. 未知词仍 DslError 不猜（含参数化前缀的畸形参数）

conditions（`dsl/chooser.py::_CONDITIONS` / `condition_met` 参数化前缀）：
11. `self_is_active` / `holder_is_active`：持有者/自身为当前战斗宝可梦（栈顶 iid 比对）
12. `first_own_turn`：自己最初的回合（state.turn == 1，turn 仅在先攻方回合开始递增）
13. `own_tera_in_play`：自己场上有太晶宝可梦（依赖 CardDef.is_tera）
14. `opponent_prizes_eq:N` / `opponent_prizes_in:[...]`：对手剩余奖赏卡数判定（参数化）
15. `holder_hp_le:N`：持有者剩余 HP ≤ N（有效 HP 含 modify_hp 修正 − 已受伤害）

引擎钩子（`engine/core.py::_do_attack`）：
16. on_attack 效果带 condition 且不满足 → 招式失败（不结算伤害/效果，回合照常结束，
    攻击事件落 failed 标记）；满足 → 正常 DSL 结算（赫普的古月鸟「则这个招式失败」语义）

随之解锁卡（三道闸，分片 tests/test_dsl_cards_b2_wp1.py）：
17. 老大的指令（CSVH1aC-023，支援者）：gust 无门控版——挂起选对手备战 1 只互换；
    对手无备战不可用（可行性门回归）；38 个印刷同文本等价类全挂载
18. 尖钉镇道馆（CSV10C-216，竞技场）：stadium_grant 检索 owner_pokemon：玛俐 入手+洗牌；
    负例：非玛俐宝可梦/训练家/能量不进池；双方各每回合 1 次（stadium_used 引擎强制）
19. 赫普的古月鸟（CSV10C-188）：随性喷吐 condition opponent_prizes_in:[4,3]——
    满足 120 伤害；不满足招式失败（无伤害、回合结束）；奖赏 5 张不满足

仍 blocked（装配复核更新原因，详见 coverage-plan 落账）：多龙奇（原因失真，实测需
top_n 检视）、水莲的照顾（recover hand up-to）、赫普的包包（db 无赫普 owner 数据）、
奥琳博士的气魄（attach 多目标各附1）等——逐项原因随批末落账更新。

### WP2+（trigger_on_event/place_damage_counters → 其余原语）

启动时按同流程细化；批次级验收口径（WP1 部分已在上节细化，此处保留 WP2+ 口径）：

- 每个新 filter/condition/原语：注册词单测 + 未知词 DslError 不猜 + 词表 vocabularies.yml 同步
- 每张落地卡走三道闸（schema → 单卡单元测试 → 人工核销），日志落 `cards/authoring-log.jsonl`
- 装配校验：故意取错印刷的用例必须被闸 1 拦下（防回归测试）
- 老大的指令：gust 互换 + 无备战不可用的可行性门单测
- 彷徨夜灵 H 标（CSV8C-082 咒怨炸弹）：自我昏厥 + 对手 1 只放置 5 指示物 + once_per_turn 限次
- 全量 pytest 绿 + ruff 零告警 + 沙奈朵镜像同种子 hash 回归
- 批末落账：coverage-plan 状态全量更新 + authoring-log 质量数据（first_pass / 人工修改量）

## 实现要点

- 严守不猜纪律：装配发现清单外机制缺口 → blocked 上报，不顺手扩展范围
- 词表一律开放字符串 + vocabularies.yml 注册，不写死代码
- 规则语义存疑 → ptcg-rules skill 查 rules-manual → rules-reference → 附录 A 决议日志
- 归组口径（2026-09-06 用户决议）：DSL 按（卡名 + 文本）等价类组织、严格拆分（同语义异措辞不合并）；
  装载键 name_group → card_id 精确挂载；闸 1 校验文件内 card_ids 归一化 text_raw 一致

## 结果与遗留

### WP0（2026-09-06 完成）：harness 装配校验 + card_id 挂载 + 审计拆分

**落地**：
- `dsl/loader.py` 新增 `CardLibrary`（dict 子类，键 = card_id）：`from_docs` 校验挂载键必填 +
  card_id 跨文件查重（含文件名上下文）；`by_name(name)` 按文档去重返回；`load_card_dir` 返回 CardLibrary。
- `engine/core.py` 新增 `effect_doc` / `effect_doc_by_ref` 解析助手，全部 17 处查询点 +
  `dsl/primitives.py`（copy_attack）改走助手：CardLibrary 仅按 card_id（无名字兜底），
  朴素 dict 按卡名（存量测试兼容路径保留）。`GameEngine.__init__` 保 CardLibrary 类型。
  copy_attack 嵌套帧 inner 改三元组（card_id, 卡名, 招式名）。
- `runner/experiment.py` 新增 `assemble_card_effects`（按 card_id 过滤 + 覆盖告警）；
  prepare / prepare_variant 改走之；worker 载荷改为去重文档列表，worker 内重建 CardLibrary。
- `cli.py` dsl-check 新增 `--db`：① card_id 存在性 ② 文件内归一化 text_raw 一致
  ③ 最新 standard 合法性快照（SDK `legal_at` LegalityPool，含再录合法口径）。无 --db 行为不变。

**审计拆分实测**（只读 SQL + SDK 复核）：全库仅 2 个文件异文本混挂——
- 不服输头带：10 → 9（剔除 CSVH1aC-016「宝可梦使用的招式」异文本类；池内印刷 CSV1C-117 保留）
- 朋友手册：20 → 11（剔除「2张」类 9 个 id：CSM1DC-246/CSM1bC-121/CSM2.1C-006/CSM2DC-255/
  CSMPkC-010/CSMPoC-007/SSP-NaN48~50；池内印刷 CSV1C-111 所在「最多2张」类保留）
- 出库 3 文件（全印刷退环境 + 池内零使用）：彷徨夜灵.yml（D 标 CS2.5C-018，任务指定）、
  **交替推车.yml / 捕获香氛.yml（全印刷 F 标退环境，同口径出库——超出任务清单的实测发现，
  单卡测试分片同步移除；若回归环境再按 WP2 管线重写）**
- 其余候选（厉害钓竿/反击捕捉器/巢穴球/高级球/神奇糖果/能量转移/夜光能量/波波/皮宝宝）
  实测单文本类且全印刷在合法性快照内（旧标经再录合法），无需收窄。

**验收**：pytest 404 全绿；ruff 零告警；`dsl-check --db` 全库 33 文件全 OK；
沙奈朵镜像同种子 hash 回归（test_deckload::test_loaded_deck_plays_game，真实卡组 +
CardLibrary 直通）通过；池内 9 套卡组印刷覆盖回归：唯一未覆盖且同名有文档的印刷 =
波波 CSV4C-099（「起风」白板异文本，合法走覆盖告警，断言豁免）。

**遗留**：
- 波波 CSV4C-099 式覆盖告警目前仅 prepare 透传打印，report 层未聚合（不影响结果口径）。
- 交替推车/捕获香氛出库后，coin_flip 节点门控 / heal+switch own_bench / own_active_is_basic
  条件失去真实卡测试载体（机制仍在 chooser/原语注册）；WP1+ 落地同机制新卡时回补。
- m5-coverage-plan / authoring-log 的彷徨夜灵已有 blocked 记录；交替推车/捕获香氛原为
  gate3 通过卡，出库落账（状态改「出库：退环境」）由主会话统一处理。
- 彷徨夜灵 H 标 CSV8C-082（咒怨炸弹）归 WP2：place_damage_counters + 自我昏厥原语落地后新写。

### WP1（2026-09-07 完成）：filters/conditions 高频解锁项 + CardDef 数据管道 + 3 卡落地

**数据管道**：CardDef 新增 `is_tera` / `owner` / `labels`（`engine/state.py`）；
`carddef_from_db` 映射 is_tera←db is_tera、owner←db owner、labels←effect_tags.labels
（db PRD v1.23 契约键，mik 机制标签「古代/未来」等——db 无独立特质列，labels 键即特质事实源）。
单测落 `tests/test_deckload.py`（含缺省空值不猜用例）。

**filters 注册**（`dsl/chooser.py`，未知词仍 DslError）：
- 卡维度：`name:<卡名>`、`owner_pokemon:<名>`（宝可梦且 owner 命中；db 未覆盖主人组恒不匹配，
  不回落卡名硬推）、`energy_<属性>` 参数化（原字面词 energy_超 泛化并入，行为回归测试保持）、
  `pokemon_no_rule_or_basic_energy`、`trait:<特质>`（CardDef.labels）
- 场上维度：`basic_pokemon`（与卡维度同词同义复用，栈顶 stage==0）、`trait:<特质>`

**conditions 注册**（`condition_met`）：`self_is_active`/`holder_is_active`（栈顶 iid 比对）、
`first_own_turn`（turn==1，turn 仅在先攻方回合开始递增）、`own_tera_in_play`、
参数化 `opponent_prizes_eq:N` / `opponent_prizes_in:[...]` / `holder_hp_le:N`
（有效 HP − 已受伤害；畸形参数 DslError 不猜）。
单测落 `tests/test_filters_conditions_wp1.py`（14 用例）。

**引擎钩子**：`_do_attack` 支持 on_attack 效果级 condition——不满足则招式失败
（不结算伤害/效果、回合照常结束、attack 事件落 failed 标记），「则这个招式失败」语义
（赫普的古月鸟）。既有卡无 on_attack condition，行为零回归。

**落地 3 卡**（三道闸前两闸全过，gate3=false 待用户核销；authoring-log 已落 first_pass=true）：
- 老大的指令（CSVH1aC-023）：gust 无门控版；38 个印刷归一化 text_raw 实测全一致、全挂载。
- 尖钉镇道馆（CSV10C-216）：stadium_grant + `owner_pokemon:玛俐`。
- 赫普的古月鸟（CSV10C-188）：`opponent_prizes_in:[4,3]` + 招式失败钩子。
- 分片测试 `tests/test_dsl_cards_b2_wp1.py`（7 用例，含老大的指令无备战不可用门、
  尖钉镇道馆过滤负例、古月鸟奖赏 4/3/5 三分支）。

**词表同步**：本批未新增 actions/selectors/counters/destinations/triggers/limits 六段词
（gust 用既有 switch、检索用既有 search_deck/shuffle_deck）；filters/conditions 按既定架构
注册于代码求值点（vocabularies.yml 无对应段，闸 1 不校验，闸 2 兜底），vocabularies.yml 无变更。

**验收**：pytest 427 全绿（基线 404 + WP1 新增 23）；ruff 零告警；`dsl-check --db`
全库 36 文件全 OK；沙奈朵镜像同种子 hash 回归（test_loaded_deck_plays_game）在套件内绿。

**遗留**：
- **db 数据缺口：cards.owner 未覆盖赫普组**（实测 DISTINCT owner = 玛俐/竹兰/莉莉艾/N/火箭队）——
  赫普的包包 blocked，需 db 侧补数（不回落卡名前缀硬推）。化朗镇/赫普的讲究头带/赫普的卡比兽
  等其余赫普机制卡届时同受其益。
- 多龙奇原 blocked 原因失真（装配复核）：实测为「牌库顶2检视选1、剩余放下方」，缺
  search_deck top_n 检视 + 剩余卡 deck_bottom 去向，归 WP2+ 原语批。
- 水莲的照顾：过滤器已备，缺 recover_from_discard hand up-to（min_choose=0，同 超级能量回收）。
- 奥琳博士的气魄：trait：古代 已备，缺 attach 多目标各附1。
- coverage-plan 已更新 13 行 blocked 原因（标注 WP1 已备项）+ 3 行 done。
