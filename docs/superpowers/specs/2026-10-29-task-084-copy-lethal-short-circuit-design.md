# task 084 · 复制击杀短路

- 日期：2026-10-29
- 状态：**规格待拍板**（本节 Q1–Q8）。Owner 已拍板方向：PR #12（task 083）的正确性子集合入；**复制击杀进 `_lethal_attack` 短路**的策略债另开本任务。拍板表答案仍待勾选。
- 本文不授权改 `heuristic.py`、不写测试、不跑 `bfsim`。拍板之后才按 `docs/superpowers/plans/2026-10-29-task-084-copy-lethal-short-circuit.md` 开 TDD。代理不合并。
- 前置：task 083 已合入 main `4262a9f`（PR #12，2026-10-29）。081 仍搁置（PR #10 不合并）。082 仍是 083 的 F1，不另开。
- 权威：一期 PRD D10（通用启发式，不为单卡组写死）。078 的 Q4 = 否（不读血月 `modify_attack_cost`）继续有效。083 的 Q1–Q15 继续有效，本刀不重开。

对外中文名：**复制击杀短路**。不要用「奖杯压力」「王牌转换」。不要把本刀写成「回滚 083」。

## 1. 背景与证据

本刀只处理策略债。正确性（共享出口、有效 HP、印面 HP 残留）已经在 PR #12 里，数字下面分开标注出处。消融与同格 500 是 Owner 本次任务书已核的数字；仓库里没有 `ABLATION_COPY_NOT_LETHAL`，本文不补造库路径，也不补造翻转局数。

### 1.1 083 已合入的正确性（维持）

| 项 | 事实 |
|---|---|
| 合并 | PR #12 → main `4262a9f`。提交说明：Owner 拍板 A，合正确性子集；copy→lethal 策略债另开任务 |
| 共享出口 | `_ko_prize_lookahead`：自己招式 / 一层 `own_bench_attack` / promote 后同一口径。撤退、promote、击杀短路都读它 |
| 有效 HP | `_ko_remaining` 与引擎 `_effective_hp` 同口径（道具 `modify_hp`，`holder_is_basic` 只认栈顶基础，`suppress_tool` 不加） |
| 印面残留 | 伤害关联弃牌与附伤目标改走 `_ko_remaining` / `_effective_max_hp`。`pokemon_score` 仍用卡面 HP 当权重 |

### 1.2 局级数字

种子 `208000..208099` 的 100 局与正式矩阵的 500 局不是同一窗口。100 局对照 t080；500 局对照正式矩阵该格。失败必须是 0 的那次 100 局，STATUS 已写。

| 跑法 | 数字 | 出处 |
|---|---|---|
| t080 baseline，100 局 | A78 / B22；B prizes **9** | task 080；种子 `208000..208099` |
| 083 有效 HP 重验，100 局 | A**72** / B28；B prizes **14**；相对 t080 胜负翻转 13/7 | `results/t083-effhp-gard-zoro.db`，代码 `af48017`；STATUS / task 083 |
| 消融 `ABLATION_COPY_NOT_LETHAL=1` | A**75** / B25；相对 t080 的胜负翻转收窄；B prizes 回到 **9** | Owner 已核。只把复制击杀排除出 `_lethal_attack`；F1 前瞻仍看见 copy。未进 main |
| 同格 500，相对正式矩阵 | sim **80.0%→77.6%**；相对 real **30.4%** 的 \|Δ\| **49.6→47.2**（−2.4pp） | Owner 已核。不够单独关掉该格残差 |
| 印面 HP 残留叠在有效 HP 上，同 100 种子 | 胜率与有效 HP 版相同 | Owner 已核。正确性修复，对本对局胜率杠杆低 |

正式矩阵（077–080，未因 083 重跑 18000）仍是：加权 \|Δ\| **19.0%**；沙奈朵 × N索 sim **80%** / real **30.4%** / Δ **+49.6%**（`results/v2-calibration-t080.db`）。

### 1.3 代码现状（main `4262a9f`，以符号为准）

`_decide_main` 在附能之后、道具 / 撤退 / 物品 / 支援者 / 竞技场之前调用 `_lethal_attack`。命中则本决策直接攻击。攻击结束回合，所以这条短路会跳过本回合后面的训练家与道具。

`_lethal_attack` 读 `_ko_prize_lookahead`。`can_ko` 且 `attack_index` 对上合法攻击，就返回该攻击。开关开时，一层复制的 `via=="copy"` 也会 `can_ko`。暗夜王牌印面无伤害，能斩杀时走的就是这条。

`_pick_retreat`：战斗场 `can_ko` 则不撤。`_pick_promote`：换上后 `can_ko` 优先于纯 `pokemon_score`（083 Q15）。这两处读的是前瞻本身，不是「要不要短路」。

`_pick_attack`（非斩杀）仍只读 `_attack_table`。复制不写进表。印面 `damage=None` 的复制招式在表里是 0。非斩杀排序里，任何更高的印面伤害都会压过它。

因此：

- 消融（复制永不进短路）之后，主阶段会先走道具、撤退、物品、支援者、竞技场，最后才到 `_pick_attack`。
- 纯复制、招式表里只有这一招时，训练家链走完后 `_pick_attack` 仍会选中它。N的索罗亚克ex 的卡面只有「暗夜王牌」（`cards/N的索罗亚克ex.yml`），属于这一类。
- 同一只身上若另有印面伤害更高、但斩杀不了的招式，`_pick_attack` 会选那一招，复制斩杀不会在短路被关掉之后补打。这是机制事实，不是消融局的逐局归因。本文不写卡名分支去特殊处理。

`ko_prize_lookahead_gate=False` 时复制对前瞻不可见，`via` 不会是 `copy`。那是 083 的总闸，本刀不改它的语义。

## 2. 本刀要回答的问题

只问一件事：**`via=="copy"` 且 `can_ko` 的招式，要不要、以及在什么条件下，占用 `_lethal_attack` 这条「先于训练家」的短路。**

前瞻里的 `can_ko` 保持为真。撤退仍不把能复制斩杀的战斗场撤下。promote 仍按 083 Q15。变的只是短路消费者。

三个选项（实现以第 5 节勾选为准）：

| 代号 | 行为 | 和证据的关系 |
|---|---|---|
| **A · 永不** | 复制击杀永远不进短路。等于把消融当默认 | 100 局 A72→**75**，B prizes 14→**9**，相对 t080 的翻转收窄。083 在这 100 局里的胜率移动和奖赏结构改善被还回去一截 |
| **B · 有准备训练家则推迟** | 合法行动里还有「准备训练家」时，复制击杀不短路；没有时仍短路。印面斩杀（`via=="print"`）始终短路 | **没有局级数字。** 不许用 A 的 A75 / B prizes 9 代替 |
| **C · 维持** | 与 main `4262a9f` 相同：复制击杀照进短路 | 100 局 A72 / B prizes 14。同格 500 只把 \|Δ\| 从 49.6 收到 47.2，残差仍在，换杠杆不在本刀 |

### 2.1 选项 B 的「准备训练家」（仅当 Q2=B 才生效）

本文建议，零卡名：

当前合法行动中存在 `play_trainer`，且 `trainer_subtype` 为「物品」或「支援者」，并且没有被现有的 `_deck_low` + `card_has_draw` 抑制。抑制规则与 `_decide_main` 里物品/支援者那两段相同。

不按卡名再分成有用 / 无用。再分会变成第二套窄门。

不计入这道门的：`attach_tool`、`play_stadium`、`retreat`。撤退已经由前瞻的 `can_ko` 决定不撤。竞技场维持 task 077 的证伪结论，不在本刀重开成主杠杆。

效果：有物品或支援者可打时，本决策不攻击，先打那张训练家；训练家打完、下一次决策不再有这类行动时，复制斩杀重新短路，于是仍先于道具和竞技场。这和 A 不同。A 在训练家用尽之后仍不短路，会继续走到 `_pick_attack`。

## 3. 决策草案

实现以第 5 节拍板后的值为准。「本文建议」在拍板前不是授权。

### D-084-1 范围

只改「复制击杀是否进入短路」。不改 `_ko_prize_lookahead` 的 `can_ko` / `best_damage` / `via` 语义，不改 `_one_layer_copy`，不改 `_ko_remaining`，不改弃牌定量与附伤目标，不改 `_attack_table`，不改 `_pick_attack` 的排序键。

### D-084-2 落点

行为放在 `_decide_main`：算出 `_lethal_attack` 之后、返回之前，看这次前瞻的 `via`。`via=="print"` 照旧返回。`via=="copy"` 按拍板的策略决定返回或继续往下排。

禁止把 `can_ko` 改成假来实现「不短路」。那样撤退和 promote 会一起看不见复制斩杀，消融没有这么做，本刀也不这么做。

环境变量 `ABLATION_COPY_NOT_LETHAL` 不进仓库。若要可消融，用下面的字段，不用未文档化的环境变量。

### D-084-3 字段（建议，待拍板）

| 方案 | 字段 | 何时用 |
|---|---|---|
| **本文建议** | `copy_lethal_policy: Literal["always", "unless_setup_trainer", "never"]` | Q2 不是 C 时添加。默认值 = Q2 的拍板。`"always"` = 083 合入行为，必须留回归 |
| 不加字段 | — | **Q2=C 时用这个。** 行为就是今天的 main，回滚靠 git |
| 单布尔 | 例如 `copy_lethal_short_circuit: bool` | 只能表达开/关，盖不住 B。不建议 |

不进 `bfsim tune` 的 10 维。`len(search_space())` 仍为 10。`bool_fields` 继续只列布尔；本字段若是字符串，断言它的名字不在 `search_space()` 里。

`ko_prize_lookahead_gate` 保持 083 的语义：关掉则复制对前瞻不可见。两个字段正交。总闸关时，策略字段看不到 `via=="copy"`。

### D-084-4 冻结

沿用 083，本刀不重开：

- `pokemon_score` / `factor_prize_diff`（公式、权重、`tests/test_features.py` 期望）
- `end_turn` / `play_stadium` 的排序
- 血月 `modify_attack_cost` / `GameEngine._effective_attack_cost`
- 080 的 `_copy_donor_key` / `_pick_choose`
- 卡名例外清单：空
- `prize_pressure_gate` 不进 main。081 的「落后且都不能击杀则换更高伤」不写

### D-084-5 验收口径草案

**先单测，后局级。** 云端无 `ptcg-cn.db` 则局级留给 Diupi-Yun。Q2=C 时没有行为差异，不重跑 100 局，task 文档写「维持 083，策略债记录在案」即收口。

单测（Q2=A 或 B 才写；文件沿用 `tests/test_heuristic_ko_prize_lookahead.py`）：

- [ ] `"always"`：现有 `test_copy_ko_attacks_before_supporter` 的局面仍是 `attack`。这条锚保留，不删
- [ ] `"never"`：同一局面（手牌有支援者、复制能斩杀）走 `play_trainer`。前瞻 `can_ko` 仍为真，`via` 仍为 `"copy"`
- [ ] `"never"`：印面招式能斩杀时仍先攻击（复制政策不误伤 `via=="print"`）
- [ ] `"unless_setup_trainer"`：有物品或支援者 → 先训练家；拿掉这些训练家、复制仍能斩杀 → `attack`
- [ ] `"unless_setup_trainer"`：只有被 `_deck_low` 抑制的抽牌训练家时，复制斩杀仍短路
- [ ] 撤退：战斗场复制能斩杀则仍不撤（三种政策都一样）
- [ ] `ko_prize_lookahead_gate=False`：仍看不见复制，与政策字段无关
- [ ] tune 仍 10 维；`pokemon_score` / `factor_prize_diff` 期望不改
- [ ] 无 `if name ==` 卡名分支

局级（仅 Q2=A 或 B；Diupi-Yun）：

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t084-gard-zoro.db
bfsim report <id> --results results/t084-gard-zoro.db --decisions
```

- 种子 `208000..208099`，失败必须 0
- 对照两列都写上：t080 的 A78/B22，以及 083 的 A72/B28（B prizes 14）
- 不预设「必须再低于 72」。A 的已有消融是 75，往 t080 回，不是往 60–70% 的中心走。B 没有基线，写实
- 记下 A/B 胜率、prizes / deck_out / no_pokemon、暗夜王牌触及、相对 t080 的翻转。失败 0
- 可选：同格 500 的 sim 与相对 real 30.4% 的 \|Δ\|，对照 80.0% / 49.6 与 083 后的 77.6% / 47.2。**不是完成条件**。不跑 18000。不新写矩阵实验定义，除非实现 PR 另批
- 不对照 081 的 A80。不宣称到 30.4%

### D-084-6 诚实预期

- 单测绿 = 短路政策与「前瞻 can_ko 不变」这两件事做完
- A 已经测过：这 100 局里它比维持现状更靠近 t080。把它当默认，是撤掉 083 的一部分结构改善
- B 未测。实现之后的 100 局可能高于或低于 72，都写实
- 同格 500 的 −2.4pp 说明 083 整包不够关掉矩阵残差。本刀即使改短路，也不把「关掉该格」写成完成条件
- 印面 HP 残留与有效 HP 胜率相同，不再当作本对局的策略杠杆

## 4. 与 081 / 082 / 083

| 号 | 关系 |
|---|---|
| 081 | 继续搁置。不重开落后窄门，不合入 PR #10 |
| 082 | 仍并在 083 的 F1。本刀不把复制从前瞻里拿掉 |
| 083 | PR #12 已合入。共享接口、有效 HP、印面 HP 残留维持。本刀只审短路 |

## 5. 拍板表（待 Owner 勾选）

实现以勾选后的值为准。

| ID | 问题 | 选项 | 本文建议（待拍板） |
|---|---|---|---|
| **Q1** | 编号与对外名？ | **084**「复制击杀短路」 / 写回 083 的补丁 | **084**。083 正确性已合，策略债单独编号 |
| **Q2** | 复制击杀进不进 `_lethal_attack` 短路？ | **A** 永不 / **B** 有准备训练家则推迟 / **C** 维持现状 | **C**。消融（=A）把 100 局从 A72、B prizes 14 拉回 A75、B prizes 9。同格 500 只动了 −2.4pp，不够关格，也不支持把短路关掉。若仍要改行为，选 **B**，不选 A |
| **Q3** | B 的「准备训练家」定义？ | 物品+支援者（deck-low 抽牌抑制沿用） / 再加竞技场 / 再加道具 / 四类都算 | **物品+支援者**。仅 Q2=B 时生效。四类都算会接近 A，而 A 的消融已经把奖赏胜还回去 |
| **Q4** | 字段？ | 枚举 `copy_lethal_policy` / 单布尔 / 不加 | **Q2=C 不加字段。** Q2=A 或 B 时用枚举，默认 = 拍板值，`"always"` 留回归。不进 tune |
| **Q5** | 冻结是否全维持？ | 是 / 否 | **是**：`pokemon_score`、`factor_prize_diff`、血月减费、卡名例外空、`end_turn` / `play_stadium` 排序、前瞻 `can_ko`、`_attack_table`、081 窄门 |
| **Q6** | 100 局怎么收？ | Q2=C 不重跑 / A 或 B 必跑同种子 100，写实、不预设低于 72 | **按左列**。对照 t080 A78 与 083 A72 两列都写。失败必须 0 |
| **Q7** | 同格 500 的 \|Δ\| 是否完成条件？ | 否（可选记录） / 是 | **否** |
| **Q8** | 回滚 083 的有效 HP / 印面 HP，或重开 081？ | 否 / 是 | **否** |

## 6. 明确不做

- 不回滚 PR #12：共享 `_ko_prize_lookahead`、`_ko_remaining`、弃牌定量、附伤目标
- 不把前瞻的 `can_ko` 改假来模拟消融
- 不重开 081 / `prize_pressure_gate` / PR #10
- 不把 `ABLATION_COPY_NOT_LETHAL` 写进产品代码
- 不改 DSL / 引擎昏厥与胜负
- 不引入 JEV / LLM；不用 MCTS / 蒸馏代替本刀
- 不跑 18000 作为完成条件；不宣称到 30.4% 或加权 \|Δ\| 闭环
- 不写卡名例外（索罗亚克 / 暗夜王牌 / 沙奈朵 / 含羞苞都不进 `if name ==`）
- 不改 `end_turn` / `play_stadium` 排序；不重开血月减费
- 规划 PR 不写实现。代理不合并

## 7. 实现入口

拍板后按 `docs/superpowers/plans/2026-10-29-task-084-copy-lethal-short-circuit.md` 执行。Q2=C 时该计划在落盘拍板后停止，不改 `heuristic.py`。
