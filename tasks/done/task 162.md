# task 162 · field-snap 探针 newer 判定收紧到合格口径

- 状态：完成
- 关联：task 156（field-snap）/ task 158（签名双判）/ task 161（内容签名）；Grok 外部评审 2026-11-27（探针口径项）

## 背景

Grok 评审指出 + 本机真库实证：`probe_field_freshness` 的 newer 判定用
`_LATEST_TOURNAMENT_SQL`（`MAX(date)` 只过滤 basis+division），**不过滤
`static_weight`/`is_qual`/`is_team`**。task 158 只对齐了 backfill 判定路径
（`qualified_count` 与 `_base_meta` 同口径），newer 路径残留宽口径。

真库后果（2026-11-27 实测）：上游已入库 11-28/29 共 17 条**未来赛事预告行**
（赛事未举办，`static_weight` 全 NULL，永远进不了快照），探针对既有快照
（窗终点 11-15）持续误报 stale/newer——用户可能被误导在场占未真实变化时
重跑全池。同库 11-22 已有 1 场合格赛事（static_weight=2.107），收紧后
newer 仍会正确报出（latest 合格 = 11-22 > 11-15），且日期指向真实新数据。

无漏报风险：未加权新赛事入库时探针静默，上游加权完成后
`qualified_count`/content hash 变化会走 backfill 路径判出。

## 目标

`_LATEST_TOURNAMENT_SQL` 与 `QUALIFIED_WHERE` 单源共享（不抄两份 SQL），
newer 判定 = 上游最新**合格**赛事超出快照窗终点。

## 验收标准（测试清单）

1. 窗外仅新增未加权赛事（`static_weight IS NULL`，master/cn）→ fresh 不误报
2. 窗外仅新增组队赛（`is_team=1`）→ fresh 不误报
3. 窗外仅新增资格赛（`is_qual=1`）→ fresh 不误报
4. 窗外新增合格赛事 → 仍 stale/newer（存量 `test_probe_stale_上游超出窗` 保持绿）
5. 全库无合格赛事 → no_baseline（措辞对齐合格口径）
6. 真库对账：探针 detail 的日期 = 真库合格口径 MAX(date)（当前应为 2026-11-22，
   而非宽口径的 2026-11-29）

## 实现要点

- `field_snap.py`：`_LATEST_TOURNAMENT_SQL` 复用 `QUALIFIED_WHERE`（参数
  `("master", "cn")`），探针执行处传参；no_baseline 措辞与 docstring 同步。
- 只动探针 newest 判定一处；导出、签名、backfill 路径零改动。

## 结果与遗留

- **实现**：`_LATEST_TOURNAMENT_SQL` 复用 `QUALIFIED_WHERE` 单源（f-string
  拼装，参数 `("master", "cn")`）；探针消息/docstring/CLI help 措辞统一为
  「合格赛事」。导出、签名、backfill 路径零改动。
- **TDD**：5 新测（窗外未加权/组队/资格赛不误报 ×3 + 窗外合格赛事仍
  stale/newer 对照 + 全库无合格赛事 no_baseline），红（4 failed，失败原因
  均为宽口径误报）→ 绿（局部 19 passed）。
- **真库对账**（2026-11-27，上游 v_tournament_weights）：旧口径 MAX(date)
  = 2026-11-29（11-28/29 共 17 条未来赛事预告行，static_weight 全 NULL）→
  持续误报 newer；新口径 latest 合格 = 2026-11-22（该日 1 场已加权
  static_weight=2.107）→ 探针报 `[stale] 上游最新合格赛事 2026-11-22 已超出
  快照窗终点 2026-11-15`，exit=3——日期指向真实新数据，预告行不再驱动误报。
- **Grok 评审事实修正**（随本任务留档）：①「上游库 11-21 后停止写入」不成立
  ——fetched_at 显示 2026-11-27 11:56 仍有 18 条新行入库；②「11-21/22 全
  NULL」已过时——11-22 已有 1 场合格（合格场数 19→20）；③探针口径缺陷属实
  （本任务修复）；④「唯一 P0 工程项」言重——真实缺口 = 上游 ~10 条已结束
  赛事待加权（Pokearena 侧）+ 本探针小修（本任务）。
- **遗留**：上游 11-21/22 ~10 条 NULL 加权属 Pokearena 仓库事项，不在本仓；
  探针 stale/newer 现为正确信号（确有 1 场新合格赛事），场窗推进决策归 Owner。
