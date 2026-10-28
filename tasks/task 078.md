# task 078 · 前场与撤退（进化线开局 + 能斩杀才换下低伤前场）

- 状态：规划（待 owner review；本文件不授权改 `heuristic.py`）
- 关联：`docs/superpowers/specs/2026-10-28-task-078-attack-active-energy-design.md` D-078-1～5、Q1–Q3；计划 Task 1；D10；task 077（`09e6a4c`）之后的下一刀
- 依赖：无代码依赖。079 / 080 的局级解读依赖本刀先落地，单测不依赖

## 目标

让启发式少把「付得起但斩杀不了」的低伤宝可梦留在战斗场，并在开局把手牌里已经有进化卡的那条基础放上来。对应诊断假说：愿增猿的精神幻觉是主攻，是因为它留在战斗场；沙奈朵ex 只有奇迹之力，`_pick_attack` 在愿增猿身上选不到那一招。

`pokemon_score` 公式不动（`tests/test_features.py` 手算锁着）。`_pick_promote` 不改。不写卡名。

## 验收标准（测试清单）

`tests/test_heuristic_board_gate.py`（计划 Task 1 有完整草稿）：

- [ ] 战斗场 60 伤已付清、对手剩余 HP 150；备战 190 已付清且撤退合法 → `observe` 返回 `retreat`
- [ ] 战斗场 190 已能斩杀 → 返回 `attack`，不撤
- [ ] `board_quality_gate=False` → 60 伤付得起时不撤
- [ ] 开局手牌同时有高伤基础、以及低伤基础 + 从它进化的一阶 → `place_active` 选低伤基础
- [ ] 手里没有进化关系 → 仍选 `pokemon_score` 更高的基础
- [ ] `promote` 仍选 `pokemon_score` 更高的备战
- [ ] `experiments/t078-gard-zoro.example.yml`：`games==100`，`seed_start==208000`，`mik_moe:678647` × `mik_moe:690359`，utf-8 可读
- [ ] `tests/test_tune_space.py`：搜索维仍是 10，`board_quality_gate` 在「不进搜索」的布尔集合里
- [ ] `tests/test_features.py` 期望值不改

本机（有 `ptcg-cn.db`；云端不做，做了要在结果节写明跳过）：

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t078-gard-zoro.db
bfsim report <id> --results results/t078-gard-zoro.db --decisions
```

先用两边 `board_quality_gate: false` 跑同一 YAML，记下 `attack.detail.name/attack`、`attach_energy.detail.target`、`evolve`、`game_over.detail.reason`。这是 077 代码上还没有的结构分母（诊断包里的 34% / 4% / 220/500 不要直接相减）。再跑默认开。

结构（相对这次关开关的重放）：

- 沙奈朵侧精神幻觉的攻击次数占比下降，奇迹之力上升（方向，不设卡名次数门槛）
- 失败局 0
- 胜率写实。本刀单独不要求进 60–75%（那是三刀叠完的口径，见规格 D-078-9）

## 实现要点

- 读规格 §2.1、§2.2 与 D-078-5。行号以 `09e6a4c` 为准
- `HeuristicParams.board_quality_gate = True`
- `_place_key` 与 `_pick_retreat` 的形状以计划 Task 1 Step 3 为准。键长固定 4
- 费用仍用印面 `_energy_satisfied`（D-WP8-5）
- 不改 `_decide_main` 的大顺序，不改特性门控，不改能量目标（那是 079）

开写前用本机库打印愿增猿与拉鲁拉丝的 HP / 印面伤害 / 撤退费，算一次 `pokemon_score`。若愿增猿并不高于拉鲁拉丝，在结果节写明，布阵条款对「开局愿增猿」这个假说不成立；撤退条款仍然独立成立与否看红测。

## 结果与遗留

- 未实现。owner 拍板 Q1–Q3 之后才 TDD
- Q3 若只批撤退：删掉「开局优先进化线」那条测试，不要留着红着
- 079、080 未做。矩阵 / 索罗亚克整行 / 500 局不在本任务
