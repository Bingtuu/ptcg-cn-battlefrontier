# task 075 · 换卡报告双轨

- 状态：完成
- 关联：`docs/superpowers/specs/2026-10-28-post-071-roadmap-design.md` §3 075；计划 `docs/superpowers/plans/2026-10-28-task-075-card-swap.md`

## 目标

在现有 `variants` / `bfsim sensitivity` 上写出换卡前后的双轨报告，并可选抽样 `render_log`。

## 验收标准（测试清单）

- `tests/test_swap_pack.py`：JSON `d_wr` 等于 `VariantComparison.d_wr`；Markdown 含 `format_sensitivity` 用语与「使用招式」；baseline 与 variant 各抽 1 局；模板只有一组 swaps
- `tests/test_sensitivity.py` 与 `tests/test_cli.py` 仍通过

## 实现要点

- `battlefrontier/report/swap_pack.py`
- `bfsim sensitivity --out` 缺省 `results/sensitivity-<base_id>`，`--replay-sample` 默认 2
- 模板 `experiments/templates/card-swap.example.yml`

## 结果与遗留

不做全卡池单卡扫描。正式跑局需要本机 `ptcg-cn.db`。PR #1 由负责人合并。
