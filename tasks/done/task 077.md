# task 077 · 启发式特性使用质量门控

- 状态：完成（本机 100 局已验收；已合入 main `09e6a4c`，PR #4）
- 关联：B 诊断 `uploads/2026-10-28-gard-zoro-delta-diagnosis`（task 076 后正式矩阵 `c436471`，沙奈朵 × N的索罗亚克 Δ=+65.6%）；M12 残留盲区「特性使用质量」；D10 不按卡名定制

## 目标

替换 `HeuristicAgent._decide_main` 里「有 `use_ability` 就 `min(iid)`」为可解释的特性质量门控。第一刀只打两类效果形态：

1. **交易类弃抽**（弃少量手牌再抽牌）：牌库将尽、没有垫牌可弃（手牌差）、手牌已经够用时拒用，合理时仍可用。对着 N的索罗亚克「交易」无脑刷 → 自磨 `deck_out`。
2. **弃牌区附能并放置伤害指示物**（精神拥抱类）：场上有「放上指示物后仍活着、且这张能量推进未付清招式」的目标才用；多只可选时 chooser 优先还没付清费用的那只。

多特性同时合法时按价值排序，平分才取 iid 小。不写卡名分支。

## 诚实预期（第一刀，不宣称 |Δ| 闭环）

B 诊断已钉死（勿重猜）：

- 沙奈朵 × N的索罗亚克：sim 96%（480/500，种子 `208000..208499`）vs real 30.4%（103/339）；沙奈朵胜因 405/480 = `deck_out`
- 索罗亚克「交易」≈11.7/局；代码路径有 `use_ability` 必用
- 消融 B `use_abilities:false`（同种子 `208000..208099`，100 局）：`deck_out` 77→10/100，B WR 4%→13%
- `play_stadium` / 单纯 `end_turn` 证伪为主因；DSL / 装载 / 引擎崩溃不是主因（失败局 0）
- N的索罗亚克对全矩阵 sim 全面塌方（1.8–15.4%），该格是峰值

单修 ability，参照该消融，该格沙奈朵 WR 大概只能从 ~96% 降到 ~85–90%。吃掉剩余 50+pp 还要攻击选择 / 前场 / 能量分配，不在本任务。

## 决议

- **D-077-1 交易类**（效果形态，不看卡名）：`ability_manual` 扁平步骤含 `discard selector=own_hand choose=N`（N 为小整数；`count: all` 的整手刷新不算）且含 `draw`、不含 `damage`。价值 0（拒用，落到后续行动）当任一成立：
  1. 牌库将尽：`deck_count <= ability_cycle_deck_floor`（默认 **12**；每发抽 2 且每回合可重复，高于训练家用的 `deck_low_threshold=6`）
  2. 手牌差：手牌最低保留分 > `ability_cycle_discard_ceiling`（默认 **2.0**）。保留分 = 能量 1 / 训练家 3 / 宝可梦 `pokemon_score`。默认线下只有能量算垫牌——没有能量可弃就拒，避免把宝可梦或支援者送进弃牌区
  3. 手牌已够：`len(hand) > ability_cycle_hand_max`（默认 **4**）。同回合多只连刷时，手牌涨过线就停
- **D-077-2 附伤类**：`attach_energy selector=own_discard` 且 `args.damage_counters > 0`。目标须命中 `target_filters`（未知词视为不匹配，不猜）、放上指示物后不昏厥，且该能量属性对某条未付清招式是「刚好付清」或「有色/无色缺口上的推进」。没有这种目标则价值 0。chooser 在目标步优先「付清 > 推进 > 无帮助」，再回落到原评分。
- **D-077-3 排序**：未归入以上两类（或 agent 侧没有 DSL 文档）保持正价值，仍然会用——只是不再无条件压过更高价值的门控类。平分 tie-break = iid 升序（确定性不变）。全 ≤0 则本步不发特性。
- **D-077-4 消融**：`ability_quality_gate=false` 恢复 `min(iid)`，chooser 也不改方向。三个阈值进 `HeuristicParams`，实验 YAML 可覆盖。不进 tune 搜索空间（与既有布尔开关一样固定默认）。
- **无卡名特例**。阈值是第一刀默认。本机 100 局命中诚实带后**未改数字**，不把它们写成已拍板的最优。

## 验收标准（测试清单）

`tests/test_heuristic_ability_gate.py`：

- 牌库 ≤ 地板时拒交易类；没有垫牌（手牌差）时拒；手牌张数超过上限时拒
- 牌库高于地板、手牌未超上限、有能量垫牌时仍用
- 附伤类：招式费用已付清则不用；能量能推进未付清招式则用
- 附伤类目标选择优先还没付清的那只，而不是同分下的较小 iid
- 多特性：低 iid 的交易类让位于高 iid、价值更高的附伤类；`ability_quality_gate=false` 仍取最小 iid
- 整手刷新（`discard count: all` + draw）不按交易类拒
- 实验定义 `experiments/t077-gard-zoro.example.yml` 可装载：种子 208000、100 局、卡组 `mik_moe:678647` × `mik_moe:690359`

存量 `tests/test_heuristic_agent.py`、`tests/test_agent_dsl_estimate.py`、`tests/test_tune_space.py` 不回归。

本机（有 `ptcg-cn.db`）结构验收见该实验文件头与 PR 说明。云端不跑正式矩阵。

## 实现要点

- `HeuristicAgent._pick_ability` + `HeuristicParams` 四个新字段
- 附伤类目标步在 `_pick_choose` 里按能量缺口重排（仍受门控开关控制）
- 不改 DSL、引擎规则、`copy_attack` / `grant_attack`、`pokemon_score`、攻击估值、能量分配

## 结果与遗留

- 单测：`tests/test_heuristic_ability_gate.py` 本机 **13/13**（YAML `read_text(encoding="utf-8")`，`191f3c1`）。代码路径不再是无条件 `min(iid)`
- **本机已验收**（Diupi-Yun，`experiments/t077-gard-zoro.example.yml`，种子 `208000..208099`，100 局，失败 0；能力门控 `e34ca9c`）。对照 baseline（同种子：A 96% / B 4% / 沙奈朵胜因 deck_out 77 / 交易 11.7/局）：
  - A 沙奈朵 WR **96%→90%**（90/100；先攻 87.3% / 后攻 93.3%）；均回合 13.3
  - B N索 WR **4%→10%**
  - 沙奈朵胜因 deck_out **77→27**/100（结构显著改善，仍非 prizes/ko 主导）
  - N的索罗亚克ex use_ability **11.7→1.35**/局
- 诚实预期带 85–90% **命中（90%）**。|Δ| 不在本任务闭环；剩余偏差要攻击/前场/能量
- 索罗亚克对其余对手的行均值另开 follow-up，不在这 100 局里宣称
- follow-up：攻击/前场/能量见 task 078–080（规划，待 owner review 后才 TDD）。`play_stadium` / `end_turn` 仍 backlog；纯抽牌特性（嘉奖硬币 / 再起动 / 化危为吉）本刀不另做牌库地板。阈值维持第一刀默认，未改数字
