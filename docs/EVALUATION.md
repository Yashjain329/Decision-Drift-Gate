# Prototype evaluation

The automated matrix evaluates trusted synthetic Python clients against the default CHK-001 / DEC-002 approved demo. It records expected and observed outcomes separately, preserves mismatches and errors, and includes full Git revisions, check digest and observations. It does not measure reviewer benefit.

```powershell
python scripts/evaluate.py --repo .ddg-demo --out .ddg-evaluation
```

Build and approve the demo first using the [README](../README.md). Evaluation leaves the input repository unchanged. Outputs remain in the ignored directory until a reviewed, sanitized result is copied into `evidence`.

## Cases and interpretation

The main regression and helper-based holdout create two jobs after a committed first submission returns 503. Corrected reconciliation, stable-key exception and unrelated changes preserve one completed job. Silent abort fails completion. Candidate policy edits require review even when valid target checks can still execute. Preexisting failure and resolved behavior are distinguished from newly introduced failure. Crashes, timeout and a missing entrypoint remain errors/incomplete, rather than passing or being called proven violations.

The helper-based implementation is absent from the proposal and bad/good/exception calibration inputs. It is a synthetic holdout authored by the same fixture generator, not an independent production dataset. All cases use the bounded adapter `python_job_client_v1`.

Actual matrix totals and source revision are recorded in [the evidence index](../evidence/README.md). Inspect every expected/observed row rather than inferring quality from the opening demo. Recorded command runtimes are local execution timings; they are not speaking duration or time saved by a human reviewer.

## Human comparison and rehearsal

No participants have completed the comparison, and no timed speaking rehearsal has been collected. The raw CSV contains headers only. [The human evaluation protocol](HUMAN_EVALUATION.md) supplies task variants, counterbalancing, separate setup/review timing and five rehearsal slots.

The original 50% review-time reduction remains an unmeasured target. Approval labels supplied by Codex identify AI integration review; they are not participant feedback or authenticated developer identities. Production usefulness, check maintenance cost and buyer demand remain hypotheses.

## Tested environment and scope

Implementation and browser checks ran on Windows with Python 3.12.4 and Git 2.51.0.windows.2. Live capture used optional `google-genai==2.28.0` and `gemini-3.8-flash`. The core, tests, Recorded generation and approved execution use Python's standard library and Git; no key or network is needed for them.

The local application does not provide a GitHub PR integration, arbitrary-repository sandbox, authenticated multiuser approval or general decision-to-test translation. Source inspection rejects unsupported adapter constructs; process separation does not make untrusted code safe. A passing aggregate means the approved covered checks passed for the pinned revisions.

## Addendum 12 October 2026

The text above describes the prototype. On `master` today:

- The Python suite has **383 tests, all passing** (3 skipped) and the browser suite 86 Playwright tests, all passing, in the last full run (19 October 2026, host and Docker modes). The 15-case matrix was re-run in Docker mode on the final code with a freshly built demo and **matched 15 of 15**. The recorded matrix in the evidence index is from the earlier commit named there and is unchanged.
- Workers run in a container (network, filesystem writes, memory, CPU, processes and privilege are limited). The static import screen is best-effort. Neither makes the verdict trustworthy against a malicious author: a revision under test can still return fabricated results for its own function. See the [threat model](THREAT_MODEL.md).
- The matrix uses the adapter `python_job_client_v1`. A second adapter, `python_function_v1`, is covered by `tests/test_adapters.py`, `tests/test_cli_real.py`, `tests/test_tamper.py` and `tests/e2e/`, not by the 15-case matrix.
- Approver identity is checked from Git (allowlist, touched paths, optional signatures). A GitHub Action exists and is tested offline against real reports; it has not run on GitHub. A pull-request-review binding does not exist.
- The tamper suite edits every JSON field of the authority files one at a time and checks that none yields a pass. This is the strongest evidence of the gate's fail-closed behaviour, and it covers the same authored scenarios, not an independent corpus.
- Model drafting was tested with fake providers and scripts. `claude_cli` and `codex_cli` were each run once by hand with a trivial prompt. No API provider and no Bedrock run exists, and no full proposal on a real decision through a CLI agent.
- Human comparison and rehearsal: still none. The review-time target remains unmeasured.
