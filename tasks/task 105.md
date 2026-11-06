# task 105 — 对齐窗重验：预注册 + 自动触发管道

- 日期：2026-11-06
- 分支：`task/t105-aligned-recheck`
- 性质：**预注册 + 只读自动管道**（文档 + 脚本；脚本常态输出 WAIT，数据达标自动转 RUN 出判决）
- 动机：task 103 判定「格级外部效度未建立」且唯一复活条件 = 赛制对齐窗（sim 卡快照 standard-2026-09-16 与真实数据同窗）。上游 A1 第一批已落地（2026-11 上旬，池内 30 局，功效不足）。本 task 把「数据达标后做什么」在见数据之前冻结，消除协议漂移空间。

## 1. 触发条件（预注册，先于一切读数）

对齐窗 = `v_tournament_weights.date >= '2026-09-16'`（basis=intl_aligned、master/NULL division），9 池 archetype 两两（镜像剔除、仅 winner_side∈{1,2}）。

- **RUN 门槛**：池内对局总数 **≥ 1,000** 且 **≥ 26 个无向格 n≥20**。
- 10–25 格 n≥20：脚本输出 `EXPLORATORY`（只出点估计+CI，不出判决），人工决定是否重注册。
- <10 格：`WAIT`（当前状态：30 局、最大格 n=7）。

## 2. RUN 态协议（预注册）

1. **真实侧**：对齐窗按有向格聚合真实胜率（口径与 pairings.py 完全一致：v_pairing_players ⋈ v_tournament_weights，权重表与 task 103 审计同式）。
2. **sim 侧**：`results/m13-baseline/full/deviation.json` 的 sim_wr（J 环境自对局，500 局/格，不随真实窗变化）。
3. **主检验**：对齐格上 sim↔real **加权 Pearson**（权重 = real_n），逐格有放回 bootstrap 10,000 次取 95% CI。**唯一主指标**，无多重比较。
4. 次读数（不作判决）：Spearman、对齐窗加权 |Δ| vs 旧窗 |Δ|、逐格对照表。
5. **判决门（D-series，接续 task 103 命名）**：
   | 门 | 判据 | 含义 |
   |---|---|---|
   | R1 | 主检验 CI 下界 > 0 | **效度复活**：格级 sim 在对齐窗有单调信号 → 解除 claims-register 二.1/二.2 禁句中关于对齐窗的部分，启动「对齐窗校准产品线」立项评估 |
   | R2 | CI 含 0 或上界 < 0 | **钉死**：零信号跨赛制对齐窗复现 → 格级外部效度永久关闭（claims register 注明「对齐窗亦验证过」），backlog A1 关闭 |
   | R3 | 触发时格数 10–25 | 只报点估计，不出判决（功效不足声明） |

6. **诚实性条款**：bootstrap 以「无向格对」为抽样单元（36 对含 0 局对也要进抽样框，保持设计不变）；real 值为 0/1 的退化格（全胜/全负且 n<20）降权剔除并记录。

## 3. 实现

- 脚本：`.kimi-code/t105_aligned_recheck.py`——单入口三态：`WAIT` / `EXPLORATORY` / `RUN(判决)`；结果落 `results/t105-aligned-recheck.json`；全部只读（上游 db + m13 包）。
- 复现：`PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 .kimi-code/t105_aligned_recheck.py`
- 上游 db 版本以 `dist/manifest.json` 的 `version`/`data_version` 为准记入结果（A2 双轨落地后 meta 表为旧轨）。

## 4. 当前状态

**WAIT**（2026-11-06 冻结协议时）：池内 30 局、10 格、最大格 n=7。上游继续堆量（169 场 GHIJ 全量 pairings + partial 映射补全）达标后重跑脚本即出判决。
