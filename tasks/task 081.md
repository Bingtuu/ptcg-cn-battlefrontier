# task 081 · 落后抢奖

- 状态：实现中 / 云端单测（100 局待本机；PR #10，不合并）
- 关联：规格 `docs/superpowers/specs/2026-10-29-task-081-prize-pressure-design.md`；计划 `docs/superpowers/plans/2026-10-29-task-081-prize-pressure.md`
- 依赖：080 已合入 main `1afa4e2`。100 局对照是当前 main / 080 的同种子 A78/B22。复制招式击杀前瞻是 task 082，不在本任务
- 拍板：Owner 已拍板 Q1–Q8，全部按规格「本文建议」。本变更只做计划 Task 1，不实现 082 / `copy_lethal_gate`

开关代码标识：`prize_pressure_gate`（默认开，不进 tune）。

## 目标

落后时抢奖。我方剩余奖赏多于对手时：谁都不能击杀，就撤退换上已付清、输出严格更高的备战；promote 优先已付清且能击杀拿奖的备战。未落后或开关关，行为与今天相同。

战斗场自己的招式能击杀时，`_lethal_attack` 已经会先打。本任务不改那条。不读 `factor_prize_diff`。不读 `copy_attack`。

## 验收标准（测试清单）

Owner 已拍板，按规格「本文建议」。Q7 = 包含 promote。

`tests/test_heuristic_prize_pressure.py`：

- [x] 我方奖赏剩 6、对手剩 2。战斗场 30 付得起，备战 120 付得起，对手 HP 200。都打不倒 → `retreat`
- [x] 双方都剩 6，同一局面 → `attack`
- [x] 我方剩 2、对手剩 6 → `attack`
- [x] `prize_pressure_gate=False` 且落后 → 不撤
- [x] 未落后，备战已付清且能击杀、战斗场不能 → 仍撤退（078）
- [x] promote：墙 HP 800 印面 10、0 能量；击杀手 HP 70 印面 90、1 能量；对手 HP 80。默认分墙更高。落后 → 换上击杀手
- [x] 同一 promote，双方奖赏都剩 6 → 仍是墙
- [x] 开关关且落后 → 仍是墙
- [x] `pokemon_score` / `factor_prize_diff` / `tests/test_features.py` 期望不改
- [x] 开关不进 tune 的 10 维

本机 100 局（**云端跳过**：无 `ptcg-cn.db`，不跑 `bfsim`。100 局待 Diupi-Yun 本机）：

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t081-gard-zoro.db
bfsim report <id> --results results/t081-gard-zoro.db --decisions
```

- [ ] 种子 `208000..208099`，失败必须是 0（云端未跑）
- [ ] 对照 080 的 A78/B22。A 胜率进入 60–70% 算方向有效；到不了写实（云端未跑）
- 这是 081 自己的带。不把 082 的局数并进来
- 不宣称到真实 30.4%，不宣称加权 |Δ| 闭环，不跑 18000
- 短行：Q4 已拍「100 局定有效带；短行建议跑，只作停手」。YAML 与局数不在本变更（计划 Task 3）。本机若跑：沙奈朵 / 多龙巴鲁托 / 玛俐各 50，猛雷鼓 / 电电虫各 20，`seed_start: 220000`。三格 N索胜率更差则停手。不进 60–70%。失败局必须是 0

## 实现要点

- 新字段 `prize_pressure_gate: bool = True`
- 落后 = `own.prizes_count > opponent.prizes_count`
- 卡名例外：无
- 不读 `modify_attack_cost`。不改 `end_turn` / `play_stadium`
- 不改 `_decide_main` 的大顺序

## 结果与遗留

- **红**：落后撤退实际是 `attack`；落后 promote 实际是 `bench_index=0`；开关关两条在字段不存在时 `TypeError`。未落后两条与 078 击杀撤退已绿。
- **绿**：`prize_pressure_gate: bool = True`。落后 = `own.prizes_count > opponent.prizes_count`。谁都不能击杀且落后时撤到已付清有效伤害严格更高的备战；落后 promote 优先已付清击杀。`board_quality_gate` 关仍直接走付不起才撤。不进 tune 的 10 维；`bool_fields` 含该字段。
- **单测**：`tests/test_heuristic_prize_pressure.py` `tests/test_heuristic_board_gate.py` `tests/test_heuristic_agent.py` `tests/test_features.py` `tests/test_tune_space.py` → **57 passed**。ruff 检查上述实现与测试文件，零告警。`test_features.py` 期望未改。
- **云端跳过 100 局**（无 `ptcg-cn.db`，不跑 `bfsim`，不跑 18000）。**100 局待本机**（Diupi-Yun）：`experiments/t078-gard-zoro.example.yml`，种子 `208000..208099`，对照 080 的 A78/B22，失败必须是 0。不实现 082。
