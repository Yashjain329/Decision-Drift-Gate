# Threat model

**Scope:** the Decision Drift Gate (DDG) code in `ddg/` on `master` as of 12 October 2026. Every control below names the file or test that shows it. If a control is not listed, assume it does not exist.

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
| Model credentials and subscription logins (optional, proposal step only) | Executing a check never needs them. API keys, AWS credentials and the Claude Code or Codex login all live on the machine that drafts proposals. |

## Trust boundaries

1. **Base is the authority.** `ddg/engine.py` reads decisions, checks, validations, approvals and the approver policy from the base commit only. A head that edits these files makes the result INCOMPLETE (policy-change warning); it cannot remove a check.
2. **Head is untrusted.** Its source module is read from Git as text (regular files only; symlinks, submodules and directories are refused), screened, copied to a temporary directory and run in a worker. Git itself is run with repository-local code execution switched off (`ddg/gitio.py`; `tests/test_edge_git.py` proves a hostile config does not fire).
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
| Runner memory growth from a chatty worker | The runner stops a worker after 1,000 protocol messages and rejects any message over 1 MiB (`ddg/harness.py`, `tests/test_sandbox_more.py`) |
| Silent host execution | If no runtime works, the run is NOT_CHECKED. Host mode needs `DDG_SANDBOX=host` and the report says "UNSAFE" (`ddg/report.py`) |
| Head code editing the evidence (job adapter) | The fake service and events live in the host process; the worker is a JSON proxy (`tests/test_harness.py::test_target_cannot_tamper_with_observed_service_state`) |
| Hostile Git configuration or history tricks | Hooks, fsmonitor, pagers, external diff, textconv and gpg programs are disabled; symlinks and submodules are never followed; shallow clones and SHA-256 repositories fail closed; merge history is walked in full (`tests/test_edge_git.py`) |
| Edited authority files | Every JSON field of the check, validation, approval, decision and approver files is mutated one at a time in `tests/test_tamper.py`; none yields a pass. Editing the superseded predecessor decision is caught through the recorded input digest. |

## What the container does NOT stop

- **Kernel and container-runtime escapes.** A container shares the host kernel. A kernel or runtime bug can let hostile code out. DDG adds no seccomp or user-namespace profile beyond the runtime defaults.
- **Side channels.** Timing, cache and resource-contention channels are not addressed.
- **A malicious approver.** An allowed approver can approve a check that enforces nothing, or a check that is wrong. DDG verifies who approved, not whether the check is good.
- **A compromised base branch.** If an attacker can write to base, they can change checks, approvers and decisions. DDG trusts base by design.
- **Forged author email without `require_signed`.** Git author email is free text. With `require_signed: false`, anyone who knows an approver's email can author a commit as that approver. Use `require_signed: true`.
- **Compromised signing key or allowed-signers file.** Signature checks rely on `gpg.ssh.allowedSignersFile` or a GPG keyring being configured on the runner. DDG does not manage them. The `signature` status code comes from Git.
- **Runner compromise.** If the CI runner or Docker daemon is compromised, nothing DDG reports can be trusted.
- **Image supply chain.** The default image is `python:3.12-slim`, pulled by tag, not by digest, and `sandbox.describe()` reports it as not pinned. A custom `DDG_SANDBOX_IMAGE` must be digest-pinned unless `DDG_SANDBOX_ALLOW_UNPINNED=1` is set. The `Dockerfile` pins its base by digest, but the GitHub Action does not pin an image. A poisoned image runs with the same limits but controls the interpreter.
- **Head code that lies inside its own scope.** Head code controls its return values. DDG checks the behaviour it can observe, not intent. For `python_function_v1` the observation is the function's own output, so a revision that special-cases the check's inputs, or writes a forged result to the protocol stream, can return the expected answers. The container protects the host; it does not make the verdict trustworthy against a determined malicious author. DDG is a regression gate for honest mistakes. The review of the code change remains a human job.

## The static import screen is best-effort

Before launch, `harness._external_import_error` parses the head module and rejects names such as `os`, `subprocess`, `socket`, `eval`, `exec`, `open` and non-stdlib imports. Both adapters use it. It also rejects low-level modules such as `_io`, `_socket` and `_ctypes`. It is not a security control. Python can reach these features by indirect routes, and the screen only reads source text (the container tests deliberately use such routes and are contained). Its job is to give a clear error for ordinary mistakes. The container is the boundary.

## Model providers

The model step runs on the machine that drafts proposals, before and apart from the gate. A bad answer can only produce a draft that must pass schema checks, exact-quote citation checks, calibration and a human approval (`ddg/proposal.py`, `tests/test_providers.py`).

| Risk | Control | Remaining risk |
|---|---|---|
| Prompt injection in decision text | Decision text is embedded only as escaped JSON data in the prompt; the answer is parsed as data and never executed (`tests/test_edge_records.py`) | A model can still be persuaded to propose a weak check. Calibration and the human reviewer are the defence |
| Credential leakage | Keys come from the environment or a local `.env`; errors carry stable codes, never response bodies; HTTP providers need `https` (plain `http` only for localhost) and never follow redirects | A logged-in CLI or cloud profile is as exposed as the machine |
| CLI agents act on the host | `claude_cli` runs with all tools off, no settings and no session; `codex_cli` with a read-only sandbox and an ephemeral session; both in an empty temporary directory with a filtered environment | They are not in a container. A bug in the CLI is outside DDG's control |
| `custom_cli` runs any command | The command is set by the operator in `DDG_CLI_COMMAND` | Treat that setting as code. Do not let untrusted input set it |
| Proposals run in CI | They do not. Executing checks never calls a model | Keep provider credentials out of the review workflow |

## Residual risks and mitigations

| Residual risk | Mitigation (operator action) |
|---|---|
| Someone edits the approver list or the workflow on base | Branch protection and required review on `.ddg/approvers.json`, `.ddg/**` and `.github/workflows/**` (CODEOWNERS plus protected base branch). |
| Forged author email | Set `"require_signed": true`. Sign approval commits. Configure `gpg.ssh.allowedSignersFile` (or a GPG keyring) on the runner. |
| Image tag changes under you | Set `DDG_SANDBOX_IMAGE` to an image pinned by digest (`name@sha256:...`). Build and review your own image from the `Dockerfile`. |
| Runner holds secrets | Use ephemeral runners. Do not run DDG on fork code in a privileged workflow (for example `pull_request_target` with secrets). |
| Container escape | Keep the runtime and kernel patched. Use rootless Podman where possible. Treat the runner as disposable. |
| History rewritten after approval | Identity checks read history reachable from base. A shallow clone fails closed with a clear message (`ddg/gitio.py`). A replacement approval by another author, or a rebase that changes the author, is rejected. Fetch full history. Protect the base branch against force-push. |
| Unverified mode left on | `DDG_ALLOW_UNVERIFIED_APPROVERS=1` accepts a repository with no policy file and marks approvers as unverified. Do not set it in CI. |

## Not built

- An Action input to pin the sandbox image by digest.
- An SBOM for releases.
- Report secret redaction that works on structured values (today it works on serialized text and can miss values containing quotes or backslashes).
- A Playwright test of the browser viewer. The viewer is a local demo for the synthetic scenario and is out of scope for hostile use.

Track these in [the productization plan](PRODUCTIZATION_PLAN.md).

## Reporting

See [SECURITY.md](../SECURITY.md).
