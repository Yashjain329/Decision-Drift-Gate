# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). There is no tagged release yet, so everything is under Unreleased. The package version in `ddg/__init__.py` is `0.1.0`.

## [Unreleased] (`master`, 12 October 2026)

### Added

- **Browser viewer rebuilt in Next.js + TypeScript** (`web/`). Seven pages (Overview, Decisions, Check Studio, Runs & Regressions, Approvals, Reports, Providers & CLI) in the Obsidian / Signal Lime design (see `DESIGN.md`): signal-first summaries, evidence behind disclosures, human state labels with the raw enum as secondary text, base trusted / head untrusted framing, and a downloadable audit report. `next build` writes a static export to `web/out`, which `ddg serve` serves from a confined, extension-allowlisted lookup with the session token injected; Node is needed only to build.
- **Container sandbox** (`ddg/sandbox.py`). Reviewed code runs in Docker or Podman with no network, a read-only root, all capabilities dropped, `no-new-privileges`, a PID limit, memory and CPU limits, a non-root user and a 16 MB `noexec` tmpfs. The container is removed on every exit path, including when the runner raises an exception mid-run. `DDG_SANDBOX=auto|docker|podman|host` picks the runtime. `DDG_SANDBOX_IMAGE` sets the image (default `python:3.12-slim`); a custom image must be digest-pinned unless `DDG_SANDBOX_ALLOW_UNPINNED=1`. `sandbox.describe()` reports mode, image and whether it is pinned.
- **Fail-closed isolation.** With no usable runtime, checks end as NOT_CHECKED. Host execution needs `DDG_SANDBOX=host`. Reports record the isolation mode and mark `host` as UNSAFE.
- **Adapter registry** (`ddg/adapters/`). `python_job_client_v1` (the original job-client check) and `python_function_v1` (call one function in one stdlib-only module and assert on return values or exception types, up to 50 cases). The adapter id is part of the approval digest.
- **Git approver identity** (`ddg/identity.py`). `.ddg/approvers.json` is read from the base revision. A bundle counts only if every commit that touched it was authored by an allowed approver, changed nothing else, and, when `require_signed` is true, has a good signature. Otherwise the aggregate is INCOMPLETE with an `APPROVER_NOT_VERIFIED` warning. `DDG_ALLOW_UNVERIFIED_APPROVERS=1` allows a repository without a policy file.
- **Model providers** (`ddg/providers/`): `gemini_api`, `anthropic_api`, `openai_api` (and any OpenAI-compatible server), `bedrock` (Bedrock API key or boto3), `claude_cli`, `codex_cli` (subscription logins) and `custom_cli` (any command). `DDG_PROVIDER` / `--provider`, `DDG_MODEL` / `--model`, `DDG_PROVIDER_TIMEOUT`, and `ddg providers`. Drafts record provider, model, client version and the timeout used. See [docs/PROVIDERS.md](docs/PROVIDERS.md).
- **CLI for real repositories.** `ddg init`; `validate --calibration-bad/--calibration-good/--calibration-exception`; `propose --adapter`; `approve` without `--commit-demo` (writes three files and prints the paths); `run --sandbox` and `run --format json|md|both`; exit code 3 for usage and infrastructure errors.
- **Packaging.** `pyproject.toml` with a `ddg` console script, optional extras `[ai]` and `[bedrock]`, and a `Dockerfile` for a digest-pinned sandbox image.
- **GitHub Action** (`action.yml`, `scripts/pr_comment.py`, `.github/workflows/ddg.yml`). Runs `ddg run` on a pull request, uploads the report, upserts one PR comment, and maps the exit code to the job result. Tested offline against real reports; not yet run on GitHub.
- **Edge-case hardening.**
  - Git: hostile repository config (fsmonitor, hooks, pagers, external diff, textconv, gpg programs) no longer runs; symlinks, submodules and directories are never followed; shallow clones fail closed; merge history is walked with `--full-history`; SHA-256 repositories are rejected with a clear error; diffs are capped at 200 KB for display; a force-pushed or rebased approval by another author is rejected; an unreadable approver policy is an error, not "no policy".
  - Records: length caps on ids, rules, exceptions, rationale and quotes; NUL and lone surrogates rejected; no Unicode normalization; decision text embedded in prompts only as escaped JSON data; Markdown code fences always longer than any backticks they contain; environment variables with secret-looking names redacted from reports; report files written atomically.
  - Engine: edits to a superseded predecessor decision are now detected (the engine rebuilds the proposal inputs and requires them to match the recorded digest).
  - Sandbox: a worker is stopped after 1,000 protocol messages; image references are validated; stdout, stderr, fork-bomb, background-thread and closed-stdin abuse are tested.
- **Tests.** The suite is 370 tests at the merge commit: sandbox, adapters, identity, providers, git and record edge cases, a mutation-style tamper suite (35 tests that edit every JSON field of the authority files one at a time), an end-to-end suite in host and Docker modes (`tests/e2e/`), CLI and Action tests.
- Demo repositories include `.ddg/approvers.json` listing `ddg-demo@example.invalid`.

### Changed

- **Browser viewer redesign** (`web/`): a dark "Obsidian control surface" with Geist and Geist Mono (bundled, SIL Open Font License, served locally). The review screen shows the gate result and exit code, a state field with one slab per observed job for the target and the candidate against the check's expected count, and Detect / Explain / Enforce / Audit built from the report. Missing observations render as hatched "not observed", state is always paired with a label and glyph, motion respects `prefers-reduced-motion`, and the layout works at 390 px. Opening view follows the URL hash (`#decision`, `#approval`, `#review`). All element ids and the session-token meta tag are unchanged. Checked with Playwright (Chromium) against a live demo in four verdict states and a mobile layout; see the `ui-obsidian-*.png` images in `evidence/`.
- Approval no longer relies on the typed reviewer name. The Git author of the approval commit is what DDG checks.
- Reports show the isolation mode and the verified approver evidence. `ordinary_tests` is empty for runs that use only the function adapter.
- Usage and I/O errors exit with 3 instead of 2, so 2 now means only INCOMPLETE.
- A live proposal's time limit is configurable and recorded (it was fixed at 30 seconds). The default is still 30 seconds for APIs and 180 for CLI agents.
- `.env` is looked up in the current directory first.
- `pyproject.toml` lists the `ddg.adapters` and `ddg.providers` subpackages (they were missing from an earlier packaging draft).

### Fixed (security)

- **Harness tamper-proofing.** An audit showed that a head module could fake a PASS and run code on the host, because the fake service state lived in the same process as the code under test. The fake service and all recorded events now stay in the runner process, and the worker only forwards calls as JSON lines (`ddg/worker.py`). Regression test: `tests/test_harness.py::test_target_cannot_tamper_with_observed_service_state`.
- Edits to the superseded predecessor decision no longer pass silently (see Engine above).
- A side-branch edit by a non-approver, hidden by an `ours` merge, is now seen by the history walk.
- Low-level modules (`_io`, `_socket`, `_winapi`, `_posixsubprocess`, `_ctypes`) are rejected by the static screen. The screen remains best-effort.

### Known gaps

- The function adapter compares nested values by equality, so a nested `1.0` or `True` can match an expected `1`.
- A revision under test can return fabricated results for its own function. DDG detects accidental regressions, not a determined malicious author.
- The container timeout includes container start, so a loaded runner can produce a false NOT_CHECKED.
- Secret redaction in reports works on serialized text and can miss values that contain quotes or backslashes.
- `web` and `evidence` install as top-level packages next to `ddg`.
- Not built: SBOM, an Action input to pin the image digest, browser (Playwright) tests, AI proposals for the function adapter, a hosted service.

### Documentation

- Added [THREAT_MODEL.md](docs/THREAT_MODEL.md), [SECURITY.md](SECURITY.md), [UPGRADING.md](docs/UPGRADING.md), [PROVIDERS.md](docs/PROVIDERS.md), [PRODUCTIZATION_PLAN.md](docs/PRODUCTIZATION_PLAN.md) and [tests/e2e/README.md](tests/e2e/README.md). Rewrote the README. Added dated addenda to the status, checklist, evaluation and evidence documents; earlier recorded evidence is kept unchanged.

## History before this changelog

The synthetic-demo prototype (110 tests, 15 acceptance cases) is described in [docs/phases/STATUS.md](docs/phases/STATUS.md).
