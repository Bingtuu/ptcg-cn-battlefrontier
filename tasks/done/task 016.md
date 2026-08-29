# task 016 · evolve 原语（神奇糖果跳阶 + 招式学习器「进化」）+ 授予招式执行

- 状态：已完成（2026-08-29）
- 关联：PRD §5.3/§6.2，里程碑 M2；rules-manual §4（进化：特殊状态恢复、伤害保留）/
  §6（招式能量需求）；task 015 道具骨架（grant_attack 声明）的解锁批
- 输入：task 015（道具骨架 + 学习器 defer 锁定）、db evolution_chain_id 字段

## 目标

落地 `evolve` 原语（词表已有词，本期注册实现）两种模式，解锁沙奈朵卡组
进化线全覆盖：

1. **神奇糖果**（CSVH1C-045，物品）：手牌【2阶进化】跳过 1 阶直接放到同链
   【基础】身上。两段式 chooser：选手牌 stage2 → 选同链基础目标。卡面限制
   「自己最初的回合 / 当回合刚出场的宝可梦不可」落可行性门与目标池排除。
   链拓扑数据驱动：`CardDef.evolution_chain`（db evolution_chain_id 装载，
   stub 测试直设），引擎零硬编码。
2. **招式学习器 进化**的授予招式「进化」（【无】）：选自己最多 2 只备战宝可梦，
   逐只从牌库检索其进化形态各 1 张放上进化，并重洗牌库。逐只即选即进化
   （每次挂起只带剩余目标，进化事件逐个入事件流）。
3. **授予招式执行**：战斗宝可梦 attached_tool 的招式并入攻击枚举（索引接在
   自身招式之后），能量由持有者附着能量支付，DSL 绑定取道具文档的 on_attack；
   无绑定的授予招式维持不枚举（task 015 纪律不变）。

## 验收标准（测试清单）

- [x] 神奇糖果两段流程：play_trainer → 选 stage2 → 选目标；栈顶变 stage2、
  特殊状态清除、伤害保留、evolved_this_turn 记入、糖果本体进弃牌区、事件可回放
- [x] 可行性门：手牌无 stage2 / 场上无同链基础 / 目标当回合登场 / 双方第一回合
  （turn==1）→ 不枚举 play_trainer（四条各自独立测试）
- [x] 目标池纪律：异链基础不进第二段选择池；当回合登场基础被 exclude
- [x] 学习器授予招式枚举：持有者能量满足【无】才枚举（attack_index 接自身招式后）；
  能量不足不枚举
- [x] 「进化」攻击流程：选 ≤2 备战（可不选）→ 逐只牌库选进化形态（up-to，可不找）
  → 进化（伤害保留/状态清除/evolved_this_turn）→ 洗牌 → 回合末道具弃置 → 对手回合
- [x] 备战池预筛：牌库无进化形态的备战宝可梦不进第一段池
- [x] 定义库：cards/ 神奇糖果.yml 入库 + 招式学习器 进化.yml 补 on_attack 绑定，共 20 卡
- [x] play_game 含神奇糖果卡组同种子 hash 一致
- [x] pytest 全绿 + ruff 零告警

## 实现要点

- `state.py`：`CardDef.evolution_chain: str | None = None`；`data/cards.py` 装载
  db `evolution_chain_id`
- chooser：`_match_one` 增 `stage2_pokemon` + 参数化前缀 `evolves_from:<名字>`；
  `_match_in_play` 增参数化前缀 `evolve_skip:<chain>`（栈顶 stage==0 且同链）；
  `resolve_pool` 增 `own_bench` 池（selectors 词表已有词）
- primitives `@register("evolve")`：
  - `args.mode == "skip_stage"`：两段式（own_hand stage2 → own_pokemon_in_play
    evolve_skip 目标，exclude 当回合登场 iids）；每次实际进化发 `evolve` 引擎事件
    （与 _do_evolve 事件流对齐）
  - `args.mode == "from_deck"`：第一段 own_bench（exclude 牌库无 evolves_from 匹配的
    备战）；之后逐只挂起 own_deck（`evolves_from:<栈顶名>`，min 0 up-to 语义），
    carry = (当前目标, *剩余目标)，即选即进化；末只完成后返回汇总
  - 进化突变：栈压卡 + conditions 清空 + evolved_this_turn 记入（规则书·进化）
- core：攻击枚举/执行并入 attached_tool 招式（`combined = 自身 + 道具`，各自取
  对应 DSL 文档判定 has_dsl；授予招式能量由持有者支付；DSL 路径 source = 道具卡实例）
- chooser.playable_feasible：增 `first_turn: bool` 参数（core 调用处传 turn==1）；
  evolve/skip_stage 门 = 非首回合 + 手牌有 stage2 + 场上有同链可进化基础
  （非当回合登场）；未知 mode = DslError（不猜）
- DSL：神奇糖果 `{action: evolve, selector: own_hand, choose: 1,
  filters: [stage2_pokemon], args: {mode: skip_stage}}`；学习器 on_attack
  `{action: evolve, selector: own_bench, choose: 2, args: {mode: from_deck}}`
  + shuffle_deck（检索后必洗牌纪律）

## 结果与遗留

- 结果：12 个新测试红→绿一次通过；全量 195 通过、ruff 零告警；定义库 20 卡
- 真实数据冒烟：沙奈朵卡组（mik_moe:644634，含神奇糖果 CSVH1C-045 / 学习器
  CSV5C-119）60 张装载零告警；沙奈朵ex evolution_chain=CSV2C-053（链锚点随
  卡组内基础印刷版本，同卡组同链即可）；整局 play_game 同种子 hash 一致
- 实现落点：
  - `state.py`：CardDef.evolution_chain；`data/cards.py` 装载 db evolution_chain_id
  - `chooser.py`：stage2_pokemon / 参数化前缀 evolves_from:<名>（卡维度）与
    evolve_skip:<chain>（场上维度）；own_bench 池；playable_feasible 增
    first_turn 参数与 evolve skip_stage 门
  - `primitives.py`：evolve 注册（skip_stage 两段式 / from_deck 逐只即选即进化，
    carry=(已进化数, 当前, *剩余)）；_apply_evolution 统一突变 + evolve 事件
  - `core.py`：攻击枚举/执行并入 attached_tool 招式（索引接续、能量持有者支付、
    DSL 文档/效果源取道具卡）；可行性门传 first_turn=turn==1
    （game turn 1 覆盖双方各自首回合——turn 只在先攻方回合开始时 +1）
- 口径说明：学习器「进化」的逐只牌库检索为 up-to 语义（min_choose=0，牌库非公开
  可以不找），与检索类原语一致；进化事件逐个入事件流，effect_primitive 结果仅
  汇总计数
- 遗留：竞技场骨架（深钵镇 stadium_grant）、剩余特性三枚（化危为吉跨回合 /
  亢奋脑力转伤 / 妖精领域弱点改写）、基因侵入 copy 归 task 017
