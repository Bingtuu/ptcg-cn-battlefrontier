# task 091 Q3 频数门（只读）

> 2026-10-30 Diupi-Yun · `C:\Vibe Project\Pokebattle\results\t086-gard-zoro.db` · db `fc25648+dirty` · **同种子引擎重放** · **不改** heuristic

## 定义


task 091 Q3 frequency gate (read-only) — mechanism L.

分母: dig 触及负 52 局（touch_loss_seeds）。权威 52。≠52 则停。

机会 L（一局至多计 1）: 同种子引擎重放 A 侧（player 0 / 沙奈朵侧），
存在一次决策同时满足：
  1. 己方奖杯剩余 < 对手奖杯剩余（领先）
  2. 合法 attack 中 `_lethal_attack` 为无（本步无斩杀可取）
  3. 代理实际打出 `use_ability`，且该特性经 `_is_cycle_discard_draw` 判定为交易类循环
  → L 会节流 = would-change

Pass: ≥15/52。不改 heuristic.py。


## 结果（门禁口径 = A 侧领先 × 无斩杀 × 发出循环特性）

| 项 | 值 |
|---|---|
| 分母（touch_loss = 权威） | **52** |
| 机会局 would-change | **0/52** |
| 有 use_ability 的局 | 48 |
| 有循环特性发出的局 | 0 |
| 曾处于领先决策的局 | 51 |
| 曾领先且无斩杀决策的局 | 50 |
| 门槛 | ≥15/52 |
| **判定** | **FAIL / 收口** |

机会种子：（无）


### would-change 例


## 诊断（非门禁，不算进 15）

- 领先且发出循环、但当时有斩杀可取（L 不节流，因有 lethal）：**0/52**


说明：门禁只计「领先 + 无斩杀 + 实际发出循环特性」。L 实现后这些决策会被节流（would-change）。


## 方法

同种子 `play_game` 重放（实验 `t078-gard-zoro.example.yml`，启发式默认参数，含 086 `prize_race_gate`）。ProbeHeuristic 只读探测 A 侧（player 0），决策不变。耗时 10.6s。



## 诊断补充（非门禁；测量标签，不进启发式）

在 8 局触及负重放抽样中，A 侧实际发出的特性名分布以 **愿增猿** / **沙奈朵ex** / **梦幻ex** 为主；
它们的 DSL **都不是** _is_cycle_discard_draw（交易类弃牌再抽）：

| 名 | 效果形状（flatten） | cycle? |
|---|---|---|
| 愿增猿 | move_damage_counters（己场指示物 → 对手） | False |
| 沙奈朵ex | attach_energy from discard + damage_counters | False |
| 梦幻ex | （同批非 cycle） | False |

因此门禁分子 **0**：不是「领先侧从不发特性」，而是 **L 锁定的识别器抓不到 A 侧发动机**。
按硬门：**不改定义、不放宽 15/52、不发明新启发式**；收口 091，下一刀文档 task 092（扩样本再定刀）。

## 未做

改 heuristic、写测试、开 TDD、跑 100 局、宣称 30.4%。M/N 诊断未另计（Q2 锁定只 L）。
