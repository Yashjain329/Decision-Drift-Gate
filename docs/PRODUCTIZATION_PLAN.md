# Productization plan

**Decisions (12 Oct 2026):** CLI + GitHub Action; Docker/Podman isolation; pluggable adapters, Python first; approver identity from Git (signed commits + allowlist).

Each phase ships with its tests and is accepted only when its exit gate passes. No phase weakens an earlier gate.

## P1 Isolation (blocks everything else) - DONE
- `ddg/sandbox.py`: run the worker in a container: `--network none --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit --memory --cpus --user nobody`, tmpfs scratch, code mounted read-only, hard wall-clock kill, container removed on every exit path.
- Runtime selection: `docker` or `podman`; no silent host fallback. The old mode needs `DDG_SANDBOX=host` (a `--unsafe-host` flag was planned; the code uses the environment variable) and is recorded in every report.
- Exit gate: escape attempts (network, write outside scratch, fork bomb, memory bomb, infinite loop, huge stdout) each yield `NOT_CHECKED`/`FAIL`, never a hang or a host effect.

## P2 Adapter interface - DONE (job_client_v1, python_function_v1; AI proposals remain job-only)
- `Adapter` protocol: `validate_check`, `scenarios`, `run(source, scenario) -> Observation`, `fingerprint`. Existing job-client logic becomes `adapters/job_client.py` unchanged in behaviour.
- Second adapter: generic Python function-behaviour adapter (call a named function with declared inputs, assert on return value / exception type / call counts of declared fakes).
- Adapter id and version are part of the approval digest.
- Exit gate: the 15-case matrix still matches on the job adapter; a new matrix passes for the generic adapter.

## P3 Identity and approval - DONE (author allowlist, mixed-path rule, signature check; no PR-review binding)
- Approval is a commit touching only `.ddg/approvals|checks|validations`, authored by a member of `.ddg/approvers` (read from **base**), with a verified SSH/GPG signature when `require_signed: true`.
- Remove typed-name trust. Reports show the verified author and signature status.
- Exit gate: unsigned, wrong-author, mixed-path and force-pushed-history approvals are rejected.

## P4 Packaging and CI - in progress (batch run)
- `pyproject.toml`, `ddg` console script, pinned optional `[ai]` extra, versioned sandbox image built from a pinned base.
- GitHub Action (composite): checks out base+head, runs `ddg run`, uploads JSON/Markdown report, posts a PR comment and a check conclusion (`success/failure/neutral` for INCOMPLETE).
- Exit-code contract documented and tested (0 pass, 1 failed, 2 incomplete, 3 usage/infra).
- Exit gate: workflow passes on a fixture repository in CI for regression, correction, exception and policy-edit PRs.

## P5 Edge-case hardening - in progress (batch run)
Enumerated and each covered by a test: shallow clones, detached heads, merge commits, renamed/deleted/binary source, CRLF, non-UTF-8, symlinks and submodules in `.ddg`, huge diffs, SHA-256 repos, concurrent runs, report written to read-only path, clock skew, provider outage / malformed model output / prompt-injection text inside decisions, duplicate decision ids, supersession cycles, check referencing a superseded decision, stale reports after force-push.

## P6 End-to-end suite - in progress (batch run)
- `tests/e2e/`: fresh temp repo -> `ddg init` -> propose (recorded) -> validate -> approve (signed) -> PR branches -> `ddg run` in container -> assert exit codes and report contents. Runs in CI on Linux; container tests auto-skip with a visible reason when no runtime exists.
- Browser e2e (Playwright) for the local viewer: full lifecycle, stale report, narrow viewport.
- Mutation-style negative suite: every tampering of check, validation, approval, decision or head policy must change the verdict to `INCOMPLETE`.

## P7 Release - in progress (batch run; docs: threat model, SECURITY.md, CHANGELOG, UPGRADING written; SBOM and pinned image digest not yet)
- Versioning, CHANGELOG, SBOM, image digest pinned in the Action, security policy, threat model document, upgrade path for existing approved bundles.

## Not in scope
Hosted multi-tenant service, JS/TS/Go adapters, auto-merge or auto-fix behaviour.
