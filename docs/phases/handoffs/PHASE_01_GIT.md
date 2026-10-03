# Phase 01 Task 1: Git fixtures and pinned reads

Task 1 is implemented in `ddg/gitio.py` and `ddg/demo.py`. Git reads use argument arrays, fixed full SHA-1 object IDs, and bounded subprocess timeouts; Git or input errors become safe `ValueError`s. The demo builder accepts an absent or empty destination, rejects files and nonempty directories before writing, initializes SHA-1 history, and supplies author identity per commit. Its generated `.ddg-demo.json` is ignored inside that demo repository.

The fixture exposes full SHA values under `refs` for `calibration_bad`, `calibration_good`, `calibration_exception`, `decision_change`, `missing_policy`, `crashing`, `timing_out`, `abort`, `missing_entrypoint`, and `initial`. `decision_change` points to `calibration_good`, which is also the checked-out working branch at completion. Corresponding hyphenated refs are available for CLI use. DEC-001 remains as a superseded record after DEC-002 replaces it; DEC-002 states duplicate prevention and rejects fabricated success and silent abandonment.

## Verification evidence

TDD RED: after writing `tests.test_gitio` and `tests.test_demo` and before implementing `ddg/demo.py`, `python -m unittest tests.test_gitio tests.test_demo -v` failed during test import with `ModuleNotFoundError: No module named 'ddg.demo'`, as expected for the missing feature.

The final targeted command is:

```powershell
python -m unittest tests.test_gitio tests.test_demo -v
```

Result: **9 tests passed**. Coverage includes a moved branch with unchanged pinned reads, exact UTF-8 source round-tripping, full-SHA validation, missing refs and objects, unsafe paths, paths containing spaces, source-only diff output, destination refusal without touching existing files, empty-destination creation, dirty parent-checkout preservation, required fixture refs, decision supersession, metadata, and clean generated repository state. The UTF-8 regression first failed against platform-default Git decoding, then passed after Git subprocess output was explicitly decoded as UTF-8. A cross-check of `python -m unittest tests.test_contracts tests.test_harness -v` currently has one independently-owned failure: `test_worker_json_protocol_writes_unicode_as_utf8` raises `UnicodeEncodeError` on ASCII stdout in `ddg/worker.py`; the remaining 22 tests pass. That worker protocol issue is outside this task's ownership.

No source commits were created by this worker. Git staging and commit are owned by the orchestrator. The full suite was not run here because later phase modules are still being implemented.
