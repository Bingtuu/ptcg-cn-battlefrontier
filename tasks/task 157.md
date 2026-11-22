# task 157 · prep 可信化——合法性/覆盖率必经 + mod-check 批次隔离硬门

- 状态：待 review（设计冻结后开工）
- 关联：task 156（prep/mod-check 产品化——本任务修其静态审查暴露的两个 P0）；task 119（check-deck）/task 131（strict-coverage 门槛）/task 141（装载器事故先例）；Grok 外部评审 ①②（Owner 已评审采纳）

## 目标

把「能装载」与「可用于正式备赛」之间的缺口关掉，两条：

1. **file 臂构筑合法性**：`_load_decklist_file`（改表 decklist 路径）补 `db.validate_deck`（60/同名 4 上限/ACE SPEC 限 1/赛制快照——与 `load_deck` db 臂同口径同调用），违规在第一局模拟前抛错。
2. **mod-check 批次化硬门**：判读只认 prep 登记的实验 ID 批次（不再按名称前缀搜全库）；种子全集 / 两臂版本一致 / 完成状态不过线 = 输出 **INCOMPLETE**，三门只在 COMPLETE 下才可置 ✅。

## 验收标准（测试清单，先测试后实现）

### 合法性 + 覆盖率
- [ ] file 臂反例全部在零局跑批前拒绝：59/61 张（现有总数校验保留）、**同名超 4（基本能量豁免）**、**双 ACE SPEC**、含赛制外印刷（validate_deck 违规透传）；db 臂行为零变化（已有 validate_deck，回归锁死）
- [ ] 装载告警（warnings）不丢弃：prep 报告含逐实验装载告警段
- [ ] prep 默认 strict 覆盖率（无文档非基本能量卡 = 拒绝开跑，零局）；`--no-strict-coverage` 显式逃生（报告头注声明降级）；db 臂对手同样过闸
- [ ] 反例用**合成最小库/构造 decklist** 复现，不依赖真实上游库

### 批次隔离 + 完整配对
- [ ] **同名两次运行**：同 prep 名跑两轮，判读只取第二轮登记的 ID 批次，第一轮数据零混入
- [ ] **两臂共同缺种子**：构造缺 seed 的库 → 判读输出 INCOMPLETE，门不置 ✅
- [ ] **重复种子**：同实验同种子两条记录 → 显式报错（拒绝静默覆盖）
- [ ] **跨版本混合**：两臂 code_version 或 data_version 不一致 → 显式报错
- [ ] **半途中断**：实验 status != done → INCOMPLETE
- [ ] 完整小样例：手算可验（沿用 task 156 手算用例），COMPLETE 下三门与手算一致
- [ ] 预期种子全集 = seed_start..seed_start+games−1（来自实验定义，非来自实际落库数）

### 全局
- [ ] 既有行为零变化：db 臂装载、run/swap-search 等存量命令不动；CLI 前缀模式 mod-check 保留（标注「非批次模式，仅一次性干净库」）
- [ ] 全量 pytest 绿 + ruff 零告警；CHANGELOG/STATUS/task 文档落账

## 实现要点

- **批次协议**：`run_prep` 收集 `run_experiment` 返回的实验 id → 写 `results/prep-<name>/batch.json`：`{slug: {base_id, mod_id}, expected_seeds: [start, end), games, seed_start, code_version, data_version, entry, pool_sha256}`；`mod_check_report` 增 `batch` 参数（给 batch.json 路径）：按 ID 取 games（废弃 LIKE 路径），校验两臂 code/data version 一致、status=done、种子集 == expected（缺/重都拒）；**verdict 增第四门 `complete`**——INCOMPLETE 时三门强制显示「不可判定」
- **file 臂合法性**：`_load_decklist_file` 收集 ids 后调 `db.validate_deck(ids, snapshots('standard')[-1].effective_from, 'standard')`（与 `load_deck` 逐字同口径）；违规则 ValueError 带 violations 明细
- **strict 进 prep**：装载后、`run_experiment` 前，对每个实验跑 `coverage.strict_violations`（复用 task 131 函数），任一违规拒绝开跑；PrepCfg 增 `strict_coverage: bool = true`，CLI `--no-strict-coverage`
- mod-check CLI 增 `--batch <batch.json>`；与 --base-prefix/--mod-prefix 互斥

## 范围外（显式不做）

- 不重拷 game_events（结果库已有，证据固化归 task 158）
- 不改 run/swap-search/league 存量路径
- 不做后台服务/并发锁（单进程备赛口径不变）

## 结果与遗留

（待填）
