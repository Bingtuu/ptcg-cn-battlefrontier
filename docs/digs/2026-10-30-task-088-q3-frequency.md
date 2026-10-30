# task 088 Q3 频数门（只读）

> 2026-10-30 Diupi-Yun · `results\t086-gard-zoro.db` · `fc25648+dirty` · **不改** heuristic

## 定义


task 088 Q3 frequency gate (read-only) — strict first-touch window.

分母: dig 40 局触及负且首触未转化。

首触窗口: 事件 turn == 首触暗夜的 turn，且限制在该次攻击结算链内
  （从本回合 B 侧行动起点到首触 copy/damage 链结束；若 turn 字段与对手重叠，
   则硬裁到首触 attack 起至下一次任一方 attack / turn 递增之前的结算尾）。

机会 A: 窗口内 B 的 switch 类 opponent_bench choose（老大的指令/反击捕捉器），
  且对手备战存在 remaining HP ≤ 首触已付清复制对战斗场 final 伤害（>0）。
机会 B: 首触攻击结算链内的 opponent_bench / 攻击效果伤害 choose，
  且候选存在 remaining HP ≤ 该下伤害。

Would-change: 上述 choose 上 C 键最优 ≠ 实际 chosen。

Pass: 机会局 ≥15/40。


## 结果（门禁口径 = 首触窗口）

| 项 | 值 |
|---|---|
| 分母 | **40** |
| 机会局 opp A∨B | **1/40** |
| would-change | **1/40** |
| opp_A / opp_B | 1 / 1 |
| 窗口内有 switch choose 的局 | 9 |
| 首触链上有 bench-dmg choose 的局 | 1 |
| 阈值 | ≥15/40 |
| **判定** | **FAIL / 收口** |

首触 paid_dmg 分布：`{"0": 39, "180": 1}`


机会种子：208091


### would-change 例

- seed **208091** seq 416: switch 老大的指令 chosen=沙奈朵ex → C=愿增猿 dmg=180 cands=[('愿增猿', 110), ('愿增猿', 110), ('拉鲁拉丝', 70), ('奇鲁莉安', 90), ('奇鲁莉安', 90), ('沙奈朵ex', 310)]
- seed **208091** seq 432: bench_dmg N的索罗亚克ex chosen=沙奈朵ex → C=拉鲁拉丝 dmg=90 cands=[('愿增猿', 110), ('愿增猿', 110), ('拉鲁拉丝', 70), ('奇鲁莉安', 90), ('沙奈朵ex', 310), ('奇鲁莉安', 90)]

## 诊断（非门禁）：首触之后整局

- 机会局 7/40：[208013, 208025, 208046, 208048, 208060, 208073, 208091]

- would-change 7/40：[208013, 208025, 208046, 208048, 208060, 208073, 208091]


说明：首触 39/40 paid_dmg=0（自拷/空供体），故首触窗口内机制 C 几乎无杠杆；
即使放宽到触后整局，机会仍需单独评估，**不能**替代 D-088-6 的首触门。


## 未做

改 heuristic、写测试、开 TDD、跑 100 局。
