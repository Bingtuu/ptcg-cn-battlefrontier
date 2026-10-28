# 换卡报告双轨导出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `bfsim sensitivity` 上，把 baseline 与 variant 的 ΔWR 写成 Markdown/HTML + CSV/JSON，并可选地各抽几局 `render_log`。

**Architecture:** 不新造换卡执行。`variants` / `sensitivity_report` / `format_sensitivity` 保持原样。`battlefrontier/report/swap_pack.py` 把 `format_sensitivity` 原文嵌进 Markdown，HTML 由该文转义，CSV/JSON 的 `d_wr` 等于 `VariantComparison.d_wr`。回放复用 task 074 的 `sample_replays`，baseline 与每个 variant 各抽默认 2 局。不扫描整池。

**Tech Stack:** Python 3.12+、现有 ResultsDB 与敏感性报告、pytest、ruff。

**权威设计：** `docs/superpowers/specs/2026-10-28-post-071-roadmap-design.md` §3 的 075。

## Global Constraints

- 站在现有 `variants` 与 `bfsim sensitivity` 上。不新造换卡命令。
- 双轨数字同源。不编造理由，不倾倒合法行动。
- 不做全卡池单卡扫描。不做 JEV/LLM，不做产品 GUI。
- 不伪造校准 |Δ|。pytest 与 ruff 对改动路径通过。
- 抽样按种子升序，不用新的随机源。

---

### Task 1: 换卡包与抽样回放

**Files:**
- Create: `battlefrontier/report/swap_pack.py`
- Create: `experiments/templates/card-swap.example.yml`
- Test: `tests/test_swap_pack.py`

**Interfaces:**
- Consumes: `sensitivity_report`、`format_sensitivity`、`sample_replays`
- Produces: `write_swap_pack(directory, rep, replays) -> dict[str, Path]`
- Produces: `swap_replays(db, rep, sample_n) -> tuple[SwapReplay, ...]`

- [x] **Step 1: Write the failing test**

baseline 10 局 A 胜 6，variant 10 局 A 胜 8。两边种子 0 各有一条 attack 事件。`sample_n=1` 时回放各 1 局且文本含「使用招式」。JSON 里 variant 的 `d_wr` 等于 `VariantComparison.d_wr`。模板只有一个 variant，不遍历卡池。

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_swap_pack.py -q`
Expected: FAIL（模块或模板不存在）

- [x] **Step 3: Implement the pack and the template**

`swap_rows`：baseline 一行 `d_wr` 为空，每个 variant 一行带 `d_wr`、`d_ci_low`、`d_ci_high`、`z`、`p`。Markdown 代码块内是 `format_sensitivity` 全文，后面接抽样回放。模板 `experiments/templates/card-swap.example.yml`：`games: 1`，一组 `反击捕捉器`×2 换 `巢穴球`×2，注释写明复制后改卡名再跑，不是全池扫描。

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_swap_pack.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add battlefrontier/report/swap_pack.py experiments/templates/card-swap.example.yml tests/test_swap_pack.py
git commit -m "task(075): 换卡报告双轨包与抽样回放"
```

---

### Task 2: `bfsim sensitivity` 默认写出换卡包

**Files:**
- Modify: `battlefrontier/cli.py`
- Test: `tests/test_swap_pack.py`（追加 CLI）

- [x] **Step 1: Write the failing CLI test**

`main(["sensitivity", base, variant, "--results", db, "--out", pack, "--replay-sample", "1"])`。标准输出仍含「ΔWR」。`pack/swap.md` 含同一段。`pack/swap.json` 的 `d_wr` 与报告对象一致。

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_swap_pack.py::test_cli_sensitivity_writes_swap_pack -q`
Expected: FAIL

- [x] **Step 3: Wire the CLI**

`--out` 缺省 `results/sensitivity-<base_id>`。`--replay-sample` 默认 2。先打印 `format_sensitivity`，再写包，最后一行「换卡包：」。

- [x] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_swap_pack.py tests/test_sensitivity.py tests/test_cli.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add battlefrontier/cli.py tests/test_swap_pack.py
git commit -m "task(075): sensitivity 默认落换卡双轨包"
```

---

### Task 3: 任务书与 STATUS

**Files:**
- Create: `tasks/done/task 075.md`
- Modify: `STATUS.md`
- Modify: `README.md`（项目状态段补一句 072–075 在 PR #1）

- [x] **Step 1: 写明命令与不做项**

```bash
bfsim run experiments/templates/card-swap.example.yml --results results/card-swap.db
bfsim sensitivity <base_id> <variant_id> --results results/card-swap.db --out results/card-swap
```

正式跑需要本机库。不做全池单卡扫描。

- [x] **Step 2: Commit**

```bash
git add "tasks/done/task 075.md" STATUS.md README.md
git commit -m "task(075): 换卡报告任务书与 STATUS"
```
