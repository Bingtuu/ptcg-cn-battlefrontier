# task 023 — 换卡敏感性（M4 收口）

来源：PRD §9「换卡敏感性：实验定义原生支持对照组/实验组模式，一次提交多组实验，报告并排呈现 ΔWR + 置信区间 + 显著性检验」；M4 验收「报告 meta 可复算」。

## 设计

1. **实验定义扩展（experiment.py）**：`ExperimentDef` 增加 `variants: list[VariantCfg] = []`。
   `VariantCfg = {name, swaps: list[SwapCfg]}`；`SwapCfg = {side: a|b（默认 a）, out: 卡名, out_count: N, in: 卡名, in_count: N}`（`in` 走 pydantic alias）。
   - 校验（定义期，不猜）：每 variant 的 Σout_count == Σin_count（卡组保持 60）；name 非空且组内唯一；side 仅 a/b。
   - 装载期校验（prepare）：baseline 卡组中 `out` 卡存量 ≥ out_count；`in` 卡经 db 解析命中（与 decklist file 同规则），未命中报错不猜。
2. **执行（experiment.py）**：`execute_group(defn, db_path, results_path, workers, cards_dir, definition_yaml) -> list[int]`——先跑 baseline 再按序跑各 variant，**同 seed_start/games（同种子区间，配对可比）**；返回 `[base_id, *variant_ids]`。复用现有 `execute_experiment`，逐组 prepare（variant 卡组 = baseline 卡组应用 swaps）。
   - variant 的 deck id 标注：`file:xxx [variant:名]` / `mik_moe:644634 [variant:名]`，落 games 行可溯源。
3. **结果库（results_db.py）**：experiments 表加 `group_name TEXT NOT NULL DEFAULT ''`、`variant TEXT NOT NULL DEFAULT ''` 两列；对旧库文件做轻量迁移（PRAGMA table_info 缺列则 ALTER TABLE ADD COLUMN）。baseline 行 variant=''。FR-10 三层表骨架不变（仅加列）。
4. **统计（report/sensitivity.py，手写不引 scipy）**：
   - 口径与 winrate.py 一致：胜率分母 = 决定局（完成且非平局）。
   - ΔWR 的 95% CI（非合并 SE）：`diff ± z·√(p₁(1-p₁)/n₁ + p₂(1-p₂)/n₂)`。
   - 显著性 = 两比例 z 检验（合并 SE，双侧）：`z = (p₁-p₂)/√(p(1-p)(1/n₁+1/n₂))`，`p = 2(1-Φ(|z|))`，Φ 用 `math.erf` 手写。
   - n=0 不除零：CI/检验记 None 并在报告中标注。
   - 正确性靠测试内参考值对拍（手算/已知统计表值）。
5. **报告**：`sensitivity_report(db, base_id, variant_ids)` + `format_sensitivity`——并排每行：variant 名、WR（Wilson CI）、ΔWR（CI）、z、p、显著性标注；meta 回显各实验 id/名称/种子区间/版本/局数（可复算纪律）。
6. **CLI**：`bfsim run` 遇到含 variants 的定义自动跑整组并逐个打印实验 id；新增 `bfsim sensitivity <base_id> <variant_id>...` 输出并排报告。

## 验收标准

- [x] variants 定义校验：Σout≠Σin、重名、未知 side、`out` 存量不足、`in` 卡名未命中 db——全部显式报错（ValueError），不猜。
- [x] `execute_group` 同定义同种子重跑：baseline 与各 variant 的 games 层逐局一致；配对区间相同。
- [x] 旧版结果库文件打开自动迁移（加列）且不丢已有行。
- [x] 统计参考值对拍：65/100 vs 35/100 → z≈4.24264、p≈2.21e-5、ΔCI≈(0.1678, 0.4322) 与手算一致（approx）。
- [x] 报告文本含全部 meta 要素 + 并排 ΔWR 表；n=0 边界不崩（标「不可用」）。
- [x] CLI：`bfsim sensitivity` 输出并排报告；`bfsim run` 含 variants 定义跑整组（真机冒烟通过）。
- [x] 全量 pytest 绿（322）+ ruff 零告警。
- [x] STATUS.md 更新 + 本文档归档 tasks/done/。

## 记录

- 2026-08-30 开工。设计依据 PRD §9 原文（一次提交多组实验 / ΔWR + CI + 显著性检验）。
- 2026-08-30 完成。落地：`SwapCfg`/`VariantCfg`（`in` 走 alias）、`apply_swaps` 纯函数、`prepare_variant`（换入卡 db 解析 + DSL 文档补入 + deck id 标注）、`execute_group`/`run_group`（同种子区间配对）；experiments 加 `group_name`/`variant` 列 + 旧库自动迁移；`report/sensitivity.py`（非合并 ΔCI + 合并两比例 z 检验，math.erf 手写）；CLI run 整组 + sensitivity 子命令。
- 真机冒烟 gardevoir-swap 20 局 ×2 组：baseline 36.8%（1 局失败=已知 copy_attack 套娃 DslError，落库不拖垮）vs variant 55.0%，ΔWR +18.2% CI -12.6..+48.9，p=0.2556 不显著——小样本下结论正确保守。
- 示例实验 `experiments/gardevoir-swap.example.yml` 入库。**M4 达成**（021/022/023 全 ✅，报告 meta 可复算）。
