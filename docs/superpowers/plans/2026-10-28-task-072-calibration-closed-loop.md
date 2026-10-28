# v2 校准闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用现有 `bfsim run` 矩阵和 `bfsim calibration` 跑卡池 v2，并在同一次 calibration 里默认写出人读 Markdown/HTML 与机器 CSV/JSON，数字来自同一份 `CalibrationReport`。

**Architecture:** 不新增命令。`experiments/v2-calibration.example.yml` 指向 `config/target-pool.v2.yml`，`expand_matrix` 仍用池内 `deck_id`。`battlefrontier/report/deviation_pack.py` 把已有 `format_calibration` 原文嵌进人读 Markdown，HTML 由该 Markdown 转义生成；CSV/JSON 从同一 `CalibrationReport.cells` 序列化。CLI `calibration` 增加 `--out`，缺省目录 `results/<实验名>-deviation`。

**Tech Stack:** Python 3.12+、pytest、ruff、现有 ResultsDB 与 `bfsim calibration`（真实侧仍是 `ptcgdb.sdk.open_db` + `stats_matchup`）。

**权威设计：** `docs/superpowers/specs/2026-10-28-post-071-roadmap-design.md` §3 的 072。用户 2026-10-28 改顺序：在未合并的 PR #1 上实现，做完再审，代理不合并。

## Global Constraints

- 只做 072。不做 073 导入体验、074 精简 B 日志、075 换卡报告、JEV、LLM、产品 GUI、编造 AI 理由。
- 卡组进入只走池 YAML 里已有的 `deck_id`。不新造校准命令。
- 不伪造校准数字。全量 36×500 局需要本机 `ptcg-cn.db`；本仓库只接上可跑的实验定义，并用小局数 smoke 定义验证展开，不把 smoke 的结果写成正式偏差。
- 种子确定性、主库只读、pytest 与 ruff 对改动路径通过。
- 双轨数字同源：Markdown 内嵌 `format_calibration` 全文；JSON/CSV 字段等于 `CalibrationCell` 的同一属性。

---

### Task 1: v2 矩阵实验定义可展开

**Files:**
- Create: `experiments/v2-calibration.example.yml`
- Create: `experiments/v2-calibration-smoke.example.yml`
- Test: `tests/test_v2_calibration_matrix.py`

**Interfaces:**
- Consumes: `load_experiment`、`load_target_pool`、`expand_matrix`（`battlefrontier/runner/experiment.py`）
- Produces: 实验名 `v2-calibration`（每对 500 局）与 `v2-calibration-smoke`（每对 1 局）

- [x] **Step 1: Write the failing test**

```python
def test_v2_pool_matrix_is_36_pairs_of_500():
    defn = load_experiment("experiments/v2-calibration.example.yml")
    pool = load_target_pool(defn.matrix.pool)
    assert len(pool.decks) == 9
    subs = expand_matrix(defn, pool)
    assert len(subs) == 36
    assert subs[0].games == 500
    assert subs[0].decks.a.source == "db"
    assert subs[0].seed_start == 200000
    assert subs[1].seed_start == 200500
    assert "N的索罗亚克" in subs[-1].name or any("N的索罗亚克" in s.name for s in subs)
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_v2_calibration_matrix.py::test_v2_pool_matrix_is_36_pairs_of_500 -q`
Expected: FAIL（实验文件不存在）

- [x] **Step 3: Write the experiment YAML**

`experiments/v2-calibration.example.yml`：

```yaml
# v2 校准：9 套 × 36 无向配对 × 500 局（task 072）
# bfsim run experiments/v2-calibration.example.yml --workers 8 --results results/v2-calibration.db
# bfsim calibration experiments/v2-calibration.example.yml --results results/v2-calibration.db
name: v2-calibration
seed_start: 200000
matrix:
  pool: config/target-pool.v2.yml
  games_per_pair: 500
agents:
  a: {type: heuristic}
  b: {type: heuristic}
```

`experiments/v2-calibration-smoke.example.yml` 同结构，`name: v2-calibration-smoke`，`games_per_pair: 1`，`seed_start: 900000`。只用于展开与冒烟命令，不把其结果当作正式偏差表。

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_v2_calibration_matrix.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add experiments/v2-calibration.example.yml experiments/v2-calibration-smoke.example.yml tests/test_v2_calibration_matrix.py
git commit -m "task(072): v2 校准矩阵实验定义可展开为 36 对"
```

---

### Task 2: 偏差包双轨写出

**Files:**
- Create: `battlefrontier/report/deviation_pack.py`
- Test: `tests/test_deviation_pack.py`

**Interfaces:**
- Consumes: `CalibrationReport`、`CalibrationCell`、`format_calibration`
- Produces: `write_deviation_pack(directory, rep) -> dict[str, Path]`，键为 `md` `html` `csv` `json`

- [x] **Step 1: Write the failing test**

构造一个两格 `CalibrationReport`（一格有 Δ，一格 `delta is None`）。调用 `write_deviation_pack`。断言四个文件存在；`format_calibration(rep)` 是 markdown 的子串；HTML 含转义后的同一段；JSON `cells[0].delta` 等于该格 `delta`；CSV 第一行 `sim_wr` 用 `float` 读回与 `sim_wr` 相差 < 1e-9。

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_deviation_pack.py -q`
Expected: FAIL（模块不存在）

- [x] **Step 3: Implement `deviation_pack.py`**

`deviation_markdown` 以 `# 校准偏差包：{group_name}` 开头，正文代码块内是 `format_calibration(rep)` 的全文。`deviation_html` 用 `html.escape` 包进 `<pre>`。`deviation_rows` 每格一个 dict，字段与 `CalibrationCell` 同名，`sim_ci_low` / `sim_ci_high` 拆开。`write_deviation_pack` 写 `deviation.md`、`deviation.html`、`deviation.csv`、`deviation.json`（`ensure_ascii=False`，含 `meta`、`weighted_mean_abs_delta`、`ci_coverage`、`cells`）。

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_deviation_pack.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add battlefrontier/report/deviation_pack.py tests/test_deviation_pack.py
git commit -m "task(072): 偏差包同时写 Markdown/HTML 与 CSV/JSON"
```

---

### Task 3: `bfsim calibration` 默认写出偏差包

**Files:**
- Modify: `battlefrontier/cli.py`（`_cmd_calibration` 与 `calibration` 参数）
- Test: `tests/test_calibration.py`（追加一条，不改既有断言）

**Interfaces:**
- Consumes: `write_deviation_pack`
- Produces: `--out` 缺省为 `results/<实验名>-deviation`；标准输出仍打印 `format_calibration`，并多一行 `偏差包：`

- [x] **Step 1: Write the failing test**

在 `test_calibration.py` 增加 `test_cli_calibration_默认写出双轨包`：沿用 `_write_defs` 与 `_FakeSdk`，`main(["calibration", exp, "--results", db, "--out", str(tmp/"pack")])`。断言 rc=0，且 `pack/deviation.md`、`.html`、`.csv`、`.json` 都存在，markdown 含 `加权平均`，json 的 `weighted_mean_abs_delta` 为 float。

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_calibration.py::test_cli_calibration_默认写出双轨包 -q`
Expected: FAIL（没有 `--out` 或没有文件）

- [x] **Step 3: Wire the CLI**

`cal_p.add_argument("--out", default=None, help="偏差包目录（默认 results/<实验名>-deviation）")`。算出报告后：

```python
out_dir = Path(args.out) if args.out else Path("results") / f"{defn.name}-deviation"
paths = write_deviation_pack(out_dir, rep)
print(format_calibration(rep))
print("偏差包：" + " ".join(str(p) for p in paths.values()))
```

不新增子命令。

- [x] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_calibration.py tests/test_deviation_pack.py tests/test_v2_calibration_matrix.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add battlefrontier/cli.py tests/test_calibration.py
git commit -m "task(072): calibration 默认落偏差包双轨文件"
```

---

### Task 4: 任务书与 STATUS

**Files:**
- Create: `tasks/task 072.md`（完成后移到 `tasks/done/task 072.md`）
- Modify: `STATUS.md` 当前段与决策日志
- Modify: `docs/superpowers/specs/2026-10-28-post-071-roadmap-design.md` 一句顺序改口（用户允许在 PR 上先实现）

- [x] **Step 1: 任务书写明验收与命令**

正式跑（需本机库，本任务不代跑、不填数字）：

```bash
bfsim run experiments/v2-calibration.example.yml --workers 8 --results results/v2-calibration.db
bfsim calibration experiments/v2-calibration.example.yml --results results/v2-calibration.db --out results/v2-deviation
```

冒烟展开不跑局：`pytest tests/test_v2_calibration_matrix.py`。

- [x] **Step 2: STATUS**

当前段写明 072 的管道已在 PR #1 上，正式矩阵未在无库环境跑出数字；073–075 未开始。决策日志加一行指向本计划。

- [x] **Step 3: Commit**

```bash
git add "tasks/done/task 072.md" STATUS.md docs/superpowers/specs/2026-10-28-post-071-roadmap-design.md
git commit -m "task(072): 校准闭环任务书与 STATUS"
```
