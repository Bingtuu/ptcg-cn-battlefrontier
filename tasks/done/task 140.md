# task 140 · 镜像局默认 50% 口径修复（M14 gate review 缺陷返修）

- 状态：完成
- 关联：四期 PRD v0.3 修订（C2 镜像局口径）；M14 gate 执行记录 `docs/digs/2026-11-15-m14-gate-input.md`；task 123/125（field-pick / matchup-snap）

## 背景

M14 gate Owner review 裁决「工具口径缺陷」：spec v0.2 的「源缺镜像自然剔除」对高份额构筑系统性不利——镜像格（f == deck）在快照中恒缺（10×9=90，无对角格），多龙黑夜（field 份额 23.9%）丢失 ≈14pp 的镜像 50%，纯多龙（2.8%）仅缺 ≈1.7pp；Owner 手算补镜像后排序变为纯多龙 62% / 沙奈朵 58% / 多龙黑夜 55%（黑夜魔灵第 7→第 3）。**不「归因可用」进 M15，修口径后同一条命令复跑，Owner 再给独立 top-3 落判。**

另：Owner 怀疑「收缩做了但 `shrunk` 标志没打上」——主会话实证现行快照 16/16 收缩格 `shrunk: true` 标志在位（n=1 格 winrate 0.5238 = (1·1+20·0.5)/21 收缩值可复算），**无标志 bug，不修**；已在 gate 记录注明。

## 验收标准（测试清单）

1. `assemble_matrix`：源缺对角格时补 (d,d) = 0.5、`source="mirror"`、`n=0`；**源提供对角格时源数据优先**（不被默认覆盖）；
2. `expected_winrate` / `field_pick`：镜像默认格纳入期望（share × 0.5 项在场）；高份额构筑因镜像补齐而期望上移的回归场景入测（Owner 裁决的数值机制固化）；
3. 既有测试随口径修订：手算复现 / 镜像纳入等断言更新（口径变了，断言跟着变；非实现 bug）；
4. `export_matchup_snapshot` 输出含对角格（快照自包含，schema 版本升 2 或显式注明）；
5. 来源构成列不受污染：`source="mirror"` 不计入真实格贡献、不计入缺格/缺格 share；
6. 同一条 field-pick 命令复跑，新排序落 gate 记录；Owner 估算值（62/58/55）交叉核对（方向一致即可，点估计允许小差——MC 与份额归一口径）；
7. 全量 pytest 绿 + ruff 零告警；CHANGELOG 记账。

## 实现要点

- 唯一装配点 `assemble_matrix`（field-pick 与 matchup-snap 共享）——镜像默认在该函数补，快照回喂路径自动继承
- MatchupCell source 词表 + docstring 同步（intl|sim|missing|mirror）
- 统计口径变更已先改 PRD（v0.3），代码与 PRD 同步纪律满足

## 结果与遗留

（2026-11-15 收官）

1. **TDD 红→绿**：3 个新断言先红（手算复现口径更新 / 补格与源优先 / 高份额机制回归）+ 既有 2 测随口径修订；快照 CLI 测试 6→9 格（镜像默认格入快照）。
2. **实现**：`assemble_matrix` 唯一装配点补镜像默认（source="mirror"、n=0、50%），源提供对角格优先；MatchupCell 词表/docstring 同步；field-pick 与 matchup-snap 共享路径自动继承。
3. **同命令复跑**（验收 6）：Dragapult 62.1% / Gardevoir 58.3% / Dragapult Dusknoir 55.1% —— **与 Owner 手算估算（62/58/55）方向与量级全对上**；黑夜魔灵第 7→第 3，登顶率 100/0/0 不变。
4. **来源构成零污染**：mirror 格不计真实格贡献 / 缺格 share / 缺格格数（专项测试）。
5. **快照重导**：100 格自包含（90 非镜像 + 10 镜像默认），回喂一致。
6. **shrunk 标志**：Owner 怀疑未实锤——实证 16/16 收缩格标志在位，无修复（gate 记录注明）。
7. 报告/测试文件 21 绿 + ruff 零告警；全量 pytest 见 STATUS。

**遗留**：gate 待 Owner 复跑后落判（独立 top-3）；Owner 保留意见（纯多龙真实格贡献构成 / 土龙节节建模气味 / 小样本 field 敏感）原样保留在 gate 记录供落判。
