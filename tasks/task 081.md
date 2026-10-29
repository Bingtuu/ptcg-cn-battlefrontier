# task 081 · 落后抢奖

> **搁置（2026-10-29 Owner）**：PR #10 **不合并**——同种子 100 局 A78→A80 方向无效；六格 ON/OFF 对 N索无益/有害；`_max_paid_ko_damage` 不展开 copy → 索ex→含羞苞自残。窄门补丁停。后续见 **task 083 · 共享击杀/拿奖前瞻**（`prize_pressure_gate` 若保留则仅为依赖共享前瞻之后的可选 F4，083 默认不实现本任务行为）。

- 状态：**搁置 / 不合并**（规格留档；实现 PR #10 仅作记录）
- 关联：规格 `docs/superpowers/specs/2026-10-29-task-081-prize-pressure-design.md`；计划 `docs/superpowers/plans/2026-10-29-task-081-prize-pressure.md`；收口 **task 083**
- 依赖：080 已合入 main `1afa4e2`。100 局对照是当前 main / 080 的同种子 A78/B22。复制招式击杀前瞻原 task 082，已并入 083

开关代码标识：`prize_pressure_gate`（**不进 main**）。

## 目标

落后时抢奖。我方剩余奖赏多于对手时：谁都不能击杀，就撤退换上已付清、输出严格更高的备战；promote 优先已付清且能击杀拿奖的备战。未落后或开关关，行为与今天相同。

战斗场自己的招式能击杀时，`_lethal_attack` 已经会先打。本任务不改那条。不读 `factor_prize_diff`。不读 `copy_attack`。

## 验收标准（测试清单）

待拍板。下面按规格「本文建议」列。Q7 若否决 promote，promote 三条删掉。

`tests/test_heuristic_prize_pressure.py`：

- [ ] 我方奖赏剩 6、对手剩 2。战斗场 30 付得起，备战 120 付得起，对手 HP 200。都打不倒 → `retreat`
- [ ] 双方都剩 6，同一局面 → `attack`
- [ ] 我方剩 2、对手剩 6 → `attack`
- [ ] `prize_pressure_gate=False` 且落后 → 不撤
- [ ] 未落后，备战已付清且能击杀、战斗场不能 → 仍撤退（078）
- [ ] promote：墙 HP 800 印面 10、0 能量；击杀手 HP 70 印面 90、1 能量；对手 HP 80。默认分墙更高。落后 → 换上击杀手
- [ ] 同一 promote，双方奖赏都剩 6 → 仍是墙
- [ ] 开关关且落后 → 仍是墙
- [ ] `pokemon_score` / `factor_prize_diff` / `tests/test_features.py` 期望不改
- [ ] 开关不进 tune 的 10 维

本机 100 局（云端无 `ptcg-cn.db` 则跳过）：

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t081-gard-zoro.db
bfsim report <id> --results results/t081-gard-zoro.db --decisions
```

- 种子 `208000..208099`，失败必须是 0
- 对照 080 的 A78/B22。A 胜率进入 60–70% 算方向有效；到不了写实
- 这是 081 自己的带。不把 082 的局数并进来
- 不宣称到真实 30.4%，不宣称加权 |Δ| 闭环，不跑 18000
- 短行仅当 Q4 拍板要跑：沙奈朵 / 多龙巴鲁托 / 玛俐各 50，猛雷鼓 / 电电虫各 20，`seed_start: 220000`。三格 N索胜率更差则停手。不进 60–70%

## 实现要点

- 新字段 `prize_pressure_gate: bool = True`
- 落后 = `own.prizes_count > opponent.prizes_count`
- 卡名例外：无
- 不读 `modify_attack_cost`。不改 `end_turn` / `play_stadium`
- 不改 `_decide_main` 的大顺序

## 结果与遗留
