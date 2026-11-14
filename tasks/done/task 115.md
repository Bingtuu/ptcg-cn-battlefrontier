# task 115 · swap `in_id` 印刷级换卡支持 + task 113 A/B 覆盖印刷重跑

- 状态：进行中
- 关联：task 113（缺口发现）/ task 075（换卡管道）；TDD 小扩，存量行为不变
- 日期：2026-11-14 立项（下一步调研拍板）

## 目标

补 task 113 发现的管线缺口：swap `in` 仅支持卡名，换入印刷 = `db.search_cards(name, limit=1)` 首命中、不可指定，可能静默退化为 vanilla。本任务加可选 `in_id` 印刷级指定，并用 DSL 覆盖印刷重跑 task 113 的 A/B 两刀，把「移除+死卡」降级数据升级为真功能替代数据。

## 设计（先定案，TDD 红测照此写）

- `SwapCfg` 加可选字段 `in_id: str | None = None`（frozen model，存量 YAML 零影响）。
- `in_id` 给定时：`db.get_card(in_id)` 解析；**存在性校验**（未命中 = ValueError 不猜）；**同名校验**（解析卡名必须等于 `in`，不一致 = ValueError 不猜——`in` 保持必填，作为人类可读名与 apply_swaps 键）。
- `in_id` 缺省 = 现状路径（search_cards 首命中），行为零变化。
- `apply_swaps` 不动（in_cards 仍按 `in` 名键入，印刷指定只发生在解析层）。

## 验收标准（测试清单）

1. 红测 → 绿：`in_id` 解析 DSL 覆盖印刷（换入卡生效、装载无 vanilla 告警）。
2. 红测 → 绿：未知 `in_id` → ValueError（不猜）。
3. 红测 → 绿：`in_id` 卡名 ≠ `in` → ValueError（不猜）。
4. 存量测试零改动全绿（缺省路径行为不变）；全量 pytest 绿 + ruff 零告警。
5. **重跑（真功能替代）**：新实验 yml（base + A′/B′ 带 `in_id`，巢穴球 `CSVH1C-043` / 摔角鹰人 `CSV1C-079`，种子 400000..400499 与 task 113 CRN 可比）→ 失败 0 → sensitivity 报告包四件 + 限定语内嵌 → dig 对比 A/B vs A′/B′（vanilla 退化 vs 真替代的差异量化）。

## 实现要点

- 只动 `battlefrontier/runner/experiment.py`（SwapCfg + prepare_variant 解析分支）+ 新测试文件（或并入既有 swap 相关测试）。
- 重跑不改 task 113 原产物（`results/v2-swap-dragapult*` 封存不动），新结果落 `results/v2-swap-dragapult-printswap.*`。

## 结果与遗留

- **TDD（验收 1–4 ✅）**：4 新测红→绿（in_id 覆盖印刷解析 / 未命中显式报错 / 卡名不一致显式报错 / 同名未覆盖印刷告警不硬错）；存量测试零改动；局部 21 passed + 相关套件 35 passed + ruff 零告警。
- **重跑（验收 5 ✅）**：`experiments/v2-swap-dragapult-dusknoir-printswap.example.yml`（base + A′/B′ 带 in_id：巢穴球 CSVH1C-043 / 摔角鹰人 CSV1C-079，种子 400000..400499）→ 失败 0/1500、装载零告警。A′ +2.2%（CI −4.0..+8.4，不显著）；B′ −5.2%（CI −11.4..+1.0，不显著）；baseline 与 task 113 逐数复现（261/239）。
- **读数（dig 已写）**：vanilla 退化扭曲 ~1–2pp 可见但小于 500 局噪声；定性结论维持（多龙奇 −1 有实质代价），定量排序需 ≥2,000 局口径（留后续按需）。管线缺口正式关闭。dig：`docs/digs/2026-11-14-task115-in-id-print-swap.md`；产物 `results/v2-swap-dragapult-printswap.*`（本机）。
- **遗留**：全量回归 ✅ **1708 passed**（+4 新测）；提交合 main 待授权。
