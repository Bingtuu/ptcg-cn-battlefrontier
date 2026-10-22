# task 064 · 修复 promote 空场判平（check_knockouts wipe 检查不跨扫描）

- 状态：完成（2026-10-21）
- 关联：task 063 诊断坐实（`.kimi-code/m12-task063-report.md`；实例 m9 game 5306
  seed 105305 已精确重放，events_hash 全等）；用户 2026-10-21 拍板修复并指定验收形态
- 性质：引擎 bug 修复（TDD）；规则出处 rules-manual §8 胜利条件②

## 背景

`check_knockouts` 的 wipe 判定（战斗场昏厥且备战空 → no_pokemon 判负）只嵌在
「本次扫描内战斗场昏厥」分支（core.py:1889-1909）。同一效果链内战斗场与备战被
**不同扫描**分别清空时（战斗场伤害节点先 KO 战斗场、备战尚存入 promote_queue；
后续铺伤节点再清空备战），wipe 漏检 → 残留 promote_queue → 效果完成翻 promote
阶段 → 备战空 → legal_actions 空 → runner 防御性判平（force_draw）。

影响面：m9 247 局（1.4%）/ v2 90 局（0.5%），no_legal_actions 类别 100% 归因本 bug；
触发招式全为「战斗场伤害 + 备战铺伤」组合（幻影潜袭/刹那斩/暗影子弹）。

## 时序语义（rules-manual §8 + 附录 A 先例链钉死，2026-10-21 用户拍板方向）

**胜利条件②与①同时点 = 昏厥结算点（每次 check_knockouts 扫描）立即判，不等效果完成。**
依据：①条件①（拿完奖赏立即获胜）既有实现即在扫描中途立即判（`_knockout_one` →
`_game_over`）；②ko_self 的战斗场空 + 备战空判负（primitives.py:1911-1924）已是
效果中途立即判，docstring 自称「与 check_knockouts 同口径」；③附录 A 2026-08-30
「放回手牌后场上无宝可梦判负」决议同语义已核。换上（promote）仍按 D-WP2-1 推迟到
效果完成后——判负时点与换上时点本就分离，本修复只补判负漏检，不动换上时序。
决议落附录 A（🔲 待核）。

## 修复方案

`check_knockouts` 扫描结束补全场空检：本扫描有昏厥结算（ko_settled）且任一玩家
active=None 且备战空且未在 wiped 中 → 追加 wiped；之后走既有 wiped 处理
（双方 → 平局 §8 同时胜利口径；单方 → 对手胜）。ko_settled 门控把影响面钉在
「有昏厥发生的扫描」，行为变化面最小化。

## 验收标准（用户指定三组单测，不只修 5306 单路径）

1. **组 1 战斗场先昏 + 同链备战清空**：DSL 攻击链（damage opponent_active +
   place_damage_counters）复现 5306 形态 → game_over / winner=攻击方 /
   reason=no_pokemon，不再进 promote 死锁
2. **组 2 双方同时清空（跨扫描）**：own_active 自伤 + all_pokemon_both 链 →
   双方场上均无宝可梦 → 平局（is_draw，§8 同时胜利口径）
3. **组 3 效果中途判负时点**：wiping 链后接 draw 节点 → 判负立即发生、
   后续节点不执行（对拍 test_run_effect_breaks_on_game_over 形态）
4. 附录 A 决议登记（🔲 待核）+ STATUS 落账 + 归档
5. 全量 pytest 绿 + ruff 零告警；5306 间谍重放验证结局由判平变 p1 胜
   （受影响局 events_hash 变化属预期行为修正，如实记录）

## 结果与遗留

（2026-10-21 完成）

- **TDD**：`tests/test_knockout_wipe.py` 4 条（组 1 跨扫描 wipe 判负 / 组 2 跨扫描双方清空平局 /
  组 3 中途判负后续节点不执行 + 1 条回归不变式「战斗场昏厥备战尚存照旧换上」）——
  修复前 3 红 1 绿（含 stash 复核最终形态在红态），修复后全绿
- **实现**：`check_knockouts` 扫描结束补全场空检（core.py，ko_settled 门控 +
  docstring 同步）；行为变化面 = 仅「有昏厥结算且某方场上已无宝可梦」的扫描
- **5306 间谍重放验证**：check_knockouts #9 出 phase=game_over，winner=1（多龙方胜）、
  draw=False——判平修复为应有胜负；events_hash 与库存不一致 = 预期行为修正（受影响局
  m9 247 / v2 90，复校准数字将因此小幅移动，量级预期见 STATUS task 063 节）
- **过程偏差披露**：组 2 测试初版走 ability_manual 触发，撞 ability_feasible 门
  （place_damage_counters own_active/all_pokemon_both 不在特性可行性白名单，DslError
  不猜）——改走 on_attack 触发（攻击枚举只需 DSL 绑定，语义等价）；组 3 初版用
  手牌数断言 draw 未执行，忘了两次昏厥的拿奖赏进手牌——改为 effect_primitive 序列
  精确断言（测试侧两处笔误，实现零迁就）
- **落账**：附录 A 决议「跨扫描全场清空的判负时点」✅ 已核 2026-10-21（用户核销，
  docs/rules-reference.md）；
  观感债（knockout/game_over 事件先于触发原语的 effect_primitive 事件）单列不修
- **遗留**：①~~附录 A 新决议待用户核销~~ **已核销（2026-10-21）——064 文档闭环**；②m9/v2 历史库的 no_legal_actions 局为旧口径
  （修复前的判平），复校准时受影响格以新跑批为准；③全量复跑 matrix 非本任务范围
  （量级预期亚 pts 级，随下次复校准顺带验证）
