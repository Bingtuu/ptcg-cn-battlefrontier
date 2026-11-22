# task 158 · 探针回填签名 + 备赛证据包 + CLI 端到端小样例（+ 赛后记录模板）

- 状态：已收官（2026-11-22：开发 + 独立复验 + 全量 2179 passed + 1 skipped、ruff 零告警，归档 tasks/done/）
- 关联：task 156（field-snap/prep 产品化）；task 157（batch.json——证据包数据源）；task 105/110（哨兵口径族）；Grok 外部评审 ③④⑤（Owner 已评审：③④采纳、⑤降档文档模板）

## 目标

1. **同窗回填检测**：field 探针从「只比 MAX(date)」升级为「日期 + 合格赛事签名」双判——上游同窗补入有效赛事必须判过期；仅新增被筛除（include_qual=False 口径外）的赛事不误报。
2. **证据包**：prep 产物从「一份 md 报告」升级为可离线追溯的制品目录：输入固化（prep yml / 卡表内容+sha256 / 场快照副本 / 矩阵快照身份）+ 判读导出（md + verdict.json/csv）+ 复算三元组回显（实验定义 sha256 / 代码版本 / 数据版本）。
3. **CLI 端到端小样例**：一条真实经过 CLI → 预检 → 模拟 → SQLite → 报告的合法小实验（≠ 全链路替换既有单测）。
4. **赛后记录模板**（P2 降档）：Markdown/CSV 模板 + 赛后汇总口径（实战与模拟分栏），不做代码、不做 Web UI、不做赛中辅助。

## 验收标准（测试清单）

### 探针签名
- [x] 导出时 meta 落 `sig = {window, n_qualified, data_version}`（n_qualified = 该窗合格赛事数，与 stats_usage 出口 meta.n_tournaments 同口径）
- [x] 同窗补入合格赛事（fixture 重放）→ probe 判 stale 且注明 backfill；MAX(date) 不动也判出
- [x] 同窗仅新增被筛除赛事（junior/团队/qual fixture）→ 仍 fresh
- [x] 数据未变 → fresh；无 sig 的旧快照 → 降级为原日期比对并注明
- [x] 签名计数口径与导出同源（共享一个 qualified-count 查询函数，不抄两份 SQL）

### 证据包
- [x] `results/prep-<name>/` 目录含：report.md（已有）+ inputs/（prep.yml 副本、基线 deck_id + 改表 decklist **内容**+sha256、field-snap 副本、matrix-snap 路径+sha256）+ verdict.json（逐格 + 四门）+ verdict.csv
- [x] 卡表文件事后被改 → 重跑 hash 与证据包不一致可发现（证据包自含 hash，不依赖外部文件）
- [x] 报告头注回显复算三元组：实验定义 sha256 / 代码版本 / 数据版本
- [x] 搬到离线环境（目录整体拷贝）→ 仅凭目录可追溯报告每个数字的来源

### CLI 端到端
- [x] 一条 subprocess 级测试：真实 CLI 入口 → 预检 → 小局数模拟（≤8 局）→ 结果库落库 → 报告/判读产物存在且与直接 API 调用一致
- [x] 首选 `open_jsonl` fixture 后端（无真实上游库依赖，离线可跑）；若 sdk jsonl 覆盖面不足（stats_usage/validate_deck 缺），退化为「pick-only CLI 全链路 + API 级真引擎小样例」，缺口如实落档（不假装覆盖）——**探测结果：覆盖面足（spike 实证），jsonl fixture 落地**；唯一缺口 = 探针裸 SQL 维持 sqlite-only（场数据管道不在 E2E 范围），如实落档
- [x] 串行结果与既有并行纪律不冲突（小样例串行即可，不重复测 workers）

### 赛后模板
- [x] `docs/tournament-log-template.md`：赛事/赛制/卡表版本(hash) + 轮次表（对手构筑/先后手/结果/失误/待练点）+ 赛后汇总（**实战 vs 模拟分栏**：模拟侧引 prep 证据包数字）
- [x] 模板自带一场示例赛事的填好的样例行（演示用法，非真实数据声明）

### 全局
- [x] 全量 pytest 绿 + ruff 零告警；CHANGELOG/STATUS/task 文档落账（**收官：2179 passed + 1 skipped（9m20s）、ruff 零告警**）

## 实现要点

- **签名函数**：`qualified_count(db, date_from, date_to)`（cn/master/口径外剔除，与 stats_usage 同 where 族）放在 `runner/field_snap.py`，导出与探针共用；探针 stale 分支区分 `newer`（MAX 超窗）与 `backfill`（签名不符）两种原因码
- **证据包**：`run_prep` 收尾阶段写 inputs/ + verdict 导出（verdict 数据来自 mod-check ModReport 序列化）；sha256 用 hashlib，小文件直接读字节
- **E2E**：tests/test_prep_e2e.py，subprocess 调 `python -m battlefrontier.cli`；fixture 构造按 sdk jsonl 后端实际覆盖面定（实现期第一步先探测并落档决策）
- 模板纯文档，随本任务交付不入版本控制之外的系统

## 范围外

- 不重拷 game_events / 不做结果库归档打包（结果库为本机资产）
- 不做赛中实时策略辅助、不做 Web UI、不做多用户
- 探针不做常驻服务（周二 cron 值守维持）

## 结果与遗留

开发完成（2026-11-22，TDD 四批 RED→GREEN，11 新测）：

- **探针签名**：`export_field_snap` meta 落 `sig={window, n_qualified, data_version}`；`qualified_count(db, from, to)` 与探针共用（QUALIFIED_WHERE where 族，DISTINCT tournament_id）；`probe_field_freshness` stale 分因 `newer`（latest > win_to）∥ `backfill`（同窗 n_qualified 变化或 `_sig_data_version` 变化；同窗仅新增被筛除赛事 → 计数不变 → fresh 不误报）；无 sig/签名残缺 → 降级纯日期比对（detail 注明）。`_sig_data_version`：sqlite 只读 PRAGMA user_version ∥ jsonl schema_version。
- **证据包**：`_evidence_pack` —— `inputs/`（prep.yml 副本[prep_source 缺省 dump cfg]、decks.json[base deck_id + mod file/sha256]、decklist 内容副本、field-snap 副本、manifest.json[inputs 全文件 sha256 + matrix_snap 路径+sha256]）+ verdict.json（meta 复算三元组 + batch sha256、cells、weights、期望、四门 gates、incomplete_reasons、seed_gaps）+ verdict.csv；报告头注回显「复算三元组：实验定义 sha256=…/代码版本/数据版本」。卡表篡改可发现 = 证据包自含 hash 与事后重算比对（测试覆盖）。
- **后端分派**：`battlefrontier/data/backend.py`（open_backend 目录→jsonl/文件→sqlite；backend_data_version；sqlite PRAGMA 走只读 URI——FR-10 保留）；10 处 open_db 调用点全切换（cli 2 / deck 1 / deck_check 1 / experiment 3 / swap_search 2 / field_snap 1）；`experiment._data_version` 委托 backend_data_version。真实上游 sqlite 行为零变化（路径类型分派）。
- **E2E**：`tests/test_prep_e2e.py` subprocess 真实 CLI（`-m battlefrontier.cli run … --strict-coverage`）→ 8 局落库零失败 → 与直接 API（run_experiment 同定义同种子）逐局一致（seed/winner/is_draw/turns/events_hash 全等）→ `report` 子命令出报告。**后端决策（实现期第一步探测落档）= open_jsonl fixture 可行**：spike 实证 JsonlBackend 覆盖 get_card/search_cards/snapshots/validate_deck 全接口；最小 dist fixture 五件（manifest/cards/sets/relations/legality）固化进 `tests/helpers.py::make_e2e_dist`（CardSchema 必填域全集 spike 逐字段钉过：deck_limit/prize_cards int 不可 None、attacks.effect_text 必填、latest_text_overrides 为 dict 等）。串行口径（小样例不重复测 workers）。E2E 路径不覆盖 field-snap 探针（探针 v_tournament_weights 裸 SQL 维持 sqlite-only，场数据管道不走路径分派以外的口径）——如实落档，非假装覆盖。
- **赛后模板**：`docs/tournament-log-template.md` 纯 docs（赛事信息 + 轮次表 + 赛后汇总实战 vs 模拟分栏——模拟侧引证据包 verdict 读数 + 判读纪律「实战 n=1 不构成对 sim 的验证/证伪」+ 示例行非真实数据声明）。
- 测试：11 新测全绿（test_backend 3：分派/两版 data_version；test_field_snap +5：签名一致/同窗回填 stale/被筛除 fresh/版本变更 stale/无签名降级；test_prep +2：证据包落盘全项/篡改可发现；test_prep_e2e 1）。既有 field_snap export 测试 fake 注入点 open_db→open_backend 机械更新 + _make_upstream 补 v_tournament_weights 表（签名真实计数）。
- 全量 pytest 绿 + ruff 零告警（收官数字见 STATUS.md）。

**独立复验（主会话，2026-11-22）**：真库实测导出发现签名口径偏差——`qualified_count` 初版漏 `static_weight IS NOT NULL` 过滤（真库 41 vs meta.n_tournaments 19，漏计 22 场未加权赛事）；已对齐 `stats_engine._base_meta` 的 n_tournaments where 族逐条件（division master-or-NULL / is_qual=0 / is_team=0 / basis=cn / static_weight IS NOT NULL），真库复测 **sig.n_qualified == meta.n_tournaments == 19 逐位一致**；新增误报防护测试（同窗新增 static_weight NULL 赛事仍 fresh）；fixture 补 is_qual/is_team/static_weight 列。复验后全量重跑绿。

遗留：无（范围内）。探针裸 SQL sqlite-only 为如实落档的覆盖缺口（E2E 不涉场数据管道）。
