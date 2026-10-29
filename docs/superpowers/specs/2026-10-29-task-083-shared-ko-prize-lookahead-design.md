# task 083 · 共享击杀/拿奖前瞻

- 日期：2026-10-29
- 状态：**规格待拍板**（本节 Q1–Qn）。Owner 已拍板方向：不合并 PR #10（task 081）；停窄门补丁；开本收口。拍板表答案仍待勾选。
- 本文不授权改 `heuristic.py`、不写测试、不跑 `bfsim`。拍板之后才按 `docs/superpowers/plans/2026-10-29-task-083-shared-ko-prize-lookahead.md` 开 TDD。代理不合并。
- 前置：task 080 已合入 main `1afa4e2`（PR #8）。081 实现 PR #10 **不合并**（见 §1）。082 规格文档已在 main，**并入本收口为 WP-copy（F1）**，不再当独立窄门硬推。
- 权威：一期 PRD D10（通用启发式，不为单卡组写死）。078 的 Q4 = 否（不读血月 `modify_attack_cost`）继续有效，本刀不重开。

对外中文名：**共享击杀/拿奖前瞻**。不要用「奖杯压力」「王牌转换」。代码开关建议名见 §5（待拍板）；旧名 `prize_pressure_gate` / `copy_lethal_gate` 不作为本刀默认合入标识。

## 1. 背景与证据（必须写进规格）

### 1.1 矩阵背景（抄 STATUS，本会话未重跑）

| 量 | 数字 | 出处 |
|---|---|---|
| 正式矩阵（077–080） | 36×500=18000，失败 0；加权 \|Δ\| **19.0%** | `results/v2-calibration-t080.db` |
| 沙奈朵 × N索（沙奈朵视角） | sim **80%** / real **30.4%** / Δ **+49.6%** | 同上 |
| 同格 100 局刀栈（main / 080） | A78 / B22，种子 `208000..208099`，失败 0 | task 080 |

N索整行（arch）：暗夜王牌触及 57–72%，触及后胜率贴着整体 sim。假说从「落后抢奖窄门」纠正为：**估值层看不见复制击杀，策略门在脏估值上换人会自残。**

### 1.2 Owner 证据：081 方向无效 + copy 估 0 自残

PR #10（`cursor/task-081-prize-pressure-3f2d`）落地了 `prize_pressure_gate`（落后换高伤 / promote 优先击杀）。**Owner 决定不合并。** 证据：

| 证据 | 数字 / 现象 | 解读 |
|---|---|---|
| 同种子 100 局 | 对照 080 的 **A78→A80**（B22→B20），失败 0 | 有效带目标约 78%→60–70%；实际 **方向无效**（略恶化） |
| 六格 ON/OFF（N索为 B，各 50 局同种子） | ΔA（ON 相对 OFF）：**+4 / +0 / +6 / 0 / +2 / 0** | 对 N索 **无益或有害**（ΔA≥0 = 沙奈朵侧更好 / N索更差） |
| 行为根因 | `_max_paid_ko_damage` **不展开** `copy_attack`；暗夜王牌印面无 damage → 估成 **0** | 落后时系统性 **索罗亚克ex → 含羞苞**（把复制手换成印面有伤但更弱的备战） |
| 对比：攻击路径已有 copy 可见性 | `_copy_attack_key` / `_copied_strike` 在 chooser 路径能读供体伤害与击杀 | **同一信息在攻击选择可见、在击杀/撤退估值不可见**——分裂，不是「再加一个 prize 门」能修 |

`prizes_count` = 剩余奖赏张数（可见）。落后定义正确：`own.prizes_count > opponent.prizes_count`。不要用 `factor_prize_diff > 0` 当领先（该因子注释与规则语义相反，已冻结，见 D-083-4）。

### 1.3 为何收口到 083，而不是继续 081/082 窄门

1. **081 策略层消费脏估值**：高低伤比较读 `_max_paid_ko_damage`，复制手永远是 0 → 换下王牌。
2. **082 单独补 copy 进 `_lethal_attack` / `_max_paid_ko_damage`** 是必要但不够：撤退、promote、攻击选择仍各写一套口径，易再分叉。
3. Owner 拍板：**一个共享前瞻接口**；082 的 copy_lethal **并入本收口（F1 / WP-copy）**，不再独立硬推；081 行为默认 **不进 main**。

编号理由：081 搁置（实现 PR 不合并）；082 规格已在 main 但角色变为 083 的 WP-copy。对外统一称 **task 083 · 共享击杀/拿奖前瞻**。沿用 082 会让「落后抢奖」与「共享前瞻」混号；故新开 083。

## 2. 代码现状（事实）

行号会漂，以符号为准。读 `battlefrontier/agent/heuristic.py`（main / 080 栈）。

### 2.1 `_max_paid_ko_damage` 只走 `_attack_table`

循环已付清招式，取 `table[index]` 的有效伤害。暗夜王牌无 damage 节点 → `estimate_attack_damage` 返回 None → 回退 `atk.damage or 0` → **0**。不读 `copy_attack`，不调用 `_copied_strike`。

后果：`_pick_retreat` 的「战斗场已能击杀则不撤 / 备战能击杀则换上」与任何基于该函数的高低伤比较，都把复制手当成 0 输出。

### 2.2 攻击路径已有 `_copy_attack_key`

pending `copy_attack` 选择时，`_copied_strike` 按供体招式估（伤害, 能否斩杀），弱点/抗性用宣言方（战斗场）属性。080 的 `_pick_choose` 用此键排供体。**信息不缺，缺共享出口。**

### 2.3 `_lethal_attack` 只读 `_attack_table`

印面/估算已有伤害的招式能击杀时，已在撤退与支援者之前打出。复制印面 0 时看不见「复制后能击杀拿奖」。

### 2.4 promote 只看 `pokemon_score`

不看能量、不看对手剩余 HP、不看复制前瞻。

### 2.5 奖赏可见且落后定义正确

`view.own.prizes_count` / `view.opponent.prizes_count` 对 Agent 可见。`factor_prize_diff` 只进 `evaluate`，不进 `observe` 决策。本收口若谈「落后」，继续用剩余张数比较，不碰该因子。

## 3. 架构目标

### 3.1 一个共享前瞻接口

建议落点（命名待拍板，本文建议 `_ko_prize_lookahead`）：

```text
_ko_prize_lookahead(view, mon | None = active) -> Lookahead
  Lookahead:
    best_damage: int | None     # 已付清（或复制免再付供体费）路径上对对手战斗场的最高有效输出
    can_ko: bool                # 该输出是否 ≥ 对手剩余 HP（且 lethal_ok）
    via: "print" | "copy" | "none"
```

回答同一问题——**「把 mon 当成战斗场时，这步能否击杀拿奖 / 有效输出是多少」**——覆盖：

| 路径 | 口径 |
|---|---|
| 自己招式 | 现有 `_attack_table` + 印面 `_energy_satisfied` |
| 复制招式 | 已付清的 `copy_attack`（本刀默认只 `selector=own_bench_attack` 一层）；供体不必自己付费；用 `_copied_strike`；未知 filter / 无文档 → 不猜，维持印面 |
| promote 后 | `_view_as_active(view, mon)` 再调同一接口 |

不写进 `_attack_table`（默认），因此不改非击杀 `_pick_attack` 排序——与原 082 D-082-5 一致（待拍板可勾选是否维持）。

### 3.2 消费者（同一接口）

| 消费者 | 本刀（F1–F3）默认 | 说明 |
|---|---|---|
| `_lethal_attack` / 攻击选择中的击杀分支 | **消费** | F1：复制能击杀则走现有击杀优先 |
| `_pick_retreat`（078 击杀撤退） | **消费** | 战斗场/备战的「能否击杀」「最高有效输出」改读共享接口 |
| `_pick_promote` | **消费（仅 F3 口径：击杀可见性）** | 默认：用共享接口回答「换上后能否击杀」；**不**默认实现 081 的「落后才优先」策略 |
| 081 式 `prize_pressure_gate`（落后换更高非击杀 / 落后 promote） | **不进 main** | 若保留概念，标为 **F4 可选策略层**，依赖共享前瞻之后；本规格默认 **不实现 081 行为** |

### 3.3 F 阶梯

| 阶 | 内容 | 本规格默认 |
|---|---|---|
| **F1** | copy 展开估值：共享接口对 `copy_attack` 一层前瞻；`_lethal_attack` 与输出查询可见 | **做**（原 082 并入） |
| **F2** | 可选止血：极窄行为补丁（例如仅禁止「复制手估 0 时因落后换到含羞苞」） | **默认不单独开刀**；仅当 F1/F3 前必须止血且 Owner 勾选才做 |
| **F3** | 共享接口被 retreat / promote / attack（击杀分支）共用；删掉分叉口径 | **做** |
| **F4** | 局势策略（落后抢奖节奏等，旧 081 概念） | **可选后续**；默认本刀不做；合入前必须证明消费的是 F1/F3 干净估值 |

推荐实现顺序：F1 → F3；（跳过 F2）；（F4 另开 task 或本刀拍板后附录）。

## 4. 决策草案

实现以第 5 节拍板后的值为准。「本文建议」在拍板前不是授权。

### D-083-1 范围 = 共享击杀/拿奖前瞻收口

含 copy 可见性（原 082）。**不含**默认实现 081 的 `prize_pressure_gate` 行为。不把 081 的 100 局 A80 当作成功基线。

### D-083-2 编号与 081/082 关系

| 号 | 关系 |
|---|---|
| **081** | 规格与实现 PR #10 **搁置 / 不合并**。原因：方向无效 + copy 估 0 导致索ex→含羞苞自残。窄门补丁停。 |
| **082** | 规格文档保留作历史；**实质工作并入 083 的 WP-copy（F1）**。不再独立开 TDD/独立有效带。 |
| **083** | 当前焦点。对外中文名「共享击杀/拿奖前瞻」。 |

### D-083-3 零卡名

允许：HP、印面伤害/费用、剩余奖赏、`owner`、DSL `copy_attack` + `filters`（`matches_in_play`）。**卡名例外清单：空。** 不写索罗亚克 / 含羞苞 / 沙奈朵 等 `if name ==`。

### D-083-4 冻结

- `pokemon_score` / `factor_prize_diff`（公式、权重、`tests/test_features.py` 期望）
- 不改 `end_turn` / `play_stadium` 排序
- 不重开血月 `modify_attack_cost` / 不调用 `GameEngine._effective_attack_cost`
- 新开关（若有）**不进** `bfsim tune` 的 10 维；`bool_fields` 可登记，`len(search_space())` 仍为 10
- 不改 080 的 `_copy_donor_key` / `_pick_choose`（复制选人）
- 不改 `_decide_main` 大顺序（击杀仍在撤退/支援者前）

### D-083-5 开关（建议，待拍板）

| 方案 | 字段 | 默认 | 含义 |
|---|---|---|---|
| **A（建议）** | `ko_prize_lookahead_gate: bool = True` | True | 关：复制与共享出口回到今天印面口径；开：F1+F3 |
| B | 沿用 `copy_lethal_gate` | True | 仅命名沿 082；语义仍是共享接口总闸 |
| C | 无新开关，行为默认永久开 | — | 回滚靠 git；与 077–080 门风格不一致 |

**不**把 `prize_pressure_gate` 合进 main。若 F4 未来需要，另字段、另拍板。

### D-083-6 复制前瞻口径（F1，继承 082 并收紧到共享出口）

- 只处理战斗场上已付清印面费用、`on_attack` 含 `copy_attack` 且 `selector=own_bench_attack` 的招式
- 一层；不递归供体上的再一次 `copy_attack`
- 供体不必付费；费用仍印面 `_energy_satisfied`
- 有 `ko` 则取这些供体最大伤害且 `can_ko=True`；否则取最大伤害且 `can_ko=False`
- 不写进 `_attack_table`（默认）

### D-083-7 验收口径草案

**先单测，后局级。** 云端无 `ptcg-cn.db` 则局级留给 Diupi-Yun。

单测（建议文件 `tests/test_heuristic_ko_prize_lookahead.py`，可含原 082 场景）：

- [ ] 复制手 `damage=None`，供体印面足够击杀 → 共享接口 `can_ko=True` 且 `_lethal_attack` 选 `attack`
- [ ] 同一局面开关关 → 不可见，维持今天（支援者或非击杀路径）
- [ ] 供体费用未付清、复制手自己付清 → 仍可见击杀（不要求供体付费）
- [ ] 078 撤退：战斗场复制能击杀 → 不撤；仅备战印面能击杀 → 仍可撤上（回归）
- [ ] promote 路径：共享接口对 `_view_as_active` 一致（契约：同一 mon 无论从哪调用，伤害/击杀一致）
- [ ] `pokemon_score` / `factor_prize_diff` / tune 10 维不变
- [ ] 080 chooser 断言不改
- [ ] **不**断言 081 式「落后且两边都不能击杀则撤到更高伤」（本刀默认不做）

局级（Diupi-Yun，待拍板表）：

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t083-gard-zoro.db
bfsim report <id> --results results/t083-gard-zoro.db --decisions
```

- 种子 `208000..208099`，失败必须 0
- **建议对照 = 当前 main / 080 的 A78/B22**（081 不合并，不能对照 A80）
- 有效带建议：见 Q 表；写实不凑 30.4%，不跑 18000 作为完成条件
- 结构观察（非门槛）：暗夜王牌触及后是否仍系统性换含羞苞；B prizes 胜是否上升

短行：建议可选停手，不进有效带（同 081/082 旧议）。

### D-083-8 诚实预期

- 单测绿 = 估值/契约完成，**不等于**矩阵 \|Δ\| 闭环
- 局级若 A 仍 ≥78%：写实；可能还需 F4 或别的杠杆，但 **禁止**在脏估值上重开 081
- 一次到真实 30.4% / 加权 \|Δ\| 闭环：都不是完成条件

## 5. 拍板表（待 Owner 勾选）

实现以勾选后的值为准。下表「本文建议」标 **待拍板**。

| ID | 问题 | 选项 | 本文建议（待拍板） |
|---|---|---|---|
| **Q1** | 任务编号是否用 **083**，对外名「共享击杀/拿奖前瞻」？ | 083 / 沿用 082 并改名 | **083** |
| **Q2** | 是否废弃 081 合入（PR #10 不合并，行为不进 main）？ | 废弃合入 / 仍想合入 | **废弃合入** |
| **Q3** | 082 是否并入 083 为 WP-copy（F1），不再独立硬推？ | 并入 / 082 仍独立实现 | **并入** |
| **Q4** | 是否实现 **F2** 可选止血？ | 不做 / 与 F1 同 PR / 仅 F1 失败后再开 | **不做**（默认跳过） |
| **Q5** | 本刀是否实现 **F4**（旧 081 落后抢奖策略）？ | 不做 / 做（依赖 F1+F3） | **不做** |
| **Q6** | F 阶梯范围？ | 仅 F1 / F1+F3 / F1+F2+F3 / 含 F4 | **F1+F3** |
| **Q7** | 开关名？ | `ko_prize_lookahead_gate` / `copy_lethal_gate` / 无开关 | **`ko_prize_lookahead_gate`**，默认开，不进 tune |
| **Q8** | `pokemon_score` / `factor_prize_diff` 继续冻结？ | 是 / 否 | **是** |
| **Q9** | 重开血月减费？ | 否 / 是 | **否** |
| **Q10** | 卡名例外？ | 无 / 有清单 | **无** |
| **Q11** | 允许改 `end_turn` / `play_stadium`？ | 否 / 是 | **否** |
| **Q12** | 局级对照基线？ | main/080 的 A78 / 081 的 A80 / 其他 | **main/080 的 A78/B22**（同种子） |
| **Q13** | 局级有效带？ | A 降入 60–70% 算方向有效 / 只要求失败 0+结构改善 / 先单测后另定 | **先单测契约；局级建议「相对 A78 向 60–70% 移动或 B prizes 结构改善」算方向有效，到不了写实** |
| **Q14** | 短行是否本刀完成条件？ | 否（可选停手）/ 是 | **否** |
| **Q15** | promote 在 F3 是否「只要换上能击杀就优先于纯 pokemon_score」（不看落后）？ | 是 / 否（promote 本刀只统一接口、行为暂不变）/ 仅落后（=F4） | **本文建议：是（击杀优先，零落后门）**——与「不实现 081」一致，但是行为变化，**务必拍板** |

Q15 若选「行为暂不变」：F3 仍要求 retreat/attack 消费共享接口；`_pick_promote` 只接接口备着，排序仍纯 `pokemon_score`，红测不写 promote 击杀优先。

## 6. 明确不做

- 不合并 PR #10；不把 `prize_pressure_gate` 带进 main（除非未来 F4 另批）
- 不把 082 当独立窄门继续硬推有效带
- 不改 DSL / 引擎伤害与胜负
- 不引入 JEV / LLM；不用 MCTS/蒸馏代替本刀启发式估值
- 不跑 18000 作为本刀完成条件；不宣称到 30.4% / \|Δ\| 闭环
- 规划/规格 PR 不写实现。代理不合并。

## 7. 实现入口

拍板后按 `docs/superpowers/plans/2026-10-29-task-083-shared-ko-prize-lookahead.md` 执行。计划中的测试是红测契约草案，不是本 PR 已落地的测试。
