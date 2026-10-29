# task 081 · 奖杯压力与王牌转换

- 状态：规格待拍板（文档 PR；本文件不授权改代码）
- 关联：规格 `docs/superpowers/specs/2026-10-29-task-081-prize-pressure-design.md`（D-081-1~8，Q1–Q9）；计划 `docs/superpowers/plans/2026-10-29-task-081-prize-pressure.md`
- 依赖：077–080 已合入 main `1afa4e2`。本机 100 局对照是 080 的同种子 A78/B22，不是矩阵的 80%

## 目标

两件分开的事，默认都做，各有一个开关：

1. **WP A 奖杯压力**（`prize_pressure_gate`）。行动梯子今天不读剩余奖赏。战斗场自己的招式能斩杀时，`_lethal_attack` 已经会先打，这刀不改那条。要补的是落后时的软压力：谁都不斩杀，就撤到已付清有效伤害严格更高的备战；promote 在落后时优先已付清且能斩杀当前对手的那只，未落后仍按 `pokemon_score`。落后 = 我方剩余奖赏多于对手。不调用 `factor_prize_diff`。
2. **WP B 王牌转换**（`copy_lethal_gate`）。暗夜王牌没有 damage 节点，攻击表回退成 0，斩杀和撤退都看不见「备战供体被复制后能斩杀」。080 已经改了复制时选谁。这刀只把一层 `own_bench_attack` 前瞻算进斩杀判定和「战斗场最高有效伤害」，不改 `_pick_choose`，不改 `_attack_table`。

开场和能量不再当主杠杆（行扫描胜负几乎持平）。血月减费维持 Q4 = 否。`end_turn` / `play_stadium` 不重开。

## 验收标准（测试清单）

拍板前清单按规格「本文建议」列。Q9 若否决 promote，下面 promote 三条删掉。Q1 若拆成 082，WP B 不在本任务。

`tests/test_heuristic_prize_pressure.py`（计划 Task 1）：

- [ ] 我方奖赏剩 6、对手剩 2。战斗场 30 付得起，备战 120 付得起，对手 HP 200。谁都不斩杀 → `retreat` 到备战
- [ ] 双方都剩 6，同一局面 → `attack`，不撤
- [ ] 我方剩 2、对手剩 6 → `attack`，不撤
- [ ] `prize_pressure_gate=False` 且落后 → 不撤
- [ ] 未落后，备战已付清且能斩杀、战斗场不能 → 仍撤退（078）
- [ ] promote：墙 HP 800 印面 10、0 能量；斩杀手 HP 70 印面 90、1 能量；对手 HP 80。默认分墙更高。落后 → `bench_index` 是斩杀手
- [ ] 同一 promote，双方奖赏都剩 6 → 仍是墙
- [ ] `prize_pressure_gate=False` 且落后 → 仍是墙
- [ ] `pokemon_score` / `tests/test_features.py` 期望不改
- [ ] `prize_pressure_gate` 不进 tune 的 10 维

`tests/test_heuristic_copy_lethal.py`（计划 Task 2）：

- [ ] 复制手 `damage=None`，供体 `owner=N`、印面 200、0 能量（自己付不起）。对手 HP 100。手牌只有支援者。默认 → `attack`，不是 `play_trainer`
- [ ] 同一局面 `copy_lethal_gate=False` → `play_trainer`
- [ ] 供体费用为空、自己上场也能斩杀 → 默认 `attack`，不是 078 的 `retreat`
- [ ] N 供体只有 10 伤，非 N 供体 400 伤。对手 HP 100 → 仍 `play_trainer`（过滤器生效）
- [ ] 引擎有文档、Agent `card_effects=None` → 不猜，仍 `play_trainer`
- [ ] 复制前瞻 170、备战已付清 120、对手 HP 300、落后：两开关开 → `attack`；只关 `copy_lethal_gate` → `retreat` 到 120 那只
- [ ] `tests/test_heuristic_attack_quality.py` 的 chooser 断言不改
- [ ] `copy_lethal_gate` 不进 tune 的 10 维

本机 100 局（云端无 `ptcg-cn.db` 则跳过）：

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t081-gard-zoro.db
bfsim report <id> --results results/t081-gard-zoro.db --decisions
```

- 种子 `208000..208099`，失败必须是 0
- 对照 080 的 A78/B22。A 胜率进入 60–70% 算方向有效；到不了写实
- 记下 A 的 prizes / deck_out / no_pokemon，以及至少一次暗夜王牌的局里 B 的胜场。不要用 500 局的 83/357 当这 100 局的分母
- 不宣称到真实 30.4%，不宣称加权 |Δ| 从 19.0% 闭环，不跑 18000
- 短行仅当 Q5 拍板要跑：沙奈朵 / 多龙巴鲁托 / 玛俐各 50，猛雷鼓 / 电电虫各 20，`seed_start: 220000`。三格 N索胜率更差则停手。不进 60–70% 那条

## 实现要点

- 新字段 `prize_pressure_gate: bool = True`、`copy_lethal_gate: bool = True`
- 卡名例外：无。夹具用 stub
- 费用继续印面（D-WP8-5）。不读 `modify_attack_cost`
- 复制前瞻用 `matches_in_play` 过滤供体，`_copied_strike` 算一击。未知 filter 不猜
- 前瞻不写入 `_attack_table`，所以非斩杀的 `_pick_attack` 仍看印面
- 不改 `_pick_energy_attach`、`_place_key`、`_decide_main` 的大顺序

## 结果与遗留
