# Phase 05 evaluator handoff

## Delivered

`scripts/evaluate.py` runs the deterministic acceptance matrix using `ddg.engine.compare` and writes `case_results.json` plus `timing.csv` under the requested output directory. The matrix includes the 12 approved-demo scenarios: regression, unseen regression, corrected, valid exception, unrelated change, abort, crashing, timeout, missing entry point, policy edit, pre-existing failure, and resolution. Three authority cases extend it: zero approved checks on the existing unapproved calibration revision, a missing approval record, and a forged approval digest.

Missing/forged approval fixtures are created in a disposable `git clone --no-hardlinks` with fixed commit metadata. They never write into the input repo and their exact generated base/head SHA values are recorded. The evaluator stores expected and observed aggregates, check verdicts, warnings, metrics, full revision hashes, check digests, ordinary-test observations, and errors. It compares warning codes exactly, so expected-warning omissions remain visible as mismatches. The input repository is unchanged. Output paths inside the input repository are rejected before writes.

`timing.csv` starts with the agreed participant-evaluation header only. Future measured rows are preserved byte-for-byte on evaluator reruns. No mock rows are included in evidence.

## Verification

- TDD red: before `scripts/evaluate.py` existed, `.venv\Scripts\python.exe -m unittest tests.test_evaluate -v` failed with `ModuleNotFoundError: No module named 'scripts'`.
- Green: `.venv\Scripts\python.exe -m unittest tests.test_evaluate -v` — 2 tests passed in 19.160 seconds. A temporary approved demo exercises actual regression and corrected comparisons, full hashes/digests/metrics, input immutability, and header-only timing output. It also verifies that an evaluator rerun preserves a clearly marked test-only row in a temporary test output; that row is not participant data. The second test verifies refusal to write anywhere inside the input repository.
- Full evaluation: `.venv\Scripts\python.exe scripts/evaluate.py --repo .ddg-demo --out .ddg-evaluation` — 15/15 cases matched the recorded expectations. Results are in ignored `.ddg-evaluation/case_results.json`; timing template is `.ddg-evaluation/timing.csv`.
- `.venv\Scripts\python.exe -m py_compile scripts/evaluate.py` and `git diff --check` passed.

The first 12-case run matched 9/12 because the expected warning list omitted `ORDINARY_TEST_ERROR` for crash, timeout, and missing-entry-point cases; the observed `INCOMPLETE`/`NOT_CHECKED` outcomes were correct. After those expected warning codes were added, all 12 matched. The three added authority cases then exposed `POLICY_REVIEW_REQUIRED` because their regression head includes policy artifacts relative to the unapproved/malformed base; the expected warning ledger was corrected to include that warning. The final 15-case run matched all 15, with every warning preserved in the report.

## Evidence limits and remaining work

No human reviewers or presenter rehearsal were available to this evaluator. The CSV has no participant data, no review-time measurement exists, and the original 50% time-saving target remains unmeasured. This phase does not claim reviewer benefit or a 20-second pitch duration. Live Gemini provenance and browser lifecycle evidence were separately verified by root during Phase 04; this evaluator makes no provider requests.

The matrix is for the synthetic Python job-client adapter and its named Git fixtures. The missing/forged records are reproducibly generated in a temporary clone rather than added to the demonstration repo. The full test suite, release documentation, evidence curation, human feedback, rehearsal, clean-source commit, and publication remain with the release owner.

## Reproduce

```powershell
python scripts/evaluate.py --repo .ddg-demo --out .ddg-evaluation
```

An exit code of 0 means all case expectations matched; 1 means one or more observed results/warnings differ; 2 indicates invalid arguments or evaluator input/output setup. Existing timing rows remain intact when regenerating case results.
