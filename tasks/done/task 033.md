# task 033 · M9 引擎收尾（D2-5 四项）

- 状态：完成（2026-10-13）
- 关联：二期 PRD §3.3 / 里程碑 M9；M6/M8b 失败局形态（`results/m6-calibration.db` / `results/m8b-recalibration2.db`）

## 目标

清掉一期遗留的四个尾巴（二期 PRD D2-5 固定清单）：

- WP1 = damage opponent_active 空战斗场 no-op 化（M6 12 局 / M8b 18 局失败同一形态）
- WP2 = 附录 A 三候选规则核对（顶尖捕捉器双侧备战门 / 学习器自弃接 suppress_tool / aura 去重键粒度）——维持或归正
- WP3 = 夜光能量异文本类 7 印刷：先查池内是否有卡组实际使用，无则 YAGNI 关闭
- WP4 = 密勒顿回池评估（db 数据新鲜度 + 建议，纯分析）

## WP1 设计（D-033-1）

**触发场景实证**（seed 100052，沙奈朵×喷火龙大比鸟，spy 复现）：古玉鱼 嫉妒业火 on_attack——首 damage 节点昏厥对手战斗场（promote_queue 排队、换上推迟到效果完成，D-WP2-1）→ 同效果后续 damage opponent_active 节点读空战斗场 → DslError（primitives.py:1089）。

**口径**：真实规则下追加伤害作用于已被昏厥的原目标（不存在）→ 该节点空结算；换上在攻击完成后进行。与既有裁决一致：WP4 宣言裁决（落点空不阻却、无法执行部分 no-op，已核）+ D-029-4 备战空 no-op 同型先例。

**实现**：`damage opponent_active` 遇 `d.active is None` → 返回 no-op 结果字典（final=0, target=None, reason="no_targets"，键位对齐 bench no-op 既有形态），不抛错、不调 check_knockouts（无伤害）；事件流照常落 effect_primitive（可观测）。

**附录 A**：新增一条决议（🔲 待核）记录本口径。

## 验收标准（测试清单）

1. damage opponent_active 空战斗场 → no-op（不抛 DslError，result 带 reason=no_targets）
2. 双节点 fixture（首节点 9999 昏厥 → 次节点 no-op）效果完整执行、回合正常收尾、promote 走队列
3. 正常路径回归（对非空战斗场伤害不变——既有测试覆盖）
4. 全量 pytest 绿 + ruff 零告警 + dsl-check 全库 OK
5. 影响面复跑：matrix 重跑（results/m9-recalibration.db）确认 0 失败局 + 确定性 500/500 抽查；胜率口径变动如实记录（原失败局现正常完局进分母）

WP2–WP4 验收：
6. 两候选各有规则出处结论（rules-manual / 官网 Q&A / EN 规则书交叉），附录 A 条目更新（维持现状=关闭归正口，或归正实现另立 WP）
7. 夜光能量 7 印刷：池内 9 套代表卡组 60 张清单逐一核对是否含这些 card_id（db 只读查询），结论落账
8. 密勒顿：db 侧最新窗口 WUR / 合法 full 卡组可用性 / 最近出场日期，给出回池或不回池建议（卡池变更权属用户）

## 实现要点

- WP1 主会话直改（小改动 TDD）；WP2 走 ptcg-rules skill 查询流程；WP3/WP4 纯 db 只读分析
- 复跑用既有 `experiments/m6-calibration.example.yml`（同种子区间，可比）

## 结果与遗留

**WP1（D-033-1 ✅ 已核）**：`damage opponent_active` 空战斗场 no-op 化落地——`_damage` else 分支返回 `reason=no_targets` 结果字典，不再抛 DslError。新测试 `tests/test_damage_empty_active.py`（双段击 fixture：首节点 9999 昏厥 → 次节点 no-op，promote 走队列）。预期修复 M6 12 局 / M8b 18 局失败（同一形态：古玉鱼 嫉妒业火首节点昏厥后次节点读空战斗场）。

**WP2（D-033-2 ✅ 已核 / D-033-3 ✅）**：
- 顶尖捕捉器 → **维持现状**（D-033-3，关闭归正口）：CN text_raw「…互换。**然后**，将自己的战斗宝可梦与备战宝可梦互换。」为顺序「然后」非条件句（对照 EN 印刷 "If you do" 条件句属在地化差异，CN 与日文原版「その後」同构）；无「只有…才可使用」前置 → 对手备战空时整卡可用、第一节点 no-op、自换照算。
- 学习器自弃 → **归正**（D-033-2）：TPCi Rules Team 2024-07-25 裁决（Compendium「Technical Machine: Evolution / Jamming Tower」条目）——自弃文本 is an effect of the Tool → 阻碍之塔在场时回合末**不弃**。实现：`_discard_turn_end_tools` strip 增 `_tool_suppressed` 守卫（原「不在消除面内」近似作废）；测试 `test_suppress_tool_discard_at_turn_end`（塔在不弃 / 顶掉即恢复自弃）。PRD 与 D-029-2 条目同步修订。
- aura 去重键粒度 → **维持现状**（D-033-4，关闭归正口）：「拥有这个特性的宝可梦…不会重复」精确去重键 = 特性名，现状按来源卡名去重（D-WP7-3③）；当前池内此类 aura 仅 慷慨（单印刷单文本），同名异特性/异名同特性双向均不可达 → 近似成立，触发重议条件写入附录 A。

**WP3（YAGNI 关闭）**：db 夜光能量共 8 印刷；已覆盖 CSV1C-127（无「还」文本类）；7 个「还附着了」异文本类印刷（CBB3C-2003/2006、CSV8C-264、CSVE1C-176、CSVH1C-059、CSVM2bC-034、SVP-419）在池内 9 套代表卡组 60 张清单中**零使用**（池内仅 mik_moe:648346 / mik_moe:655776 各 4 张 CSV1C-127）→ 按 D2-5 措辞关闭，回归池时另文新写。

**WP4（建议：不回池）**：
- 合法性障碍已消除：09-05/09-06 窗口 7 套 full 卡组（最新 mik_moe:670501）；standard-2026-09-16 快照 allowed_marks=[G,H,I,J]，G 标仍合法，存量卡组不因轮转失效（banned_cards 空）。
- 但数据口径不支持：canon wur.sql（archetype 粒度，CN master，07-16~09-09 窗口）密勒顿 **WUR 0.27% / rank #32/82 / n=15**，远低于池内最低 赫普的苍响（0.70% / #23 / n=28）；池锁定原则 = WUR 排名驱动，不拍脑袋。
- 09-16 新环境赛事数据为零（db 数据止于 09-09），无法评估新环境表现 → 待数据积累后若重回 WUR 前列再评估（数据驱动，非一次性裁决）。

**影响面复跑**：`results/m9-recalibration.db`（36 配对 × 500 局，workers=16）——**失败局 18 → 1**（仅剩 沙奈朵×猛雷鼓厄诡椪 1 局 = M8b 已知 copy_attack 嵌套层级>1 形态，seed 100536，本任务范围外）；原失败局修复后正常完局进分母，相关格胜率小幅变动（如实记录不设阈值，D2-5 口径）。串并一致抽查：matrix 第 1 配对（沙奈朵×喷火龙大比鸟，种子 100000-100499）串行 500 局 vs 并行 events_hash **500/500 全等**（`results/m9-serial-check.db`）。dsl-check 全库 101 文件 OK；全量 964 绿 + ruff 零告警。

**遗留**：①M8b 已知 1 局 `copy_attack 嵌套层级>1` 失败（seed 100536）不在本任务范围，复跑预期仍存在；②MCTS 立项仍待用户拍板；③D-033-1 / D-033-2 附录 A ✅ 已核销 2026-10-13。
