# task 083 · 共享击杀/拿奖前瞻

- 状态：**规格已拍板；实现进行中**（Q1–Q15 整包按规格「本文建议」；代理不合并）
- 关联：规格 `docs/superpowers/specs/2026-10-29-task-083-shared-ko-prize-lookahead-design.md`；计划 `docs/superpowers/plans/2026-10-29-task-083-shared-ko-prize-lookahead.md`
- 依赖：080 已合入 main `1afa4e2`。**081 搁置**（PR #10 不合并）。**082 并入本任务 WP-copy（F1）**，不再独立硬推
- 对外中文名：共享击杀/拿奖前瞻（不要「奖杯压力」「王牌转换」）

开关代码标识（Q7 已拍板）：`ko_prize_lookahead_gate`（默认开，不进 tune）。

## 拍板（2026-10-29 Owner，整包按规格「本文建议」）

| ID | 拍板 |
|---|---|
| Q1 | 任务编号 **083**，对外名「共享击杀/拿奖前瞻」 |
| Q2 | 不合并 081，不合入 PR #10 |
| Q3 | 082 并入为 F1 / WP-copy，不再独立硬推 |
| Q4 | 不做 F2 |
| Q5 | 不做 F4，不实现 `prize_pressure_gate` |
| Q6 | 只做 F1+F3 |
| Q7 | 开关名 `ko_prize_lookahead_gate`，默认 True，不进 tune 10 维 |
| Q8 | 冻结 `pokemon_score` / `factor_prize_diff` |
| Q9 | 不重开血月减费 |
| Q10 | 无卡名例外 |
| Q11 | 不改 `end_turn` / `play_stadium` |
| Q12 | 局级对照 main/080 的 A78/B22，种子 `208000..208099`；不对照 081 的 A80 |
| Q13 | 先单测绿；局级相对 A78 向 60–70% 移动，或 B prizes 结构改善，算方向有效（云端无库跳过 `bfsim`） |
| Q14 | 短行不作完成条件 |
| Q15 | **是**：promote 存在换上后 `can_ko` 候选时优先于纯 `pokemon_score`（不看是否落后） |

## 目标

一个共享前瞻接口，回答「把某只宝可梦当成战斗场时，能否击杀拿奖 / 有效输出是多少」——覆盖自己招式、一层 `copy_attack`、promote 后。撤退、promote、攻击击杀分支消费同一接口。

修复证据链上的根因：`_max_paid_ko_damage` 不展开 copy → 暗夜王牌估 0 → 081 落后门系统性索ex→含羞苞。本刀默认 **不**实现 081 的 `prize_pressure_gate` 行为。

F 阶梯默认：**F1（copy 展开）+ F3（共享消费）**；F2 止血默认不做；F4 局势策略（旧 081）默认不做。

## 验收标准（测试清单）

已拍板。按规格「本文建议」列（Q15 = 是）。

单测 `tests/test_heuristic_ko_prize_lookahead.py`：

- [ ] copy 伤可见：印面 `damage=None` 的复制手，供体足够 → 击杀优先 `attack`
- [ ] 开关关 → 不可见
- [ ] 供体未付费、复制手已付清 → 仍可见
- [ ] 共享接口契约：同一 mon 经 active / `_view_as_active` 口径一致
- [ ] retreat 消费接口：复制能击杀则不撤
- [ ] promote：按 Q15（建议：能击杀优先于纯 `pokemon_score`；不看落后）
- [ ] 无 081「落后且都不能击杀则撤更高伤」断言
- [ ] `pokemon_score` / `factor_prize_diff` / tune 10 维 / 080 chooser 不改

局级（Diupi-Yun；建议对照 main/080 同种子 A78/B22）：

```bash
bfsim run experiments/t078-gard-zoro.example.yml --workers 8 --results results/t083-gard-zoro.db
bfsim report <id> --results results/t083-gard-zoro.db --decisions
```

- 种子 `208000..208099`，失败 0
- 有效带建议待拍板（规格 Q12–Q13）
- 不对照 081 的 A80；不宣称 30.4%；不跑 18000 作完成条件

## 实现要点

- 共享 `_ko_prize_lookahead`（Q7 已拍板此名）
- F1：一层 `own_bench_attack` copy 展开；不写 `_attack_table`
- F3：retreat / attack(/promote) 只读该接口
- 冻结：`pokemon_score` / `factor_prize_diff`；无卡名例外；不改 end_turn/stadium；不重开血月减费；不进 tune 10 维
- `prize_pressure_gate` **不进 main**

## 与 081 / 082

| 号 | 关系 |
|---|---|
| 081 | PR #10 不合并：方向无效（A78→80）+ 六格 ON/OFF 对 N索无益/有害 + copy 估 0 自残。窄门停。 |
| 082 | 规格留档；工作并入本任务 F1 / WP-copy |

## 结果与遗留

（实现进行中。单测绿后回写本节能做完的部分。局级 `bfsim` 按 Q13：云端无 `ptcg-cn.db`，本刀跳过，不对照 081 的 A80。）
