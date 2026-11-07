# task 110 — 对齐窗重验门槛修订：可达子池口径（修订 task 105 §1 门）

- 日期：2026-11-07
- 分支：`task/t110-gate-amendment`
- 性质：**预注册修订档**（文档先行，判据本档冻结；修订生效前不出任何判决）
- 动机：上游 data_version 4（v20261107.4）落地 GHIJ 收割轮后，task 107 R3「供给约束」的事实前提改变——对齐窗 pairings 供给结构性修复（窗内 221 场 intl_aligned 赛事、45,999 行 pairings、池内去镜像 1,492 局、周供给 ~180–230 局）。但 census 暴露新问题：**Gardevoir 与 Charizard Pidgeot 在对齐窗国际真实环境零出场**，判定池实际只有 7 个构筑 → 无向对上限 C(7,2)=21 < task 105 预注册 RUN 门 ≥26，**原门数学上不可达**（无论再堆多少量）。本档按预注册修订纪律冻结新门。

## 1. 修订内容（唯一改动 = §1 触发条件的 RUN 门）

- **判定池**（动态，每次运行重取）：9 池构筑中在该对齐窗有 ≥1 非镜像对局（winner_side∈{1,2}、basis=intl_aligned、master/NULL division、口径与 pairings.py 一致）者。当前 = {Dragapult Dusknoir, Grimmsnarl Froslass, Raging Bolt Ogerpon, N's Zoroark, Dragapult, Flareon Noctowl, Joltik Box}（7 个；Gardevoir、Charizard Pidgeot 零出场不入判定池）。
- **可达对数** K = C(|判定池|, 2)。当前 K=21。
- **RUN 门（新）**：qualified（无向格 n≥20 数）≥ min(26, ⌈0.85·K⌉) 且池内对局总数 ≥ 1,000。当前即 **≥18 对且 ≥1,000 局**。
  - ⌈0.85·K⌉ 的取整理由（冻结前声明）：要求覆盖可达 meta 的绝大多数交叉格；0 局对不进判决但保持诚实性条款的抽样框设计不变。85% 为常数，不随任何胜率读数调整。
  - |判定池| 回升至 8（K=28）时门 = min(26, 24) = 24；回升至 ≥9 时退化为原 26。公式单向收紧原门、永不放松。
- 三态结构其余部分不变：<10 qualified → `WAIT`；10 ≤ qualified < 门 → `EXPLORATORY`（只报点估计，不出判决）。

## 2. 不修订部分（显式冻结）

task 105 §2 RUN 态协议全不动：真实侧口径、sim 侧 m13 包、**唯一主检验 = 加权 Pearson + 无向格对 bootstrap 10k 95% CI**、R1/R2 判决门（CI 下界>0 → 复活 / 含 0 或上界<0 → 钉死）、次读数、诚实性条款。

## 3. 反操纵声明（修订纪律）

- 本修订的触发事实 = **出场 census（结构量）**，非任何胜率读数。
- 披露：修订起草前主会话已做过一次观测性点估计（n≥20 格 11 个，加权 r≈0.644，加权 MAD≈22.5pp）。该读数**不构成修订依据，更不构成判决**；新门（18/21）不参考该读数。正式判决只能由修订后脚本在 RUN 态产出。
- 若将来再有门级修订，须同样文档先行、以结构量为由、披露已见读数。

## 4. 附加 validity 限定（随判决生效）

真实侧供给来自国际线上周赛人群（TOURNAMENT OF DOOM / Amyverse / Rare Candy Club 等 recurring 周赛），与卡池 v2 定义的 CN 官方赛事人群不同。RUN 态出判决时，报告与 claims register 必须内嵌限定语「对齐窗真实侧 = 国际线上周赛 meta」，与既有宣称边界纪律一致。

## 5. 实现与验收

- 脚本 `.kimi-code/t105_aligned_recheck.py` 按本档改门（判定池动态重取 + 门公式），历史 jsonl 行格式兼容（增列不改旧列）。
- 验收：修订后脚本即时运行必须仍为 `WAIT`（当前 qualified=8 < 10，物理上不可能出判决）；`pytest -q` 全绿 + `ruff check` 零告警（脚本为 .kimi-code harness 无单测，验证 = 实跑 + 门逻辑抽查）。
- 当前状态：**WAIT**（2026-11-07：池内 1,492 局、17/21 对有对局、8 对 n≥20）。cron 值守继续，达标自动转 RUN。
