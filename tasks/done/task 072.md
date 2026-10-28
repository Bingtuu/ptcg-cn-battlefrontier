# task 072 · v2 矩阵 + 校准偏差包双轨

- 状态：完成（管道与导出；正式 18000 局未在无库环境跑出数字）
- 关联：`docs/superpowers/specs/2026-10-28-post-071-roadmap-design.md` §3 072；计划 `docs/superpowers/plans/2026-10-28-task-072-calibration-closed-loop.md`

## 目标

用卡池 v2 的九套 `deck_id` 展开 matchup 矩阵，并让既有 `bfsim calibration` 默认写出人读 Markdown/HTML 与机器 CSV/JSON。数字来自同一份 `CalibrationReport`。

## 验收标准（测试清单）

- `tests/test_v2_calibration_matrix.py`：`v2-calibration` 展开 36 对、每对 500 局、种子 200000 起连续不重叠；smoke 每对 1 局、种子 900000 起
- `tests/test_deviation_pack.py`：四文件；Markdown 含 `format_calibration` 全文；JSON/CSV 的 Δ 与胜率等于格子字段
- `tests/test_calibration.py::test_cli_calibration_默认写出双轨包`：`--out` 写出四文件，标准输出仍含偏差表正文
- 不新造校准命令；不实现 073–075

## 实现要点

- `experiments/v2-calibration.example.yml` / `experiments/v2-calibration-smoke.example.yml`
- `battlefrontier/report/deviation_pack.py`：`write_deviation_pack`
- `battlefrontier/cli.py`：`calibration --out`，缺省 `results/<实验名>-deviation`

## 结果与遗留

正式跑（需本机 `ptcg-cn.db`，本任务不代跑、不填数字）：

```bash
bfsim run experiments/v2-calibration.example.yml --workers 8 --results results/v2-calibration.db
bfsim calibration experiments/v2-calibration.example.yml --results results/v2-calibration.db --out results/v2-deviation
```

冒烟跑局同样需要卡牌库：`experiments/v2-calibration-smoke.example.yml`。无库时只跑展开测试。

留给 073：卡表/粘贴导入。留给 074：精简 B 过程日志。留给 075：换卡报告。PR #1 由负责人合并，代理不合并。
