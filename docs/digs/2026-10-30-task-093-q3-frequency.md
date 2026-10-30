# task 093 Q3 频数门（只读）

> 2026-10-30 Diupi-Yun · `C:\Vibe Project\Pokebattle\results\t092-gard-zoro-500.db` · db `af0b04d+dirty` · tip `82c6bbd798d1ac5c7443ef76709a1aae1ffe35df` · **同种子引擎重放** · **不改** heuristic

## 定义


task 093 Q3 frequency gate (read-only) — mechanism R.

分母: results/t092-gard-zoro-500.db 触及负（有 B 侧暗夜王牌事件且 winner==0）。
权威 236；重算 ≠236 则停。

机会 R（一局至多计 1）: 同种子引擎重放 B 侧（player 1 / N索侧），
在本局第一下 copy_attack 攻击事件之前，存在一次决策同时满足：
  1. 落后：own.prizes_count > opponent.prizes_count
  2. 今天 _decide_main 正返回 attack；can_ko 为假；该招 DSL 是一层
     copy_attack + selector=own_bench_attack；有效伤害为 0
     （via=="copy" 用 best_damage，否则用印面表）
  3. 存在合法 place_bench 基础：临时看成无能量/无伤害在场宝可梦，
     matches_in_play(filters) 且 max(_copied_strike) > 0
  → R 会改打 place_bench = would-change

Pass: ≥15/236。不改 heuristic.py。


## 结果（门禁口径 = B 侧落后 × 零伤一层 copy × 手里有合格供体基础）

| 项 | 值 |
|---|---|
| 分母（touch_loss = 权威） | **236** |
| 机会局 would-change | **49/236** |
| 门槛 | ≥15/236 |
| **判定** | **PASS** |

机会种子：208008, 208011, 208023, 208027, 208036, 208038, 208048, 208051, 208052, 208072, 208076, 208095, 208097, 208127, 208130, 208147, 208149, 208182, 208183, 208187, 208191, 208198, 208202, 208204, 208207, 208208, 208220, 208229, 208239, 208269, 208270, 208271, 208275, 208292, 208297, 208303, 208308, 208312, 208324, 208339, 208378, 208414, 208416, 208446, 208450, 208467, 208473, 208475, 208492


### would-change 例

- prizes B6/A4 via=copy dmg=0 place=N的火红不倒翁(iid=10005) strike=100
- prizes B6/A2 via=copy dmg=0 place=N的莱希拉姆(iid=10014) strike=340
- prizes B6/A3 via=copy dmg=0 place=N的莱希拉姆(iid=10015) strike=340
- prizes B6/A1 via=print dmg=0 place=N的莱希拉姆(iid=10015) strike=340
- prizes B6/A3 via=copy dmg=0 place=N的莱希拉姆(iid=10015) strike=340
- prizes B6/A3 via=copy dmg=0 place=N的莱希拉姆(iid=10014) strike=340
- prizes B6/A3 via=copy dmg=0 place=N的莱希拉姆(iid=10015) strike=340
- prizes B6/A3 via=copy dmg=0 place=N的莱希拉姆(iid=10015) strike=170
- prizes B6/A3 via=copy dmg=0 place=N的火红不倒翁(iid=10004) strike=100
- prizes B6/A4 via=copy dmg=0 place=N的莱希拉姆(iid=10015) strike=340
- prizes B6/A3 via=copy dmg=0 place=N的火红不倒翁(iid=10005) strike=100
- prizes B6/A4 via=copy dmg=0 place=N的莱希拉姆(iid=10014) strike=340
- prizes B6/A5 via=print dmg=0 place=N的火红不倒翁(iid=10005) strike=100
- prizes B6/A3 via=copy dmg=0 place=N的火红不倒翁(iid=10004) strike=100
- prizes B6/A2 via=print dmg=0 place=N的莱希拉姆(iid=10014) strike=340
- prizes B6/A2 via=copy dmg=0 place=N的莱希拉姆(iid=10015) strike=340
- prizes B6/A1 via=copy dmg=0 place=N的莱希拉姆(iid=10015) strike=340
- prizes B6/A3 via=copy dmg=0 place=N的火红不倒翁(iid=10005) strike=100
- prizes B6/A1 via=copy dmg=0 place=N的火红不倒翁(iid=10005) strike=100
- prizes B6/A3 via=copy dmg=0 place=N的索罗亚(iid=10007) strike=40

## 诊断（非门禁，不算进 15）

- 首触前曾有 copy 挥击决策的局：**236/236**

- 见到第一下 copy 事件的局：**236/236**

- 落后失败（copy 挥击时不落后）：**67/236**

- 挥击伤害 >0：**100/236**

- 手里没有 place_bench 基础：**13/236**

- 过滤不过：**7/236**

- `_copied_strike` 全 0：**0/236**


说明：门禁只计「落后 + 零伤一层 copy + 合格 place_bench」。R 实现后这些决策会改打 place_bench（would-change）。诊断各格可重叠，不自动改成 T/U。


## 方法

同种子 `play_game` 重放（实验 `t092-gard-zoro-500.yml`，启发式默认参数）。ProbeHeuristic 只读探测 B 侧（player 1），决策不变。耗时 20.4s。


## 未做

改 heuristic、写测试、开 TDD、跑 100 局、宣称 30.4%。T/U 未另计（Q2 锁定只 R）。
