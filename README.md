# BattleFrontier（对战开拓区）

> AI 宝可梦卡牌（PTCG 简中环境）对战模拟与卡组强度测试引擎

**BattleFrontier** 让两个 AI 选手在完整的简中 PTCG 规则下自动对战，通过大规模模拟对局回答三类问题：

- **强度**：卡组 A 对抗卡组 B 的胜率是多少？（附置信区间与先后手拆分）
- **策略**：某卡组在某对阵下的最优打法是什么？（从对局决策数据中聚合产出）
- **敏感性**：换掉卡组里的几张卡，胜率变化显著吗？

> ⚠️ 边界：以上数字都是**自对局模拟结果**，不构成真实胜率预测——格级外部效度未建立是定量证实的结构事实（task 102/103）。对外引用前请对照 [claims register](docs/claims-register.md)。

## 快速开始

### 1. 安装

要求 Python 3.12+：

```bash
git clone <本仓库地址>
cd Pokebattle
pip install -e .
```

安装后获得命令行工具 `bfsim`。

### 2. 准备卡牌数据

本项目不自带卡牌数据，需要搭配数据项目 [ptcg-cn-db](https://github.com/Bingtuu/ptcg-cn-db) 使用：

```bash
# 安装数据层 SDK（指向你本机的 ptcg-cn-db 检出）
pip install -e "C:/path/to/ptcg-cn-db"

# 复制配置模板，填写本机的卡牌数据库路径
cp config/battlefrontier.example.yml config/battlefrontier.local.yml
```

`battlefrontier.local.yml` 已被 gitignore，支持 SQLite 直读或 JSONL 导出目录两种数据源。

### 3. 跑第一个实验

实验用一个 YAML 文件定义——对阵双方、AI 类型、局数、随机种子：

```yaml
# my-first-match.yml
name: my-first-match
games: 100            # 对局数
seed_start: 1000      # 随机种子起点（同种子可完整复现每一局）
decks:
  a: {source: db, deck_id: "mik_moe:644634"}   # 数据层中的赛事卡组 id
  b: {source: db, deck_id: "mik_moe:650353"}
agents:
  a: {type: heuristic}   # 启发式 AI（内置）
  b: {type: random}      # 随机 AI（内置，常用作对照）
  # 也可用 MCTS：{type: mcts, params: {worlds: 2, iterations: 50}}
  # （多世界 determinized UCT；迭代预算而非墙钟，同种子仍可复现——
  #   注意单局成本约两分钟/进程级，适合定点分析而非大批量）
  # 或蒸馏策略学生：{type: distilled, params: {policy_path: models/policy-m12-v2.json}}
  # （MCTS 行为蒸馏产物，~0.06s/局，定位「分钟级粗筛」而非精排）
```

运行（`--workers` 开启多进程并行，结果与串行逐局一致）：

```bash
bfsim run my-first-match.yml --workers 4
```

```
实验 #1「my-first-match」完成：100 局 A胜 65 / B胜 35 / 平 0 / 失败 0（结果库 results/battlefrontier-results.db）
数据版本 2026-07-16 (user_version=13)；种子区间 1000..1099
```

更多示例见 `experiments/` 目录。

### 4. 查看报告

```bash
bfsim report 1              # 1 = 实验 id（run 完成时会打印）
bfsim report 1 --decisions  # 追加「关键决策聚合」分节：每张卡的选择分布与对应胜率
bfsim report 1 --mcts-consider  # 追加 MCTS 决策分析：行动类别访问份额 / 高熵决策点 / 置信×胜率
bfsim report 1 --autopsy  # 追加败局解剖：终局类型 × 死亡回合分桶（≤6/7–9/10–12/13–15/>15）+ 每桶抽样回放包
```

```
实验 #1「my-first-match」胜率报告
meta：种子区间 1000..1099 / 代码 d084e13 / 数据 2026-07-16 / 局数 100
完成 100 局（决定局 100，平 0，失败 0），平均回合 10.4
A 胜 65 / B 胜 35 —— A 胜率 65.0%（Wilson 95% CI 55.3%..73.6%，分母=决定局）
先攻时 A 胜率 70.7%（CI 57.7%..81.5%）
后攻时 A 胜率 61.0%（CI 44.5%..75.4%）
```

### 5. 换卡敏感性分析

在实验定义里加 `variants`，一次跑出 baseline 与若干变体（同种子区间配对可比）：

```yaml
variants:
  # 对照组：A 方 2 反击捕捉器 → 2 巢穴球（卡组保持 60 张）
  - name: swap-catcher-to-nestball
    swaps:
      - {side: a, out: 反击捕捉器, out_count: 2, in: 巢穴球, in_count: 2}
```

```bash
bfsim run with-variants.yml --workers 4        # 自动依次跑 baseline + 各变体
bfsim sensitivity 1 2                          # baseline vs 变体并排对比
```

报告给出每个变体的胜率变化（ΔWR）、95% 置信区间与显著性检验（两比例 z 检验）。

### 5.5 备赛三场景（导入卡表 / 假想敌 / 换卡估算）

**场景 1：导入自己的卡表。** 写一个 txt（每行「张数 卡名」，满 60 张；卡名可加 `[card_id]` 指定印刷，防止同名多印刷时落到无效果印刷——task 118）：

```text
# my-deck.txt
4 多龙奇
3 多龙巴鲁托ex
2 高级球 [30thC-101]
1 巢穴球 [CSVH1C-043]
# …凑满 60 张
```

```yaml
decks:
  a: {source: file, path: my-deck.txt}
```

写完卡表先跑预检（秒级、零跑批：60 张校验 / 卡名与印刷命中 / DSL 覆盖状态）：

```bash
bfsim check-deck my-deck.txt
```

`bfsim run` 开跑前默认输出每个参赛卡组的 DSL 覆盖率报告（覆盖 / vanilla 异文本 / 无文档三态 + 豁免细分）；`--strict-coverage` 时存在「无文档且非豁免」（非基本能量、非纯白板卡面）卡即拒绝开跑（零局跑批），报错指明卡组侧与卡名。

**场景 2：指定假想敌。** `decks.a` / `decks.b` 完全独立，敌方可以是 db 赛事卡组（`deck_id`）、另一个 file 卡表，或用 `matrix` 段对整池自动展开全部配对（见 §6）。

**场景 3：估算换卡的胜率影响。** 加 `variants` 段（换入卡建议带 `in_id` 指定覆盖印刷），一次跑出 baseline + 各变体（同种子 CRN 成对）：

```yaml
variants:
  - name: 多龙奇减一换摔角鹰人
    swaps:
      - {side: a, out: 多龙奇, out_count: 1, in: 摔角鹰人, in_count: 1, in_id: CSV1C-079}
```

```bash
bfsim run my-swap.yml --workers 16 --results results/my-swap.db
bfsim sensitivity 1 2 --results results/my-swap.db --out results/my-swap
```

**功效口径（task 113/117 实证）**：500 局 CRN 的 CI 半宽 ≈±6pp（±2pp 级效应判不动）；**2,000 局口径 CI 半宽 ≈±3pp，≥3pp 效应可分辨**——定量判断请用 2,000 局以上。读数纪律：阴性对照（机制惰性卡互换）验噪声底；「1-of 卡 = 边缘」的先验不成立（task 117 反例），1-of 互换读数按探针解读。全部结论 = 同模拟器内敏感性，不构成真实预测。

**场景 4：不知道换哪张？换卡搜索器自动扫（task 130）。** 给一个对手，自动从邻近卡组高频单卡生成候选、按「DSL 覆盖 → 赛制 → 60 张结构」过滤，两阶段（低局数筛选 → CRN 成对确认 + Bonferroni/BH 校正）排序输出候选刀位：

```bash
bfsim swap-search --deck <我方 deck_id> --vs <假想敌 deck_id> --budget 73000 --workers 8
```

方法论与判据口径见 `docs/digs/2026-11-14-deck-swap-search-design.md`；演示档对 ±2pp 级效应排序功效有限（诚实声明），定量结论用 2,000 局确认档。

### 6. matchup 矩阵与校准（M6）

实验定义改用 `matrix` 段，即可对卡组池自动展开全部无向配对（镜像不打）：

```yaml
# my-matrix.yml
name: my-matrix
seed_start: 100000
matrix:
  pool: config/target-pool.v1.yml   # 卡组池（9 套 → 36 个配对）
  games_per_pair: 500               # 每配对局数
agents:
  a: {type: heuristic}
  b: {type: heuristic}
```

```bash
bfsim run my-matrix.yml --workers 8         # 自动逐配对跑批，统一分组落库
bfsim calibration my-matrix.yml             # 模拟 vs 真实赛事 matchup 偏差表
```

偏差表逐格给出模拟胜率（含置信区间）与真实赛事胜率的差值 Δ，按 |Δ| 降序，并附加权平均 |Δ| 等汇总——用于校准模拟与真实环境的偏差。

### 7. 启发式参数自调优

`bfsim tune` 对启发式 AI 的决策参数（评分权重 / 决策开关）做坐标下降搜索：候选参数 vs 默认参数在训练对阵集上配对对局，逐维采纳显著提升（>噪声门槛）的取值：

```bash
bfsim tune experiments/tune-smoke.example.yml --workers 4
```

评估全程走与 `bfsim run` 相同的确定性路径（公共随机数种子协议，跨候选共享种子区间降方差）；搜索过程不产生正式结果，轨迹逐次评估落 `results/tune-<名>.jsonl`（含采纳历史与逐维敏感性）。搜索到的参数是否回写为默认值需人工裁决，不在工具内自动执行。

### 8. 校验卡牌定义

每张有效果的卡牌由 `cards/` 下一个 YAML 文件定义（引擎不认识任何具体卡牌，全部行为由数据驱动）。新增或修改卡牌定义后校验：

```bash
bfsim dsl-check cards/博士的研究.yml            # 结构与词法校验
bfsim dsl-check cards/*.yml --db <卡牌数据库>   # 追加校验：卡牌存在、文本一致、赛制合法
```

### 9. 赛事选卡（field-pick，task 123）

给定目标 field 分布（使用率快照 JSON，来自数据层 `stats usage` 出口），对卡池内候选卡组按「期望胜率 = Σ share×matchup」排序，matchup 矩阵三层合成：intl 窗真实格 / sim 同口径补全 / 缺口格标 `low_confidence`：

```bash
bfsim field-pick --field results/field-snap-2026-10.json \
  --pool config/target-pool.v2.yml \
  --intl-db "C:/path/to/ptcg-cn.db" \
  --from 2026-09-16 --to 2026-11-14
```

输出含 9 池排序、期望胜率分布（钉种子蒙特卡洛 Dirichlet 抖动）、每行「真实格贡献%」来源构成、n<20 经验贝叶斯收缩、field 快照与 intl 窗错位 >28 天告警，以及限定语头注。定位 = 「给定 field 分布的卡组选择参考」，不是胜率预测。

matchup 快照可一键导出并回喂（task 125，格值与内联装配逐格一致）：

```bash
bfsim matchup-snap --pool config/target-pool.v2.yml --intl-db <db> --from 2026-09-16 --to 2026-11-14 --out snap.json
bfsim field-pick --field <snap.json> --pool config/target-pool.v2.yml --matrix-snap snap.json
```

### 10. 备赛编排（prep / field-snap / mod-check，task 156–164）

一场比赛的端到端备赛流程一键编排（场刷新 → field-pick → 报名卡组 × 池内全对手成对跑批 → 批次判读 + 证据包 → 统一报告）：

```bash
bfsim field-snap --probe --snap results/field-snap-<旧>.json   # 就绪探针：退出码 0=新鲜 / 3=有新数据（签名双判 newer/backfill + 合格行内容签名）
bfsim prep experiments/prep.example.yml --workers 16           # 全量（场刷新 + 选卡 + 成对跑批 + 判读 + 证据包）
bfsim prep experiments/prep.example.yml --pick-only            # 只跑场刷新 + field-pick（零对局）
bfsim mod-check --results <db> --batch results/prep-<名>/batch.json \
  --field <snap.json> --pool config/target-pool.v2.yml --entry <中文名> \
  [--family-size M]   # 单独判读：按 prep 登记的实验 ID 取数（同名重跑零混入）+ 完整性第四门
```

prep yml 能力面（task 157–161）：`entry.deck_id`（基线表）+ `entry.modified`（改表 decklist）+ `opponent_builds`（对手额外构筑——逐 build 判读、最劣 build 保守门、期望 = 各 build 等权均值）+ `family_size`（扫描 M 个候选改表批时的 Bonferroni α/M 校正）+ strict 覆盖率默认开（`--no-strict-coverage` 显式逃生）。

纪律由命令固化（不靠记忆）：实验名 `{prep名}-{arm}-vs-{slug}`（额外构筑 `~bN` 后缀）同名后缀配对、同种子域 = 成对 CRN、报名卡组恒 a 侧；判读三门（全正/全显著/零回吐）+ 批次完整性第四门（INCOMPLETE 时三门「不可判定」）；报告头注限定语必嵌（登顶率 ≠ 夺冠概率、改表增益 = sim 口径），并附 Bo3 比赛胜率与瑞士轮出线概率的赛制口径换算（解析派生、简化口径注记）。

证据包（task 158/161）：判读落 `results/prep-<名>/` = inputs/（定义副本 + **开跑前冻结**的卡表内容+sha256——按 `{键}__{原名}` 落盘防同名覆盖 + 场快照副本 + 矩阵快照身份 + manifest 自含 hash）+ verdict.json/csv（逐格 + 四门 + 扫描族 meta）+ batch.json（实验 ID 批次 + 预期种子全集 + 两臂版本）——目录整体拷走即可离线复核每个数字来源，卡表事后篡改可发现；无改表臂（base 模式）同样按 ID 批次取数，INCOMPLETE 不出完整基线结论。

**实战全流程**（task 163 全链路实证样板，新场窗 2026-11-01..11-22）：

1. **数据就绪**：`bfsim field-snap --probe --snap <旧快照>`——探针按**合格口径**（master / 非组队 / 非 qual / 已加权）报 newer/backfill（task 162），未加权或预告赛事不误报；探针不动就不跑批。
2. **场快照**：`bfsim field-snap --from <起> --to <止> --out results/field-snap-<日期>.json`——meta 自含签名，`sig.n_qualified` 与上游直查对账。
3. **选卡**：`bfsim field-pick --field <快照> --pool <池> --matrix-snap <矩阵快照>`（池版本不变则矩阵快照复用，零对局）——期望胜率 + 登顶率排序是**输入不是判决**：结合历史判读资产（已有改表验证）与风险读数（劣势对局）拍板，理由成文。
4. **prep 跑批**：每候选一个 prep yml——首选无改表资产走 base-only，带预验证改表走 paired；`seed_start` 与全部历史不重叠（`grep -rhoE "seed_start: [0-9]+" experiments/ | sort -u` 查重），`family_size` 诚实口径（单一预注册改表 = 1，扫描 M 个候选 = M）。
5. **判读**：报告自带四门（全正 / 全显著 / 零回吐 / COMPLETE）+ 池内条件期望 + Bo3/瑞士轮换算；门是保守口径——字面未过 ≠ 方向错误，逐格 Δ/p 与机制读数一并看（例：噪声级回吐格不否定整体方向，但按纪律不自动采纳）。
6. **证据包核验**：`results/prep-<名>/inputs/` 全文件 sha256 重算对 manifest；复算三元组（实验定义 sha256 / 代码版本 / 数据版本）在 verdict meta 回显。

实证数字（task 163/164，sim 口径不构成真实胜率预测）：首选多龙巴鲁托 base 池内条件期望 77.9%（20,000 局零失败）；备选沙奈朵两刀改表新场头下维持成立（+4.0pp，全显著门 10/10→9/10 降档）；ACE SPEC 槽位「不公印章 → 新冲天能量」+2.7pp 方向一致但未过保守门 → 不自动采纳。完整流程文档（本节移植源，含逐格判读表）：[docs/digs/2026-11-27-t163-prep-walkthrough.md](docs/digs/2026-11-27-t163-prep-walkthrough.md)。

## 评估与验证方法

一次完整的「评估/测试」工作流（备赛研究实证口径，2026-11-14）：

1. **模拟对战**：实验 YAML 定义对阵 + AI 类型 + 局数 + 种子；`bfsim run` 落结果库（每局全量事件流入 `game_events` 表，供回放与挖掘）。
2. **跑前体检**：`bfsim check-deck` 预检卡表（60 张校验 / 印刷命中 / DSL 覆盖状态）——无 DSL 文档的卡按无效果（vanilla）结算，预检会明示。
3. **统计验证（换卡/对比）**：变体与基线**同种子区间成对**（CRN，公共随机数）——同代码版本 + 同数据版本 + 同对手 + 同种子下，数值差异只能来自被改的卡表；定量口径 2,000 局（CI 半宽 ≈±3pp，≥3pp 效应可分辨，task 113/117 实证）。配对读数用符号检验/McNemar（只看翻转局，比独立 CI 对比省 4 倍方差）。
4. **机制验证**：数字之外要求事件流解释——从 `game_events` 挖败因（如「败局中核心打手零出手占比」「首杀归属」「终局原因分布」），换卡结论须与败因主线自洽才算 actionable（例：加保护件 ↔ 核心存活率上升）。
5. **复现核验**：同种子重跑基线应逐局一致；报告 meta 回显代码 hash / 数据版本 / 种子区间，数字可原样重放。
6. **归因边界**：上述数字 = 卡表 + AI 策略适应的**联合效应**（agent 会对新卡改变打法），不分离纯卡牌因果；sim 数字不外推真实（格级 sim↔real 相关 ≈ 0，task 102/103），真实侧仅 intl 对局级数据可定性旁证。

开发自检（提交前必过）：

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m pytest -q
.venv/Scripts/ruff.exe check .
```


## 设计理念

- **卡牌效果即数据**：每张卡做什么全部写在 YAML 里，由解释器执行；规则引擎只负责回合流程、伤害、胜负等骨架，对卡牌内容零硬编码。
- **完全可复现**：所有随机（洗牌、掷币、抽牌）走单一随机源——同一个实验定义 + 同一段种子，重跑结果逐局一致，并行与串行一致。
- **AI 接口统一**：`observe(可见状态, 合法行动) -> 行动`。合法行动由引擎枚举，AI 永远不会违规操作；启发式、蒙特卡洛树搜索（MCTS）、MCTS 行为蒸馏学生（distilled，均已实现）、强化学习（远期）可互换、可混编对照。
- **结果独立存放**：模拟结果写入独立的 SQLite 结果库，卡牌数据库始终只读。

## 项目状态

**当前口径（2026-11-28）**：产品定位已收窄并钉死为「**对局模拟 + 决策分析工具**」——模拟胜率是**自对局结果，不构成真实胜率预测**（v1/v2 双池格级 sim↔real 相关 ≈ 0，跨池 + 跨窗 + 低混因子图稳健，task 102/103 定量关闭）；对外宣称边界见 [claims register](docs/claims-register.md)（两层宣称 + 三态复活条件 + 使用守则，报告/校准/敏感性输出已内嵌限定语）。证据边界内全部路径闭环：

- **validity 线终局**（097–107）：MCTS 预算 no-go 封顶（27h/600 局）；窄刀时代收官（088–101，16 大格归因全闭环）；报告层单调校准证伪（102）；赛制混因排除（103，低混因子图 12 格 Pearson −0.010）；对齐窗重验 R3「不可验证（供给约束）」（105→107：上游 2026 年起 GHI 赛事 pairings 结构性断档，预注册 RUN 协议 + 双 sentinel 值守保留）。
- **对齐窗门槛修订**（110）：上游 data_version 4 落地 GHIJ 收割轮后供给结构性修复（窗内 221 场 intl_aligned 赛事、周供给 ~200 局），但 Gardevoir / Charizard Pidgeot 在对齐窗零出场、判定池上限 21 对 → 原 RUN 门（≥26）数学不可达；修订为可达子池口径（判定池动态、门 = min(26,⌈0.85K⌉) = 现 18 对 n≥20 且 ≥1,000 局），105 §2 判决协议不动，附带「真实侧 = 国际线上周赛 meta」限定语。
- **换卡敏感性正式资产**（113/115）：首个资产落地（多龙黑夜魔灵 1×3 扫描，预注册 5 门含阴性对照 CI 覆盖 0）；swap `in_id` 印刷级换卡支持（换入卡印刷可控、防 vanilla 静默退化）；500 局口径功效边缘（±2pp 判不动）已实证，定量排序扩容在 task 117。
- **使用便利性 + 选卡器**（118–123）：decklist 印刷级行 / check-deck 预检 / 盘面快照回放 / agent_explain 决策理由 / 换卡森林图；**M14 首任务收官**：metamages 式选卡器 `bfsim field-pick`（真实格收缩 + 来源构成 + 限定语头注，spec v0.2）。
- **核验与诚实性收口**（111/114）：task 102「无向 36 对」预检数勘误（口径未存档不可复现，权威口径 = 有向 72 格 + 判决 JSON）；`format_sensitivity` 补 sim 解释限定语（claims register 守则 1 遗留缺口）。
- **引擎与观测层收官**（108）：事件序观感债修复（招式效果窗口内昏厥/拿奖事件滞后到链收尾入流，replay 抽查 20/20 四指标等价 + 排水内层帧漏洞修复）。
- **M12 残留盲区清零**（109）：use_ability / play_stadium / end_turn 三盲区预注册诊断预检全部关闭（教师强信号 lift 均 ≤ 0——use_ability 甚至 −8.5pp 反向；end_turn 与 066 低上限结论互证）。
- **备赛编排线收官**（156–164，2026-11-28）：`bfsim prep / field-snap（含就绪探针）/ mod-check` 三命令 + 批次隔离协议（batch.json 按实验 ID 取数，paired/base 双模式）+ 证据包（开跑前冻结卡表 + 自含 hash，篡改可发现）+ 对手多构筑分布（最劣 build 保守门）+ 扫描族 Bonferroni 校正 + Bo3/瑞士轮赛制换算 + 探针内容签名与合格口径 newer 判定（162）；赛后记录模板 `docs/tournament-log-template.md`。Grok 两轮外部评审 9 条建议全闭环。**全流程实战演练收官**（163）：新场窗 11-01..11-22（合格 20 场）下自主选卡全链路走通——首选多龙巴鲁托（field-pick 三期连续第一、base 池内条件期望 77.9%）、备选沙奈朵两刀改表维持成立（+4.0pp，全显著门降档），prep 60,000 局零失败、证据包 hash 全核验；ACE SPEC 槽位评估（164）：不公印章 → 新冲天能量 +2.7pp 方向一致但保守门未过，不自动采纳。下一步 = 12 月新窗 v3 池评估（task 154，待上游加权落地）+ 报名决策归牌手。

**度量地基**：`results/m13-baseline/` 三份双轨偏差包（full/development/validation，72/72 格 `sim_failed=0`，串行=并行 100/100）；启发式加权 |Δ| 15.0%–18.1% 为**自对局结构度量**，非精度指标。全量 **2206 测试绿** + ruff 零告警；DSL 定义库 160 份（v2.x+ 池 11 套零缺口——2026-11-15 定向补池：赛富豪纯构筑第 11 套 + 4 卡引擎扩展，近窗覆盖 85.25%→field 快照口径，task 135/136/138/139/152）；四类 AI（启发式 / 随机 / MCTS / 蒸馏学生）+ 学得评估器与蒸馏模型资产 `models/`。

**待触发（值守线 task 112）**：t105 哨兵 + cron 周期普查（当前 WAIT：9/18 对 n≥20、池内 1,520 局），达标（≥18 对且 ≥1,000 局）即自动出 RUN 判决（R1 解禁 / R2 钉死）；判决报告必嵌「真实侧 = 国际线上周赛 meta」限定语。新方向立项待 Owner 拍板。

**历史脉络（当前口径以上段为准）**：一期 M1–M6（2026-10-03）；二期 M7–M10 收官（2026-10-05，MCTS 落地 + M10 加权 |Δ| 9.7%）；其后引擎性能优化（MCTS 成本 −38.5%）、全库 code review 闭环、MCTS 信息泄漏修复与决策分析上线（task 037–042）；方向 B 启发式参数自调优收官（045–047）；**三期 M11–M12 收官**（2026-10-21）：M11 学得评估器双锚达成，M12 蒸馏终判部分达成收口（D3-7，学生定位「分钟级粗筛」）+ 063/064 promote 空场判平修复 + 065/066 盲区归因与处置证伪 + 067 复校准地基 9.715%；**卡池 v2 锁定**（068，WUR 覆盖 80.5%）+ 069/070/071 引擎扩展两批与 DSL 缺口清零（134 份）；M13 校准地基（094–096）→ M14 结构归因 no-go（097）→ 098–101 决策差异挖掘与窄刀证伪收官 → 102/103 格级外部效度零信号钉死（2026-11-02/03）→ 104 claims register → 105–107 对齐窗线终局 → 108 事件序观感债修复 → 109 M12 盲区触发式闭环 → 110 对齐窗门槛修订（上游供给修复后，2026-11-07）。详细逐日进展见 [STATUS.md](STATUS.md)。

## ⚖️ 合规声明

本项目与 Nintendo、The Pokémon Company、宝可梦（上海）**无任何隶属或背书关系**。卡面文本与卡牌数据版权归宝可梦（上海）/ The Pokémon Company 所有；本项目不采集、不存储、不分发卡图与卡牌数据，仅限本地研究与工具自用。

## 📄 License

代码与文档基于 MIT License 发布（卡牌数据版权见上方声明，不在许可范围内）。
