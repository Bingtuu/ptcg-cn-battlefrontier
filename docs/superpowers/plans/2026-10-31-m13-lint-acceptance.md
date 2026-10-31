# M13 Lint Acceptance Implementation Plan

> **For agentic workers:** Execute inline in the existing M13 workspace on branch `task/m13-lint-acceptance`. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the unchanged M13 deliverable pass the full `ruff check .` hard gate without weakening lint rules, deleting local assets, or changing Agent, DSL, engine, or game behavior; then repeat the M13 acceptance suite and decide whether the branch is eligible for `main`.

**Architecture:** Keep Ruff 0.16's expanded default rules and pin the verified tool version. Preserve untracked one-off analysis scripts by moving them beneath the already ignored `results/m13-scratch/` directory, while continuing to lint every tracked Python file. Fix the remaining 37 diagnostics in the six tracked read-only experiment scripts, then run full regression and real calibration reproduction.

**Tech Stack:** Python 3.12, Ruff 0.16.4, pytest, Git, existing M13 calibration CLI.

---

## Evidence and scope

- Current red gate: `ruff check .` reports 415 diagnostics.
- Tracked files report 37 diagnostics in `experiments/t088_q3_frequency.py`, `t089_q3_frequency.py`, `t089_status_q3_template.py`, `t090_q3_frequency.py`, `t091_q3_frequency.py`, and `t093_q3_frequency.py`.
- The other 378 diagnostics are in untracked local `_*.py` analysis scripts. `ruff check battlefrontier tests` is clean.
- Ruff 0.16 expanded its default set from 59 to 413 rules. Restoring the old `E4,E7,E9,F` selection is not a solution: it still reports 367 diagnostics across the workspace and 31 in tracked files.
- `results/` is already ignored in `.gitignore`; no new Ruff exclusion, blanket `noqa`, or rule downgrade is permitted.

### Task 096-L1: Document, quarantine, and verify the tracked red set

**Files:**
- Create: `docs/superpowers/plans/2026-10-31-m13-lint-acceptance.md`
- Modify: `tasks/task 096.md`
- Modify: `pyproject.toml`
- Move only untracked local scratch: root `_*.py` and `experiments/_*.py` into corresponding paths below `results/m13-scratch/`

- [x] **Step 1: Review the written loop before touching files**

Confirm that the goal is the existing M13 completion criterion, the expected intermediate count after quarantine is exactly 37, and every failure stops this loop. Do not proceed if the move set includes a tracked file, an M13 deliverable, a database, or a non-Python user asset.

- [x] **Step 2: Record the red gates**

Run:

```bash
.venv/Scripts/ruff.exe --version
.venv/Scripts/ruff.exe check . --statistics
git ls-files '*.py' -z | xargs -0 .venv/Scripts/ruff.exe check --statistics
```

Expected: version `0.16.4`; 415 total; 37 tracked. Any different starting count requires reclassification before moving files.

- [x] **Step 3: Preserve local scratch with a reversible move manifest**

Write the untracked move list and SHA-256 hashes to `results/m13-scratch-manifest.json`, then move each file without editing its contents. Root scripts go to `results/m13-scratch/root/`; experiment scripts go to `results/m13-scratch/experiments/`. The manifest records source, destination, and hash for every file.

Run:

```bash
.venv/Scripts/ruff.exe check . --statistics
git ls-files '*.py' -z | xargs -0 .venv/Scripts/ruff.exe check --statistics
```

Expected: both commands report the same 37 diagnostics. If not, stop and restore any mistaken move; do not add an exclusion to hide the difference.

- [x] **Step 4: Pin the verified lint toolchain**

Change the development dependency to `ruff==0.16.4`. Do not add a `select`, `ignore`, `extend-exclude`, or per-file ignore. Run `ruff check battlefrontier tests`; expected: all checks passed.

### Task 096-L2: Fix the 37 tracked diagnostics without gameplay changes

**Files:**
- Modify only: the six tracked experiment scripts listed above

- [x] **Step 1: Apply safe fixes only to the six files**

Run Ruff `--fix` on exactly those six paths. Expected: 22 safe fixes applied and 15 manual diagnostics remain. Review the diff; revert any change outside import ordering, unused imports, encoding declarations, or other provably behavior-preserving syntax cleanup.

- [x] **Step 2: Resolve the remaining diagnostics individually**

Remove unused locals, collapse nested conditions, rename unused unpacked values, and replace blind exception handlers with the narrow expected exception types while preserving each diagnostic script's fallback. For JSON parsing, catch parse/type/value failures rather than every exception. For the optional Git-tip lookup, catch subprocess and OS failures. Do not change DB queries, event interpretation, frequency denominators, output metrics, or any `battlefrontier/` file.

- [x] **Step 3: Verify syntax and the tracked lint gate**

Parse all six files with `ast.parse` and run:

```bash
git ls-files '*.py' -z | xargs -0 .venv/Scripts/ruff.exe check
.venv/Scripts/ruff.exe check .
```

Expected: zero diagnostics. If a semantic-preserving fix cannot be found, leave the file modified only up to the last safe state, record the blocker, and stop without suppressing the diagnostic.

### Task 096-L3: Repeat M13 acceptance and make the integration decision

**Files:**
- Modify: `STATUS.md`
- Modify: `tasks/task 096.md`
- Modify: `docs/superpowers/plans/2026-10-31-m13-calibration-validation-foundation.md`
- Modify: this plan's execution outcome

- [x] **Step 1: Run the full regression gates**

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m pytest -q
.venv/Scripts/ruff.exe check .
git diff --check
```

Expected: 1674 passed, zero Ruff diagnostics, and clean diff whitespace. Any failure keeps Task 096 open.

- [x] **Step 2: Reproduce the real M13 reports**

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m battlefrontier.cli calibration experiments/v2-calibration.example.yml --results results/v2-calibration-post086.db --tournament-split time-70-30 --validation-protocol config/m13-validation-v1.yml --out results/m13-baseline
```

Expected: rc=0 and all full/development/validation packs plus manifest regenerated. Assert 72/72 raw/SDK `real_n` and `real_wr` equality, zero `sim_failed` in all 72 cells, and unchanged weighted/unweighted |Δ| and high-residual counts.

- [x] **Step 3: Audit determinism evidence and scope**

Reuse the existing 100/100 serial/parallel/post-086 event-hash evidence only if no runtime file changed in this lint loop. Confirm the final diff contains no Agent, DSL, or engine-rule change and no new lint suppression.

- [x] **Step 4: Synchronize records and decide integration**

Mark Task 096 complete only when every M13 criterion is green. Commit the reviewed M13 and lint changes on `task/m13-lint-acceptance`. Merge into `main` only if the branch diff is limited to the approved M13/report/lint scope and all acceptance evidence passes; otherwise leave the branch unmerged and record the exact blocker.

## Fallbacks

- Unexpected post-quarantine count: stop, inspect the move manifest, and restore mistaken moves.
- Unsafe automatic fix: revert that hunk and perform a manual behavior-preserving edit.
- Unable to narrow an exception safely: stop with M13 blocked; do not hide the diagnostic.
- Pytest, calibration, or scope regression: revert the responsible lint change, rerun the failed gate, and keep the branch unmerged.
- If every original local script must remain in place and be linted, abandon quarantine and clean all original diagnostics instead; never silently narrow the meaning of the full gate.

## Execution outcome (2026-10-31)

- Branch `task/m13-lint-acceptance`; 125 untracked scratch files moved with SHA-256 verification. The full and tracked Ruff sets both converged to the expected 37 diagnostics.
- Ruff pinned to 0.16.4 with its expanded defaults intact. Twenty-one automatic fixes plus fifteen manual fixes cleared the tracked set; 6/6 scripts passed AST parsing and `ruff check .` passed without exclusions or suppressions.
- Final pytest: 1674 passed in 590.69s. Real full/development/validation reports reproduced with unchanged metrics, raw/SDK 72/72 equality, and zero simulation failures. Existing serial/parallel/post-086 databases matched for all 100 seeds.
- STATUS, the M13 spec/plan, and Task 096 have been synchronized. Integration review found the diff compliant with the approved M13/report/lint scope and eligible for local merge into `main`.
