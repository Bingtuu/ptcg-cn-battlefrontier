# task 090 Q3 频数门（只读）

> 2026-10-30 Diupi-Yun · `C:\Vibe Project\Pokebattle\results\t086-gard-zoro.db` · db `fc25648+dirty` · **同种子引擎重放** · **不改** heuristic

## 定义


task 090 Q3 frequency gate (read-only) — mechanism S.

分母: 088 的「触及负且首触未转化」——与 experiments/t088_q3_frequency.py 同口径
  从 touch_loss_seeds 重算；权威 40。≠40 则停。

机会 S（一局至多计 1）: 同种子引擎重放，存在一次决策同时满足：
  1. 本局第一下暗夜攻击事件之前
  2. 该次决策按今天 _decide_main 优先级会走到支援者档，且合法支援者含
     DSL {action: switch, selector: opponent_bench}
  3. 前瞻 via=="copy" 且 best_damage>0 且 can_ko 为假
  4. 按今天 pokemon_score（平手 iid 小）这张 switch 的目标剩余 HP ≤ best_damage
     （备战不计弱点/抗性）
  5. 代理实际没有打这张 switch（would-change）

Pass: ≥15/40。不改 heuristic.py。


## 结果（门禁口径 = 首触前支援者 × 机制 S）

| 项 | 值 |
|---|---|
| 分母（重算 = 权威） | **40** |
| 机会局 would-change | **0/40** |
| 首触前走到支援者的局 | 40 |
| 首触前合法含 switch 支援者的局 | 23 |
| 重放见到第一下暗夜的局 | 40 |
| 阈值 | ≥15/40 |
| **判定** | **FAIL / 收口** |

机会种子：（无）


### would-change 例


## 诊断（非门禁，不算进 15）

- 备战有人剩余 HP ≤ dmg，但 pokemon_score 赢家不是那只：**1/40** 种子 [208091]

- 第一下**之后**仍满足 2–5 的 would-change：**0/40** 种子 []


说明：门禁只计首触前；若诊断列远大于门禁列，实现窗口比「首触前」宽，TDD 前先改规格。


## 方法

同种子 `play_game` 重放（实验 `t078-gard-zoro.example.yml`，启发式默认参数，含 086 `prize_race_gate`）。ProbeHeuristic 只读探测，决策仍是今天的 `min(iid)` 支援者。耗时 9.3s。


## 未做

改 heuristic、写测试、开 TDD、跑 100 局、宣称 30.4%。H/Y 诊断未另计（Q2 锁定只 S）。
