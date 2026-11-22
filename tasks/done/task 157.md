# task 157 · prep 可信化——合法性/覆盖率必经 + mod-check 批次隔离硬门

- 状态：已收官（2026-11-22：开发完成 + 小型验收通过 + 归档 tasks/done/）
- 关联：task 156（prep/mod-check 产品化——本任务修其静态审查暴露的两个 P0）；task 119（check-deck）/task 131（strict-coverage 门槛）/task 141（装载器事故先例）；Grok 外部评审 ①②（Owner 已评审采纳）

## 目标

把「能装载」与「可用于正式备赛」之间的缺口关掉，两条：

1. **file 臂构筑合法性**：`_load_decklist_file`（改表 decklist 路径）补 `db.validate_deck`（60/同名 4 上限/ACE SPEC 限 1/赛制快照——与 `load_deck` db 臂同口径同调用），违规在第一局模拟前抛错。
2. **mod-check 批次化硬门**：判读只认 prep 登记的实验 ID 批次（不再按名称前缀搜全库）；种子全集 / 两臂版本一致 / 完成状态不过线 = 输出 **INCOMPLETE**，三门只在 COMPLETE 下才可置 ✅。

## 验收标准（测试清单，先测试后实现）

### 合法性 + 覆盖率
- [x] file 臂反例全部在零局跑批前拒绝：59/61 张（现有总数校验保留）、**同名超 4（基本能量豁免）**、**双 ACE SPEC**、含赛制外印刷（validate_deck 违规透传）；db 臂行为零变化（已有 validate_deck，回归锁死）
- [x] 装载告警（warnings）不丢弃：prep 报告含逐实验装载告警段
- [x] prep 默认 strict 覆盖率（无文档非基本能量卡 = 拒绝开跑，零局）；`--no-strict-coverage` 显式逃生（报告头注声明降级）；db 臂对手同样过闸
- [x] 反例用**合成最小库/构造 decklist** 复现，不依赖真实上游库

### 批次隔离 + 完整配对
- [x] **同名两次运行**：同 prep 名跑两轮，判读只取第二轮登记的 ID 批次，第一轮数据零混入
- [x] **两臂共同缺种子**：构造缺 seed 的库 → 判读输出 INCOMPLETE，门不置 ✅
- [x] **重复种子**：同实验同种子两条记录 → 显式报错（拒绝静默覆盖）
- [x] **跨版本混合**：两臂 code_version 或 data_version 不一致 → 显式报错
- [x] **半途中断**：实验 status != done → INCOMPLETE
- [x] 完整小样例：手算可验（沿用 task 156 手算用例），COMPLETE 下三门与手算一致
- [x] 预期种子全集 = seed_start..seed_start+games−1（来自实验定义，非来自实际落库数）

### 全局
- [x] 既有行为零变化：db 臂装载、run/swap-search 等存量命令不动；CLI 前缀模式 mod-check 保留（标注「非批次模式，仅一次性干净库」）
- [x] 全量 pytest 绿 + ruff 零告警；CHANGELOG/STATUS/task 文档落账

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

开发完成（2026-11-22，TDD 三批 RED→GREEN）：

- **file 臂合法性**：`_load_decklist_file` 在 60 张总数校验后调 `db.validate_deck(ids, snapshots('standard')[-1].effective_from, 'standard')`（与 `load_deck` 逐字同口径），违规则 `ValueError("decklist 构筑校验失败: {violations}")`；db 臂 `load_deck` 零改动。
- **prep 装载告警**：run_prep 改 prepare/execute 两步（原 run_experiment 直调拆开），逐实验收集 `prep.warnings` 进报告「装载告警」段。
- **strict 进 prep**：`PrepCfg.strict_coverage: bool = True`；装载后、开跑前对每个实验跑 `side_coverage` × 2 + `strict_violations`，任一违规 `ValueError`（零局）；CLI `--no-strict-coverage` → `strict_coverage=False`，报告头注降级声明 + 违规落告警段（前缀 `[strict 已关闭]`）。
- **批次协议**：`_write_batch_json` 落 `results/prep-<name>/batch.json`（`slugs: {slug: {base_id, mod_id}}` + `expected_seeds: [seed_start, seed_start+games)` + `games/seed_start/code_version/data_version/entry/pool_sha256`）；`mod_check_report` 增 `batch` 参数（与 base_prefix/mod_prefix 互斥）：`_load_batch_arms` 按 ID 取数，校验两臂 code/data version 一致（不一致显式报错）、status=done、种子集 == 预期全集（缺/超 → INCOMPLETE 原因）、重复种子显式报错；**第四门 `complete`**——INCOMPLETE 时 `all_positive/all_significant/zero_giveback` 强制 False，format 显示「不可判定」+ 逐格原因。
- **CLI**：mod-check `--batch`（与前缀互斥，前缀 help 标注「非批次模式，仅一次性干净库」）；prep `--no-strict-coverage`。
- 测试：18 新测全绿（test_experiment.py +5：同口径调用/同名超 4/双 ACE/赛制外透传/总数校验保留；test_prep.py +3：装载告警段+batch 登记/strict 默认拒绝零局/逃生口降级；test_mod_check.py +8：手算 COMPLETE/同名两轮隔离/缺种子 INCOMPLETE/重复种子报错/跨版本报错/中断 INCOMPLETE/缺登记报错/互斥）；既有 t118/t156 测试 fake 注入点跟随 prepare/execute 拆分机械更新（断言不变）。
- 全量 pytest 绿 + ruff 零告警（收官数字见 STATUS.md）。

遗留：无（范围内）。证据固化（game_events 重拷/签名/E2E）归 task 158。
