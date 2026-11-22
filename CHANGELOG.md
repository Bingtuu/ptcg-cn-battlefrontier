# CHANGELOG

> 四段式：Added / Changed / Deprecated / Removed（AGENTS.md 规矩）。
> 粒度 = 里程碑/任务级，逐日流水见 `STATUS.md` 与 `docs/status-archive.md`。

## Unreleased（2026-11）

### Added

- 探针回填签名 + 备赛证据包 + CLI 端到端小样例（task 158，Grok 外部评审③④采纳 + ⑤降档模板）：**探针签名双判**——field-snap 导出 meta 落 `sig={window, n_qualified, data_version}`（`qualified_count` 与探针共享同一 SQL——cn/master 口径 where 族，DISTINCT tournament_id），探针 stale 分因 `newer`（MAX 超窗）∥ `backfill`（同窗补入合格赛事/数据版本变更，MAX 不动也判出；同窗仅新增 junior/团队/qual 被筛除赛事不误报）；无 sig 旧快照降级纯日期比对并注明；**备赛证据包**——`run_prep` 改表判读落 `results/prep-<name>/inputs/`（prep.yml 副本 + 基线 deck_id + 改表 decklist 内容+sha256 + field-snap 副本 + matrix-snap 路径+sha256 + manifest 自含 hash——目录整体拷走仅凭目录可追溯每个数字来源）+ `verdict.json`（逐格+四门）+ `verdict.csv`，报告头注回显复算三元组（实验定义 sha256/代码版本/数据版本）；**上游后端分派**——`battlefrontier/data/backend.py` `open_backend`（目录=jsonl dist ∥ 文件=sqlite，10 处 open_db 调用点全切换，行为零变化）+ `backend_data_version`（sqlite 只读 PRAGMA user_version ∥ jsonl schema_version，experiment._data_version 委托）；**CLI 端到端小样例**——`tests/test_prep_e2e.py` subprocess 真实 CLI：run（strict 预检→8 局模拟→SQLite 落库）→ 与直接 API 逐局一致（seed/winner/draw/turns/events_hash 全等）→ report 子命令；**后端决策落档 = open_jsonl fixture 可行**（spike 实证 JsonlBackend 覆盖 get_card/search_cards/snapshots/validate_deck 全接口，最小 dist fixture = manifest/cards/sets/relations/legality 五件，helpers.py `make_e2e_dist` 固化）；**赛后记录模板** `docs/tournament-log-template.md`（纯 docs：赛事/轮次表/赛后汇总实战 vs 模拟分栏——模拟侧引 prep 证据包数字，示例行非真实数据声明）；12 新测（backend 3 + 签名 6[含复验后补 static_weight NULL 误报防护] + 证据包 2 + E2E 1）；**收官：全量 2178 passed + 1 skipped、ruff 零告警**——独立复验实证并修复签名口径偏差（qualified_count 对齐 stats_engine._base_meta 的 n_tournaments 逐条件，static_weight IS NOT NULL 为关键过滤，真库 sig==meta==19 逐位一致），复验后全量重跑绿
- prep 可信化 P0（task 157，Grok 外部评审建议①②采纳落地）：**file 臂构筑合法性**——`_load_decklist_file` 补 `db.validate_deck`（60 同名 4 上限/ACE SPEC 限 1/赛制快照，与 `load_deck` db 臂逐字同口径同调用），违规在第一局模拟前抛错带 violations 明细，db 臂行为零变化；**装载告警不丢弃**——prep 报告新增「装载告警」段逐实验落账；**strict 覆盖率进 prep**——默认开（无文档非基本能量卡拒绝开跑零局），`--no-strict-coverage` 显式逃生（报告头注声明降级 + 违规如实落告警段），db 臂对手同样过闸；**mod-check 批次隔离硬门**——prep 登记 `results/prep-<name>/batch.json`（实验 ID 批次 + 预期种子全集来自实验定义 + 两臂版本 + 池 sha256），`mod-check --batch` 按 ID 取数（废弃 LIKE 前缀搜全库，同名两轮静默合批封堵）+ 校验两臂 code/data version 一致（跨版本显式报错）、status=done、种子集 == 预期全集（缺/超 = INCOMPLETE，重复种子显式报错）；**verdict 第四门 `complete`**——INCOMPLETE 时三门强制「不可判定」；前缀模式保留（CLI 标注「非批次模式，仅一次性干净库」）；既有行为零变化（run/swap-search 存量路径不动）；反例全部合成最小库/构造 decklist 复现（零真实上游依赖）；18 新测（file 臂 5 + prep 3 + batch 8 + 互斥 1 + 端到端/pick-only 注入点更新）

- task 152 闸 3 核销（2026-11-22，Owner 逐卡原文对照）：酿光市 / 盖诺赛克特ex / 伽勒尔 喵喵 / 波克基斯 4 卡 6 决议（D-152a-1/2 部分减伤原语、D-152b-1 竞技场雷能量回收、D-152c-1 昏厥触发额外奖赏、D-152c-2 手牌计数词）全 ✅ 已核——附录 A 四行 + authoring-log gate3=true 落账；证据分歧一处：防卫充能 db 三印刷 text_raw 均「-30」，Owner 口述 -50 系误记，以原文为准；dsl-check 4/4 + 35 单卡测试重跑全绿
- 备赛流程编排命令化（task 156，Owner 2026-11-22 规划三件收官：②编排命令 + ③就绪探针 + ①任务档案归档）：`bfsim field-snap`（场快照导出 = 上游 stats_usage 钉口径产品化 + `--probe` 就绪探针，上游最新赛事 vs 快照窗终点，退出码 0=新鲜/3=有新数据——首跑即命中：上游 11-22 新赛事已超 11-15 窗终点）/ `bfsim mod-check`（改表成对判读 = t152_gard_verdict 泛化：同种子双侧二项配对 p + 场权重条件期望 + 全正/全显著/零回吐三门 + 种子缺口显式 + error 局不静默；实验名纪律 slug=slugify(en_archetype) 入代码）/ `bfsim prep`（prep yml 一键：场刷新 → field-pick → 报名卡组 × 池内全对手成对跑批（同种子域 CRN、报名恒 a 侧）→ 统一报告 md 含限定语头注 + 下一步命令指针；`--pick-only` 零对局档）；18 新测；**真库回测**：t152 沙奈朵 40,000 局库逐格数字与判读脚本逐位一致（10/10 格、p 值全同），条件期望口径修订为池内归一（权重和=1）——t152 会话脚本把池外份额静默摊薄（+4.3pp），新口径 +5.5pp，判定不变；既有行为零变化（纯新增三模块 + CLI 三子命令）
- v2.x+ 定向补池与沙奈朵新场核对（task 152 备赛线，Owner 离线 goal loop 2026-11-22 凌晨收官）：第 11 套赛富豪纯构筑入池（mik_moe:716219，11-01..15 窗 rank 1，池覆盖 69.78% 缺口封堵）；strict-coverage 连环暴露 4 卡缺口清零——酿光市（stadium_grant 雷能量回收）/ 盖诺赛克特ex（金属信号钢进化检索 + 防卫充能）/ 伽勒尔 喵喵（聚宝功抽牌 + 宝物突进手牌计数伤害）/ 波克基斯（奇迹之吻掷币额外奖赏）；**引擎扩展三件**——`reduce_attack_damage` 部分减伤原语（5/6 元 attack_shield 长度判别，皇冠蛋白石存量逐位不变，D-152a-1/2）、`opponent_active_ko` 事件 + `take_extra_prize` 原语（昏厥结算点发射/卡名去重不叠加/completion_hint 完成形态，D-152c-1）、`own_hand_count` 计数词（D-152c-2）；55 对 × 500 矩阵零失败（种子 410000）→ matchup-snap-2026-11-22（121 格 0 low_confidence）→ field-pick 11 套（Dragapult 64.1% 登顶 / Gardevoir 59.4% / 赛富豪纯自评 38.1% 第 10）；**沙奈朵改表新场核对**：基线 + 改表 × 池内 10 对手同种子成对 40,000 局零失败——10/10 格全正全显著（最差 p=0.040）零回吐，池内条件期望 47.1%→51.4%（+4.3pp），两刀改表新场头下维持成立；风险读数 = 改表对纯多龙仍 38.0% 大劣；D-152a/b/c 六决议占位待 Owner 闸 3 核销；全程 dig `docs/digs/2026-11-21-field-refresh.md`
- BC 自蒸馏阶段与停损判读（task 152 / M16 BC 主线首段，**提升门 FAIL → kill criteria 触发 → 按 PRD 停损**）：task 151 数据集（147,635 行，混合教师 mcts 46.6%/heuristic 53.4%）全量零报错转换（v2.x 词表 131，`build_card_vocab` 现成机制，行级 `agent` 键无感兼容）；BC 训练 `models/policy-m16-bc1.json`（11.3 min，M12 钉死超参零偏离，holdout argmax 0.4717，一致率锚 54–58% 混合教师口径）；联赛评估面注册表 `experiments/t152-bc-league.example.yml`（3 agents × v2.x 10 decks × 8 局 × CRN 双向 = 60 细胞 480 局，教师 = task 151 同款 2×50+eval-v3 截断 10，评估预算冻结含功效披露与 inconclusive 带处置）；**判决**：BT-MLE mcts 1588.9 / heuristic 1535.1 / bc 1375.9，bc 对启发式 26.3%（−47.5pp）对教师逐 deck median 0.25（10/10 负）→ 提升门两条件 FAIL，kill 停损线（点估计 < +3pp）触发——**RL 不启动，回 M15 水平线，资产留档**；归因（假设级）= 混合教师无条件化模式平均 + covariate shift 复合误差 + 特征表达折扣；重启候选仅留档（agent 条件化 BC / DAgger / 纯教师子集，须新预注册）；全程 dig `docs/digs/2026-11-21-t152-bc-data.md`
- 自对弈数据飞轮数据集 v1（task 151 / M16 BC 数据面，预注册 2026-11-20 冻结，**2026-11-21 收官：质量门 5/5 过**）：混编种群 {MCTS 2×50 + eval-linear-v3 截断 10, 启发式} 按 `(seed−对种子起点)%2` 交替指派（行级 `agent` 标签，header `mix:true`），v2.x 池 45 对 × 22 局 = 990 局零失败、147,635 决策点（种子域 1020000..1020989，与训练/探针域不重叠），产物 `results/m16-flywheel-v1/`；工程面 = `collect-snapshots` 增 `--mix-population`/`--evaluator-path`/`--eval-cutoff-turns`（缺省 None = 现状零变化）+ `SnapshotCollector.record_players`（混编启发式侧无 consideration 也入流，缺省空集零变化）+ Pool `maxtasksperchild=500`；10 新测；WP2 真实配置串/并逐字节 6/6 全等；**门 ② 裁决（Owner，建议 (a)）**：交付时字面 147,635 < 150k（98.4%），根因 = 预注册 ~170k 估计锚 M12 双侧 MCTS 口径、混编密度不可移植（实测 149.1/局）——接受数据集，门 ② 修订 ≥145k（根因披露 dig §4；修订纪律：后续采集任务密度估计按种群口径分别锚定）；全程 dig `docs/digs/2026-11-20-t151-flywheel-data.md`
- 非线性评估器天花板 spike 与判决（task 155a / M16 BC 停损评审决策输入，预注册 dig `docs/digs/2026-11-20-t155a-nl-eval-spike.md`）：torch MLP 560→128→64（3 epoch，复用 task 155 的 4,073,978 行零新采集）60 局 v2.x 探针 AUC = **0.7867**，**ridge v3 同探针 0.7874 逐位打平** → 模型类不是瓶颈、特征集信息天花板 ≈ 0.79；预注册决策规则（<0.85）触发 **gate 校准修订案**：0.90 门 = v1 时代尺子（不可约随机性），建议改「≥ 天花板参考 MLP AUC 的 95% + Δ≥+0.05 vs 30 维基线」——按此口径 ridge v3 立即过门（0.7874 ≈ 99.9% 天花板，Δ=+0.11），task 151/152 待 Owner 解冻拍板；探针 `.kimi-code/t155a_nl_spike.py`（冻结 gate 脚本不动）
- 评估器特征 v3 与过线判读（task 155 / M16 BC 开工门修复候选，Owner 裁决 task 150 停损选项 A，**主门 FAIL 转 Owner 停损评审**）：特征层 `battlefrontier/agent/eval_features.py`（36 基座只读复用 M11 30 维 + 弃牌 6 维 + 4 区 × 131 词卡身份 = 560 维，对手手牌身份零泄漏）；采集 v3（首行 header 钉清单 + 位置行紧凑格式，`collect-features --feature-set v3`）；训练 v3（numpy 分块两遍流式，`train-eval --feature-set v3`，λ 候选六档）；资产 format `bf-linear-eval-v3` 装载/预测分派（v1 路径逐字不动）；**采集产线两次内存修复**——主进程结果流式落盘（v3 行 ~20KB 对象 × 400 万行全批累积 ≈ 80GB 顶穿内存 → imap 逐条落盘 O(单局)）+ spawn worker 回收 `maxtasksperchild=500`（地址空间棘轮定界）；正式产线需 `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`（worker 经 agent/distilled 传递性载 numpy+OpenBLAS，默认 22 BLAS 线程 × 16 workers 顶穿系统提交额度）。资产 `models/eval-linear-v3.json`（54,000 局 / 4,073,978 行，λ=10000 顶候选上限，验证 MSE 0.1758 vs 基线 0.2500）——冻结探针 v2.x 对决 AUC **0.7571**（0.6743→0.7571，方向证实特征层归因，距门 0.90 仍 0.14）；v1 对决对照臂不可比（v3 词表锚定 v2.x，跨池卡名触发词表外 ValueError = 不猜纪律按设计拦截）；判决 dig `docs/digs/2026-11-19-t155-eval-feature-v3.md`（Owner 决策输入：A' 非线性评估器 / B 教师去评估器化 / C 延期）
- v2.x 评估器重训与过线判读（task 150 / M16 BC 开工门，**FAIL 转 Owner 停损评审**）：`models/eval-linear-v2.json`（v2.x 池 54,000 局 / 4,073,978 行重训，λ=100，验证 MSE 0.1995 vs 基线 0.2500）——t145 同款探针 v2.x 对决 AUC 0.6743（门 0.90 未过）；in-distribution 重训零提升（对照 v1 资产 0.6755）→ 归因 = 30 维特征层对 v2.x 新机制失明（非数据分布）；过线探针 `.kimi-code/t150_eval_gate.py`（t145 冻结不动）；判决 dig `docs/digs/2026-11-18-t150-eval-v2x-retrain.md`（Owner 三选项：特征 v3 立项 / 教师去评估器化 / M16 延期）
- 吞吐决策点 spike 探针（task 149 / M16 前置，判决 **R2 可行、Rust spike 不立项**）：`bfsim probe-throughput --agent {heuristic,random,distilled} --games N --workers W [--deck-id X] [--policy P] [--net-forward N]`——串行采样精确决策点计数（CountingAgent 包装 observe）+ 并行计时（复用 execute_experiment 纪律）+ policy 纯 numpy 前向微基准；`decide_r2` 三态判定纯函数（预注册门槛 ≥3M 决策点/天 且 ≥300k 局/天）；实测 heuristic × 沙奈朵真实卡表 = 5.2M 局/天 + 7.4 亿决策点/天（门槛 17×/245×），M16 kill criteria 吞吐项解除；distilled v2 词表锚定 v1 池再确认（task 150 供给面）。判决 dig：`docs/digs/2026-11-18-t149-throughput-spike.md`
- agent 种群联赛设施（task 127 / M15→BC 评估面前置，PRD v0.5）：`bfsim league <registry.yml> --results db [--workers N]`（跑+报一体）与 `--report <league名>` 纯报告模式——注册表 yml 钉死规模（agents[id+type/params 白名单复用] × decks × games_per_cell，seed_stride 防区间重叠）；CRN 双向配对（同无序对 ab/ba 共享种子区间、卡组 mirror，先手偏差聚合层对消）；**BT-MLE 评级主估计子**（Bradley-Terry MM 迭代，平局 0.5、零均值 log-strength + Elo 标度展示——task 148 教训：固定大步长顺序 Elo 未收敛、不交付）；成对胜率矩阵 + meta 回显（registry sha256/种子/代码+数据版本）+ 限定语头注；实验细胞复用 execute_experiment（并串逐局一致/增量落库/失败局落 error 纪律全继承）；31 新测（评级解析锚 ln(s/(n−s)) 精确复现/循环对称/结果取反对称/双跑与并串逐局一致）
- MCTS value_guide 树内 value 引导（task 126 / M15，D-M15-1）：UCT 子节点选择加 `value_guide_weight · V(child)` 项——V = 展开时刻子节点状态评估器估值（root 视角缓存 `_Node.v_raw`，对手节点翻边同 mean 口径），选择/回传阶段零评估器调用；`value_guide=true` 必填 `evaluator_path`（复用 load_model 强校验），`value_guide_weight=0` = 永不触发路径（与关闭逐局等价 = 行为门钉零臂）；默认关（行为零变化纪律）；mcts params 词表 +2（`value_guide` / `value_guide_weight`）
- v2.x 矩阵与选卡器快照刷新（task 137）：45 无向对 × 500 局 = 22,500 局零失败（`experiments/t1115-v2x-matrix.example.yml`，种子锚 400000）；`matchup-snap-2026-11-15.json`（90 格 / 0 low_confidence）+ `field-snap-2026-11.json`（2026-11-01..14 窗，10 池覆盖 85.25%）
- 太乐巴戈斯ex DSL 档（task 138，CSV9C-175 档 7 印刷等价类，`cards/太乐巴戈斯ex.yml`，库 154→155）：同盟打击 usage_gate=second_player_first_turn（D-138-1，枚举点使用门，「无法使用」≠「招式失败」）+ bench_count_own 计数词（D-138-2）；皇冠蛋白石 prevent_attack_damage 时效减伤（D-138-3，timing=opponent_next_turn + attacker_stage=basic + except_attacker_type=无，「下一个对手的回合」窗口精确圈定、对手回合结束清除，仅免疫招式伤害）；新词表段 usage_gates + actions/counters 各一词；附录 A 三行 🔲 待核
- 池阻断卡引擎扩展批（task 139）：钥圈儿 / 桃歹郎ex / 乌栗 / 重力山 4 卡 DSL 过闸（各等价类全印刷挂载）+ 侧 quest 异文本拆分档 索财灵-小使者（CSV9C-096 档）/ 雪童子-冰砾（CSV6C-032 档）；引擎扩展九件——apply_status selector=own_active（D-139-1）、switch filters 透传 + 特性可行性门分支（D-139-2）、suppress_ability 广义化 args.stage=basic 阶段过滤 + args.except_ability 具名豁免 + 宝可梦来源 effect.condition（D-139-3/4，数据底座 CardDef.ability_names ← db abilities[].name）、discard selector=opponent_active_tool（D-139-5，接 protection 守卫）、choose_mode 模式二选一原语 + if_mode 节点条件（D-139-6，不可行模式预筛不进池、恰一可行自动选定、选择随挂起冻结穿透）、modify_damage args.target_rule_box 列表（D-139-7，乌栗「宝可梦【ex】・V」）、modify_hp 竞技场来源 + args.target_filters（D-139-8，重力山）、节点条件 if_opponent_active_type:<属性>（D-139-9，雪童子-冰砾）
- 换卡搜索器原型（task 130）：`bfsim swap-search --deck <id> --vs <id> --budget <n>`——单卡替换候选扫描（槽位分类 + 邻近卡组 top-N/手填候选源 + DSL→赛制→结构过滤链）+ 筛选→确认两阶段（CRN 成对、换种子重验）+ ΔWR/Bonferroni/BH 排序输出；方法论设计文档 `docs/digs/2026-11-14-deck-swap-search-design.md`（四问定案 + 预注册判据）
- I 标渗透件 DSL 批（task 136）：轻飘飘 / 胖嘟嘟ex / 能量回收-10.6（I 标异文本拆分档）/ 道具拆除器 / 英勇手镯 5 新档（库 138→143）；引擎扩展三件——passive_static `lock_play` 广义门类（category=item/tool，D-136-1）、节点条件 `if_attached_energy_ge:N`（D-136-2）、`discard selector=tools_attached_both`（D-136-3）
- 换卡敏感性首个正式资产（task 113）：多龙黑夜魔灵 1×3 扫描，预注册 5 门（含阴性对照 CI 覆盖 0）；`experiments/v2-swap-dragapult-dusknoir.example.yml`
- swap `in_id` 印刷级换卡支持（task 115）：`SwapCfg.in_id` 可选字段 + 存在性/同名校验，换入卡印刷可控、防 vanilla 静默退化；覆盖印刷重跑实验定义 `experiments/v2-swap-dragapult-dusknoir-printswap.example.yml`
- 对齐窗判决值守线（task 112）：WAIT 态周期维护 + 触线按 task 105 §2 出判决
- claims register（task 104）：产品宣称两层（可宣称/不可宣称）+ 使用守则

### Changed

- **M16 BC 开工门判据修订（PRD v0.7，2026-11-20 Owner 拍板）**：旧「v2.x 绝对 AUC ≥ 0.90」（v0.5）实证为 v1 尺子——task 155a spike 显示 560 维特征集天花板 ≈0.79（MLP 0.7867 vs ridge 0.7874 逐位打平，瓶颈 = 不可约随机性非模型类）；修订为同 60 局探针成对判据「≥95% 天花板参考 + Δ≥+0.05 vs 30 维基线」，含重锚协议（换代必重跑 spike）/ 临界复判（90–100% 带扩 120 局）/ 种子域不重叠三条款。**判决：eval-linear-v3 双条件过（0.7874 / 参考 0.7867 / 基线 0.7111）→ PASS，task 151/152 解冻**；t150 冻结脚本保留为历史件不再用于门判（探针实现 = t155a spike 的 sample_states/auc）；风险 review 五条款落 dig
- 镜像局口径 v0.3（task 140，M14 gate review 裁决）：源缺镜像由「自然剔除」改为按 50% 默认计入——自然剔除对高份额构筑系统性不利；`assemble_matrix` 补 source="mirror" 对角格（源提供对角时源数据优先），快照自包含 100 格；复跑 field-pick 与 Owner 手算交叉对上（62.1/58.3/55.1 vs 62/58/55）
- 卡池 v2.x 定向修订（task 135，依据 task 133 dig 建议档）：6 套高漂移表刷新为近窗（2026-11-01..14）冠军表 + 赛富豪土龙节节第 10 套入池；`config/target-pool.v2.yml` 修订（version 保持 2 + revised_at，task 068 原始锁定段保留为注释事实源）；近窗覆盖 85.25%
- `format_sensitivity` 末行补 `SIM_INTERPRETATION_NOTE`（task 114）：敏感性输出纳入 claims register 守则 1
- task 102 文档勘误（task 111）：「无向 36 对」预检点估计口径未存档不可复现，权威口径 = 有向 72 格 + `results/t102-calibration.json`
- 报告层/校准输出内嵌 sim 解释限定语（task 106）；事件序观感债修复——昏厥/拿奖事件滞后到招式效果链收尾（task 108）

### Deprecated

- 格级胜率预测与强度排序宣称（task 102/103 定量关闭，claims register 禁句区）

### Removed

- M12 三残留盲区（task 109 预注册预检全部关闭，backlog 清零）

## 2026-10

### Added

- 卡池 v2（task 068，`config/target-pool.v2.yml`，WUR 覆盖 80.5%）+ 引擎扩展两批（069/071）+ DSL 缺口清零 134 份（070/071）
- M13 校准地基（094–096）：full/development/validation 三份双轨偏差包
- MCTS 决策分析（task 042）：`bfsim report --mcts-consider` 三件套
- M11 学得评估器（049–055，`models/eval-linear-v1.json`）/ M12 蒸馏学生（056–062，`models/policy-m12-v1/v2.json`，定位分钟级粗筛）

### Changed

- MCTS 信息泄漏修复（task 039，带冻结集部分 determinize）
- promote 空场判平引擎修复（task 064，时序语义定案 + 附录 A 决议）
- MCTS 成本优化（task 037–042 期，−38.5%，行为零变化 events_hash 逐局全等）

## 2026-08 ~ 2026-09

一期 M1–M6 全段（引擎骨架 / DSL+解释器 / 启发式 Agent / 报告层 / 覆盖扩展 / 校准基线）——逐日记录见 `docs/status-archive.md`。
