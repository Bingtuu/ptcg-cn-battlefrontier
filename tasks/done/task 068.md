# task 068 · 卡池 v2 锁定（代表卡组 + 合法性 + 缺口定案 + 机制评估 + 校准口径实测）

- 状态：完成（2026-10-21；判据 1–7 全 ✅）
- 关联：三期 PRD §3.3 卡池 v2 独立线（D3-5，数据就绪 task 044）；v1 流程 = task 024；侦察数据 `.kimi-code/t068-pool-v2-scout.md` / `.json`

## 目标

锁定 `config/target-pool.v2.yml` 为当前赛制环境（standard-2026-09-16）的卡池事实源，并把后续 DSL 批次的工程量与引擎改动面定案。

## 设计决议

- **D-068-1 选池窗口（2026-10-21 用户拍板）**：只用 09-16 后窗口（46 场 CN master），与当前赛制快照严格对齐；全窗口数据仅作低样本置信参考，不改排名
- **D-068-2 池构成（2026-10-21 用户拍板）**：Top-9 全新排（覆盖率 ≈80.5%）——多龙巴鲁托 黑夜魔灵 / 玛俐的长毛巨魔 雪妖女 / 沙奈朵 / 猛雷鼓 厄诡椪 / N的索罗亚克 / 火伊布 猫头夜鹰 / 电电虫Box / 多龙巴鲁托 / 喷火龙 大比鸟；苍响（0.55%）/ 赛富豪（2.0%）/ 多龙喷（0.97%）掉出
- **D-068-3 代表卡组**：沿用 v1 规则（合法 full 卡组中窗口内最高名次，并列取日期近/出战多）；侦察已实测 9 套全部窗口内 rank 1 且 standard-2026-09-16 合法性过、零 fallback。deck_id 见池文件
- **D-068-4 v1 封存**：`config/target-pool.v1.yml` 与既有结果库全部不动；v2 独立文件，matrix 36 格同规模
- **D-068-5 学习线解耦**：v2 锁定后 M11/M12 复跑（D3-5）不在本任务，另立项拍板

## 边界

- 本任务零引擎/DSL 代码改动；机制评估只出「DSL 可承接 / 需引擎扩展 / 需 PRD 决议」分类与改动点清单，扩展实现进后续任务
- DSL 编写（34 张缺口）进 task 069+ 批次，不在本任务
- v2 matrix 跑批与校准进 task 07x，本任务只实测真实侧数据可得性

## 验收标准（终止判据先行）

1. `config/target-pool.v2.yml` 落盘：query 段字段与 v1 对齐（granularity / window / division / basis / min_n / n_tournaments / mapping_status / snapshot / name_group_rules_hash），9 套 decks 各带 archetype / en_archetype / wur / n / deck_id / note；en_archetype 对齐 db EN 段（无 EN 对应的标注缺失不猜）
2. 9 个 deck_id 经 `load_deck` 合法性校验全过（脚本实证输出落任务档）
3. DSL 缺口 34 张定案：再录分类核销（30thDC-039 老大的指令 = 同文本纯挂载零新写；30thC-101 高级球 / 30thDC-037 裁判 = 异文本严格拆分口径）、vanilla 8 张人工核销结论落档
4. 5 类机制处置定案（伊布ex 虹色因子 / 皮卡丘ex 顽强之心 / 璀璨结晶任意属性减费 / 力之沙漏回合末触发 / 盖诺赛克特 ACE 锁）：每类给 DSL 可承接性判定 + 若需引擎扩展则列改动点与测试面
5. v2 校准真实侧可得性实测：72 有向格中有 real 数据的格数落账（EN 侧对新 archetype 的覆盖预期不全，如实记录）
6. 全量 pytest 绿 + ruff 零告警（零代码变更回归确认）
7. STATUS.md 落账 + 本档归档

## 结果与遗留

**判据 1/2 ✅**：`config/target-pool.v2.yml` 落盘（窗口 2026-09-16..10-21 / 46 场 / snapshot standard-2026-09-16 / hash f2c86aa8f7e3 / 覆盖率 80.48%）；9 个 deck_id 经 `load_deck` 合法性全过（60 张 × 9，脚本实测）。

**判据 3 ✅（34 张缺口定案，逐类核销）**：再录 3 张复核属实——30thDC-039 老大的指令 = text_raw 逐字全等纯挂载（零新写，card_ids 追加即可）；30thC-101 高级球 / 30thDC-037 裁判 = 同效果异文本（措辞语序差异实测），按严格拆分口径各新写一份（裁判异文本 task 026 WP7 已预知「另文」）；vanilla 8 张 scout 人工核对（含波波先例对齐）。明细 `.kimi-code/t068-pool-v2-scout.md`。

**判据 4 ✅（机制处置定案，explore 评估 + 主会话规则文档复核）**：
- **DSL 可承接（零引擎改动）**：TERA ×5（规则盒原生 + 备战免伤 D-027-1 已就位）、逆转能量（provide_energy 条件分层框架 + chooser 加一个组合词）、火伊布ex 双招式、30th 再录 3 张
- **需引擎扩展（小）**：璀璨结晶任意属性减费（`modify_attack_cost` args 加 `types: all` + chooser `holder_is_tera`，core.py:1491/1520 落点）
- **需引擎扩展（中）**：伊布ex 虹色因子（进化合法性枚举加 DSL 声明分支 core.py:352，新原语 modify_evolution；`_do_evolve` 复用零改）；皮卡丘ex 顽强之心（伤害截顶三落点 + 新原语 prevent_ko，不碰 task 064 扫描结构）；力之沙漏（新事件词 own_turn_end + `_drain_event_triggers` 寻源扩 attached_tool + attach_energy target_pool=self）；盖诺赛克特 ACE 锁（lock_play 改 passive_static + category 扩 ace_spec + 四处手牌使出枚举守卫）
- **附带 DSL 原语小扩**（explore 发现）：discard own_attached_energy choose=3（皮卡丘ex 黄晶伏特）；计数词 opponent 全场附着能量版（叶伊布ex 绿叶风暴）；heal 自己备战全体形态（苔纹玛瑙）
- **待用户核销决议 2 条（进附录 A，随 task 069 实现核销）**：①力之沙漏时点口径——引擎落点 = 检查阶段内状态结算后（对本卡结果等价，与官方「先于宝可梦检查」有名义偏差；严格先于状态结算需两段式检查推进，改动明显更大，评估建议取前者）；②盖诺赛克特「使出」覆盖面——含能量附着+道具附着（官方 "play a card from hand" 广义）vs 收窄训练家三类

**判据 5 ✅（超预期）**：v2 校准真实侧 **72/72 有向格全有 real 数据、低置信格 0**（v1 为 8 格 ⚠低置信）——3 个新 archetype 在 EN 校准窗均大样本（Joltik Box n=2095 / Flareon Noctowl n=1549 / N's Zoroark n=998）。

**判据 6 ✅**：全量 pytest 1404 绿（12m48s）+ ruff 零告警（零代码变更；侦察脚本 2 处 lint 顺手修）。
**判据 7 ✅**：STATUS/README/AGENTS 对账随归档同步。

**遗留**：34 张 DSL 编写 + 4 处引擎扩展 + 2 条附录 A 决议核销 → task 069（引擎扩展先行，DSL 批次随后，LLM harness 三道闸惯例）；v2 matrix + 校准 → task 07x（真实侧 72 格全覆盖，口径比 v1 更硬）；v2 锁定后学习线复跑（D3-5）另立项。
