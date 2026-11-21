# task 082 · 复制招式击杀前瞻

> **并入 task 083（2026-10-29 Owner）**：不再当独立窄门硬推。实质工作 = **083 的 WP-copy（F1）**。对外中文名跟 083「共享击杀/拿奖前瞻」，不要单独推「复制招式击杀前瞻」有效带。081 已搁置（PR #10 不合并），本号原「等 081 合入再局级」前提作废。

- 状态：**并入 083 / 规格留档**（本文不授权改代码；实现跟 083 计划）
- 关联：规格 `docs/superpowers/specs/2026-10-29-task-082-copy-lethal-design.md`（历史）；收口规格 `docs/superpowers/specs/2026-10-29-task-083-shared-ko-prize-lookahead-design.md`；计划以 083 为准
- 依赖：080 已合入 main `1afa4e2`。081 搁置。局级对照改跟 083（建议 main/080 的 A78/B22）

开关代码标识：原建议 `copy_lethal_gate`；083 建议总闸 `ko_prize_lookahead_gate`（待拍板）。

## 目标

暗夜王牌印面没有伤害，攻击表当成 0。击杀判定和撤退看不见「复制备战招式之后能击杀拿奖」。本任务把一层 `own_bench_attack` 前瞻算进 `_lethal_attack` 和 `_max_paid_ko_damage`。不改 `_attack_table`，因此不改非击杀时选哪一招。不改 080 的复制选人。

## 验收标准（测试清单）

待拍板。下面按规格「本文建议」列。

`tests/test_heuristic_copy_lethal.py`：

- [ ] 复制手 `damage=None`，供体 `owner=N`、印面 200、0 能量。对手 HP 100。手牌只有支援者。默认 → `attack`
- [ ] 同一局面 `copy_lethal_gate=False` → `play_trainer`
- [ ] 供体费用为空、自己上场也能击杀 → 默认 `attack`，不是 078 的撤退
- [ ] N 供体只有 10 伤，非 N 供体 400 伤 → 仍 `play_trainer`
- [ ] Agent 没有文档 → 不猜，仍 `play_trainer`
- [ ] `tests/test_heuristic_attack_quality.py` 的 chooser 断言不改
- [ ] `pokemon_score` / `factor_prize_diff` 不改
- [ ] 开关不进 tune 的 10 维
- [ ] 仅当树上已有 `prize_pressure_gate`：复制前瞻 170、备战 120、对手 HP 300、落后 → 默认不撤；关掉 `copy_lethal_gate` 才撤到 120。本任务不新增 `prize_pressure_gate`

本机 100 局（云端跳过；**建议等 081 合入并回写 100 局之后再跑**）：

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t082-gard-zoro.db
bfsim report <id> --results results/t082-gard-zoro.db --decisions
```

- 种子 `208000..208099`，失败必须是 0
- 对照是 081 的同种子 100 局，不是 A78/B22
- 081 的 A 胜率仍高于 70%：再往 60–70% 走算方向有效
- 081 已在 60–70%：A 胜率不得推出这带
- 不与 081 合成「从 78% 一次量到 70%」
- 081 未合入则先不做这次局级验收
- 不宣称到 30.4%，不跑 18000
- 短行不作为 082 的有效带。081 若已跑短行，082 用同一 YAML 复跑，对照 081

## 实现要点

- 新字段 `copy_lethal_gate: bool = True`
- 供体过滤用 `matches_in_play`。未知 filter 不猜
- 供体不必自己付费。只看一层，只处理 `own_bench_attack`
- 费用继续印面。不读 `modify_attack_cost`
- 卡名例外：无
- 不改 `end_turn` / `play_stadium`，不改 080 的 chooser

## 结果与遗留
