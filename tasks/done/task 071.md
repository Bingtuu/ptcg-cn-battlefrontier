# task 071 · 卡池 v2 引擎扩展第二批 + 070 收口（blocked 19 张清零）

- 状态：完成（2026-10-28；`--db` 装载核销留到有主库的环境）
- 关联：task 070 第一批（15 落地 / 19 blocked）→ 本任务（blocked 缺口扩展 + DSL 编写 + 070 判据 5/6 收口）→ task 07x（v2 matrix + 校准）
- 缺口事实源：`cards/authoring-log.jsonl` batch 10 blocked 行（精确到读点）+ 各组子代理报告

## 目标

两阶段：**阶段 1** 落地 19 张 blocked 卡所需的引擎/DSL 框架扩展（TDD）；**阶段 2** 编写 19 张 DSL（三道闸），v2 池 125 卡装载零缺口，070 收口。

## 设计决议

- **D-071-1 分组（文件面防冲突，069 惯例）**：组 A = chooser.py + interpreter.py 面（WP1–3 + WP16）；组 B1/B2 = primitives.py 面串行两批（WP4–6 / WP7–10）；组 C = core.py 读点面（WP11–15）；WP17 跨面小改主会话在组 A/B/C 全部返回后直做。子代理 TDD + 主会话独立复验；缺词/规则歧义报主会话，禁止自造未注册词、禁止改存量测试断言迁就实现
- **D-071-2 规则出处**：突进进化（§1.1 一般进化锁的卡面放宽）；多谢款待（§8 奖赏拿取卡面加成）；N的城堡（§1.3 竞技场对双方生效 + §5 撤退费用）；激流水泵（§6 招式可选段「在这种情况下」时序）；均落附录 A 决议，主会话定稿
- **D-071-3 reveal opponent_hand 信息公开口径（咕咕）**：最小实现 = reveal 事件入流（观测性/回放保真），Agent 可见视图与 MCTS determinization 冻结集**不扩**（信息利用损失记 backlog，防 069 级信息泄漏回潮）；附录 A 决议
- **D-071-4 grant_attack 合成口径（能量涡轮 latent gap）**：db 不解析训练家卡面招式 → grant_attack args 扩 `{cost, damage}`（缺省 damage=null 纯效果招式），引擎枚举/执行落点在 `tool.card.attacks` 为空时按声明合成 AttackDef；db 侧补解析报上游另记，不阻塞。既有学习器（进化/退化）声明零变化行为不变
- **D-071-5 不降级纪律**：整卡不可完整表达则标 blocked 报主会话，不写半截 DSL（猛雷鼓ex 先例）

## 工作包（阶段 1，落点由各组 TDD 实证定位）

- **WP1 卡牌维度过滤器 ×3**（组 A）：`pokemon_no_rule`（supertype=pokemon ∧ rule_box None，任意阶段；宝可平板）；`rule_box:<值>` 参数化正向过滤（席蓝 rule_box:ex）；`pokemon_tera`（CardDef.is_tera；太晶珠）
- **WP2 条件词 ×3**（组 A）：effect 级参数化 condition `holder_trait:<标签>`（读 CardDef.labels，对齐 holder_owner: 先例；驱劲能量 未来——先实证 db effect_tags.labels 供数）；节点级条件 `if_own_prizes_eq:N`（莉莉艾的决心，draw 6 + 门控 draw 2 = 文本「变为8张」）；节点级白名单放行参数化 `holder_has_energy:<属性>`（电蜘蛛麻麻网，effect 级 task 017 已有此前缀）
- **WP3 ability 成本门**（组 A）：ability_feasible 放行 discard own_hand choose=N 特性成本形态（N的索罗亚克ex 交易；chooser.py:727 白名单）
- **WP4 attach_energy 组合 ×2**（组 B1）：multi_target × target_pool=own_bench 放行+实现（玻璃喇叭，primitives.py:813 显式 DslError 处；逐只各附着 1 张弃牌区基本能量）；own_deck 段 2 目标池读 target_pool=own_bench（能量涡轮 a，备战限定）
- **WP5 move_energy any_count→self**（组 B1）：任意数量自己场上附着能量转附固定目标=self（铁斑叶ex 快速游标转附段；既有 any_count 全场交互 up-to 与 choose=N 定点之外的第三形态）
- **WP6 discard 两形态**（组 B1）：对手侧——新选择器 `opponent_attached_energy`（词表 + chooser 对手附着能量池解析）+ discard 执行分支（粉碎之锤，掷币门控用既有 if_flip_heads）；self 全弃自动——来源宝可梦附着能量全部弃置无选择（焚身加农炮，N的达摩狒狒）
- **WP7 附着能量回库**（组 B2）：新形态「从自身摘下 N 个附着能量放回牌库 + 重洗」（厄诡椪 激流水泵前段；discard 仅进弃牌区、move_energy 仅场上转附，均不合）；可选（「若希望」）用既有 min_choose=0/up-to 形态
- **WP8 reveal opponent_hand**（组 B2）：reveal 原语扩 selector=opponent_hand（咕咕 寂静之翼；信息公开口径 D-071-3）
- **WP9 计数词**（组 B2）：`opponent_discard_basic_energy_count`（对手弃牌区基本能量张数；N的达摩狒狒 复燃 ×30）
- **WP10 copy_attack 备战维度**（组 B2）：复制源选择器扩自己备战区维度 + owner_pokemon:N 过滤（暗夜王牌「备战区中的『N的宝可梦』所拥有的1个招式」；嵌套执行口径对齐梦幻ex 先例；多级嵌套禁区声明沿用）
- **WP11 竞技场撤退读点**（组 C）：`_effective_retreat_cost` 加竞技场文档扫描分支（现仅持有者道具 + 己方宝可梦卡两分支，实证静默白板）；「【撤退】所需能量全部消除」= 置 0 口径（与既有减免叠加序钉死）；owner 过滤 = 对撤退方持有者求「N的宝可梦」（N的城堡；附录 A）
- **WP12 进化门放宽**（组 C）：modify_evolution 扩 args 或新声明——声明持有者在战斗场时跳过 entered_play_this_turn / turn==1 双门（伊布 突进进化；`_ability_suppressed` 守卫；§1.1 一般规则卡面放宽，附录 A）
- **WP13 suppression 宝可梦来源 + 效果类型定向**（组 C）：`_suppress_ability_types`（core.py:1921 现仅扫 stadium）扩到双方场上宝可梦特性文档声明；定向子类 = suppress_ability args 加 `with_primitive: ko_self`（「令自身【昏厥】的效果的特性」= 特性文档 ability_manual 效果的 actions 含 ko_self 原语——ko_self 是词表唯一自昏厥原语，词表开放、后续新族追加值即可；可达鸭 湿气消除双方全部此类特性，动态求值——湿气来源被监视塔消除则抑制同步失效；附录 A）
- **WP14 prize_bonus 非太晶 scope**（组 C）：多谢款待「因这个招式的伤害昏厥 → 多拿取1张奖赏卡」——触点 core.py:2256 现要求攻击方 is_tera；扩 scope=attack_ko 不限太晶（铁臂膀ex 非太晶；§8 卡面加成，附录 A）
- **WP15 lock_attack 全招式形态**（组 C）：args scope=all 锁持有者全部招式（火伊布ex 红玉髓「在下一个自己的回合，这只宝可梦无法使用招式」；双招式卡 D-WP4-5 单招式近似不可借用）
- **WP16 「在这种情况下」节点门控**（组 A，interpreter.py 面）：节点级条件——前序**可选**节点实际执行了才放行本节点（厄诡椪 激流水泵后段备战 120；interpreter 记录可选节点执行结果，与 if_flip_heads 族同层）
- **WP17 grant_attack 合成 AttackDef**（主会话直做，组 A/B/C 全部返回后动手防文件冲突）：D-071-4；schema args 白名单 + 枚举/执行双落点 + 既有学习器回归

## 阶段 2：19 张 DSL 编写（阶段 1 完成后派批，三道闸）

- 批 4a 训练家 7 张：宝可平板 / 席蓝 / 太晶珠 / 莉莉艾的决心 / 玻璃喇叭 / 粉碎之锤 / N的城堡
- 批 4b 训练家 2 张 + 宝可梦：驱劲能量 未来 / 招式学习器 能量涡轮 / 可达鸭 / 咕咕 / N的达摩狒狒
- 批 4c 宝可梦 7 张：N的索罗亚克ex / 伊布 / 厄诡椪 水井面具ex / 火伊布ex / 铁臂膀ex / 铁斑叶ex / 电蜘蛛
- 分片 `tests/test_dsl_cards_b071_w{4a,4b,4c}.py`；authoring-log batch 11 主会话集中落账

## 边界

- 不动 v1 池与既有结果；不改 runner/report 层；电电虫洗牌 2 次偏差维持现状记 backlog（用户未拍板新形态）
- 规则歧义报主会话裁决进附录 A；WP13 定向消除判定族清单若定不下 → 可达鸭降级 blocked 不猜

## 验收标准（终止判据先行）

1. 每 WP 单测覆盖：正向 + 抑制交互（监视塔/阻碍之塔）+ 边界（侧别/空池/可放弃/双招式锁全）；存量测试零改动
2. 19 张 DSL 全过闸 1（dsl-check --db）+ 闸 2（分片单测，函数名含中文卡名）；闸 3 = 用户核销
3. 全量 pytest 绿 + ruff 零告警（主会话亲跑）
4. **v2 池 125 卡装载零缺口**（9 卡组 load_deck 零告警 + 缺口 = 0；070 判据 5 收口）
5. 附录 A 决议落 `docs/rules-reference.md`（WP11/12/13/14 + D-071-3/4），待核标记
6. authoring-log batch 11 + STATUS.md 落账 + 本档与 task 070 归档

## 结果与遗留

**2026-10-28 收口。** main 上没有 `tests/test_primitives_t071_a.py`，阶段 1 按任务书重新 TDD。

- **WP1–17 ✅**：过滤器 3、条件词（含节点级 `if_own_prizes_eq` / `holder_has_energy` / `holder_trait`）、特性弃手牌成本、attach 多目标备战与牌库备战池、`single_target`（燃烧充能全部附到 1 只）、move_energy 任意数量转自身与回库重洗、对手附着能量弃置与来源全弃、reveal 对手手牌、计数词、备战复制招式、竞技场撤退、突进进化、湿气 `with_primitive: ko_self`、`prize_bonus scope=attack_ko`、`lock_attack scope=all`、「在这种情况下」、grant_attack 合成 AttackDef。复眼用 `modify_damage scope=self` + `target_has_ability`
- **19 张 DSL ✅**（闸 2；闸 3=false）。无 `--db` 的 dsl-check 通过。authoring-log batch 11
- **2026-10-28 核销**：闸 1 / 闸 3 = 19/19；附录 A 七条 ✅ 已核。激流水泵初稿 `up_to` 过宽（够 3 张仍可只交 1～2），改为 `opt_exact`（TPCi 2024-09-12：可放弃；执行则恰好 min(3, 身上张数)）
- **未在本环境完成**：v2 九卡组 `load_deck` 零缺口（无 `ptcg-cn.db`）。粉碎之锤只挂 `30thDC-029`
- **未做**：072 及以后
