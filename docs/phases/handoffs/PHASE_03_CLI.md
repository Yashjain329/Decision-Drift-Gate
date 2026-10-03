# Phase 03 handoff: CLI and report delivery

**Scope:** `ddg/report.py`, `ddg/cli.py`, `ddg/__main__.py`, `tests/test_cli.py`, and this handoff. No Git staging or commit was performed by this worker.

## Delivered interfaces

- `write_report(report, destination)` writes UTF-8 JSON plus a Markdown sidecar. The Markdown includes full base/head hashes, active base decisions (including uncovered decisions), per-check verdicts, complete observations, approval/validation provenance, changed-line context, ordinary-test results, and warnings. Dynamic text is HTML-escaped for safe rendering.
- `is_stale(repo, report, base, head)` resolves current refs and compares them with the saved full commit hashes. It does not change the stored report; an unresolved ref is stale, while an option-like/invalid ref is a `ValueError`.
- `python -m ddg` exposes `demo-init`, `propose`, `validate`, `approve`, `run`, `status`, and `serve`. `serve` imports the Phase 04 web module only when requested. Recorded proposal mode defaults to the sanitized capture under the source package's `evidence/` folder and works from another working directory. Manual proposal mode requires an explicit `--check` file.
- `run` writes JSON and Markdown and maps `PASSED_CHECKS` to exit 0, `FAILED` to exit 1, and `INCOMPLETE` to exit 2. Invalid invocation/data returns 2 with a concise stderr message and no traceback. The CLI configures UTF-8 stdout/stderr for Windows.
- CLI drafts, validations, and reports are rejected under the target's governed `.ddg` directory. The approval output path is preflighted before approval or demo activation.

## TDD and verification

RED evidence: the initial `python -m unittest tests.test_cli -v` could not import the missing `ddg.report`. A later lifecycle regression reproduced a mutation bug: approval artifacts were written before rejecting an output path under `.ddg`; the test failed because `.ddg/checks/CHK-001.json` existed after the CLI returned 2. Output-path preflight now runs before approval. A stale-report regression also caught a missing “Rerun required” message and now passes.

Final focused command:

```powershell
python -m unittest tests.test_engine tests.test_cli -v
```

Result: **22 tests passed** (engine and CLI suites). The CLI tests cover the demo lifecycle using a recorded capture without a provider call, exit codes 0/1/2, full report provenance, moved-ref staleness with immutable saved bytes, HTML escaping, Unicode (Chinese and emoji) subprocess I/O, paths containing spaces, output-path refusal before mutation, and secret absence from reports.

A real CLI report was generated against the existing approved `.ddg-demo` without modifying that repository:

```powershell
python -m ddg run --repo .ddg-demo --base approved-base --head regression --out .ddg-state/check_contracts-phase03.json
```

Observed result: exit 1, aggregate `FAILED`, verdict `VIOLATION_INTRODUCED`; base was PASS with one unique job, head was FAIL with two jobs and a returned existing job, and ordinary tests passed on both revisions. The JSON report and Markdown sidecar are in ignored `.ddg-state/` for local inspection only. No provider call was made during tests or report generation.

## README notes for the orchestrator

Use the plan's PowerShell quickstart:

```powershell
python -m ddg demo-init --destination .ddg-demo
python -m ddg serve --repo .ddg-demo --state-dir .ddg-state
```

Document proposal modes clearly: live is the default; recorded reads the bundled capture and is labeled recorded; manual requires `--mode manual --check examples/manual_check.json` and remains a hand-authored sample. Show the four lifecycle commands from Task 6, explain that reports create `.json` and `.md` files, and document run exit codes plus `status` returning CURRENT or STALE with “Rerun required.” Provider setup should remain separate from the execution quickstart.

## Handoff to Phase 04

The browser should call the same `propose`, `validate_draft`, `approve`, `compare`, `write_report`, and `is_stale` functions. `compare` returns full `base_sha`/`head_sha`, `active_decisions`, `checks`, warnings, UTC `run_at`, adapter version, and ordinary-test observations. No separate browser verdict logic is needed.
