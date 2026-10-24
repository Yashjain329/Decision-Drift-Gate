# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version 0.1.0 is the first tagged release (`v0.1.0`). It is not published to PyPI. Install it from the tag or from the wheel on the [release page](https://github.com/Yashjain329/Decision-Drift-Gate/releases/tag/v0.1.0).

## [Unreleased]

### Added

- **Anthropic API as the second API provider.** `anthropic_api` now uses the official `anthropic` SDK (optional extra `[anthropic]`) and defaults to Claude Haiku 5.5 (`claude-haiku-5-5`); `DDG_MODEL` or `DDG_ANTHROPIC_MODEL` overrides it. With no `DDG_PROVIDER`, the configured key picks the provider: `GEMINI_API_KEY` first, then `ANTHROPIC_API_KEY`. `ddg providers` shows the resolved default. Refusals and answers cut off at `max_tokens` are provider errors. It is tested offline through the SDK with a mock transport; no live Anthropic call has been made yet.

### Changed

- **No fixed repository layout.** `python_job_client_v1` reads the module named by the governing decision's `scope` instead of a fixed `src/job_client.py`. The scope must be a repository `.py` path, and it is already bound by the approved input digest. Existing demo bundles are unchanged: their scope is `src/job_client.py`.
- **Decision and check ids.** `ddg propose` no longer defaults to `DEC-002`. It uses the only active decision that supersedes another and asks for `--decision` when there are several. Model proposals use `--check-id` or the next free `CHK-NNN` instead of always `CHK-001`.
- **Ordinary tests** (the no-fault job submission) run only for an approved job-client check's module, never against a hard-coded path.

### Fixed

- **Clearer missing-commit error.** When the commit a check was proposed from cannot be read, the run warning names the commit and the cause (missing commit, missing decision records, or missing target module). Before, every case said `shallow or rewritten history?`.
- `tests/test_proposal.py` no longer needs the optional `google-genai` package installed.

## [0.1.0] - 2026-10-19

### Added

- **Release packaging.** The wheel installs only the `ddg` package. The built viewer and the recorded capture install inside it as `ddg/_viewer` and `ddg/_evidence`, so no generic `web` or `evidence` package lands in site-packages. `ddg.viewer_dir()` and `ddg.recorded_capture()` use the installed copy and fall back to the source checkout. `tests/test_packaging.py` builds the wheel offline and checks the layout.
- **Sandbox image in reports.** Each report has `sandbox_image` (the image, and whether it is digest-pinned). The Markdown report and the PR comment show it. The Action input `sandbox-image` sets `DDG_SANDBOX_IMAGE`.
- **SBOM.** `sbom/viewer.cdx.json` (CycloneDX 1.5) lists the npm packages of the viewer. Regenerate it with `npm run sbom` in `web/`. The Python package has no runtime dependencies.
- **Self-gating.** This repository has an approved check (`.ddg/`, CHK-001 on `validate_decisions`), and its pull requests run it through the Action.
- **Developer guide.** `docs/TRY_IT.md`: the demo, a live proposal through Claude Code or Codex, a first check on your own repository, and how to report results.

- **Browser viewer for real repositories.** `ddg serve` on a repository without the demo marker opens a read-only view: the approved bundle at `--base` (default `HEAD`) and an optional saved report (`--report`). Every action request is refused with 403; the UI hides or locks its controls and says to use the CLI. `python_function_v1` checks get a per-case matrix (one row per assertion, pass or fail per revision) in Check Studio and the Run Inspector instead of the job-count charts, and the session chart counts failing cases on head. Covered by `tests/test_web_repository.py` and `web/e2e/repository.spec.ts`.
- **UI end-to-end suite** (`web/e2e/`, Playwright). 76 tests against real `ddg serve` instances in Docker and host modes: routing, the full UI lifecycle, all 12 scenarios checked against the engine report, edge cases (engine down, forged token, double submit, stale refs, host isolation, provider failure), altered-state honesty checks, seven breakpoints, keyboard, reduced motion and an axe WCAG 2.1 A/AA scan. Fixes found by it: legacy hash aliases are rewritten to the canonical view; the session chart keeps its id once populated; scrollable JSON and diff blocks are keyboard-focusable; zero-count outcomes meet contrast; a run without a recorded isolation mode reads "not recorded" instead of "no run yet".
- **Browser viewer rebuilt in Next.js + TypeScript** (`web/`). Seven pages (Overview, Decisions, Check Studio, Runs & Regressions, Approvals, Reports, Providers & CLI) in the Obsidian / Signal Lime design (see `DESIGN.md`): signal-first summaries, evidence behind disclosures, human state labels with the raw enum as secondary text, base trusted / head untrusted framing, and a downloadable audit report. `next build` writes a static export to `web/out`, which `ddg serve` serves from a confined, extension-allowlisted lookup with the session token injected; Node is needed only to build.
- **Container sandbox** (`ddg/sandbox.py`). Reviewed code runs in Docker or Podman with no network, a read-only root, all capabilities dropped, `no-new-privileges`, a PID limit, memory and CPU limits, a non-root user and a 16 MB `noexec` tmpfs. The container is removed on every exit path, including when the runner raises an exception mid-run. `DDG_SANDBOX=auto|docker|podman|host` picks the runtime. `DDG_SANDBOX_IMAGE` sets the image (default `python:3.12-slim`); a custom image must be digest-pinned unless `DDG_SANDBOX_ALLOW_UNPINNED=1`. `sandbox.describe()` reports mode, image and whether it is pinned.
- **Fail-closed isolation.** With no usable runtime, checks end as NOT_CHECKED. Host execution needs `DDG_SANDBOX=host`. Reports record the isolation mode and mark `host` as UNSAFE.
- **Adapter registry** (`ddg/adapters/`). `python_job_client_v1` (the original job-client check) and `python_function_v1` (call one function in one stdlib-only module and assert on return values or exception types, up to 50 cases). The adapter id is part of the approval digest.
- **Git approver identity** (`ddg/identity.py`). `.ddg/approvers.json` is read from the base revision. A bundle counts only if every commit that touched it was authored by an allowed approver, changed nothing else, and, when `require_signed` is true, has a good signature. Otherwise the aggregate is INCOMPLETE with an `APPROVER_NOT_VERIFIED` warning. `DDG_ALLOW_UNVERIFIED_APPROVERS=1` allows a repository without a policy file.
- **Model providers** (`ddg/providers/`): `gemini_api`, `anthropic_api`, `openai_api` (and any OpenAI-compatible server), `bedrock` (Bedrock API key or boto3), `claude_cli`, `codex_cli` (subscription logins) and `custom_cli` (any command). `DDG_PROVIDER` / `--provider`, `DDG_MODEL` / `--model`, `DDG_PROVIDER_TIMEOUT`, and `ddg providers`. Drafts record provider, model, client version and the timeout used. See [docs/PROVIDERS.md](docs/PROVIDERS.md).
- **CLI for real repositories.** `ddg init`; `validate --calibration-bad/--calibration-good/--calibration-exception`; `propose --adapter`; `approve` without `--commit-demo` (writes three files and prints the paths); `run --sandbox` and `run --format json|md|both`; exit code 3 for usage and infrastructure errors.
- **Packaging.** `pyproject.toml` with a `ddg` console script, optional extras `[ai]` and `[bedrock]`, and a `Dockerfile` for a digest-pinned sandbox image.
- **GitHub Action** (`action.yml`, `scripts/pr_comment.py`, `.github/workflows/ddg.yml`). Runs `ddg run` on a pull request, uploads the report, upserts one PR comment, and maps the exit code to the job result. Verified on GitHub on 13 October 2026 with FAILED, PASSED_CHECKS and INCOMPLETE pull requests.
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
- The default sandbox image is the `python:3.12-slim` tag, not a digest. Reports mark it as not pinned. Pin it with `sandbox-image` or `DDG_SANDBOX_IMAGE`.
- The function adapter accepts only modules that import no process, file or network modules.
- Not built: PyPI publishing, AI proposals for the function adapter, adapters for other languages, a hosted service.
- No human evaluation and no measured review-time saving.

### Documentation

- Added [THREAT_MODEL.md](docs/THREAT_MODEL.md), [SECURITY.md](SECURITY.md), [UPGRADING.md](docs/UPGRADING.md), [PROVIDERS.md](docs/PROVIDERS.md), [PRODUCTIZATION_PLAN.md](docs/PRODUCTIZATION_PLAN.md) and [tests/e2e/README.md](tests/e2e/README.md). Rewrote the README. Added dated addenda to the status, checklist, evaluation and evidence documents; earlier recorded evidence is kept unchanged.

## History before this changelog

The synthetic-demo prototype (110 tests, 15 acceptance cases) is described in [docs/phases/STATUS.md](docs/phases/STATUS.md).

[Unreleased]: https://github.com/Yashjain329/Decision-Drift-Gate/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Yashjain329/Decision-Drift-Gate/releases/tag/v0.1.0
