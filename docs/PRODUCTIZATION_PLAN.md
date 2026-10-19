# Productization plan and outcome

**Decisions (12 October 2026):** CLI plus GitHub Action; Docker or Podman isolation; pluggable adapters, Python first; approver identity from Git (allowlist plus optional signatures); model providers beyond one vendor API, including CLI agents that use a subscription login.

**Outcome on `master`:** P1 to P8 are done and verified by 383 passing Python tests and 86 passing Playwright browser tests (19 October 2026, host and Docker modes) and a 15 of 15 acceptance run in Docker mode. Release `v0.1.0` is tagged. Items not built are listed under each phase and in [the changelog](../CHANGELOG.md). Nothing here claims a human evaluation or a measured review-time saving; neither exists.

## P1 Isolation - done
- `ddg/sandbox.py` runs the worker in a container: no network, read-only root, all capabilities dropped, `no-new-privileges`, PID, memory and CPU limits, non-root user, `noexec` tmpfs, source mounted read-only, wall-clock kill, container removed on every exit path.
- No silent host fallback. Host mode needs `DDG_SANDBOX=host` (there is no `--unsafe-host` flag; `ddg run --sandbox host` sets the same thing) and is marked UNSAFE in reports.
- Image policy: custom images must be digest-pinned unless `DDG_SANDBOX_ALLOW_UNPINNED=1`; `sandbox.describe()` reports whether the image is pinned.
- Evidence: `tests/test_sandbox.py`, `tests/test_sandbox_more.py` (network, writes, memory bomb, infinite loop, fork bomb, output floods, closed stdin, leftover-container checks, `docker inspect` of the real limits, an exact-flag pin test). Podman parity tests exist and skip when Podman is absent.
- Each report records `sandbox_image` (the image, and whether it is digest-pinned) next to the `sandbox` mode. The Markdown report and the PR comment show it.

## P2 Adapter interface - done
- `ddg/adapters/`: a registry whose modules must provide `NAME`, `validate_body`, `source_path`, `observe`, `ordinary`, `expected_case`. Adapters: `python_job_client_v1` and `python_function_v1`. The adapter id is part of the approval digest.
- Not done: model proposals for `python_function_v1`; adapters for other languages; call-count assertions on declared fakes.

## P3 Identity and approval - done
- `ddg/identity.py`: `.ddg/approvers.json` at base; author allowlist; approval commits may touch only the three artifact folders; optional good-signature requirement; full-history walk; evidence in reports.
- Not done: binding approval to a GitHub pull request review.

## P4 Packaging and CI - done except as noted
- `pyproject.toml` with the `ddg` script and `[ai]` and `[bedrock]` extras (installed and run in a fresh virtual environment); `Dockerfile` with a digest-pinned base; `ddg init`; `--calibration-*`, `--sandbox`, `--format`; exit codes 0, 1, 2, 3.
- GitHub Action (`action.yml`, `scripts/pr_comment.py`, `.github/workflows/ddg.yml`). Verified on GitHub on 13 October 2026: on a test repository, four pull requests (regression, unrelated change, allowed exception, policy edit) got FAILED, PASSED_CHECKS, PASSED_CHECKS and INCOMPLETE, each with one PR comment and the Docker sandbox. This repository now gates its own pull requests with an approved check (`.ddg/`, CHK-001).
- The `sandbox-image` input sets `DDG_SANDBOX_IMAGE`. Pass an image pinned by digest.
- The wheel installs only the `ddg` package. The built viewer and the recorded capture install as `ddg/_viewer` and `ddg/_evidence`. `tests/test_packaging.py` builds the wheel offline and checks this.

## P5 Edge-case hardening - done
Covered by tests: shallow clones, detached heads, merge commits, renamed, deleted, binary, empty and non-UTF-8 source, CRLF, symlinks and submodules (under `.ddg` and as source), huge diffs, SHA-256 repositories (rejected), history rewrite after approval, hostile repository configuration, duplicate decision ids, supersession cycles, a check naming a superseded decision, length caps and odd Unicode, prompt-injection text in decisions, report writing to bad paths and concurrent writers, report escaping, concurrent `compare` calls, stale reports after force-push, and clock skew.
- Known gaps: the function adapter compares nested values by equality (a nested `1.0` or `True` can match `1`); secret redaction works on serialized text; a newline in a filename could not be tested on Windows; the hostile `gpg.program` hardening has no control test.

## P6 End-to-end suite - done except as noted
- `tests/e2e/`: the real CLI as subprocesses in host and Docker modes (demo lifecycle, ten scenario branches, function adapter, unapproved author, stale report, `serve` over HTTP). `tests/test_cli_real.py` covers a new repository with no demo marker.
- `tests/test_tamper.py`: every JSON field of the authority files mutated one at a time (35 tests, about 25 minutes).
- `web/e2e/`: Playwright tests of the browser viewer against real `ddg serve` instances (routing, the full lifecycle, all scenarios, edge cases, altered states, seven breakpoints, keyboard, axe WCAG scans, and the read-only view of a real repository).

## P7 Release - done
- `CHANGELOG.md`, `SECURITY.md`, `docs/THREAT_MODEL.md`, `docs/UPGRADING.md`, `docs/PROVIDERS.md`, `docs/TRY_IT.md`, versioned package (`0.1.0`), tag `v0.1.0`.
- SBOM: `sbom/viewer.cdx.json` (CycloneDX, the npm packages of the viewer). The Python package has no runtime dependencies. See `sbom/README.md`.
- Not done: publishing to PyPI; a default sandbox image pinned by digest (the default stays the `python:3.12-slim` tag, and reports mark it as not pinned).

## P8 Model providers - done
- `ddg/providers/`: Gemini API, Anthropic API, OpenAI-compatible, Bedrock, Claude Code CLI, Codex CLI and any command. Provider, model, client version and time limit are recorded in the draft. See [PROVIDERS.md](PROVIDERS.md).
- Verified by 38 tests in `tests/test_providers.py` (33 unit tests with fake transports and scripts, and 5 full-lifecycle tests with non-Gemini providers), and one manual run each of `claude_cli` and `codex_cli` with a trivial prompt. Not verified: any API provider against its real service, Bedrock, or a full proposal on a real decision through a CLI agent. `docs/TRY_IT.md` Part 2 describes that test for other developers.
- Considered and rejected: depending on a separate routing service. A single human-approved proposal per decision does not need cost-based routing, a ledger or reservations.

## Not in scope
Hosted multi-tenant service, JS/TS/Go adapters, auto-merge or auto-fix behaviour.
