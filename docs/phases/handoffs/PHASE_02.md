# Phase 02 accepted AI and approval lifecycle

Delivered commits: `e3147be` (grounded Gemini proposal and decision contracts), `03916d4` (calibration and approval).

Root's independent fresh `python -m unittest discover -s tests -v` passed **70 tests in 139.355 seconds**, exit 0. Sol High independently replayed the actual capture, calibrated and approved it, verified inherited review/error revisions and unchanged calibration refs, and reproduced then rechecked the boundary fixes. No remaining important or critical blocker was found in the supported synthetic scope.

Actual live capture: [gemini-proposal.json](../../../evidence/gemini-proposal.json), model `gemini-3.8-flash`, SDK `2.28.0`, capture time `2026-10-03T18:19:56.974766Z`. Recorded replay requires identical input content and preserves original model/time/source metadata separately from current source revision. Manual samples remain disclosed. No credential was found in publishable files; `.env` is ignored.

Stable interfaces and strict record fields are documented in [proposal handoff](PHASE_02_PROPOSAL.md) and [approval handoff](PHASE_02_APPROVAL.md). Engine authority must read `.ddg/checks`, `.ddg/validations`, `.ddg/approvals` and decisions from pinned base, then call `verify_bundle(check, decision, validation, approval)` and validate citations against that base decision graph.

`activate_demo(repo, check_id="CHK-001")` creates inherited review branches. Public refs include `approved_base`, `regression`, `unseen_regression`, `corrected`, `exception`, `unrelated`, `abort`, `policy_edit`, `preexisting_base`, `preexisting_head`, `resolved`; error cases have `review_crashing`, `review_timing_out`, `review_missing_entrypoint`. Original calibration histories are preserved. Full SHA provenance remains outside its containing approval commit.

Review corrections include actual-input citation boundaries, preserved recorded response metadata, strict schema and observation types, provenance validation, generic check IDs, and rejection before artifact writes on collisions, dirty demos and reapproval. Content digests are not signatures; local reviewer labels are not authenticated identity or human evaluation evidence.
