# Phase 02 Task 4: Approval gate handoff

## Delivered

`ddg/approval.py` implements the calibration, review, and verification boundary. `validate_draft(repo, draft, refs)` validates the complete proposal envelope against the pinned source/decision context, checks citations against DEC-001 and DEC-002, and runs all three mandatory cases: the known-bad implementation must fail with duplicate submissions, the known-good implementation must pass with one job, and the documented exception must pass with one job. Execution errors, missing completion, inconsistent observations, and weakened assertions make the proposal ineligible.

The persisted validation records schema version, check/draft/decision/input digests, adapter and proposal provenance, source SHA, the complete proposal preimage, each observed case with its full SHA, calibration hashes, eligibility, and validation time. `approve(...)` requires a nonempty reviewer and reason, an eligible fresh validation, unchanged calibration observations, and a clean marked synthetic demo when activation is requested. It refuses existing artifacts and branch collisions before writing or mutating Git. `verify_bundle(check, decision, validation, approval)` verifies strict schemas, provenance, calibration semantics, and canonical content digests offline.

Activation commits exactly the check, validation, and approval records to the approved base, then creates the review histories. It preserves the original Phase 01 abort ref as `calibration_abort`; public `abort` and `review_abort` point to the approved inherited abort fixture. The other approved-base error fixtures are `review_crashing`, `review_timing_out`, and `review_missing_entrypoint`. `corrected` is both a metadata ref and a branch. Review branches include `regression`, `unseen_regression`, `exception`, `unrelated`, `policy_edit`, `preexisting_base`, `preexisting_head`, and `resolved`.

## Verification evidence

TDD RED cases reproduced weak calibration, manual-to-live provenance relabeling, review-branch collision after writes, floating-point schema versions accepted after recomputing digests, boolean `submit_calls`, malformed proposal-mode types, and hard-coded CHK-001 activation. Corresponding tests now pass.

Commands and results:

- `python -m unittest tests.test_approval -v` — 19 tests passed (77.573 seconds).
- `python -m unittest tests.test_proposal tests.test_governance` — 17 tests passed.
- `python -m unittest tests.test_harness` — 14 tests passed.

No provider credentials are persisted. Manual provenance is explicitly marked manual; a live or recorded label without complete consistent provenance is rejected. The SHA-256 digests bind content and are not cryptographic signatures.
