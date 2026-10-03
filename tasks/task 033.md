# task 033 · M9 引擎收尾（D2-5 四项）

- 状态：进行中
- 关联：二期 PRD §3.3 / 里程碑 M9；M6/M8b 失败局形态（`results/m6-calibration.db` / `results/m8b-recalibration2.db`）

## 目标

清掉一期遗留的四个尾巴（二期 PRD D2-5 固定清单）：

- WP1 = damage opponent_active 空战斗场 no-op 化（M6 12 局 / M8b 18 局失败同一形态）
- WP2 = 附录 A 两候选规则核对（顶尖捕捉器双侧备战门 / 学习器自弃接 suppress_tool）——维持或归正
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

（完工填写）
