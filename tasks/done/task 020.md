# task 020 · copy_attack 嵌套 chooser（挂起帧二级支持）

- 状态：完成
- 关联：PRD §5.2 chooser / rules-reference 附录 A；task 017 遗留「嵌套挂起=显式 DslError」；task 019 CLI 初测实际触发（梦幻ex 基因侵入复制吉雉鸡ex 残忍箭矢）

## 目标

支持 copy_attack 复制「自身含运行时选择的 DSL 招式」：外层效果挂起在 copy 节点
（选招式）→ 内层效果（被复制招式的效果块）可再挂起（如残忍箭矢选目标）→ 内层
完成后回到外层 copy 节点收尾（不重复执行内层）→ 按外层 completion 推进。
嵌套层级 >1（被复制招式自身再复制含选择的招式）维持显式 DslError（不猜）。

## 设计

`PendingChoice` 增加嵌套帧字段：

- `inner: tuple[str, str] | None`——内层效果定位（DSL 文档卡名 + 招式名）；None = 现状单层
- `outer_cursor: int` / `outer_choice: tuple[int, ...]`——外层 copy 节点游标与已消费的招式选择

`NeedChoice` 增加 `inner` / `inner_cursor` 传递字段；copy_attack 内层 run_effect 挂起时
标注并向上传播（外层 run_effect 覆盖 cursor 前已转存 inner_cursor）。

恢复路径（`_run_or_suspend` / `_do_choose`）：

1. pending.inner 非空 → 按 inner 定位内层效果续跑（我方视角，source 仍为外层来源卡）；
2. 内层再挂起 → 沿用 inner 帧再挂起（同层多次选择，如双选择节点）；
3. 内层完成 → 以 `inner_done` 标记恢复外层 copy 节点：copy_attack 只回结果
   （不重复执行内层、不重复发 copy_attack 事件），外层继续后续节点；
4. need.inner 在已有 inner 帧时出现 → DslError（嵌套层级 >1 不猜）。

## 验收标准（测试清单）

文件：`tests/test_copy_nested.py`（+ state/chooser/primitives/core 既有测试不回归）。

1. **真实卡回归**：梦幻ex 基因侵入复制吉雉鸡ex 残忍箭矢（真实 cards/ 文档）——
   攻击 → 选招式 → 选目标（opponent_pokemon_any）→ 目标受到 100 伤害 →
   回合推进给对手；事件流含 copy_attack 与内层 effect_start。
2. **内层同层多次挂起**：被复制招式含两个选择节点 → 两轮 choice 依序恢复，两笔伤害
   各自落在所选目标。
3. **外层后续节点续跑**：外层效果在 copy 节点后还有节点（如 draw）→ 内层完成后
   外层继续执行完毕（手牌 +1），completion="attack" 回合推进。
4. **白板复制路径不回归**：复制纯伤害招式仍即时结算（test_m2_closeout 既有测试保绿）。
5. **嵌套层级 >1 显式 DslError**：套娃构造（复制「复制含选择招式」的招式）→
   apply 抛 DslError，不猜不静默。
6. **确定性**：同一脚本化选择序列重放两次，事件流 hash 一致。
7. `pytest -q` 全绿 + `ruff check .` 零告警；修后重跑 M3 百局验收（失败数应仍为 0，
   且结果库口径不变）。

## 实现要点

- HeuristicAgent `_pick_choose` 的池映射补对手场上宝可梦（opponent_pokemon_any 类
  选择的评分可见性），保持确定性 tie-break。
- 不改动既有单层挂起语义；PendingChoice 新字段默认值兼容旧状态构造。

## 结果与遗留

**完成**（2026-08-29）：`PendingChoice`/`NeedChoice` 嵌套帧字段 + copy_attack 标注传播 +
`_run_or_suspend`/`_do_choose` 嵌套恢复路径 + HeuristicAgent 对手池映射。
TDD 7 新测试全红→绿；全量 273 绿 + ruff 零告警。

M3 百局复验：0 失败、并行 vs 串行逐局一致、copy_attack 在真实对局实际触发 10 次
正常结算（A胜 65/B胜 35——heuristic 决策口径微调后的新基线，属预期）。

遗留：嵌套层级 >1（套娃复制）维持显式 DslError，真实卡组池出现该类卡对时再评估；
M4 报告层（胜率/Wilson CI/决策聚合/换卡敏感性）为下一里程碑。
