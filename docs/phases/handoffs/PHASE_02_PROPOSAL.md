# Phase 02 handoff: grounded AI proposal and decision governance

Implemented the proposal and governance boundary in the assigned source files:

- `ddg/proposal.py`: pinned context loading, content-only input hashing, exact citation grounding, explicit manual/recorded/live proposal modes, bounded JSON-schema repair, a 30-second Gemini request timeout, and a sealed proposal envelope.
- `ddg/contracts.py`: strict decision record validation, duplicate/missing predecessor/cycle rejection, and competing-active-decision rejection.
- `ddg/gitio.py`: `list_at(repo, sha, prefix)` for tracked paths at a pinned commit, with Git quote handling enabled.
- `tests/test_proposal.py` and `tests/test_governance.py`: offline behavior and failure cases.
- `requirements-ai.txt` and `.env.example`: optional SDK pin and local configuration template.
- `evidence/gemini-proposal.json`: sanitized output from a real Gemini call on synthetic decision/source inputs.

`load_context` reads both decision records and `src/job_client.py` at one resolved commit. The provider receives only the predecessor, replacement decision, corrected source, adapter version, prompt version, and fixed vocabulary; holdout/calibration refs and expected outcomes are excluded. `input_digest` excludes the source SHA. Proposal validation accepts citations only from the old/new decision pair, requires an active new decision and matching `supersedes`, checks exact quote substrings, and requires a citation to the governing decision.

`draft_digest` hashes the whole draft envelope except its own digest field. Recorded mode verifies the original envelope fingerprint and exact content input digest, then keeps the captured model/time/SDK/request/response provenance and original source SHA while binding a new draft to the current source SHA. Manual drafts carry null AI provenance and require an explicit check body. Provider exceptions are converted to a generic error; keys and raw error details are never included in the draft or logs.

## Verification evidence

TDD was used for the new behavior. Initial RED runs failed on missing `ddg.proposal` and `validate_decisions`. A reviewer regression test for citing an unrelated active decision also failed before its fix because the proposal accepted the extra decision from full context; after narrowing validation to the two supplied decisions it passes. A recorded-capture provenance assertion failed before preserving the captured sanitized response and passed after the fix.

Final offline command:

```powershell
python -m unittest tests.test_proposal tests.test_governance tests.test_contracts tests.test_gitio tests.test_demo tests.test_harness -v
```

Result: **51 tests passed**.

A real call completed using `.venv`, model `gemini-3.8-flash`, google-genai `2.28.0`, at `2026-10-03T18:19:56.974766Z`. The captured check is CHK-001 for DEC-002, with `commit_then_503`, `unique_jobs = 1`, and `returned_job_exists = true`. Capture input digest: `1c989add39089f031714f92738d4ea1ef6b6c18ab6c16967e90baa5d00c32a4c`. Draft digest: `5391f7a4fa3ac58a27c21d7e55b1a1802b6e1468bf7156025a9d7e685fb0a07b`. Captured source SHA: `2ce6713f7d834722e01592e304f07fe5a62a3b11`.

Recorded replay was exercised on a freshly rebuilt synthetic history. It kept the same input digest and model/time/SDK, reported the rebuilt commit as current `source_sha`, and retained the capture commit separately as `capture_source_sha`. No external customer data was used. No phase commit was created; Git staging and commits remain with the orchestrator.

## Phase 03 interfaces

- `load_context(repo, decision_id="DEC-002", revision=None) -> dict`
- `input_digest(context) -> str`
- `wrap_draft(context, check, mode="manual", model=None) -> dict`
- `propose(context, mode="live", client=None) -> dict`
- `validate_decisions(records) -> dict[id, record]`
- `validate_citations(check, decisions) -> validated check`
- `list_at(repo, sha, prefix) -> list[str]`

A draft includes `check`, `draft_digest`, `input_digest`, `decision`, `proposal_mode`, `model`, `captured_at`, `source_sha`, `adapter_version`, `sdk_version`, `capture_source_sha`, `request_metadata`, `provider_response`, and sanitized `attempts`. Approval must recompute the full draft digest. Real live evidence exists at `evidence/gemini-proposal.json`; the example under `examples/manual_check.json` remains a hand-authored sample.
