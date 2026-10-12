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

The text above describes the prototype. Since commit `bbb0e33`:

- The statement "process separation does not make untrusted code safe" is still true of the static import screen. Workers now also run in a container, which limits network, filesystem writes, memory, CPU, processes and privilege. It does not stop kernel or runtime escapes. See [threat model](THREAT_MODEL.md).
- The evaluation matrix uses the adapter `python_job_client_v1`. A second adapter, `python_function_v1`, has its own tests in `tests/test_adapters.py`; those tests are not part of the 15-case matrix.
- The suite has 144 tests at `bbb0e33`. The 15-case matrix result in the evidence index was recorded on the earlier commit named there. It has not been re-recorded for `bbb0e33`.
- "Does not provide authenticated multiuser approval" is partly outdated: approver identity is now checked from Git. DDG still does not provide a GitHub PR integration (a GitHub Action is planned) or general decision-to-test translation.
- Human comparison and rehearsal: still none.
