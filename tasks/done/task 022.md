# task 022 · 决策事件 + 决策聚合报告（M4）

- 状态：完成
- 关联：PRD §5.4（可观测性：observe 锚点）/ §9（决策聚合报告）；task 021 胜率报告；task 019 结果库 game_events

## 目标

决策聚合的数据前提与报告本体：

1. **choose 决策事件**：`_do_choose` 恢复执行前发 `choose` 事件——effect_id / 来源卡 /
   池 / 选中 iids + 卡名（opponent_active_attack 池的 iid 是招式索引，解析为招式名）；
   嵌套帧（task 020）同样落事件（effect_id 含 `copy>` 标注）。
2. **observe 锚点入库**：cards/ 关键检索/回收卡补 `observe: [key_search]`（高级球/巢穴球/
   大地容器/厉害钓竿/夜间担架/秘密箱/派帕），注释引用 text_raw 原文；词表开放不校验。
3. **决策聚合报告**：`report/decisions.py`——按 (侧, 卡, 池) 分组，选择标签分布
   （选中卡名 "+" 连接 / 空选 = 「（放弃）」）× 各自最终胜率（对局级去重，
   分母 = 该选择出现过的决定局）+ Wilson CI；effect_observe 锚点经 effect_id
   关联到决策点（同局内）作为展示标签。
4. **CLI**：`bfsim report <id> --decisions` 追加决策聚合分节。

注意：choose 事件入流会改变 events_hash 基线——完工后重跑 M3 百局验收重记基线
（并行 vs 串行一致 + 0 失败）。

## 验收标准（测试清单）

文件：`battlefrontier/report/decisions.py`、`tests/test_decisions.py`、cards/ 七卡补锚点。

1. 检索挂起恢复后事件流含 `choose`：card/effect_id/pool/chosen iids/chosen_names 齐全。
2. 嵌套 copy 流程（task 020 场景）两个 choose 事件都在，内层 effect_id 含 `copy>`。
3. opponent_active_attack 池的 choose 事件 chosen_names 解析为招式名（非卡名）。
4. 合成结果库对账：已知 choose 事件分布 → 次数/覆盖局数/胜率/CI 逐项精确断言；
   同一局同一选择重复出现只对局级计一次；平局/失败局不进分母。
5. 锚点关联：同局 effect_observe 的 anchor 经 effect_id 挂到决策点展示。
6. cards/ 七卡 observe 锚点 load_card_dir 校验通过且锚点字段非空。
7. CLI：`bfsim report <id> --decisions` 输出含决策分节（卡名 + 分布行）。
8. render.py 补 choose 模板（人工 check 模式可读）。
9. `pytest -q` 全绿 + `ruff check .` 零告警；M3 百局复跑重记基线。

## 实现要点

- 卡名解析：扫描双方全区域建 iid→name 映射（deck/hand/discard/prizes/场上栈/附着物）；
  招式索引池单独解析对手战斗场 attacks。
- 聚合只统计完成局；决策归属按选择方 side（0=A 卡组）。
- 不改 PendingChoice schema；纯增量（事件 + 报告 + DSL 锚点）。

## 结果与遗留

**完成**（2026-08-29）：choose 决策事件入流（`_do_choose` + `_resolve_choose_names`）+
cards/ 七卡 observe 锚点 + `report/decisions.py` + `bfsim report --decisions` +
render.py choose 模板。TDD 14 新测试；全量 300 绿 + ruff 零告警。

口径：只统计完成局；games 为覆盖的不同决定局数（同局重复选择只计一局）；
锚点经同局 effect_id 关联；空选标签「（放弃）」。

**M3 基线已重记**（choose 入流改变 events_hash，预期变更）：100 局 0 失败、
并行 vs 串行逐局一致、胜负 65/35 不变；真实库决策聚合首跑验证可用。

遗留：换卡敏感性归 task 023（M4 收口）；决策聚合目前按（卡, 池）分组，
「首回合」等时序切片（turn 维度过滤）留待报告层按需扩展。
