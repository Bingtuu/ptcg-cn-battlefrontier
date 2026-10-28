# task 080 · 同体招式的可见伤害，与复制目标

- 状态：规划（待 owner review；本文件不授权改代码）
- 关联：规格 D-078-7、假说 H/I/J；计划 Task 3
- 依赖：单测不依赖 078/079。本机 100 局在两刀都默认开启之后跑

## 目标

两件独立的事：

1. `opponent_discard_basic_energy_count` 对 Agent 可见（对手弃牌区公开），但 `dsl_estimate._visible_counter` 不认识它，复燃的 30× 会退回印面基值。补上之后，现有「伤害高者优先」在弃牌区能量够多时会选复燃，而不是印面 90 的焚身加农炮。不另写「不要自弃能量」的惩罚。
2. 暗夜王牌的两段选择今天按供体的 `pokemon_score`、以及招式下标最小来选。改为按被复制招式打到对手战斗场的有效伤害，斩杀优先。开关 `attack_quality_gate`。

暗夜王牌的局触及率主要不是这刀的活（假说 I：它经常是那张卡的唯一招式）。触及率看 078+079。本刀看「已经在复制时有没有选到能结算的那招」。

精神幻觉 vs 奇迹之力不在本刀：它们不在同一张招式表上。本刀加一条回归，确认 60 与 190 同时付得起时仍选 190，只有 60 时仍然攻击，不改 end_turn。

## 验收标准（测试清单）

`tests/test_heuristic_attack_quality.py`（计划 Task 3 有草稿）：

- [ ] 对手弃牌区 4 张基本能量，招式 `count: opponent_discard_basic_energy_count`、`per: 30` → `estimate_attack_damage` 为 120 且 `lethal_ok`
- [ ] 同一只还有印面 90 的第二招，两招都付得起 → `_pick_attack` 选 120 那招；弃牌区 0 张基本能量 → 选 90
- [ ] 复制第一段：两只 `owner=N`。A 的 HP 800、伤害 10（`pokemon_score` 更高，斩杀不了 HP 100 的对手）；B 的 HP 80、伤害 200。`attack` 进入 `own_bench` 选择后，默认开关的 `observe` 选 B 的 iid
- [ ] 同一局面 `attack_quality_gate=False` 选 A
- [ ] 第二段 `anchored_pokemon_attack`：下标 0 伤害 10、下标 1 伤害 200 → 默认选 1；开关关选 0
- [ ] 测试断言 `pending_choice.pool` 与供体 iid 所在字段（读代码时期望是 `payload`）。字段对不上就改启发式的读法，不改引擎
- [ ] 同一只 60 与 190 都付得起 → 选 190；只有 60 → 选攻击，不是 `end_turn`
- [ ] `tests/test_primitives_t071.py` 的复制测试保持手写 `apply(choose)`，断言不改
- [ ] 计数词补全不包在开关里：`attack_quality_gate=False` 时估算仍是 120
- [ ] 开关不进 tune 的 10 维

本机 100 局：

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t080-gard-zoro.db
bfsim report <id> --results results/t080-gard-zoro.db --decisions
```

对照 079 那次 100 局。记录 `game_over.reason`、沙奈朵胜率、精神幻觉 / 奇迹之力 / 暗夜王牌 / 复燃 / 血月的局数、失败数。失败必须是 0。

三刀叠完的诚实口径（规格 D-078-9）：胜率从约 90% 向 30% 移动，落到 60–75% 算这一轮有效。到不了也写实。不跑 500，不跑矩阵，不写 \|Δ\| 闭环。

云端无库则跳过。

## 实现要点

- `_visible_counter` 增加该词，读 `view.opponent.discard` 的 `is_basic_energy`
- `_pick_choose` 只在挂起效果的当前步骤是 `copy_attack` 时改排序。读不到 DSL 文档则回到今天的 `pokemon_score`，不猜
- 夹具抄 `tests/test_primitives_t071.py` 的 `test_wp10_copy_bench_attack_owner_filter`，卡名用 stub
- 不改 `copy_attack` 原语，不改帧栈

## 结果与遗留

- 未实现
- owner 闸门（本任务不做）：N索对其余对手的行、沙奈朵对其余对手的加权 \|Δ\|。要用新代码重跑矩阵，不能用 `c436471` 或这 100 局外推
- `play_stadium` / `end_turn` 仍是 backlog
