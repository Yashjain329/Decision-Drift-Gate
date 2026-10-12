# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). There is no tagged release yet, so everything is under Unreleased.

## [Unreleased]

### Added (in the code at commit `bbb0e33`)

- **Container sandbox** (`ddg/sandbox.py`). The worker runs in Docker or Podman with no network, a read-only root, all capabilities dropped, `no-new-privileges`, a PID limit, memory and CPU limits, a non-root user and a 16 MB tmpfs. The container is removed on every exit path. `DDG_SANDBOX=auto|docker|podman|host` picks the runtime; `DDG_SANDBOX_IMAGE` sets the image (default `python:3.12-slim`).
- **Fail-closed isolation.** With no usable runtime, checks end as NOT_CHECKED. Host execution needs `DDG_SANDBOX=host`. Reports record the isolation mode and mark `host` as UNSAFE.
- **Adapter registry** (`ddg/adapters/`). Two adapters: `python_job_client_v1` (the original job-client check, moved unchanged in behaviour) and `python_function_v1` (call one function in one stdlib-only module and assert on its return value or exception type). The adapter id is part of the approval digest.
- **Git approver identity** (`ddg/identity.py`). The policy file `.ddg/approvers.json` is read from the base revision. A bundle counts only if every commit that touched it was authored by an allowed approver, changed nothing else, and (when `require_signed` is true) has a good signature. Otherwise the aggregate is INCOMPLETE with an `APPROVER_NOT_VERIFIED` warning. `DDG_ALLOW_UNVERIFIED_APPROVERS=1` allows a repository without a policy file.
- Demo repositories now include `.ddg/approvers.json` listing `ddg-demo@example.invalid`.
- Tests for the sandbox, adapters and identity. The suite is 144 tests at this commit.

### Changed

- Approval no longer relies on the typed reviewer name. The Git author of the approval commit is what DDG checks.
- Reports show the isolation mode and the verified approver evidence.

### Fixed (security)

- **Harness tamper-proofing.** An earlier audit showed that a head module could fake a PASS and run code on the host, because the fake service state lived in the same process as the code under test. The fake service and all recorded events now stay in the runner process. The worker only forwards calls as JSON lines (`ddg/worker.py`). The worker also runs in the container. Regression test: `tests/test_harness.py::test_target_cannot_tamper_with_observed_service_state`.

### Planned (not in the code at `bbb0e33`; other work in the same batch)

These are being added in parallel. Verify each after merge before relying on it.

- Packaging: `pyproject.toml`, a `ddg` console script, a pinned optional `[ai]` extra, a versioned sandbox image.
- CLI for real repositories: `ddg init`, `--calibration-*` flags, `--sandbox`, `--format`, and exit code 3 for usage or infrastructure errors.
- A GitHub Action that runs `ddg run`, uploads the report, comments on the PR and sets a check conclusion.
- Edge-case hardening (shallow clones, merge commits, symlinks, SHA-256 repositories and others listed in the plan).
- End-to-end tests (`tests/e2e/`).
- Release items: SBOM, image digest pinned in the Action.

### Documentation

- Added [THREAT_MODEL.md](docs/THREAT_MODEL.md), [SECURITY.md](SECURITY.md) and [UPGRADING.md](docs/UPGRADING.md).
- Added dated addenda to the status, checklist, evaluation and evidence documents. Earlier recorded evidence is kept.

## History before this changelog

The synthetic-demo prototype (110 tests, 15 acceptance cases) is described in [docs/phases/STATUS.md](docs/phases/STATUS.md).
