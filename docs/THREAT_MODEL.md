# Threat model

**Scope:** the Decision Drift Gate (DDG) code in `ddg/` as of commit `bbb0e33` plus the planned work marked "planned". Every control below names the file or test that shows it. If a control is not listed, assume it does not exist.

## What DDG decides

DDG compares two Git revisions. The **base** is the revision you trust. The **head** is the revision under review. DDG runs the checks that were approved at base against both revisions and reports PASSED_CHECKS, FAILED or INCOMPLETE.

## Assets

| Asset | Why it matters |
|---|---|
| The verdict (PASS/FAIL/INCOMPLETE) | A wrong PASS lets old behaviour return. |
| Approved bundles: `.ddg/checks`, `.ddg/validations`, `.ddg/approvals` | They decide what is enforced. |
| `.ddg/approvers.json` | It decides who may approve. |
| `.ddg/decisions/` | It holds the rules that checks cite. |
| The CI runner and its secrets | The head code runs near them. |
| Model API key (optional, proposal step only) | Executing a check never needs it. |

## Trust boundaries

1. **Base is the authority.** `ddg/engine.py` reads decisions, checks, validations, approvals and the approver policy from the base commit only. A head that edits these files makes the result INCOMPLETE (policy-change warning); it cannot remove a check.
2. **Head is untrusted.** Its source module is read from Git as text, screened, copied to a temporary directory and run in a worker.
3. **Approvers file.** `.ddg/approvers.json` at base lists approver emails and `require_signed` (`ddg/identity.py`). A bundle is trusted only if every commit that touched its three artifacts was authored by an allowed approver and touched nothing else. With `require_signed: true`, each such commit also needs a good signature (`git log %G?` equal to `G`).
4. **Container.** The worker runs in Docker or Podman (`ddg/sandbox.py`). This is the only boundary that limits what hostile head code can do.
5. **Host.** The Python process that runs DDG. It owns the fake service and all recorded observations. The worker reaches the service only through JSON lines (`ddg/worker.py`), so head code cannot edit the evidence.

## Attacker capabilities assumed

- A contributor can open a pull request and control every file in the head revision, including the Python module under test.
- The contributor can edit `.ddg/` files in the head, add commits that look like approvals, and set any author name or email on a commit.
- The contributor cannot push to the base branch and cannot change the CI workflow that runs on the base branch.

## What the container stops

Controls from `container_argv` in `ddg/sandbox.py`, checked by `tests/test_sandbox.py` (container tests skip when no runtime exists).

| Threat | Control |
|---|---|
| Network access | `--network none` |
| Writes to the filesystem | `--read-only`; source and worker mounted `:ro`; only `/tmp` is writable (tmpfs, 16 MB, `noexec`) |
| Memory exhaustion | `--memory 128m --memory-swap 128m` |
| CPU exhaustion | `--cpus 0.5` and a wall-clock timeout; DDG kills and removes the container on every exit path |
| Fork bombs | `--pids-limit 64` |
| Privilege | `--cap-drop ALL`, `--security-opt no-new-privileges`, `--user 65534:65534` |
| Large output | Worker output is size-limited; an oversized message is an error |
| Secrets in the environment | Container gets only `PYTHONDONTWRITEBYTECODE` and `PYTHONIOENCODING`; host mode passes a small allowlist (`small_environment`) |
| Silent host execution | If no runtime works, the run is NOT_CHECKED. Host mode needs `DDG_SANDBOX=host` and the report says "UNSAFE" (`ddg/report.py`) |
| Head code faking a PASS | The fake service and events live in the host process; the worker is a JSON proxy (`tests/test_harness.py::test_target_cannot_tamper_with_observed_service_state`) |

## What the container does NOT stop

- **Kernel and container-runtime escapes.** A container shares the host kernel. A kernel or runtime bug can let hostile code out. DDG adds no seccomp or user-namespace profile beyond the runtime defaults.
- **Side channels.** Timing, cache and resource-contention channels are not addressed.
- **A malicious approver.** An allowed approver can approve a check that enforces nothing, or a check that is wrong. DDG verifies who approved, not whether the check is good.
- **A compromised base branch.** If an attacker can write to base, they can change checks, approvers and decisions. DDG trusts base by design.
- **Forged author email without `require_signed`.** Git author email is free text. With `require_signed: false`, anyone who knows an approver's email can author a commit as that approver. Use `require_signed: true`.
- **Compromised signing key or allowed-signers file.** Signature checks rely on `gpg.ssh.allowedSignersFile` or a GPG keyring being configured on the runner. DDG does not manage them. The `signature` status code comes from Git.
- **Runner compromise.** If the CI runner or Docker daemon is compromised, nothing DDG reports can be trusted.
- **Image supply chain.** The default image is `python:3.12-slim` (`DDG_SANDBOX_IMAGE`). It is pulled by tag, not by digest. A poisoned image runs with the same limits but controls the interpreter.
- **Head code that lies inside its own scope.** Head code controls its return values. DDG checks the behaviour it can observe through the fake service, not intent.

## The static import screen is best-effort

Before launch, `harness._external_import_error` parses the head module and rejects names such as `os`, `subprocess`, `socket`, `eval`, `exec`, `open` and non-stdlib imports. Both adapters use it. It is not a security control. Python can reach these features by indirect routes, and the screen only reads source text. Its job is to give a clear error for ordinary mistakes. The container is the boundary.

## Residual risks and mitigations

| Residual risk | Mitigation (operator action) |
|---|---|
| Someone edits the approver list or the workflow on base | Branch protection and required review on `.ddg/approvers.json`, `.ddg/**` and `.github/workflows/**` (CODEOWNERS plus protected base branch). |
| Forged author email | Set `"require_signed": true`. Sign approval commits. Configure `gpg.ssh.allowedSignersFile` (or a GPG keyring) on the runner. |
| Image tag changes under you | Set `DDG_SANDBOX_IMAGE` to an image pinned by digest (`name@sha256:...`). Build and review your own image. The planned Action pins a digest (see Planned). |
| Runner holds secrets | Use ephemeral runners. Do not run DDG on fork code in a privileged workflow (for example `pull_request_target` with secrets). |
| Container escape | Keep the runtime and kernel patched. Use rootless Podman where possible. Treat the runner as disposable. |
| History rewritten after approval | Identity checks read history reachable from base. A shallow clone fails closed ("No commit history", see `ddg/identity.py`). Fetch full history. Protect the base branch against force-push. |
| Unverified mode left on | `DDG_ALLOW_UNVERIFIED_APPROVERS=1` accepts a repository with no policy file and marks approvers as unverified. Do not set it in CI. |

## Planned (not in the code at this commit)

- Action input to pin the sandbox image by digest and a versioned image build.
- Stronger edge-case coverage (shallow clones, merge commits, symlinks) in Phase P5.
- An SBOM for releases (P7).

Track these in [the productization plan](PRODUCTIZATION_PLAN.md).

## Reporting

See [SECURITY.md](../SECURITY.md).
