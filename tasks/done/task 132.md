# task 132 · 备赛 DSL 缺口补齐批（斗子 / 太乐巴戈斯ex / 古剑豹）

- 状态：完成
- 关联：备赛 P0 goal loop；`bfsim dsl-check` 三道闸 + task 131 strict 门槛
- 口径修订（2026-11-14，task 131 实测证据）：~~多龙梅西亚(CSV8C-157)~~ 移出本批——task 131 `_is_pure_vanilla` 判定其为纯白板（无特性 + 纯固定伤害招式），vanilla 结算语义无损，非真缺口；**古剑豹(CSV9C-053) 移入**——strict 门槛判为阻断卡（非纯白板，有特性/非固伤招式），真实冠军表在用。

## 目标

为 strict 门槛实测阻断的三张卡编写 DSL 定义，走 dsl-authoring skill 固定管线三道闸：

| 卡 | card_id | 阻断证据 |
|---|---|---|
| 斗子 | CSV10.6C-085 | 新弹 J 标支援者，双方冠军表各 2 张 |
| 太乐巴戈斯ex | CSV9C-175 | 真实冠军表 1 张（特性减伤影响存活结论） |
| 古剑豹 | CSV9C-053 | 真实冠军表 1 张（非纯白板，vanilla 有损） |

## 验收标准（测试清单）

1. 闸 1：三张卡 `bfsim dsl-check <file> --db <db>` 全过（schema / 词表 / args 白名单 / card_id 存在 / 文本等价类一致 / 赛制合法）；
2. 闸 2：每卡单卡单元测试（跟随 tests/test_cards_*.py 或现有单卡测试惯例），断言效果关键行为；
3. 闸 3：人工核销——交付 Owner 的核销清单 = 每卡 text_raw 原文 vs DSL 逐条对照 + 人工裁定记录（项目惯例：PRD §5.5 三道闸，人工修改量记录）；
4. 补录后 task 131 strict 门槛对 `experiments/t1114-*.yml` 全部实验通过（零阻断）；
5. 全量 pytest 绿 + ruff 零告警；DSL 定义库份数 134 → 137。

## 结果与遗留

（2026-11-14 收官，闸 3 人工核销待 Owner）

- **斗子（CSV10.6C-085）：闸 1+2 过**（闸 3 待核销）——`cards/斗子.yml` + `tests/test_dsl_cards_b132_douzi.py` 5 测；两段式 search_deck（进化宝可梦×1 + 能量×1，各 reveal + 必洗牌）；闸 2 实证 choose_groups 组间互斥「或」语义不适配「和…各1张」（小刚的发掘先例踩坑→重写，first_pass=false）。主会话独立复验：dsl-check rc=0 + 5/5 绿。
- **古剑豹（CSV9C-053）：闸 1+2 过**（闸 3 待核销，first_pass=true）——`cards/古剑豹.yml` 2 效果 + `tests/test_dsl_cards_b132_chienpao.py` 5 测；特性埋入雪中（own_play_from_hand_to_bench + discard_stadium）+ 冰柱环 120 + 能量回手。前置引擎扩展 `move_energy destination=hand`（TDD：11 新测，既有 34 测零变化证明；只加不改）+ `tests/test_primitives_t071.py`。**vocabularies/schema 零缺口**（destinations 词表本已含 hand）。
- **太乐巴戈斯ex（CSV9C-175）：blocked 转引擎扩展 backlog**——三效果句全需引擎扩展：①后攻首回合招式使用门（`_main_actions` 枚举点无挂点，古月鸟失败语义不可借）②`bench_count_own` 计数词缺失③下回合基础（非无）招式伤害免疫（protection 无时效/source filter，core.py:187 减伤插入点未实现）。成本-收益裁决：1-of 卡 vs 触核招式枚举 + 全新防御侧减伤管道，超本 goal 范围。7 印刷同文本等价类全 legal 待解锁。**验收 ④ 相应修订**：strict 门槛对 t1114 实验的剩余阻断 = 太乐巴戈斯ex×1（vanilla 会低估同盟打击 30× 伤害，strict 拒跑是正确行为）；其余全过。
- 移出本批（task 131 纯白板证据，vanilla 语义无损）：多龙梅西亚、玛俐的诈唬魔。
- authoring-log.jsonl 已集中落账三行（斗子 done / 古剑豹 done / 太乐巴戈斯ex blocked）。
- 遗留：①闸 3 人工核销清单（见下）待 Owner；②太乐巴戈斯ex 引擎扩展三项待立项；③DSL 定义库 134 → 136。
