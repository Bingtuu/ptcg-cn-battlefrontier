# task 158 · 探针回填签名 + 备赛证据包 + CLI 端到端小样例（+ 赛后记录模板）

- 状态：待 review（设计冻结后开工；须在 task 157 之后——证据包固化 batch.json 格式依赖 157）
- 关联：task 156（field-snap/prep 产品化）；task 157（batch.json——证据包数据源）；task 105/110（哨兵口径族）；Grok 外部评审 ③④⑤（Owner 已评审：③④采纳、⑤降档文档模板）

## 目标

1. **同窗回填检测**：field 探针从「只比 MAX(date)」升级为「日期 + 合格赛事签名」双判——上游同窗补入有效赛事必须判过期；仅新增被筛除（include_qual=False 口径外）的赛事不误报。
2. **证据包**：prep 产物从「一份 md 报告」升级为可离线追溯的制品目录：输入固化（prep yml / 卡表内容+sha256 / 场快照副本 / 矩阵快照身份）+ 判读导出（md + verdict.json/csv）+ 复算三元组回显（实验定义 sha256 / 代码版本 / 数据版本）。
3. **CLI 端到端小样例**：一条真实经过 CLI → 预检 → 模拟 → SQLite → 报告的合法小实验（≠ 全链路替换既有单测）。
4. **赛后记录模板**（P2 降档）：Markdown/CSV 模板 + 赛后汇总口径（实战与模拟分栏），不做代码、不做 Web UI、不做赛中辅助。

## 验收标准（测试清单）

### 探针签名
- [ ] 导出时 meta 落 `sig = {window, n_qualified, data_version}`（n_qualified = 该窗合格赛事数，与 stats_usage 出口 meta.n_tournaments 同口径）
- [ ] 同窗补入合格赛事（fixture 重放）→ probe 判 stale 且注明 backfill；MAX(date) 不动也判出
- [ ] 同窗仅新增被筛除赛事（junior/团队/qual fixture）→ 仍 fresh
- [ ] 数据未变 → fresh；无 sig 的旧快照 → 降级为原日期比对并注明
- [ ] 签名计数口径与导出同源（共享一个 qualified-count 查询函数，不抄两份 SQL）

### 证据包
- [ ] `results/prep-<name>/` 目录含：report.md（已有）+ inputs/（prep.yml 副本、基线 deck_id + 改表 decklist **内容**+sha256、field-snap 副本、matrix-snap 路径+sha256）+ verdict.json（逐格 + 四门）+ verdict.csv
- [ ] 卡表文件事后被改 → 重跑 hash 与证据包不一致可发现（证据包自含 hash，不依赖外部文件）
- [ ] 报告头注回显复算三元组：实验定义 sha256 / 代码版本 / 数据版本
- [ ] 搬到离线环境（目录整体拷贝）→ 仅凭目录可追溯报告每个数字的来源

### CLI 端到端
- [ ] 一条 subprocess 级测试：真实 CLI 入口 → 预检 → 小局数模拟（≤8 局）→ 结果库落库 → 报告/判读产物存在且与直接 API 调用一致
- [ ] 首选 `open_jsonl` fixture 后端（无真实上游库依赖，离线可跑）；若 sdk jsonl 覆盖面不足（stats_usage/validate_deck 缺），退化为「pick-only CLI 全链路 + API 级真引擎小样例」，缺口如实落档（不假装覆盖）
- [ ] 串行结果与既有并行纪律不冲突（小样例串行即可，不重复测 workers）

### 赛后模板
- [ ] `docs/tournament-log-template.md`：赛事/赛制/卡表版本(hash) + 轮次表（对手构筑/先后手/结果/失误/待练点）+ 赛后汇总（**实战 vs 模拟分栏**：模拟侧引 prep 证据包数字）
- [ ] 模板自带一场示例赛事的填好的样例行（演示用法，非真实数据声明）

### 全局
- [ ] 全量 pytest 绿 + ruff 零告警；CHANGELOG/STATUS/task 文档落账

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

（待填）
