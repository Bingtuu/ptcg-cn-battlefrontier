# M13 Calibration and Validation Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver reproducible full/development/validation calibration reports and a frozen M13 baseline manifest without changing game or Agent behavior.

**Architecture:** Add a read-only tournament splitter beside the existing pairing query, an optional tournament-ID filter to that query, and pure summary/manifest helpers in the report layer. Extend the existing calibration CLI only when `--tournament-split time-70-30` is explicit; legacy stdout and JSON fields remain unchanged when the flag is absent.

**Tech Stack:** Python 3.12, SQLite read-only views, dataclasses, PyYAML, pytest, ruff.

---

### Task 095: Tournament split, calibration summaries, reports, and manifest

**Files:**
- Create: `battlefrontier/data/validation.py`
- Create: `battlefrontier/report/validation.py`
- Create: `config/m13-validation-v1.yml`
- Create: `tasks/task 095.md`
- Modify: `battlefrontier/data/pairings.py`
- Modify: `battlefrontier/report/calibration.py`
- Modify: `battlefrontier/report/deviation_pack.py`
- Modify: `battlefrontier/cli.py`
- Test: `tests/test_validation_split.py`
- Test: `tests/test_calibration.py`
- Test: `tests/test_deviation_pack.py`

- [ ] **Step 1: Write the task document and failing tournament-split tests**

Create `tasks/task 095.md` with the M13 scope, red-test checklist, and prohibition on Agent changes. Create `tests/test_validation_split.py` using two same-day tournaments at the split boundary:

```python
import sqlite3

from battlefrontier.data.validation import tournament_time_split


def _db(tmp_path):
    path = tmp_path / "validation.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE v_tournament_weights "
        "(tournament_id TEXT, date TEXT, division TEXT, basis TEXT)"
    )
    conn.executemany(
        "INSERT INTO v_tournament_weights VALUES (?, ?, ?, ?)",
        [
            ("t1", "2025-01-01", "master", "intl_aligned"),
            ("t2", "2025-01-02", "master", "intl_aligned"),
            ("t3", "2025-01-02", "master", "intl_aligned"),
            ("t4", "2025-01-03", "master", "intl_aligned"),
            ("t5", "2025-01-04", "master", "intl_aligned"),
            ("t6", "2025-01-05", "senior", "intl_aligned"),
            ("t7", "2025-01-06", "master", "cn"),
        ],
    )
    conn.commit()
    conn.close()
    return path


def test_time_split_uses_ordered_ids_across_same_date_boundary(tmp_path):
    split = tournament_time_split(
        _db(tmp_path), date_from="2025-01-01", date_to="2025-12-31",
        basis="intl_aligned", division="master",
    )
    assert split.development_ids == ("t1", "t2", "t3")
    assert split.validation_ids == ("t4", "t5")
    assert split.meta["development_last"] == "t3"
    assert split.meta["validation_first"] == "t4"


def test_time_split_rejects_empty_tournament_set(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="赛事为空"):
        tournament_time_split(
            _db(tmp_path), date_from="2030-01-01", date_to="2030-12-31",
            basis="intl_aligned", division="master",
        )
```

- [ ] **Step 2: Run the split tests and verify RED**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/test_validation_split.py`
Expected: FAIL with `ModuleNotFoundError: battlefrontier.data.validation`.

- [ ] **Step 3: Implement the deterministic read-only splitter**

Create `battlefrontier/data/validation.py`:

```python
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TournamentSplit:
    development_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    meta: dict


def tournament_time_split(
    db_path: str | Path,
    *,
    date_from: str,
    date_to: str,
    basis: str,
    division: str = "master",
    development_fraction: float = 0.7,
) -> TournamentSplit:
    if not 0 < development_fraction < 1:
        raise ValueError("development_fraction 必须在 (0,1) 内")
    path = Path(db_path).resolve()
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT tournament_id, date FROM v_tournament_weights "
            "WHERE date BETWEEN ? AND ? AND basis = ? "
            "AND (division = ? OR division IS NULL) "
            "ORDER BY date, tournament_id",
            (date_from, date_to, basis, division),
        ).fetchall()
    finally:
        conn.close()
    if len(rows) < 2:
        raise ValueError("赛事为空或不足以切分")
    cut = int(len(rows) * development_fraction)
    development = tuple(str(row[0]) for row in rows[:cut])
    validation = tuple(str(row[0]) for row in rows[cut:])
    meta = {
        "method": "time-70-30",
        "tournament_count": len(rows),
        "development_count": len(development),
        "validation_count": len(validation),
        "development_last": development[-1],
        "validation_first": validation[0],
        "development_date_last": rows[cut - 1][1],
        "validation_date_first": rows[cut][1],
    }
    return TournamentSplit(development, validation, meta)
```

Create `config/m13-validation-v1.yml` with the frozen real query, expected counts, and boundary IDs from the M13 spec. Add a test that loads this file with `yaml.safe_load` and asserts `development_count == 286`, `validation_count == 123`, and the two exact IDs from D-M13-2.

- [ ] **Step 4: Add the optional tournament-ID pairing filter with red tests first**

Append to `tests/test_pairings.py`:

```python
def test_contrast_can_filter_exact_tournament_ids(tmp_path):
    path = _db(tmp_path)
    all_rows = pairing_contrast(
        path, ["Alpha", "Beta"], date_from="2025-04-11",
        date_to="2025-08-31", basis="intl_aligned",
    )
    selected = pairing_contrast(
        path, ["Alpha", "Beta"], date_from="2025-04-11",
        date_to="2025-08-31", basis="intl_aligned",
        tournament_ids=("t1",),
    )
    assert selected.cells == all_rows.cells
    assert selected.sample_total == all_rows.sample_total
    empty = pairing_contrast(
        path, ["Alpha", "Beta"], date_from="2025-04-11",
        date_to="2025-08-31", basis="intl_aligned",
        tournament_ids=("not-present",),
    )
    assert empty.cells == () and empty.sample_total == 0
```

Run: `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/test_pairings.py`
Expected: the new test FAILs with an unexpected `tournament_ids` keyword argument.

Modify `pairing_contrast` to accept `tournament_ids: tuple[str, ...] | None = None`. When not None, require a non-empty tuple and append `AND pp.tournament_id IN (...)` with exactly one placeholder per ID; when None, keep the existing SQL and results unchanged.

- [ ] **Step 5: Add failing summary tests and implement pure metrics**

Append to `tests/test_calibration.py`:

```python
def test_validation_summary_has_unweighted_high_residual_and_rows(db_path):
    from battlefrontier.report.validation import calibration_summary
    rep = _report(db_path, [
        _real("Alpha", "Beta", 100, 0.60),
        _real("Beta", "Alpha", 100, 0.00),
    ])
    summary = calibration_summary(rep)
    assert summary["weighted_mean_abs_delta"] == rep.weighted_mean_abs_delta
    assert summary["unweighted_mean_abs_delta"] == (0.025 + 0.375) / 2
    assert summary["high_residual_cells"] == 1
    assert summary["rows"][0]["archetype"] == "A宝"
    assert summary["rows"][0]["max_cell"]["opponent"] == "B宝"
```

Run: `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/test_calibration.py -k validation_summary`
Expected: FAIL because `battlefrontier.report.validation` does not exist.

Create `battlefrontier/report/validation.py` with `calibration_summary(rep)`. For every valid cell, include `abs(delta)` in weighted/unweighted means; count `abs(delta) >= 0.25`; group rows by archetype using real_n weights and retain the maximum-|Δ| cell. Return only JSON-serializable dictionaries/lists. Empty valid sets return None means, zero high-residual count, and empty rows.

Also implement `write_validation_manifest(directory, *, protocol, reports, artifacts)` in the same module. It writes `manifest.json` containing the protocol, each report's `group_name`, `meta`, and `calibration_summary`, plus SHA-256 for every artifact path. The caller supplies `reports={"full": rep, "development": dev_rep, "validation": val_rep}` and artifact paths for the experiment YAML and results DB.

- [ ] **Step 6: Expose summaries in text and JSON without changing legacy fields**

Modify `format_calibration` to append unweighted |Δ|, high-residual count, and one line per archetype row using `calibration_summary` only when `rep.meta["validation_split"]` is present. Modify `deviation_payload` to add `"summary": calibration_summary(rep)` only in that same split mode. Legacy stdout, JSON keys, and CSV columns remain unchanged.

Add assertions to `tests/test_deviation_pack.py` that a report whose meta contains `validation_split="time-70-30"` has a JSON summary with the same weighted value as the report and contains `unweighted_mean_abs_delta`, `high_residual_cells`, and `rows`; also assert a legacy report has no `summary` key. Run:

Run: `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/test_calibration.py tests/test_deviation_pack.py`
Expected: PASS after the new assertions and implementation are present.

- [ ] **Step 7: Add CLI split-mode tests and implement explicit orchestration**

Add a CLI test to `tests/test_validation_split.py` that builds a two-deck matrix result DB and a temporary real DB, then calls:

```python
rc = main([
    "calibration", str(exp), "--results", str(results_db),
    "--db", str(real_db), "--tournament-split", "time-70-30",
    "--validation-protocol", str(protocol), "--out", str(out),
])
assert rc == 0
assert (out / "full" / "deviation.json").is_file()
assert (out / "development" / "deviation.json").is_file()
assert (out / "validation" / "deviation.json").is_file()
assert (out / "manifest.json").is_file()
```

Run the test before implementation and expect argparse to reject the new option. Add `--tournament-split {time-70-30}` and `--validation-protocol` to the calibration parser. In split mode, compute the split once, call `pairing_contrast` for full/development/validation IDs, build three reports through the existing `calibration_report`, and use `dataclasses.replace` to set each report meta's `validation_split="time-70-30"` before writing three deviation packs and the manifest. Validate actual counts and boundary IDs against the YAML protocol. Do not call `stats_matchup` in split mode. Keep the existing SDK path unchanged when the flag is absent.

- [ ] **Step 8: Run focused verification and lint**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/test_validation_split.py tests/test_pairings.py tests/test_calibration.py tests/test_deviation_pack.py tests/test_cli.py`
Expected: PASS.

Run: `.venv/Scripts/ruff.exe check battlefrontier/data/validation.py battlefrontier/data/pairings.py battlefrontier/report/validation.py battlefrontier/report/calibration.py battlefrontier/report/deviation_pack.py battlefrontier/cli.py tests/test_validation_split.py tests/test_pairings.py tests/test_calibration.py tests/test_deviation_pack.py`
Expected: no warnings.

### Task 096: End-to-end reproduction, determinism, and M13 acceptance

**Files:**
- Create: `tasks/task 096.md`
- Create: `experiments/m13-determinism.yml`
- Modify: `STATUS.md`
- Modify: `docs/superpowers/specs/2026-10-31-phase4-accuracy-validity-design.md`
- Modify: `docs/superpowers/plans/2026-10-31-m13-calibration-validation-foundation.md`

- [ ] **Step 1: Write the acceptance document and deterministic experiment**

Create `tasks/task 096.md` listing the exact raw/SDK 72-cell comparison, zero simulation failures, serial/parallel event-hash equality, full pytest, ruff, and STATUS requirements. Create `experiments/m13-determinism.yml` with the same decks and seeds as `experiments/t078-gard-zoro.example.yml`, 100 games from seed 208000, and default heuristic agents.

- [ ] **Step 2: Reproduce all three reports from the locked baseline**

Run: `.venv/Scripts/python.exe -X utf8 -m battlefrontier.cli calibration experiments/v2-calibration.example.yml --results results/v2-calibration-post086.db --tournament-split time-70-30 --validation-protocol config/m13-validation-v1.yml --out results/m13-baseline`
Expected: rc=0; full/development/validation packs and `results/m13-baseline/manifest.json` are created; `sim_failed` is 0 in all 72 cells.

- [ ] **Step 3: Compare raw full aggregation with the existing SDK aggregation**

Run a Python read-only assertion that loads `results/m13-baseline/full/deviation.json` and `results/v2-deviation-post086/deviation.json`, keys cells by `(en_archetype, en_opponent)`, and asserts all 72 `real_n` and `real_wr` values match exactly. Expected output: `72/72 real cells match`.

- [ ] **Step 4: Verify serial/parallel game determinism**

Run the deterministic experiment with workers=1 into `results/m13-determinism-serial.db`, then workers=4 into `results/m13-determinism-parallel.db`. Compare `events_hash` by seed for all 100 games. Expected: 100/100 equal and 0 errors. Also compare the parallel result with the existing post-086 behavior baseline for those 100 seeds; expected: no game behavior change.

- [ ] **Step 5: Run full project verification**

Run: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 -m pytest -q`
Expected: all tests pass.

Run: `.venv/Scripts/ruff.exe check .`
Expected: no warnings.

- [ ] **Step 6: Synchronize records and audit M13 completion**

Update `STATUS.md`, the M13 spec/plan, and task 094–096 with actual commands and results. Move completed task documents to `tasks/done/`. Audit every M13 criterion; if any report, comparison, determinism check, test, or lint fails, stop in Task 096 and do not mark the goal complete.

## Execution outcome (2026-10-31)

- Task 094–096 complete; M13 accepted.
- Real reports and manifest reproduced; raw/SDK 72/72 match; serial/parallel/post-086 100/100 event hashes match; simulation failures 0.
- Final full regression: 1674 pytest passed; Ruff 0.16.4 `ruff check .` zero diagnostics; `git diff --check` passed.
- The lint follow-up preserved Ruff 0.16's expanded defaults. It archived 125 untracked local scripts under `results/m13-scratch/` with verified SHA-256 hashes and fixed 37 diagnostics in six tracked historical experiment scripts without adding exclusions or suppressions.
- Independent review found no Critical issues. Its 2 Important and 3 Minor findings were fixed test-first (limitation metadata, protocol method/fraction validation, report paths, SQLite error wrapping, and non-empty split sides); 52 focused tests pass and real artifacts were regenerated successfully.
