# task 084 · 复制击杀短路

- 状态：**规格待拍板**（文档 PR；本文件不授权改代码 / 不开 TDD / 不合并）
- 关联：规格 `docs/superpowers/specs/2026-10-29-task-084-copy-lethal-short-circuit-design.md`；计划 `docs/superpowers/plans/2026-10-29-task-084-copy-lethal-short-circuit.md`
- 依赖：083 已合入 main `4262a9f`（PR #12）。**081 搁置**（PR #10 不合并）。082 仍是 083 的 F1
- 对外中文名：复制击杀短路（不要「奖杯压力」「王牌转换」；也不要写成「回滚 083」）

政策字段（本文建议，待拍板）：Q2=C 时不加字段。Q2=A 或 B 时用 `copy_lethal_policy`（`"always"` / `"unless_setup_trainer"` / `"never"`），不进 tune。

## 目标

083 已经让一层复制击杀进入 `_ko_prize_lookahead`，并且 `_lethal_attack` 会在训练家之前打出它。Owner 拍板 A：正确性合入；**这条短路算不算策略债，另开本任务拍板。**

本任务只问：`via=="copy"` 且 `can_ko` 时，要不要占用这条短路。前瞻的 `can_ko` 保持为真。撤退、promote 继续读前瞻。

## 验收标准（测试清单）

待拍板。按规格「本文建议」：Q2=C 则不改代码、不重跑 100 局。

若 Q2=A 或 B，单测 `tests/test_heuristic_ko_prize_lookahead.py`：

- [ ] `"always"` 仍先于支援者攻击（现有 `test_copy_ko_attacks_before_supporter` 的锚保留）
- [ ] `"never"`：同一局面走支援者；前瞻 `can_ko` 仍真、`via` 仍 `"copy"`
- [ ] `"never"`：印面斩杀仍短路
- [ ] `"unless_setup_trainer"`：有物品/支援者则先训练家；没有则攻击
- [ ] deck-low 抽牌抑制沿用 `_decide_main`，被抑制的训练家不挡住复制斩杀
- [ ] 三种政策下，复制能斩杀的战斗场仍不撤
- [ ] `ko_prize_lookahead_gate=False` 的旧语义不变
- [ ] tune 10 维 / `pokemon_score` / `factor_prize_diff` 不改
- [ ] 无卡名例外

局级（仅 A 或 B；Diupi-Yun；对照 t080 与 083 两列）：

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t084-gard-zoro.db
bfsim report <id> --results results/t084-gard-zoro.db --decisions
```

- 种子 `208000..208099`，失败必须 0
- 不预设必须低于 A72。A 的消融已是 A75 / B prizes 9
- 可选同格 500 的 \|Δ\| 记录，不是完成条件
- 不对照 081 的 A80；不宣称 30.4%；不跑 18000

## 实现要点

- 落点：`_decide_main` 在 `_lethal_attack` 返回之后看 `via`。不改 `_one_layer_copy` 的 `can_ko`
- B 的准备训练家（建议）：物品或支援者，deck-low 的抽牌抑制与今天相同。道具和竞技场不算
- 冻结：有效 HP、印面 HP 残留、共享接口、081 窄门、血月减费、`end_turn` / `play_stadium` 排序
- 不把 `ABLATION_COPY_NOT_LETHAL` 写进仓库

## 与 083

| 项 | 083 合入后 | 本任务 |
|---|---|---|
| 前瞻看见复制斩杀 | 是 | 维持 |
| 复制斩杀先于训练家 | 是 | Q2 待拍板。建议维持 |
| 有效 HP / 弃牌 / 附伤 | 已修 | 不回滚 |

## 结果与遗留

（拍板并实现后回写。Q2=C 时只回写「维持」，不填新的 100 局。）
