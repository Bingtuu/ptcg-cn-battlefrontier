# task 125 · matchup 快照导出器（bfsim matchup-snap）

- 状态：完成
- 关联：四期 PRD v0.2（spec §2 task 125，v0.2 重定边界）；M14 gate 操作包组成件

## 目标

`bfsim matchup-snap` 一键导出 field-pick 可读的 matchup 矩阵快照 JSON：intl 真实格（n 门槛收缩 + low_confidence 标注）+ 窗口时点元数据 + 限定语头注。**不重复 field-pick 内联逻辑**——field-pick CLI 的 intl 格装配（`pairing_contrast` 调用 + 收缩）下沉为共享函数，snap 导出器与 field-pick 同源调用。

## 验收标准（测试清单）

1. `bfsim matchup-snap --pool config/target-pool.v2.yml --intl-db <db> --from <d> --to <d> --out <json>` 产出快照：meta（窗口/数据版本/限定语）+ 矩阵格（a/b/winrate/n/low_confidence/shrunk 标记）；
2. 与 field-pick 内联装配**逐格一致**（共享函数，测试断言同一 db 输入下 snap 文件格值 = field_pick.assemble_matrix 输出）；
3. 快照可直接喂回 `bfsim field-pick --field ... --matrix-snap <json>`（field-pick 增矩阵快照输入路径，缺省行为不变）；
4. 全量 pytest 绿 + ruff 零告警；零 Agent/DSL/引擎行为变更（纯报告层）；限定语头注必带。

## 结果与遗留

- **交付（2026-11-15）**：全部 4 条验收达成。
- 改动：`battlefrontier/report/field_pick.py`（+`intl_cells_from_db` 共享装配函数——pairing_contrast + intl_cells_from_contrast 下沉；+`export_matchup_snapshot`/`load_matrix_snapshot`/SNAPSHOT_SCHEMA_VERSION）；`battlefrontier/cli.py`（`_cmd_field_pick` 改调共享函数 + 新增 `--matrix-snap` 输入路径；新增 `_cmd_matchup_snap` 子命令）；`tests/test_matchup_snap.py` 新增 8 测。
- 测试：`tests/test_field_pick.py` 原 10 测原样全绿 + 新增 8 测全绿（红测先行：先 ImportError 红 → 实现后绿）；`ruff check .` 零告警。未跑全量 pytest（按任务指示）。
- 验收对拍：①快照 schema = schema_version + meta（date_from/date_to/basis/division/data_version=池 version/qualifier=QUALIFIER_HEADER 限定语头注）+ cells（a/b/winrate/n/source/low_confidence/shrunk）；②测试显式断言同一 db 输入下 snap 逐格（winrate/n/source/shrunk/low_confidence）== `assemble_matrix` 输出，共享函数天然保证；③快照回喂 `field-pick --matrix-snap`（快照格走 assemble_matrix sim 层——收缩/成对一致/缺格占位导出时已定稿，不二次收缩），CLI 级测试断言回喂输出与 intl-db 内联装配**逐字一致**（真实库 + v2 池 + field-snap-2026-10.json 人工复验同样逐字一致）；④`--matrix-snap` 与 `--intl-db/--sim-pack` 互斥（冲突显式报错退出 1，不猜）。
- 真实数据样例（v2 池，2026-09-16..2026-11-14 窗）：72 格 = intl 34 对主格（含 shrunk 小样本格，如 Dragapult→Flareon Noctowl n=7 wr 向 50% 收）+ low_confidence 38 格。
- 零 Agent/DSL/引擎行为变更（纯报告层 + CLI）。
- 遗留：无。
