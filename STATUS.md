# STATUS.md — ptcg-cn-battlefrontier

> 进展速记：每完成一步更新。规范对齐 db 项目（进展记在这里，不进 README）。
> 历史段落与 task 066 及更早的工作记录已归档至 `docs/status-archive.md`（2026-10-27 精简）。

## 当前

**当前焦点 = 核销 PR 待审**（070 闸 3 十五张 + 069 附录 A 三条 + 区分词 / 电电虫偏差；只改文档，不合并）。task 076 正式矩阵已在 main（`c436471`：18000 局失败 0；加权 |Δ| 18.5% 仍是启发式策略偏差）。未做：构筑 GUI、全池单卡扫描、JEV、LLM。v2 锁定后学习线复跑（D3-5）另立项。

**三期主线已收官（M11 ✅ M12 ✅ 部分达成收口，D3-7 2026-10-21 用户拍板）**：蒸馏学生正式定位「分钟级粗筛」——锚 1 决策一致率 ✅ / 锚 3 分钟级 ✅（全 matrix 18000 局 7.4min，教师口径 73×）/ 锚 2 过第一门槛（加权 |Δ| 12.5% ≤ 启发式基线 13.2%，未及 M10 9.7%）；跨配对保序两版实证不成立（Spearman≈0），精排/深挖仍归 MCTS。残留盲区 backlog：特性使用质量（4.05/局 < 5 门槛）/ play_stadium / end_turn；~~copy_attack 多级嵌套~~ / ~~IndexError（沙奈朵）~~ 已由 task 076 修掉；事件排序观感债攒批随引擎改动顺手清。M12 终判链路（061 根因诊断 → 062 特征 v2 → 063/064 promote 空场判平修复 → 065/066 盲区归因与处置证伪 → 067 复校准地基 9.715%）细节见归档与 `tasks/done/`。

**卡池 v2 独立线（D3-5）**：v2 已锁定（task 068，`config/target-pool.v2.yml`，覆盖率 80.48%，校准真实侧 72/72 格零低置信）；引擎扩展批 ✅（task 069）；DSL 第一批 15 张 ✅（task 070，闸 3 十五张 ✅ 2026-10-28 助手核销）；引擎扩展第二批 + 原 blocked 19 张 ✅（task 071，闸 1/闸 3 19/19 与附录 A #1–#7 已核）。Mega 线暂缓（2026-10-07 决议：简中环境无 Mega）。DSL 定义库 134 文件。本机正式矩阵已跑完（Diupi-Yun，code `8a3aecb`，启发式，16 workers，约 5.6min）：`load_deck` 九卡组 9/9、n=60、warnings=0；`dsl-check --db` 134/134 OK。数字与失败拆分见下方 task 072 节。换卡正式 `results/*swap*` 未见，只有模板和代码。

**核销（2026-10-28，助手，owner 授权 C）**：task 070 闸 3 十五张 ✅；高级球「才可以使用」/裁判「手牌全部」同语义异措辞 ✅（拆文件正确，DSL 同构，gate3 PASS）；电电虫洗牌 2 次 vs 原文 1 次 ✅ 已核工程偏差（均匀重洗等价，RNG 多耗 1 次）；附录 A 虹色因子 / 顽强之心 / types:all ✅。力之沙漏时点与 ACE 锁维持原 ✅，未重开。

## 里程碑

- ✅ M1 引擎骨架（白板对局 + 同种子复现）——task 001–004 全 ✅（2026-08-25）
- ✅ M2 DSL + 解释器 + 首批原语（第一套目标卡组）——task 005–008、010–017 全 ✅
- ✅ M3 启发式 Agent + Runner + 结果库（百局端到端）——task 018–020 全 ✅（2026-08-29）
- ✅ M4 报告层（胜率 / 决策聚合 / 换卡敏感性）——task 021–023 全 ✅（2026-08-30）
- ✅ M5 覆盖扩展 + LLM 辅助编写试验——task 024–027、029 全 ✅（2026-09-20，用户确认达成：覆盖清零 81/81 + gate3 42 文件全核 + 附录 A 41 条全核）
- ✅ M6 校准基线 + 一期验收——task 030 ✅（2026-10-03，用户确认达成：偏差表 72 格产出 + 硬验收全过）
- ✅ M7 偏差归因（二期首里程）——task 031 ✅（2026-10-03：5 大偏差格全判定 Agent 主导、DSL 零缺陷；D2-3 细化为 M8a 启发式修复 → M8b 复校准 → MCTS 评估点）
- ✅ M8a/M8b 启发式修复批 + 复校准——task 032 ✅（2026-10-03：A1 代价选择方向 / A2 变量伤害估算 / A3 囤能例外（修订版）/ A4 牌库保护落地，961 绿；复校准机制指标改善但 |Δ| 不收敛 → MCTS 立项论证成立，待用户拍板）
- ◐ M9 引擎收尾 ✅ / 环境演进调研待数据——task 033 ✅（2026-10-03：D2-5 四项清零——damage 空战斗场 no-op（D-033-1 ✅）/ 附录 A 三候选裁决（顶尖捕捉器维持 D-033-3、学习器自弃归正进消除面 D-033-2 ✅、aura 去重键粒度维持 D-033-4）/ 夜光能量 7 印刷 YAGNI 关闭 / 密勒顿回池评估→建议不回池（WUR 0.27% #32/82）；复跑失败局 18→1、串并一致 500/500、964 绿）；Mega 调研暂缓（2026-10-07 用户决议：简中环境无 Mega，见决策日志）
- ✅ M8c MCTS 决策层——task 034 ✅（2026-10-03：多世界 determinized UCT（D-034-1~9）落地，type=mcts 进实验定义；单格验证赛富豪(MCTS) 18.75%→46.6% / 苍响(MCTS) 81.25%→95.2%（500×2 向，失败 0）；996 绿 + 串并一致 20/20；性能 ~219s/局/worker → 全 matrix 铺开 ≈68.7h 不适合例行）
- ✅ M8 铺开与预算档定案——task 035 ✅（2026-10-04：阶段 A 预算标定曲线 20u 37.7% / 50u 42.9% / 100u 46.6% / 400u 54.2%，边际递减未平台化 → 标准档 2×50 维持 + 深档 4×100+ 仅单格深挖（D-035-5）；阶段 B 五重点格弱侧 MCTS 2500 局零失败——5/5 格 +24.4~38.8pts，赛富豪×玛俐 58.1%/猛雷鼓×玛俐 53.8% 精确命中真实值（58.1%/54.8%），归因「策略深度主导」跨卡组闭环；996 绿 + ruff 零告警）
- ✅ M10 二期校准复核——task 036 ✅（2026-10-05：MCTS 增强版偏差表加权 |Δ| 9.7%（M6 13.2% → M9 15.0% 轨迹）；D2-7 归因闭环 ✅——|Δ|≥25% 五格全有解释+证据 id，沙奈朵/玛俐/猛雷鼓三对 CI 双覆盖（|Δ|≤1.3）；沙奈朵格双侧 MCTS 500 局零失败：63.8% vs real 65.1%，单侧残余完整归因「对照侧启发式操作质量」；**二期 M7–M10 全段收官**）
- ✅ M11 学得评估器接 MCTS rollout（三期首里程）——task 049–055 ✅（2026-10-18，用户确认达成：锚 1 决策一致率相对教师天花板口径 100.2% ≥ 0.85；锚 2 定点格按同预算净效应口径达成——满预算验证格 2×50 K=10 学生 66.4% vs 基准 62.0%，CRN 成对 CI95 [-0.013,+0.101] 覆盖 0，评估器两档预算零失真；选档 2×25 K=10 + eval-linear-v1）
- ✅ M12 MCTS 行为蒸馏（**部分达成收口**，2026-10-21 用户拍板 D3-7）——task 056–062 ✅：锚 1 ✅（v1 相对天花板 88.8% ≥ 0.85；task 062 特征 v2 补全失败面测量 use_ability 0.009%→20.9%）；锚 3 ✅（v2 全 matrix 18000 局 7.4min，教师口径 ~9h → 73×）；锚 2 过第一门槛（v2 加权 |Δ| 12.5% ≤ 启发式 13.2%，未及 M10 9.7%）；**学生定位分钟级粗筛**（保序两版实证不成立）；残留盲区进 backlog（特性使用质量 / play_stadium / end_turn / copy_attack 多级嵌套）

## 工作记录

### 2026-10-28 核销：070 闸 3 十五张 + 069 附录 A 三条（文档，不合并）

- **授权**：owner C 授权助手查资料确认并核销。核销人 = 助手；日期 2026-10-28（Asia/Shanghai）。不改引擎、不跑矩阵、不引入 JEV/LLM
- **闸 3**：`cards/authoring-log.jsonl` batch 10 十五张 `gate3=true`（全部 PASS）：高级球、裁判、能量回收、N的PP提升剂、璀璨结晶、力之沙漏、逆转能量、伊布ex、叶伊布ex、皮卡丘ex、密勒顿ex、N的莱希拉姆、盖诺赛克特、电电虫、老大的指令。blocked（`gate1=false`）行未改
- **区分词**：高级球「才可以使用」vs「才可使用」、裁判「手牌全部」vs「所有手牌」= 同语义异措辞，拆文件正确，DSL 同构，gate3 PASS
- **电电虫**：洗牌 2 次 vs 原文 1 次 = ✅ 已核工程偏差（两段 `attach_energy own_deck` 各内建重洗；均匀重洗等价，RNG 多耗 1 次）
- **附录 A**：虹色因子 / 顽强之心 / types:all（璀璨结晶）🔲→✅。力之沙漏时点与 ACE 锁维持原 ✅，未重开
- **依据**：伊布ex 卡面括号门 + EN Rainbow DNA（登场/最初回合仍不可进化；`modify_evolution` 不走 `skip_play_gates`）；皮卡丘ex 卡面「招式的伤害」+ Compendium 2041（满 HP 在伤害放置当时判定）；璀璨结晶卡面「任意属性」+ EN Sparkling Crystal，引擎可视费用 = 优先【无】否则 cost 首个有色

### 2026-10-28 task 076 ✅：正式矩阵两大失败（IndexError / copy_attack 嵌套）

- **IndexError 根因（栈自证，不是精神拥抱）**：`HeuristicAgent._attack_table` 只读 `card.attacks`。招式学习器 能量涡轮卡面 attacks 为空，引擎用 `grant_attack` 合成招式（task 071 D-071-4），合法 `attack_index` 落到表外 → `list index out of range`（`heuristic.py` 斩杀检测）。全库只有这一张卡走合成路径；矩阵 888 局 100% 含沙奈朵 `mik_moe:678647`，与「该卡组带这张学习器、其它卡组互打几乎不炸」一致。修复 = 启发式与引擎共用 `resolve_tool_attacks`
- **copy_attack 根因**：task 020 只留一层帧，内层再传播即 `DslError`（不猜）。暗夜王牌复制「自身又会挂起的 copy_attack」即第二层（858 局，100% 含 N的索罗亚克 `mik_moe:690359`，钉在暗夜王牌）；梦幻ex 基因侵入同形态 2 局。第一层复制「不挂起的招式」原本就能走完。卡面「作为这个招式使用」没有层数上限，rules-manual 无条款 → 附录 A ✅ 已核（助手 2026-10-28 搜卡核实）：帧栈不设上限；已在栈上的 (来源 iid, 招式名) 不再可选，池空则 no_copyable 空结算
- **测试**：`tests/test_t076_matrix_failures.py`（合成招式打分 + 驱动一步、嵌套 2/3 层伤害、基因侵入套暗夜王牌、同招式不再入池）+ `test_copy_cycle_ends_attack_without_error`
- **本机正式复跑**（Diupi-Yun，分支 `cursor/v2-matrix-failures-f02a` @ `c436471`，启发式，16 workers）：`bfsim run experiments/v2-calibration.example.yml --results results/v2-calibration-pr2.db`，随后 `bfsim calibration ... --out results/v2-deviation-pr2`。矩阵 36×500 = 18000 局，**失败 0/18000**（修前同口径 1748：IndexError 888 + copy_attack 暗夜王牌 858 + 基因侵入 2）。`load_deck` 九卡组 9/9、n=60、warnings=0；`dsl-check cards/*.yml` 全 OK；相关 pytest `test_t076_matrix_failures.py` + `test_copy_nested.py` 13 passed。偏差包：加权平均 |Δ| **18.5%**，CI 覆盖 2.8%（2/72），低置信 0/72；最大 Δ 沙奈朵 vs N的索罗亚克 **+65.6%**（对称 −65.6%）。真实侧抽检：偏差包 72 格 `real_n`/`real_wr` 与 `ptcg-cn.db` `v_pairing_players` 重算 **72/72 全等**；沙奈朵×N的索罗亚克决定局 339 = 沙奈朵 103（30.4%）/ 索罗亚克 236（69.6%）。口径：引擎修复验证通过（失败清零）；残留 |Δ| 是启发式策略偏差（该格 sim 沙奈朵 96% vs real 30.4%），不是引擎崩溃。产物留本机，不入库：`results/v2-calibration-pr2.db`、`results/v2-deviation-pr2/`
- **未做**：特性使用质量 / play_stadium / end_turn 仍在 backlog。附录 A「copy_attack 多级嵌套」保持 ✅ 已核

### 2026-10-28 task 075 ✅：换卡报告双轨（PR #1 未由代理合并）

- **站在现有命令上**：`variants` 跑批仍是 `bfsim run`；报告仍是 `bfsim sensitivity`。新增 `--out` 与 `--replay-sample`（默认各抽 2 局）
- **导出**：`swap.md` 内嵌 `format_sensitivity`；HTML 由该文转义；CSV/JSON 的 `d_wr` 等于 `VariantComparison.d_wr`。回放复用 074 的 `sample_replays` / `render_log`
- **模板**：`experiments/templates/card-swap.example.yml` 只声明一组换卡，不扫描卡池
- **命令**（跑局需要本机库）：

```bash
bfsim run experiments/templates/card-swap.example.yml --results results/card-swap.db
bfsim sensitivity <base_id> <variant_id> --results results/card-swap.db --out results/card-swap
```

072–075 在这条 PR 上收口。代理不合并。

### 2026-10-28 task 074 ✅：精简对局日志 B（PR #1 未由代理合并）

- **数据**：只读结果库 `games` / `game_events`。主阶段 kind = attack / retreat / play_trainer / play_stadium / evolve / attach_energy / end_turn。`choose` 仍由 `--decisions` 负责
- **默认开**：每局一行（种子、先后、胜负、回合、失败文本）。抽样回放默认 3 局，完成局按种子升序，`--replay-sample 0` 可关掉正文。不渲染全部对局
- **导出**：`results/report-<id>-log`。Markdown 内嵌胜率、汇总、行动、回放原文；HTML 由该文转义；CSV/JSON 的胜率等于 `ActionStat`
- **命令**：

```bash
bfsim report <experiment_id> --results results/exp.db --out results/report-log
```

不做假理由、合法行动全量转储、关键路径 LLM。075 未做。

### 2026-10-28 task 073 ✅：三种入口模板 + 只读真实对阵（PR #1 未由代理合并）

- **入口**：`experiments/templates/deck-id.example.yml`（`source: db`）、`pool-yaml.example.yml`（`matrix.pool`，每对 1 局冒烟）、`name-count.example.yml` + `name-count.example.txt`（「N 卡名」，示例不足 60，装载会拒绝）
- **对阵**：`battlefrontier/data/pairings.py` 以 `mode=ro` 读 `v_pairing_players` ⋈ `v_tournament_weights`。只留池内 `en_archetype`、镜像剔除、`winner_side=0` 不进分母。不是浏览产品，也不填正式 |Δ|
- **命令**（需本机库才能跑出真实行；测试用临时库）：

```bash
bfsim run experiments/templates/deck-id.example.yml --results results/deck-id-smoke.db
bfsim run experiments/templates/pool-yaml.example.yml --results results/pool-smoke.db
bfsim pairings --pool config/target-pool.v2.yml --out results/v2-pairings
```

卡名×张数须先把列表凑满 60 张再跑。不做构筑 GUI。074/075 未做。

### 2026-10-28 task 072 ✅：v2 校准管道 + 正式矩阵已跑（PR #1 仍由代理不合并）

- **范围**：卡组入口是池 YAML 的 `deck_id`。不新造校准命令。管道与 073–075 同在 PR #1；本 PR 不修下面两处引擎缺口
- **实验**：`experiments/v2-calibration.example.yml`（`v2-calibration`，种子 200000，每对 500 局，池 `config/target-pool.v2.yml`）。冒烟定义 `experiments/v2-calibration-smoke.example.yml`（每对 1 局，种子 900000）不作为正式偏差
- **导出**：`battlefrontier/report/deviation_pack.py`。Markdown 内嵌 `format_calibration` 全文；HTML 由该 Markdown 转义；CSV/JSON 字段来自同一 `CalibrationCell`
- **本机正式跑**（Diupi-Yun，code `8a3aecb`，启发式，16 workers，约 5.6min）：
  - `load_deck` 九卡组 9/9，n=60，warnings=0
  - `dsl-check --db` 134/134 OK
  - 相关 pytest 29 passed；PR 上 072–075 套件曾报 47 passed / 9 skipped
  - 矩阵 18000 局 → `results/v2-calibration.db`。失败 1748：IndexError 888（100% 含沙奈朵 `mik_moe:678647`；无堆栈，路径未钉死）、`copy_attack` 嵌套 >1「暗夜王牌」N的索罗亚克ex 858（100% 含 `mik_moe:690359`）、梦幻ex 基因侵入 2
  - 偏差包 `results/v2-deviation/`：加权平均 |Δ| **18.5%**（`weighted_mean_abs_delta`≈0.1849）、CI 覆盖 2.8%（2/72）、低置信 0/72、最大 Δ N的索罗亚克 vs 沙奈朵 −64.7%
  - 对阵包 `results/v2-pairings/`、report 冒烟 `results/v2-report-smoke/` 已写出
  - 换卡正式 `results/*swap*` 未见（仅模板 `experiments/templates/card-swap.example.yml` 与代码）
- **统一审**：管道验收通过。|Δ| 被上述 IndexError 与索罗亚克招式复制嵌套抬高。这不是笼统的「特性使用」：索罗亚克失败是 `copy_attack` 多级嵌套；IndexError 只与沙奈朵共现。两处下一任务修，本 PR 不修
- **命令**（本次正式跑用 16 workers）：

```bash
bfsim run experiments/v2-calibration.example.yml --workers 16 --results results/v2-calibration.db
bfsim calibration experiments/v2-calibration.example.yml --results results/v2-calibration.db --out results/v2-deviation
```

### 2026-10-28 task 071 ✅：引擎扩展第二批 + 19 张 DSL（闸 3 与附录 A 已核，PR #1 待合并）

- **阶段 1**：WP1–17 全部落地。main 上没有中断留下的红测文件，按任务书重新 TDD（`tests/test_primitives_t071.py` 23 测）。组 A chooser/interpreter、组 B primitives、组 C core 读点、WP17 合成 AttackDef
- **规则口径**：突进进化只跳过登场/最初回合门；N的城堡 value=all 与既有减免同一归零旗标；reveal 对手手牌只进事件流；grant_attack 在卡面无招式时用 cost/damage 合成。激流水泵为 `opt_exact`（TPCi 2024-09-12：可放弃，执行则恰好 min(3, 身上张数)），后段 `if_prev_optional_done`。附录 A 第 1–7 条 ✅ 已核（2026-10-28）
- **电蜘蛛**：复眼是 `modify_damage scope=self`（只加成这只宝可梦的招式）+ `target_has_ability`。麻麻网用计数词 `one_if_holder_has_energy_雷` 合成一次伤害，避免复眼按伤害节点重复叠加。节点条件 `holder_has_energy` 已注册，本卡不拆节点
- **阶段 2**：19 张 DSL 入库（批 4a/4b/4c，分片测试）。闸 1（本机 `--db`）与闸 3 均为 19/19 ✅（2026-10-28 用户核销；厄诡椪在 `opt_exact` 修正后核销）
- **存量测试**：两处负例随新契约移出（`multi_target × own_bench`、`reveal opponent_hand`）；`effects_by_name` 白名单加「咕咕」。其余存量断言未改
- **未做**：072+（v2 matrix / 校准 / 备赛）。电电虫洗牌 2 次于 2026-10-28 改为 ✅ 已核工程偏差（均匀重洗等价，RNG 多耗 1 次），不改引擎。粉碎之锤只挂池内 J 标 `30thDC-029`（旧系列印刷未复核赛制合法性）

### 2026-10-27 task 071 立项：引擎扩展第二批 + 070 收口（阶段 1 派遣遭配额中断，待恢复）

- **立项**：用户拍板；任务书 `tasks/task 071.md`——D-071-1 分组（组 A chooser/interpreter 面 WP1–3+16 / 组 B1·B2 primitives 面串行 WP4–6、WP7–10 / 组 C core.py 读点面 WP11–15 / WP17 grant_attack 合成主会话直做）；D-071-2 规则出处（rules-manual §1.1/§1.3/§5/§8：突进进化 / 多谢款待 / N的城堡 / 激流水泵）；D-071-3 reveal opponent_hand 最小口径（事件入流，Agent 视图与 MCTS 冻结集不扩，防信息泄漏回潮）；D-071-4 grant_attack args 扩 {cost, damage} 合成 AttackDef（db 训练家招式 latent gap 引擎自足承接）；D-071-5 不降级纪律
- **规则口径钉定**：可达鸭 湿气定向 = suppress_ability args `with_primitive: ko_self`（ko_self 为词表唯一自昏厥原语，词表开放后续追加）；进化门放宽限「战斗场持有者」+ `_ability_suppressed` 守卫
- **中断记录**：组 A/B1/C 派遣后约 10 分钟配额 429（5 小时窗口）全灭——组 A 留 TDD 红阶段遗产 `tests/test_primitives_t071_a.py` 25 测（WP1/2/3/16 全覆盖，实现零改动可直接 resume）；B1/C 零残留。恢复路径沿用 070 同事故实证（resume + continue）
- **遗留**：阶段 1 四组完成 → WP17 → 阶段 2 DSL 批 4a/4b/4c（19 张）→ 判据 4（v2 装载零缺口）收口 070

### 2026-10-27 task 070 ✅：卡池 v2 DSL 批次第一批——15/34 落地 + 19 blocked（表达力缺口全清单；闸 3 于 2026-10-28 核销）

- **立项**：task 069 表达力备齐后的 DSL 编写棒；任务书 `tasks/task 070.md`（D-070-1 分组 4 批子代理 + 主会话直做 WP0 / D-070-2 纪律 / D-070-3 印刷对齐 / D-070-4 规则不猜）
- **WP0 主会话直做**：逆转能量组合词 `own_prizes_more_and_holder_evolved_no_rule_box`（chooser.py，9 测 `test_primitives_t070.py`）；老大的指令 30thDC-039 纯挂载（text_raw 逐字全等实证，闸 1 ✅）
- **落地 14 张（4 组子代理并行，闸 1+闸 2 全部一次通过、零返工）**：WP1a 高级球-才可以使用/裁判-手牌全部/能量回收；WP1b N的PP提升剂/璀璨结晶/力之沙漏/逆转能量；WP2 伊布ex（modify_evolution）/叶伊布ex/皮卡丘ex（prevent_ko）；WP3 密勒顿ex/N的莱希拉姆/盖诺赛克特（lock_play ace_spec）/电电虫；测试分片 4 文件共 49 测，ruff 零告警
- **blocked 19 张**：全部是引擎/DSL 表达力缺口（子代理按纪律未自造词未降级），缺口精确到读点 → task 071 输入；含 1 项 db 侧 latent gap（训练家卡面招式不解析，招式学习器族）
- **主会话处置**：同名多文本测试碰撞（高级球/裁判再录拆分）按火恐龙先例收口——helpers 白名单 + 2 处语义测试改逐等价类断言
- **核销（2026-10-28，助手，owner 授权 C）**：闸 3 十五张 gate3=true（全部 PASS）；高级球/裁判区分词 = 同语义异措辞、拆文件正确；电电虫洗牌 2 次 = ✅ 已核工程偏差。blocked 19 行未改。authoring-log batch 10 落账 34 行

### 2026-10-21 task 069 ✅：卡池 v2 引擎扩展批（5 机制 + 3 原语小扩，TDD）

- **立项**：task 068 机制定案的实现棒；D-069-1（力之沙漏时点 = 检查阶段内状态结算后）/ D-069-2（ACE 锁 = 广义五门类）用户拍板；D-069-3 三组子代理 TDD（A = WP1/3/5 `_main_actions` 面 / B = WP2 伤害路径 / C = WP4+WP6 回合末面）+ 主会话独立复验
- **交付**：新原语 `modify_evolution` / `prevent_ko`；`modify_attack_cost` 扩 `types:all`；词表 `own_turn_end` 事件 + `attached_energy_on_opponent_all` 计数词；chooser 新 condition `holder_is_tera` / `holder_has_tool`；`lock_play` 扩 passive_static + ace_spec；`_survival_cap` / `_ace_spec_play_locked` / `_modify_evolution_args` 引擎助手；discard choose=N / heal own_bench / attach_energy target_pool=self
- **验收**：判据 1–5 全 ✅——50 新测（WP1 8 / WP2 12 / WP3 6 / WP4 8 / WP5 8 / WP6 9），全量 1454 绿 + ruff 零告警（主会话亲跑）；附录 A 决议 5 行（D-069-1/2 当时已核；虹色因子 / 顽强之心 / D-WP5-4 扩展当时待核，2026-10-28 已核）；存量测试零改动
- **插曲**：组 C 子代理首轮上下文压缩丢失任务（误判为核验员），主会话 resume 纠正后正常交付；组 B 报告自伤不截顶决定（对齐 _damage_self 先例，认可）
- **遗留**：34 张 DSL 编写 → task 070；附录 A 3 条（虹色因子 / 顽强之心 / types:all）于 2026-10-28 核销 ✅；v2 matrix + 校准 → task 072–076

### 2026-10-21 task 068 ✅：卡池 v2 锁定（Top-9 全新排 + 缺口定案 + 机制评估 + 校准口径实测）

- **立项**：D3-5 独立线开工；D-068-1 窗口（只用 09-16 后 46 场）与 D-068-2 构成（Top-9 全新排）用户拍板；侦察子代理实测（`.kimi-code/t068-pool-v2-scout.md`）+ 机制评估子代理 + 主会话核销
- **池锁定**：`config/target-pool.v2.yml`（snapshot standard-2026-09-16 / 覆盖 80.48%）；9 代表卡组全部窗口内 rank 1、`load_deck` 合法性 60×9 全过；v1 封存（D-068-4）
- **缺口 34 张定案**：28 独有 + 6 共有再录；再录核销 = 30thDC-039 老大 text_raw 逐字全等纯挂载 / 30thC-101 高级球 + 30thDC-037 裁判异文本各新写（裁判异文本 task 026 WP7 已预知）；vanilla 8 张核销
- **机制评估**：DSL 可承接 = TERA×5（D-027-1 备战免伤就位）/ 逆转能量（provide_energy 分层 + chooser 组合词）/ 火伊布ex 等；引擎扩展 = 虹色因子（进化枚举声明分支）/ 顽强之心（伤害截顶三落点）/ 力之沙漏（own_turn_end 时点 + attached_tool 寻源）/ ACE 锁（lock_play passive_static + 四处枚举手牌守卫）/ 璀璨结晶（types:all 小扩）；附带原语小扩 3 项（discard choose=3 / opponent 全场附着计数 / heal 备战全体）；附录 A 待核决议 2 条（力之沙漏时点 / ACE 锁覆盖面，随 task 069 核销）
- **校准口径实测（超预期）**：v2 真实侧 72/72 有向格全有 real 数据、低置信格 0（3 新 archetype EN 校准窗 n=2095/1549/998）；v1 为 8 格低置信
- **验收**：判据 1–7 全 ✅；1404 绿 + ruff 零告警（零代码变更回归确认）

### 2026-10-21 task 067 ✅：064 修复后复校准——matrix 重跑 + MCTS 增强表重算 + 旧口径局核销

- **立项**：优先级拍板第一顺位（064 修复后度量地基 + 核销历史库旧口径局）；任务书 `tasks/done/task 067.md`（D-067-1 零代码变更 / D-067-2 种子逐格对齐 M6/M9 / D-067-3 增强表分阶段闸门 / D-067-4 串并抽验 / D-067-6 用户拍板只跑高残留 3 格）
- **matrix 重跑**（`results/t067-recalibration.db`，16 workers 6m47s）：18000 局**平 0（m9 247→0，no_legal_actions 清零实证）**、失败 1 = copy_attack 嵌套已知形态；新启发式加权 |Δ| **15.0%**（持平 M9），逐格移动全部来自旧平局回归分母（最大 1.8pts / 中位 0.45pts，063 量级预期全命中）；串并抽验 500/500 events_hash 全等
- **MCTS 三库旧口径清点**：113 局全部 no_legal_actions（m8c-mcts 30 / m8c-spread 83 / m10-double 0）→ D-067-6 拍板重跑高残留 3 格（`results/t067-mcts-rerun.db`，4h16m，平 0 败 0）：赛富豪×苍响 42.2%（旧 46.6）/ 玛俐×赛富豪 52.0%（旧 58.1）/ 多龙黑夜×赛富豪 59.8%（旧 65.0）
- **MCTS 增强版偏差表两阶段重算**（`.kimi-code/t067-enhanced-table.py`，m9 自检复现 15.0%→9.7% 逐格全等后应用）：阶段一（复用旧格）9.686% → 阶段二（3 格换新）**9.715%**——修复后增强口径与 M10 的 9.7% 持平；格级：玛俐×赛富豪 0.0→±6.1（旧闭环格变小偏差）、多龙黑夜 ±11.6→±6.4（改善）、赛富豪×苍响 -16.6→-21.0
- **验收**：判据 1–7 全 ✅（NLA 清零 / diff 量级 / 增强表 / 清点+重跑 / 串并 / 1404 绿+ruff / 文档对账）；遗留：低残留 2 格（多龙喷 17 / 猛雷鼓×玛俐 6）留档，随卡池 v2 新口径消解


## 决策日志

| 日期 | 决策 | 出处 |
|------|------|------|
| 2026-08-25 | D1–D12 | PRD §2 |
| 2026-08-30 | 退赛 4 archetype 以退赛后窗口 WUR 前列替补（玛俐长毛巨魔雪妖女/赛富豪/多龙巴鲁托/赫普的苍响） | config/target-pool.v1.yml 头注；task 024 |
| 2026-09-06 | DSL 归组口径 =（卡名 + 文本）等价类，**严格拆分**：同语义异措辞也拆（朋友手册「最多2张」/「2张」级别差异不合并）；装载键 name_group → card_id 精确挂载；闸 1 校验文件内 card_ids 归一化 text_raw 一致 | 用户决议（池内实测：112 卡名中 40 个全库多文本、火恐龙/索财灵池内同名异效）；归 task 026 前置 |
| 2026-09-06 | task 026 re-scope：解锁项驱动替代字母批；顺序 = 装配校验前置 → filters/conditions → trigger_on_event + place_damage_counters → 其余按解锁卡数；老大的指令顺带 | 用户决议；tasks/task 026.md |
| 2026-09-19 | 卡池 v1 维持锁定（db 新快照 standard-2026-09-16 + 数据至 09-09 后不换池）——校准基线需要池稳定；密勒顿回池评估留待 M6 后 | 用户决议；STATUS 2026-09-19 数据更新验收节 |
| 2026-10-03 | M6 立项三决策：单 task 030 一次做完 / 模拟矩阵每配对格 500 局 / matrix 声明式实验定义 + `bfsim calibration` 报告（偏差表参数 = matrix YAML 路径非组名）；Jev 决策模型调研后不引入（观察项） | 用户决议；设计文档 2026-10-03-m6-calibration-design.md |
| 2026-10-07 | Mega 环境演进线（D2-6）暂缓：简中环境目前无 Mega——赛事不涉及、db 无简中 Mega 数据，调研前提不成立；待简中 Mega 上线再启动。卡池 v2 不依赖 Mega，可随 db 数据积累独立推进 | 用户决议；二期 PRD D2-6/§3.4/M9 行已同步标注 |
| 2026-10-11 | D-046-1 holdout 双门槛：采纳回写须同时 ①复评训练集胜率 > 0.5（严格）②holdout ≥ 0.5（含平）；过线者取 holdout 最高（tie → 训练 → 搜索 fitness 序） | 用户拍板；tasks/task 046.md、方向 B 设计文档 §8 开放项关闭 |
| 2026-10-11 | D-046-5 默认参数回写裁决：折中存档不回写——deck_low_threshold 6→12 双门槛过线但复校准加权 \|Δ\| 恶化（15.0%→16.1%），默认参数维持 M6–M10 基线锚点；调优参数档存 `experiments/t046-recalibration.example.yml` 供对抗强度实验选用 | 用户拍板；tasks/done/task 046.md 最终结论节 |
| 2026-10-16 | **三期立项**：采纳方向 A 预研结论（有条件可行，两步走 M-A 学得评估器 → M-B MCTS 蒸馏）；学习目标函数钉死「拟合 MCTS 教师 + 复校准 \|Δ\| 不回归」双锚，ELO 不作验收；torch dev-only 依赖开口推迟到 M-B 立项再定 | 用户拍板；预研报告 2026-10-16-learning-agent-feasibility.md、tasks/done/task 047.md |
| 2026-10-18 | M11 里程碑达成确认 + M12 立项：torch dev-only 训练 + numpy runtime 推理（D3-3 核销）+ 训练非复算面声明（D3-4）+ 教师 2×50 + 10³ 试点采集 | 用户拍板；tasks/done/task 056.md |
| 2026-10-21 | **M12 终判 D3-7 = 部分达成收口**：锚 1 ✅（相对天花板 88.8%）/ 锚 3 ✅（7.4min）/ 锚 2 过第一门槛（12.5% ≤ 13.2%，未及 9.7%）；蒸馏学生正式定位「分钟级粗筛」（保序两版实证不成立），残留盲区进 backlog（特性使用质量 / play_stadium / end_turn / copy_attack 多级嵌套） | 用户拍板；tasks/done/task 062.md、STATUS task 062 节 |
| 2026-10-21 | task 063 诊断 → task 064 修复拍板：promote 空场判平引擎 bug 修复（check_knockouts 跨扫描全场空检）；时序语义定案 = 胜利条件②与①同时点（昏厥结算点立即判，换上仍推迟 D-WP2-1）；三组指定单测；事件排序观感债单列不混修 | 用户拍板；tasks/done/task 063.md、tasks/done/task 064.md、rules-reference 附录 A 决议 ✅ 已核 2026-10-21 |
| 2026-10-21 | task 065 盲区归因 → task 066 处置拍板：先 C（A 零采集重训先行 + B 特征 v3 按残余决定）；A 两轮（×3/×2 → ×1.5/×1.25）剂量-响应全单调、\|Δ\| 12.5%→15.9%→18.6% 证伪后拍板**整体收口维持 v2 基线，B 不立项**；残留盲区留档 backlog；加权资产不入库（存档 results/），加权管线 harness 保留 | 用户拍板；tasks/done/task 065.md、tasks/done/task 066.md |
| 2026-10-21 | 后续优先级拍板（066 收口后）：task 067 = 064 修复后复校准先行（新度量地基）→ 卡池 v2 独立线（D3-5）→ M12 残留盲区转触发式处理（不整包重做，v3 不立项维持）→ 事件排序观感债攒批随引擎改动顺手清 | 用户拍板；tasks/task 067.md |
| 2026-10-21 | task 067 D-067-6 MCTS 定点重跑范围：高残留 3 格重跑（赛富豪×苍响 30 / 玛俐×赛富豪 32 / 多龙黑夜×赛富豪 28 旧口径局，2×50×500 种子对齐原格）；低残留 2 格（多龙喷 17 / 猛雷鼓×玛俐 6）不重跑留档，随卡池 v2 整体新口径消解 | 用户拍板；tasks/task 067.md |
| 2026-10-21 | task 068 D-068-1/2 卡池 v2 口径拍板：选池窗口只用 09-16 后（46 场，对齐 standard-2026-09-16 J 标快照）+ Top-9 全新排（覆盖 80.48%；苍响/赛富豪/多龙喷掉出，索罗亚克/火伊布猫头夜鹰/电电虫Box 新入）；v1 封存（D-068-4） | 用户拍板；tasks/done/task 068.md |
| 2026-10-21 | task 069 D-069-1/2 规则决议：力之沙漏「回合结束时」时点 = 检查阶段内状态结算后（本卡结果等价，名义偏差记附录 A）；盖诺赛克特 ACE 锁「使出」= 广义五门类（物品/支援者/竞技场 + 道具附着 + 能量附着） | 用户拍板；tasks/done/task 069.md、rules-reference 附录 A |
| 2026-10-28 | 071 之后路线：受众 = 研究者/备赛（CLI + 文件 + 导出，无产品 GUI）；导出默认双轨（Markdown/HTML + CSV/JSON）；日志 = 精简 B；JEV/LLM 不进 072–075。顺序原为合并 PR #1 → 072 → 073 → 074 → 075。同日改口：072 整段做完再审，实现留在 PR #1，代理不合并。070 闸 3 十五张与 069 附录 A 三条不挡 072 | 用户拍板；`docs/superpowers/specs/2026-10-28-post-071-roadmap-design.md` |
| 2026-10-28 | 072–075 统一审 = 管道验收通过。正式矩阵（code `8a3aecb`，启发式，18000 局）加权 \|Δ\| 18.5%，被两缺口抬高：沙奈朵 IndexError（888，无堆栈、路径未钉）与 N的索罗亚克 `copy_attack` 多级嵌套「暗夜王牌」（858）。二者下一任务修，本 PR 不修。顺序：① 更新 STATUS → ② 提交并合并 PR #1（代理不合并）→ ③ 下一任务再修引擎。残留盲区保留特性使用质量 / play_stadium / end_turn / copy_attack 多级嵌套，并补入 IndexError（沙奈朵） | 用户拍板；STATUS task 072 节 |
| 2026-10-28 | task 076 修正式矩阵两失败：IndexError = 启发式攻击表漏 `grant_attack` 合成招式（能量涡轮）；copy_attack 多级 = 帧栈 + 同 (iid, 招式名) 不再可选（附录 A ✅ 已核，2026-10-28 搜卡核实）。完整 18000 复跑留本机 | 用户拍板下一任务；tasks/done/task 076.md |
| 2026-10-28 | task 076 本机正式复跑（`c436471`，18000 局）失败 0；加权 \|Δ\| 18.5% 仍为启发式策略偏差（最大格沙奈朵 vs N的索罗亚克 +65.6%，sim 96% vs real 30.4%），不是引擎崩溃。真实侧 72/72 与 `v_pairing_players` 全等。owner 授权 STATUS 回写后合并 PR #2 | 用户授权；STATUS task 076 节 |
| 2026-10-28 | 核销 070 闸 3 十五张 + 069 附录 A 三条：owner C 授权助手查资料确认后核销（核销人=助手）。闸 3 十五张全部 PASS；高级球「才可以使用」/裁判「手牌全部」= 同语义异措辞、拆文件正确、gate3 PASS；电电虫洗牌 2 次 = ✅ 已核工程偏差（均匀重洗等价，RNG 多耗 1 次）；虹色因子 / 顽强之心 / types:all ✅。力之沙漏时点与 ACE 锁不重开。不改引擎、不跑矩阵、不引入 JEV/LLM | owner 授权 C；STATUS；rules-reference 附录 A |
