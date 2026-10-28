# task 078 · 前场与撤退（进化线开局 + 能斩杀才换下低伤前场）

- 状态：实现已进 PR（单测绿）。owner 整包拍板 Q1–Q8 按规格建议生效。100 局本机验收未跑（云端无 `ptcg-cn.db`，跳过 `bfsim`）
- 关联：`docs/superpowers/specs/2026-10-28-task-078-attack-active-energy-design.md` D-078-1～5；计划 Task 1；D10；规划 PR #5 merge `6bbcdbf`；task 077（`09e6a4c`）之后的下一刀
- 依赖：无代码依赖。079 / 080 未做。局级解读依赖本刀先落地，单测不依赖

## 目标

让启发式少把「付得起但斩杀不了」的低伤宝可梦留在战斗场，并在开局把手牌里已经有进化卡的那条基础放上来。对应诊断假说：愿增猿的精神幻觉是主攻，是因为它留在战斗场；沙奈朵ex 只有奇迹之力，`_pick_attack` 在愿增猿身上选不到那一招。

`pokemon_score` 公式不动（`tests/test_features.py` 手算锁着）。`_pick_promote` 不改。不写卡名。

## 验收标准（测试清单）

`tests/test_heuristic_board_gate.py`（计划 Task 1 有完整草稿）：

- [x] 战斗场 60 伤已付清、对手剩余 HP 150；备战 190 已付清且撤退合法 → `observe` 返回 `retreat`
- [x] 战斗场 190 已能斩杀 → 返回 `attack`，不撤
- [x] `board_quality_gate=False` → 60 伤付得起时不撤
- [x] 开局手牌同时有高伤基础、以及低伤基础 + 从它进化的一阶 → `place_active` 选低伤基础
- [x] 手里没有进化关系 → 仍选 `pokemon_score` 更高的基础
- [x] `promote` 仍选 `pokemon_score` 更高的备战
- [x] `experiments/t078-gard-zoro.example.yml`：`games==100`，`seed_start==208000`，`mik_moe:678647` × `mik_moe:690359`，utf-8 可读
- [x] `tests/test_tune_space.py`：搜索维仍是 10，`board_quality_gate` 在「不进搜索」的布尔集合里
- [x] `tests/test_features.py` 期望值不改

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

- **拍板已生效**：owner 整包拍板 Q1–Q8，全部按规格建议。078 两件都做（斩杀撤退 + 开局进化线），共用 `board_quality_gate`（默认开）。`pokemon_score` 公式不动。无卡名例外。不加 `modify_weakness` 布阵分。079 不在本 PR（也不读血月减费）。规划 PR #5 已合并 `6bbcdbf`，随后授权本刀 TDD
- **实现**：`HeuristicParams.board_quality_gate = True`。`_pick_place` 走 `_place_key`（键长 4）；`_pick_retreat` 在开关开时，战斗场已付清招式斩杀不了、合法撤退目标已付清且能斩杀，则换到有效伤害最高者（平手 bench 下标小）。谁都不能斩杀，或开关关，走原来的 `_pick_retreat_powerless`。`_pick_promote`、特性门控、能量目标、`_decide_main` 大顺序未改
- **单测**：`tests/test_heuristic_board_gate.py` 红→绿（撤退两条先失败：返回 `attack` 而非 `retreat`；开局选 iid 10 而非 11）。`test_heuristic_agent.py` 导入会拉 `ptcgdb`，夹具 `setup_state` / `engine_with` 按原语义抄进新文件。`tests/test_features.py` 期望未改。`board_quality_gate` 在 `test_tune_space.py` 的 bool_fields 里，`len(search_space())==10`
- **印面分未打印**：云端无 `ptcg-cn.db`，没有愿增猿 / 拉鲁拉丝的 HP、印面伤害、撤退费，不算 `pokemon_score`。开局「愿增猿高于拉鲁拉丝」这个假说在本环境未验证；布阵条款仍按规格落地（手里有进化线则优先该基础）。撤退条款由红测独立成立
- **100 局跳过**：云端无 `ptcg-cn.db`，本代理不跑 `bfsim`。父代理在 Diupi-Yun 验收。入库 YAML 是默认开。关开关分母不要提交，临时把两边改成 `params: {board_quality_gate: false}` 再跑同一文件

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t078-gard-zoro.db
bfsim report <id> --results results/t078-gard-zoro.db --decisions
```

先记关开关的 `attack.detail.name` / `attack`、`attach_energy.detail.target`、`evolve`、`game_over.detail.reason`，再跑默认开。失败局必须是 0。胜率写实。本刀单独不要求进 60–75%

- 079、080 未做。矩阵 / 索罗亚克整行 / 500 局不在本任务。代理不合并
