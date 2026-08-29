# task 005 · 锁定第一套目标卡组与首批原语清单

- 状态：完成
- 关联：PRD §5.2 / §5.3 / §13，里程碑 M2

## 目标

按 PRD §5.3「原语先行，逐卡落地」的覆盖策略，用 db 项目 `stats_usage(granularity="archetype")` 当前 WUR 排名驱动，锁定 M2 第一套目标卡组；列出该卡组全部涉及卡（含 `text_raw` / effect_tags），归并出 DSL 首批原语、选择器、触发器需求清单，回答 PRD §13 的两个开放问题（目标卡组名单、选择器体系初稿）。

## 验收标准（测试清单）

本任务为分析产出任务，验收以文档与数据为准：

- [x] 记录 WUR 查询的时间、数据版本（快照 id）与排名结果，可复算
- [x] 锁定第一套目标卡组，给出完整 60 卡卡表（card_id / name_group / 数量 / 卡牌类别）
- [x] 每卡附 `text_raw` 原文与 db effect_tags（原文保真，不改写；按合规约束原文不落库，以快照 id + 查询条件为复算锚点）
- [x] 归并首批原语清单：动作原语 / 选择器 / 触发器 / 成本限制四类，标注覆盖哪几张卡
- [x] 明确 M2 范围边界：哪些效果暂不实现（YAGNI），列入遗留
- [ ] 结果落入本文档；pytest 全绿 + ruff 零告警（不破坏现有代码）

## 实现要点

- 数据只进不出：ptcgdb SDK 只读访问，不改主库
- WUR 排名以 archetype 粒度为准，取第一名的具体卡组（同名群归并以 name_group 对齐）
- 原语词表对齐 db `config/vocabularies/effect_tags.yml`（29 意图标签 + 3 机制 flag），开放字符串不写死

## 结果与遗留

### WUR 查询记录（可复算）

- 查询时间：2026-08-28；SDK `stats_usage(granularity="archetype")`（canonical `wur.sql`，加权出场率）
- 数据源：`C:/Vibe Project/Pokearena/data/ptcg-cn.db`（只读 mode=ro），`data_version=v20260809.1`，`user_version=13`
- 窗口：2026-05-30 ~ 2026-08-28（默认 90 天滚动窗）；division=master，basis=cn，排除 qual/team；`n_tournaments=6`
- archetype WUR 前五：沙奈朵 0.129（n=56）> 喷火龙 大比鸟 0.116（n=42）> 猛雷鼓 厄诡椪 0.115（n=29）> 放逐Box 0.088（n=7）> 雷吉铎拉戈 0.061（n=20）

### 锁定结果

**第一套目标卡组 = 沙奈朵**（WUR 第一）。代表卡表取窗口内最近一场冠军且 mapping_status=full 的卡组：`mik_moe:644634`（赛事 `mik_moe:3463`，2026-08-01，49 人，rank 1，合计 60 张校验通过）。

| # | 数量 | 卡名 | card_id | 类别 | 标记 | effect_tags |
|---|------|------|---------|------|------|-------------|
| 1 | 3 | 拉鲁拉丝 | CSV2C-053 | 宝可梦·基础 | G | — |
| 2 | 2 | 奇鲁莉安 | CSV2C-054 | 宝可梦·1阶 | G | — |
| 3 | 2 | 沙奈朵ex | CSV2C-055 | 宝可梦·2阶·ex | G | spread/heal/status/energy_accel |
| 4 | 1 | 飘飘球 | CSV2C-060 | 宝可梦·基础 | G | — |
| 5 | 1 | 吼叫尾 | CSV6C-065 | 宝可梦·基础·古代 | G | lock（误标，实为计数伤害） |
| 6 | 3 | 愿增猿 | CSV8C-094 | 宝可梦·基础 | H | spread/status + once_per_turn/conditional |
| 7 | 1 | 吉雉鸡ex | CSV8C-135 | 宝可梦·基础·ex | H | draw/spread/lock + once_per_turn/conditional |
| 8 | 1 | 梦幻ex | 151C-151 | 宝可梦·基础·ex | G | draw/copy + once_per_turn |
| 9 | 1 | 莉莉艾的皮皮ex | CSV10C-082 | 宝可梦·基础·ex | I | modifier |
| 10 | 4 | 高级球 | CSV1C-112 | 物品 | G | search |
| 11 | 2 | 巢穴球 | CSVH1C-043 | 物品 | G | search |
| 12 | 2 | 大地容器 | CSV6C-115 | 物品·古代 | G | search |
| 13 | 2 | 神奇糖果 | CSVH1C-045 | 物品 | G | evolution |
| 14 | 2 | 夜间担架 | CSV8C-183 | 物品 | H | discard_recover |
| 15 | 1 | 厉害钓竿 | CSV1C-109 | 物品 | G | discard_recover/bounce |
| 16 | 1 | 能量转移 | CSVH1aC-008 | 物品 | G | energy_move |
| 17 | 2 | 反击捕捉器 | CSV6C-114 | 物品 | G | gust + conditional |
| 18 | 1 | 秘密箱 | CSV8C-176 | 物品·ACE SPEC | H | search |
| 19 | 3 | 勇气护符 | CSV1C-118 | 宝可梦道具 | G | modifier |
| 20 | 2 | 招式学习器 进化 | CSV5C-119 | 宝可梦道具 | G | search/evolution/special_behavior |
| 21 | 4 | 博士的研究 | CSV1C-121 | 支援者 | G | draw |
| 22 | 4 | 奇树 | CSV3C-123 | 支援者 | G | draw/hand_disrupt/bounce |
| 23 | 2 | 派帕 | CSV1C-123 | 支援者 | G | search |
| 24 | 2 | 深钵镇 | CSV2C-127 | 竞技场 | G | search + once_per_turn |
| 25 | 7 | 基本超能量 | CSVE1C-PSY | 能量 | — | — |
| 26 | 3 | 基本恶能量 | CSVE1C-DAR | 能量 | — | — |

各卡 `text_raw` 原文、attacks/abilities 结构化字段已逐卡核对（查询可复现：`deck_id='mik_moe:644634'` JOIN cards，数据快照 `data_version=v20260809.1`）。按合规约束（不存储/分发卡牌数据），`text_raw` 原文不落本仓库，以快照 id + 查询条件为复算锚点。注意：神奇糖果 `text_raw` 在 db 中末尾缺右括号（源站数据如此），按「原文保真」原则照原样引用，DSL 注释不改写。吼叫尾 effect_tags 误标 lock（「不计算弱点、抗性」规则引用句被旧 pattern 命中，task 040 已收窄但此卡未复扫），仅作参考，以 text_raw 为准。

### 首批原语清单（四类，按 db 词表对齐）

**动作原语**（动作 → 覆盖卡）：

- `draw`：固定 N（化危为吉 3）；补至手牌 N（再起动至 3）；计数抽 = 剩余奖赏卡数（奇树）——博士的研究/化危为吉/再起动/奇树
- `discard`：手牌全部（博士的研究，兼作效果非成本）；手牌选 N 张作成本（高级球 2 / 大地容器 1 / 秘密箱 3）
- `search_deck`：过滤器 card_type / stage / trainer_subtype / 排除规则盒；数量 up-to-N；去向 = 手牌（高级球/大地容器/派帕/秘密箱）/ 直接放备战区（巢穴球/深钵镇）/ 直接进化（学习器·进化）；后接 `shuffle_deck`
- `recover_from_discard`：入手牌（夜间担架，宝可梦或基本能量 1 张）；回牌库+洗牌（厉害钓竿，宝可梦+基本能量合计 ≤3）；附着到宝可梦（精神拥抱，基本超能量→超宝可梦）
- `damage`：固定伤害打战斗场（白板已有）；任选对手 1 只（含备战，备战不计算弱点抗性——残忍箭矢/凶暴吼叫）；变量伤害 = 目标伤害指示物×N（凶暴吼叫）/ 自身指示物×N（气球炸弹）/ 对手战斗场附着能量×N（精神强念）/ 双方备战数×N（满月回旋曲）
- `place_damage_counters`：己方放置（精神拥抱附 2 个，禁止致死限制）；`move_damage_counters`：己方→对手转放 ≤3（亢奋脑力）
- `attach_energy`：来自弃牌区的额外附着（精神拥抱，不受每回合 1 次限制）
- `move_energy`：场上宝可梦间转附 1 个基本能量（能量转移）
- `apply_status`：混乱（精神幻觉）；`clear_status`：自身全部特殊状态恢复（奇迹之力）
- `switch`：强制对手备战↔战斗互换（gust，反击捕捉器）
- `put_into_play`：基础宝可梦从牌库直放备战区（巢穴球/深钵镇）
- `evolve`：跳阶进化（神奇糖果：基础→2阶，跳过 1 阶，首回合与当回合出场禁止）；从牌库进化 ≤2 只备战（学习器·进化）
- `hand_to_deck_bottom`：双方手牌洗回牌库下方（奇树）
- `copy_attack`：复制对手战斗宝可梦 1 个招式（基因侵入）
- `reveal`：给对手看过（检索/回收通用副动作，事件级记录即可）

**选择器**（作用对象 → 覆盖卡）：

- `self` / `opponent_active` / `opponent_active_attack`（复制目标）
- `own_hand`：all / chosen N，可带 card_type 过滤（博士的研究/高级球/秘密箱/神奇糖果）
- `own_deck`：chosen，过滤（card_type / stage=基础 / trainer_subtype∈{物品,道具,支援者,竞技场} / 排除规则盒 / evolves_from 指定宝可梦）
- `own_discard`：chosen，过滤（基本能量 / 宝可梦 / 基本超能量）
- `own_pokemon_in_play`：chosen，过滤（属性=超 / 附着有恶能量 / 基础）
- `own_bench`：chosen ≤2（学习器·进化）
- `opponent_pokemon_any`：chosen 含备战（残忍箭矢/凶暴吼叫/亢奋脑力落点）
- `opponent_bench`：chosen 1（反击捕捉器）

**触发器**（→ 覆盖卡）：

- `on_play`：训练家卡从手牌使用（全部物品/支援器）
- `ability_manual`：自己回合主动发动；限次变体：`once_per_turn` 每只（再起动/亢奋脑力）、`once_per_turn` 同名全卡组共享（化危为吉）、`unlimited`（精神拥抱）
- `on_attack`：招式附加效果（混乱/恢复/变量伤害）
- `passive_static`：常驻修正（妖精领域改写对手龙系弱点；勇气护符 +50 HP）
- `trigger_on_event`：跨回合状态条件（化危为吉：上一个对手回合自己宝可梦昏厥过 → 需跨回合 flag）
- `stadium_grant`：竞技场赋予双方每回合 1 次行动（深钵镇）

**成本与限制**（→ 覆盖卡）：

- 能量成本：多能量类型 + 无色通用（引擎 `attack_cost` 需升级为成本列表）
- 手牌丢弃成本：N=1/2/3 张（大地容器/高级球/秘密箱）
- 使用前提：剩余奖赏卡比较（反击捕捉器：自己 > 对手）；首回合与当回合出场禁止（神奇糖果）
- `once_per_turn`：支援者每回合 1 张（引擎骨架，PRD §6.6）；特性限次（上）；竞技场每玩家每回合 1 次
- ACE SPEC 每卡组限 1 张（秘密箱；卡组校验层）
- 道具每宝可梦限 1 张；学习器自己回合结束时弃置（特殊行为）

### 引擎缺口（M2 必须先补的骨架扩展）

现引擎是白板 stub（`CardDef` 仅单招式固定伤害），覆盖本卡组需扩：

- `CardDef` 字段扩充：弱点/抗性、rule_box（ex→奖赏 2 张）、多招式列表（成本为能量类型列表）、特性、能量类型、trainer_subtype、is_ace_spec
- 弱点/抗性结算（含「备战不计算」贯穿规则）、备战区伤害与昏厥（铺伤/转放可致备战昏厥 → 奖赏结算需在任意时机检查，不限攻击后）
- 训练家卡使用骨架：play_trainer 行动 + 支援者回合标记（PRD §6.6 已规划）
- 宝可梦道具附着/容量 1、竞技場槽位（场上限 1，替换规则）
- 特殊状态落地：至少混乱（攻击掷币）+ 回合间结算框架（task 003 遗留，本卡组只需混乱）
- 跨回合 flag（化危为吉触发条件）
- 硬币：本卡组 27 种卡零 `coin_flip` 命中——**首批原语不需要掷币**（混乱用硬币，引擎层已规划随机源）

### M2 范围边界（YAGNI 暂不实现）

- V-UNION / 放逐区 / 迷失轴（PRD §6.5 已排除，本卡组不涉及）
- 中毒/灼伤/麻痹/睡眠的完整回合间结算（本卡组只需混乱；框架预留）
- 招式复制（基因侵入）与弱点改写（妖精领域）为最难两项：列入 M2 范围但排最后实现；若阻塞，允许暂以「该卡不使用该效果」降级跑局并记录偏差
- 多卡组对局池：M2 只做沙奈朵镜像（self-play）验收，第二套卡组归 M5 覆盖扩展

### 遗留

- mulligan 让先选择权 Agent 化（task 003 遗留）仍挂起，随 M3 启发式 Agent 处理
- 吼叫尾误标已反馈点：可向 db 项目提 pattern 收窄建议（非本项目改动范围）
- 下一任务：task 006（DSL schema）→ task 007（解释器+事件流）→ task 008+（按上表逐个原语落地，单卡测试）
