# task 112 · 对齐窗判决值守线（WAIT 态维护 + 触线处置）

- 状态：进行中（值守线；「完成」= RUN 判决产出并归档）
- 关联：task 105（预注册协议）/ task 110（可达子池门修订）/ claims register 守则 5
- 日期：2026-11-13 立项（独立核验评估会话的建议 ③；cron 值守已于本会话重建）

## 目标

维护 task 105/110 对齐窗重验线的周期值守，直到 WAIT 触线自动出 RUN 判决（R1 效度复活 / R2 永久钉死）后收口归档。全程零代码变更：哨兵脚本 `t105_aligned_recheck.py` 与 105 §2 判决协议冻结不动。

## 背景

- 2026-11-07 上游 data_version 4 修复供给断档（窗内 221 场 intl_aligned 赛事）；task 110 将 RUN 门修订为可达子池口径：判定池 = 窗内有非镜像出场的池构筑（动态重取，现 7 套），K = C(7,2) = 21，门 = qualified ≥ min(26, ⌈0.85·K⌉) = **18 对 n≥20 且池内 ≥1,000 局**。
- 普查轨迹（`results/t105-sentinel-history.jsonl`）：11-07 = 8 对 / 1,492 局；**11-13 = 9 对 / 1,520 局**（一周 +1 对、+28 局，斜率下 RUN 预计需数月）。
- cron 值守不跨会话存活（2026-11-13 核验发现此前值守已漂移失效）；本会话已重建：每周二 10:17（id `01M7AKPN20NQK02HS9AP8A5Q7G`）。

## 每周期值守动作

1. 开工先手动补跑哨兵（会话边界纪律）：`.venv/Scripts/python.exe -X utf8 .kimi-code/t105_aligned_recheck.py`（只读；落 `results/t105-aligned-recheck.json` + 历史行）。确认 cron 仍存在，失效则以同表达式重建。
2. **WAIT 态** → 只把 census 增量（pool_games / pairs_n_ge_20 / 判定池 / upstream version）更新进 STATUS 当前焦点段，其余不动。
3. **EXPLORATORY 态**（10–17 对）→ 点估计入 STATUS，不下结论。
4. **RUN 态**（≥18 对且 ≥1,000 局）→ 严格按 task 105 §2 协议执行：加权 Pearson + 无向格对 bootstrap 10k（脚本内已含）；CI 下界 > 0 → R1 效度复活；CI 含 0 / 上界 < 0 → R2 永久钉死。产物：判决 dig 落 `docs/digs/`；STATUS + `docs/claims-register.md` 守则 5 同步；**判决报告必嵌「真实侧 = 国际线上周赛 meta」限定语**。

## 验收标准（收口判据）

1. `results/t105-sentinel-history.jsonl` 每周一行、无断档（会话边界补跑计入）。
2. STATUS 当前焦点段数字与 `results/t105-aligned-recheck.json` 逐字段一致。
3. RUN 判决产出时：判决 dig 存在、bootstrap 10k 可复现、限定语内嵌、claims register 同步——四件齐全本 task 归档 done/。
4. 全程 `ruff check .` 零告警、全量 pytest 绿（应零变化；如出现变化说明越界，立即停手上报）。

## 禁止事项

- 不改 RUN 门公式、不改 105 §2 协议、不提前下结论、不基于 EXPLORATORY 点估计写 claims。
- 不动 Agent / DSL / 引擎 / heuristic。
- 供给萎缩导致回退（判定池缩小、门数学再次不可达）时，按 task 110 修订纪律（文档先行、结构量为唯一理由）另立 task，不在本线内自行改门。

## 结果与遗留

（值守中；当前 WAIT：9/18 对 n≥20、1,520/1,000 局）
