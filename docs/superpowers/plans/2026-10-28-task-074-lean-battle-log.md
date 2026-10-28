# 精简对局日志 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有 `bfsim report` 上默认给出每局一行汇总、抽样 `render_log` 回放，以及主阶段行动 × 胜率，并写入与 072 相同的 Markdown/HTML + CSV/JSON 包。

**Architecture:** 不新造事件。`battlefrontier/report/battle_log.py` 读结果库 `games` 与 `game_events`。主阶段 kind 只认 `attack` / `retreat` / `play_trainer` / `play_stadium` / `evolve` / `attach_energy` / `end_turn`。`choose` 仍由 `--decisions` 负责。回放调用现成 `render_log`，按种子升序取前 N 局完成局（默认 3），不渲染全部，也不倾倒合法行动。

**Tech Stack:** Python 3.12+、现有 ResultsDB 与 `GameEvent`、pytest、ruff。

**权威设计：** `docs/superpowers/specs/2026-10-28-post-071-roadmap-design.md` §2.2 与 §3 的 074。

## Global Constraints

- 复用 `game_events`。不编造 AI 理由。不逐步倾倒合法行动。关键路径不调用 LLM。
- 汇总表默认开，不需要额外开关才出现。
- 导出默认双轨，数字来自同一 `BattleLogReport`。Markdown 内嵌格式化原文，HTML 由该文转义。
- 不伪造校准数字。不做 075 的全卡池扫描。
- pytest 与 ruff 对改动路径通过。抽样顺序由种子决定，不用新的随机源。

---

### Task 1: 汇总、主阶段行动胜率、抽样回放

**Files:**
- Create: `battlefrontier/report/battle_log.py`
- Test: `tests/test_battle_log.py`

**Interfaces:**
- Produces: `battle_log_report(db, experiment_id, *, sample_n=3) -> BattleLogReport`
- Produces: `write_battle_log_pack(directory, rep) -> dict[str, Path]`

- [x] **Step 1: Write the failing test**

造四局：种子 1，A 用「喷火龙：火之玉」并获胜，事件里另有一条 `choose`；种子 2，同一招式 A 落败；种子 3 平局只有 `end_turn`；种子 4 失败局无事件。断言汇总 4 行；该招式 occurrences=2、wins=1、winrate=0.5；`choose` 不出现；`sample_n=1` 只回放种子 1，文本含「使用招式」；JSON 的 winrate 等于 `ActionStat.winrate`。

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_battle_log.py -q`
Expected: FAIL（模块不存在）

- [x] **Step 3: Implement `battle_log.py`**

`action_label`：attack 用 `name：attack`，retreat 用 `out→into`，evolve 用 `onto→name`，attach 用 `target`，trainer/stadium 用 `name`，end_turn 固定 `end_turn`。胜率分母 = 决定局（平局计次数不计胜负），与 `decisions.py` 相同。失败局只进汇总。抽样 = 完成局按 `(seed, id)` 取前 `sample_n`，交给 `render_log`。

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_battle_log.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add battlefrontier/report/battle_log.py tests/test_battle_log.py
git commit -m "task(074): 每局汇总、抽样回放与主阶段行动胜率"
```

---

### Task 2: `bfsim report` 默认写出对局包

**Files:**
- Modify: `battlefrontier/cli.py`（`report` 增加 `--out` 与 `--replay-sample`，默认写出）
- Test: `tests/test_battle_log.py`（追加 CLI）

- [x] **Step 1: Write the failing CLI test**

`main(["report", id, "--results", db, "--out", pack, "--replay-sample", "1"])`。标准输出含「每局汇总」与「主阶段行动」，且不含「理由」。`pack/log.md` 含「使用招式」。`pack/log.json` 的行动胜率与对象一致。

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_battle_log.py::test_cli_report_writes_log_pack -q`
Expected: FAIL（没有 `--out` 或没有文件）

- [x] **Step 3: Wire the CLI**

胜率正文之后无条件打印汇总与主阶段分节。`--decisions` 仍只追加 chooser。`--replay-sample` 默认 3。`--out` 缺省 `results/report-<id>-log`，写 `log.md` / `log.html` / `summary.csv` / `actions.csv` / `log.json`。回放正文进包，标准输出只给路径。

- [x] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_battle_log.py tests/test_winrate.py tests/test_decisions.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add battlefrontier/cli.py tests/test_battle_log.py
git commit -m "task(074): report 默认落对局日志双轨包"
```

---

### Task 3: 任务书与 STATUS

**Files:**
- Create: `tasks/done/task 074.md`
- Modify: `STATUS.md`

- [x] **Step 1: 写明命令**

```bash
bfsim report <experiment_id> --results results/exp.db --out results/report-log
```

不做假理由、合法行动全量转储、LLM。075 未开始。

- [x] **Step 2: Commit**

```bash
git add "tasks/done/task 074.md" STATUS.md
git commit -m "task(074): 对局日志任务书与 STATUS"
```
