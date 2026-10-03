# Phase 01 accepted foundation

Delivered commits: `84546e6` (Git reads and synthetic history), `2bd447b` (strict check schema and behavioral runner).

The orchestrator independently ran `python -m unittest discover -s tests -v` after review corrections: **34 tests passed in 29.644 seconds**, exit 0. Earlier integration runs exposed issues and are not acceptance evidence. Worker handoffs record their actual failing and passing test cycles.

Independent Sol High review identified default Windows codepage corruption, malformed child-protocol handling, and dynamic import mechanisms outside the supported adapter. All were corrected and included in the passing suite. This is bounded execution of trusted synthetic source, not a malicious-code sandbox.

Stable interfaces: `contracts.validate_check`, `canonical_bytes`, `digest`; `gitio.resolve_commit`, `read_at`, source-only `diff_at`; `demo.build_demo`; `harness.observe` and `observe_happy_path`. Check adapter/version is `python_job_client_v1`. Successful completion remains mandatory independently of candidate assertion values.

Synthetic repositories have a path-bound ignored `.ddg-demo.json` marker with full commit SHAs. The checkout ends on `calibration-good`; fixture operations preserve source and parent workspace.

Next phase extends decision/citation contracts, generates a grounded proposal, calibrates it, and binds approval to exact artifact bytes. Gemini access has been verified through model listing; no proposal has yet been captured.
