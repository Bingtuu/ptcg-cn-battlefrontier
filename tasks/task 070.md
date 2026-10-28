# task 070 · 卡池 v2 DSL 批次（34 张缺口卡清零）

- 状态：进行中（2026-10-21 立项）
- 关联：task 068（卡池 v2 锁定 + 缺口定案）→ task 069（引擎扩展批，表达力备齐）→ 本任务（DSL 批次）→ task 07x（v2 matrix + 校准）
- 侦察事实源：`.kimi-code/t068-pool-v2-scout.md`（34 张明细 + 卡组归属）+ `.kimi-code/t068-scout-detail.json`（全量 125 卡 text_raw）
- 编写规范：`.kimi-code/skills/dsl-authoring/SKILL.md`（LLM 辅助编写管线 + 三道验收闸，PRD §5.5）

## 目标

卡池 v2（`config/target-pool.v2.yml`，9 卡组）的 34 张 DSL 缺口清零：33 张新写/再录拆分 + 1 张纯挂载；外加 068 定案的逆转能量 chooser 组合词小代码改动。完成后 v2 池 9 卡组装载零告警，可进 matrix。

## 设计决议

- **D-070-1 分组**：按机制批分 4 组派子代理（卡面文件互不重叠，并行安全）；`cards/老大的指令.yml` 纯挂载与逆转能量 chooser 组合词由主会话直接做（前者是唯一存量文件改动，后者是代码改动）
- **D-070-2 纪律**：沿用 task 026 起惯例——子代理 TDD + 主会话独立复验；每执行者独立测试分片 `tests/test_dsl_cards_b070_w<组>.py`（不共写 test_dsl_cards.py）；子代理不碰 `cards/authoring-log.jsonl`，报告里给 JSONL 行由主会话集中落账；缺词标 blocked 报主会话，禁止自造未注册词
- **D-070-3 印刷对齐**：按池内 card_id 取 text_raw；同名多文本严格拆分（高级球 30thC-101、裁判 30thDC-037 为同效果异文本再录，各新写一份）；card_ids 仅收同文本等价类 + 最新 standard 快照（standard-2026-09-16，J 标）合法印刷
- **D-070-4 规则不猜**：TERA 规则盒引擎原生（只写特性/招式）；力之沙漏时点 = D-069-1（检查阶段内状态结算后）；ACE 锁 = D-069-2 广义五门类；附录 A 3 条待核决议（虹色因子/顽强之心/D-WP5-4）所涉卡按已实现口径编写，决议核销不走本任务

## 工作包

- **WP0 主会话直做**：① 逆转能量 chooser 组合词（「自己奖赏比对手多 ∧ 持有者为进化宝可梦且无规则盒」；`own_prizes_more_than_opponent` chooser.py:516，组合词先例 `self_is_active_and_first_own_turn` chooser.py:543）+ 单测；② 老大的指令 30thDC-039 纯挂载（text_raw 与 CSVH1aC-023 逐字全等，card_id 追加进 `cards/老大的指令.yml`，零新写）
- **WP1a 训练家批 A（8 张）**：高级球 30thC-101（再录拆分）、宝可平板 30thC-102、莉莉艾的决心 30thDC-040、裁判 30thDC-037（再录拆分，对应既有 `cards/裁判-4张.yml` 口径）、席蓝 CSV9C-198、能量回收 CSVH1C-034、玻璃喇叭 CSV9C-178、太晶珠 CSV9C-181
- **WP1b 训练家批 B（8 张）**：粉碎之锤 30thDC-029、N的PP提升剂 CSV10C-190、N的城堡 CSV10C-215、驱劲能量 未来 CSV6C-119、招式学习器 能量涡轮 CSV4C-119、璀璨结晶 CSV8C-186（ACE SPEC 道具，modify_attack_cost types:all + holder_is_tera）、力之沙漏 CSV8C-188（own_turn_end + attach_energy target_pool=self，D-069-1 时点）、逆转能量 CSV2C-128（provide_energy 条件分层 + WP0 组合词）
- **WP2 TERA/进化批（6 张）**：伊布ex CSV9.5C-140（虹色因子 modify_evolution）、伊布 CSV9C-153（突进进化）、厄诡椪 水井面具ex CSV8C-067、叶伊布ex CSV9.5C-006（绿叶风暴 attached_energy_on_opponent_all + 苔纹玛瑙 heal own_bench）、火伊布ex CSV9.5C-023、皮卡丘ex CSV9C-054（顽强之心 prevent_ko + 黄晶伏特 discard choose=3）
- **WP3 其他宝可梦批（11 张）**：可达鸭 CSV10C-043（湿气）、咕咕 CSV7C-159、N的达摩狒狒 CSV10C-041、N的索罗亚克ex CSV10C-145（暗夜王牌 copy_attack 家族，参照 `cards/梦幻ex.yml`）、N的莱希拉姆 CSV10C-166、电电虫 CBB5C-1501、密勒顿ex CSV1C-050、铁臂膀ex CSV6C-051、铁斑叶ex CSV7C-033、电蜘蛛 CSV8C-010、盖诺赛克特 CSV9C-133（ACE消除器 lock_play ace_spec + holder_has_tool）

## 边界

- 不动引擎/DSL 框架（WP0 组合词除外）；不动 v1 池与既有结果；不改 runner/report 层
- 规则歧义报主会话裁决，不自行猜；附录 A 待核决议不随本任务核销

## 验收标准（终止判据先行）

1. 34 张全部过闸 1：`bfsim dsl-check cards/<卡>.yml --db <ptcg-cn.db>`（card_id 存在性 / text_raw 一致 / 赛制合法 / on_attack 招式名绑定）
2. 每张新写卡闸 2 单测过（测试函数名含中文卡名；特性/招式/抑制交互按 dsl-authoring skill 覆盖清单）；全量 pytest 绿 + ruff 零告警（主会话亲跑）
3. 闸 3 人工核销 = 用户确认（gate3=false 落账直到用户核销）
4. `cards/authoring-log.jsonl` 集中落账（一次通过率 / 人工修改量按 092 惯例记录）
5. v2 池 9 卡组装载零告警（load_deck + DSL 挂载校验全过）
6. STATUS.md 落账 + 本档归档

## 结果与遗留

**第一批收官（2026-10-27）：落地 15/34，blocked 19/34**（blocked 全部是引擎/DSL 表达力缺口，子代理按纪律未自造词、未降级乱写）。

- **WP0（主会话）**：逆转能量组合词 `own_prizes_more_and_holder_evolved_no_rule_box` 落 chooser.py（9 测，`tests/test_primitives_t070.py`）；老大的指令 30thDC-039 纯挂载（text_raw 与 CSVH1aC-023 逐字全等实证）
- **落地 14 张（4 组子代理，全部闸 1+闸 2 一次通过，零返工）**：高级球-才可以使用 / 裁判-手牌全部 / 能量回收（WP1a）；N的PP提升剂 / 璀璨结晶 / 力之沙漏 / 逆转能量（WP1b）；伊布ex / 叶伊布ex / 皮卡丘ex（WP2）；密勒顿ex / N的莱希拉姆 / 盖诺赛克特 / 电电虫（WP3）。测试分片 `tests/test_dsl_cards_b070_w{1a,1b,2,3}.py` 共 49 测（11+14+12+12）
- **主会话测试碰撞处置（火恐龙先例 + D-070-3）**：`tests/helpers.py` KNOWN_MULTI_TEXT_GROUPS 追加 高级球/裁判；`test_decisions.py::test_cards_observe_anchors` 与 `test_deckload.py::test_library_docs_semantics` 改为逐等价类断言（同名多文档兼容）
- **blocked 19 张 = task 071 引擎扩展第二批输入**（缺口精确到读点，明细见 authoring-log batch 10 notes）：过滤器 3（pokemon_no_rule / rule_box:ex / pokemon_tera）+ 节点条件 2（if_own_prizes_eq:N / 条件追加伤害）+ attach_energy 组合 2（multi_target×own_bench / own_deck target_pool=own_bench）+ 对手附着能量操作链（粉碎之锤）+ 竞技场撤退读点（N的城堡）+ holder_trait 条件（驱劲能量 未来）+ 训练家授予招式数据缺口（能量涡轮，db latent gap）+ 进化门放宽（伊布）+ 能量回库+节点门控（厄诡椪）+ lock_attack 全招式（火伊布ex）+ 宝可梦来源 suppression 定向（可达鸭）+ reveal opponent_hand（咕咕）+ 计数词/discard 全弃（N的达摩狒狒）+ ability 成本门 + copy_attack 备战维度（N的索罗亚克ex）+ prize_bonus 非太晶（铁臂膀ex）+ move_energy any_count→self（铁斑叶ex）+ modify_damage 目标 has_ability 过滤（电蜘蛛）
- **待用户核销**：闸 3 全部 15 张（gate3=false）；高级球/裁判再录区分词裁量点；电电虫洗牌 2 次 vs 原文 1 次偏差（🔲 待核）

**判据 1/2/4 ✅（落地部分）；判据 3 待用户核销；判据 5/6 待 071 补齐 blocked 后收口**。
