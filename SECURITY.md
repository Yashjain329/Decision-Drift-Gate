# Security policy

## Supported versions

DDG has no tagged release yet. Only the latest commit on the default branch receives security fixes. When a first version is tagged, this table will list it.

| Version | Supported |
|---|---|
| Latest commit on the default branch | Yes |
| Older commits | No |

## Report a vulnerability

Do not open a public issue for a security problem.

1. Use GitHub private vulnerability reporting on the repository (Security tab, "Report a vulnerability"), if it is enabled.
2. If it is not enabled, open a public issue that says only "security contact requested" with no details. A maintainer will reply with a private channel.

Include the commit, the steps to reproduce, and the effect (for example "a head revision gets PASSED_CHECKS without the check running"). No response-time commitment exists at this stage; this is a small project.

## Scope

In scope:

- A head revision that changes the verdict, hides a failure, or reads or writes outside the sandbox.
- A way to make an unapproved or unverified bundle count as approved (see `ddg/identity.py`, `ddg/engine.py`).
- A way to bypass the container limits listed in the [threat model](docs/THREAT_MODEL.md), or to make a run silently use the host.
- Leaks of API keys into reports or child environments.

Out of scope (documented residual risks in the threat model):

- Kernel or container-runtime vulnerabilities.
- A malicious approver, a compromised base branch, or a compromised CI runner.
- Forged author email when `require_signed` is `false`.
- Bypasses of the static import screen alone. It is best-effort and not a security boundary.
- The local browser interface used by a hostile local user. It binds to loopback for demos only.

## Safe use

Read the [threat model](docs/THREAT_MODEL.md) before running DDG on code you do not trust. Use a container runtime, set `require_signed: true`, and protect `.ddg/approvers.json`.
