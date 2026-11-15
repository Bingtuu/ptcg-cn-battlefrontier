# task 137 · v2.x 矩阵重跑 + 选卡器快照刷新

- 状态：完成
- 关联：task 072–076 v2 矩阵管线；task 125 matchup-snap 导出器；task 131 strict-coverage 门槛；task 133/135/136 前置；M14 gate 的数据底座；备赛 P1 goal loop 第 2 环（135/136 之后）

## 目标

10 套 v2.x 池全矩阵重跑 + matchup/field 快照刷新，恢复 sim 口径对当前 meta 的代表性；产出 M14 gate 所需的全部输入（刷新后的 matchup-snap + field 快照），使 gate 在 v2.x 数据上执行。

## 验收标准（测试清单）

1. **矩阵实验定义**：45 无向对（10 套 C(10,2)）× 500 局 = 22,500 局，group_name 归组，种子区间钉死（可复算纪律：实验 id / 种子区间 / 版本 / 数据版本回显 meta）；复用 v2 矩阵实验定义结构，仅池引用换 v2.x；
2. **跑前 strict-coverage 门槛通过**（task 131）：v2.x 十套表内全部阻断卡有 DSL（I 标渗透件由 task 136 覆盖）。**太乐巴戈斯ex 显式分支**（task 131 豁免仅基本能量 / vanilla 异文本 / 纯白板三种，「已知有损豁免」不存在，不得新造）：135 修订时核查刷新表——若含太乐巴戈斯ex 且 task 138 未完成，则 (a) 137 排期以 138 完成为前置，或 (b) 该表所在实验非 strict 跑批并逐格标注 vanilla 有损，处置记入 task 文档（含卡证据：近窗最高名次火伊布系表 mik_moe:711874 含太乐巴戈斯ex×1，`_t1114_flareon.txt:27`）；
3. **跑批零失败**（平 0），结果落新独立结果库（如 `results/t1115-v2x-matrix.db`，不落旧库）；
4. **matchup-snap 重新导出**（`bfsim matchup-snap`，窗口时点元数据 = v2.x 窗 + 限定语头注 + low_confidence 标注）；intl 真实格 n<20 收缩与窗口错位 >28 天告警纪律原样生效；
5. **field 快照刷新**：从上游 stats usage 导 2026-11 窗 field 分布快照（division=master），与 matchup 窗口错位 ≤28 天（C1 纪律）；沿用 `results/field-snap-*.json` 格式；
6. **field-pick 冒烟**：用新 matchup-snap + 新 field 快照跑一次选卡器，输出 10 套排序 + 来源构成列 + 数据充分性标注，限定语三行头注齐全；数值可手算复现（钉种子）；
7. 纯跑批任务：除矩阵实验定义 YAML 与快照产物外零代码变更；若有代码缺口（如池套数硬编码），记录并按需回开任务，不临时绕道；
8. 成本预算：约 1–1.5 小时机时（45 对 × 500 局，多进程），超 2 倍需停下复盘。

## 实现要点

- 矩阵口径与 task 072–076 一致（无向配对、CRN 种子纪律），只对池与窗做修订
- **C1 错位告警读数口径**（预写防误读）：intl 真实格仍是 m13 口径旧窗（2025-04..08），与 2026-11 field 快照错位远超 28 天 → matchup-snap 与 gate 输出将带**常驻错位告警**，这是 intl 供给面的既成事实（task 107），**不是 v2.x 数据事故**；gate 执行时按此口径读数
- 旧 v2 矩阵库与快照封存不动（可追溯纪律）；所有新结论标注 v2.x 口径
- 跑批完成 → 数据底座就绪，移交 Owner 执行 M14 gate（spec §2 gate 判据：top-3 交集非空或记录归因）

## 结果与遗留

（2026-11-15 收官）

1. **矩阵零失败**：45 无向对 × 500 局 = 22,500 局，平 0 失 0，14.6 分钟（16 workers，远低于 2×熔断门）；结果库 `results/t1115-v2x-matrix.db`（种子锚 400000，meta 回显代码/数据版本）。
2. **跑前 coverage 口径**：task 138 落地后 coverage gate 11/11 全绿（验收 2 的联合前置达成）；矩阵装载期三态覆盖率报告无阻断。
3. **偏差包 + matchup-snap**：`bfsim calibration` → `results/t1115-v2x-deviation/`（加权 |Δ| 16.3%，CI 覆盖 15.6%，最大 Δ = 赛富豪土龙节节 vs 沙奈朵 −54.9pp——格级效度未建立是 task 102/103 已定死的结构事实，本批不涉效度宣称）；`matchup-snap-2026-11-15.json` = 90 格 / **0 low_confidence**（第 10 套 en_archetype Gholdengo Dudunsparce 在 intl_aligned 有真实格，缺口路径未触发）。
4. **field 快照刷新**：`field-snap-2026-11.json`（2026-11-01..14、master、decks 口径，与 matchup 窗错位 0 天；10 池覆盖 85.25%）。
5. **field-pick 冒烟**：10 套排序 + MC 分布 + 来源构成列 + 限定语三行头注齐；C1 错位告警按预注册口径在场（intl 真实格为 m13 旧窗 2025 数据 = task 107 供给面既成事实，非 v2.x 事故）；缺格 0。当前排序（仅同模拟器内口径）：Dragapult 60.4% > Gardevoir 52.8% > Charizard Pidgeot 51.6% > N's Zoroark 50.9% > Flareon Noctowl 49.3% > Raging Bolt 45.1% > Dragapult Dusknoir 41.1% > Joltik Box 41.0% > Grimmsnarl 40.7% > Gholdengo Dudunsparce 23.3%。
6. **零代码变更**：仅实验定义 YAML + 快照产物 + 结果库（验收 7）；旧 v2 矩阵库与快照封存不动。

**遗留**：M14 gate 待 Owner 执行（输入包 = `docs/digs/2026-11-15-m14-gate-input.md`）。
