# task 073 · 三种入口 + 只读真实对阵

- 状态：完成（模板与只读拉取；正式对阵行未在无库环境跑出）
- 关联：`docs/superpowers/specs/2026-10-28-post-071-roadmap-design.md` §3 073；计划 `docs/superpowers/plans/2026-10-28-task-073-import.md`

## 目标

卡组进入保持三条已有路径，并给出复制即可跑的实验模板。从 ptcg-cn.db 只读拉取池内 archetype 的逐桌对阵，服务对照，不做成浏览产品。

## 验收标准（测试清单）

- `tests/test_ingress_templates.py`：deck_id / 池 YAML / 「N 卡名」三份模板可装载
- `tests/test_pairings.py`：窗内决定局聚合成有向格；镜像、窗外、非赛区、非 basis、池外不进；winner_side=0 不进分母但可出现在抽样；只读连接拒绝写入；CSV/JSON 与 `PairingCell` 相同
- 不做构筑 GUI，不做 074/075

## 实现要点

- 模板目录 `experiments/templates/`
- `pairing_contrast` + `bfsim pairings --pool ... --out ...`
- 缺省窗口与 basis 与 `bfsim calibration` 的 `REAL_DATE_*` / `REAL_BASIS` 相同

## 结果与遗留

正式对阵命令需要本机 `ptcg-cn.db`。本任务的测试用临时视图，不填真实 n。卡名列表模板不足 60 张，凑满后再跑。
