# Decision Drift Gate Phased Execution

**Date:** 3 October 2026. **Current state:** planning complete; no application phase has started.

**Orchestrator:** GPT 6.1 Sol High (`gpt-6.1-sol`, effort `high`). **Execution agent:** GPT 6 Luna (`gpt-6-luna`, inherited execution effort).

The orchestrator decides what is ready to execute and reviews what was delivered. Luna implements the assigned scope and supplies evidence. Only Sol marks a phase accepted and dispatches the next one.

## Roadmap

| Phase | Deliverable | Detailed tasks | Entry requirement | Exit evidence |
|---|---|---|---|---|
| [01 Foundation and behavioral proof](docs/phases/PHASE_01_FOUNDATION.md) | Synthetic Git history and executable check runner | 1-2 | Execution requested; design/plan available | Bad fails; fix and exception pass; abort fails; errors stay errors |
| [02 AI proposal and approval](docs/phases/PHASE_02_AI_AND_APPROVAL.md) | Grounded proposal, calibration, exact approved bundle | 3-4 | Phase 01 accepted | Provider provenance, calibration, invalidation, approval and demo activation |
| [03 Review engine and CLI](docs/phases/PHASE_03_ENGINE_AND_CLI.md) | Two-revision verdicts and reproducible reports | 5-6 | Phase 02 code reviewed and approved artifacts usable | Holdout, authority, attribution, coverage, exit codes and stale evidence |
| [04 Live browser demo](docs/phases/PHASE_04_LIVE_DEMO.md) | Real browser actions backed by the engine | 7 | Phase 03 accepted | Full lifecycle, honest mode labels, HTTP tests and browser inspection |
| [05 Evaluation and submission](docs/phases/PHASE_05_EVALUATION_AND_SUBMISSION.md) | Verified evidence, pitch rehearsal, docs and source delivery | 8 | Phase 04 accepted | Fresh-checkout reproduction, measured case matrix and accurate submission |

Phases run sequentially. Shared files such as `ddg/demo.py`, `ddg/contracts.py`, and `tests/support.py` are extended by the current phase only. No additional agent topology, infrastructure, or parallel implementation is needed.

## Source of truth

1. User instructions and this repository's [AGENTS.md](AGENTS.md).
2. [Design specification](docs/superpowers/specs/2026-10-03-decision-drift-gate-design.md): expected product behavior.
3. [Detailed implementation plan](docs/superpowers/plans/2026-10-03-decision-drift-gate.md): task interfaces, code examples and checks.
4. The assigned phase document: ownership, milestone and acceptance.
5. [Status and handoffs](docs/phases/STATUS.md): what actually ran and what remains.

If these disagree, Sol resolves the discrepancy and records the decision before Luna implements it. Dates and checkboxes in a plan are not proof of completion.

## Dispatch and review loop

1. Sol checks working-tree state, predecessor handoff, current phase entry gate, and accepted interfaces.
2. Sol dispatches a worker with `model="gpt-6-luna"` and `fork_turns="none"`. Supply the source directory, phase path, design/plan paths, precise ownership, preceding commit and interface decisions. Do not rely on context the worker did not receive.
3. Luna follows the phase task list, runs meaningful checks, commits its scope, and writes `docs/phases/handoffs/PHASE_0N.md` for the assigned phase.
4. Sol inspects the diff, reported limitations, and real command results. Run focused independent verification where needed; do not rerun unrelated checks without a reason.
5. If requirements are unmet, Sol sends a concrete correction to the same Luna worker and keeps the phase `CHANGES_REQUIRED`.
6. Sol records accepted commits, verification, remaining external evidence, and the next eligible phase in `STATUS.md`.

The current chat's model must actually match the orchestrator setting before claiming that this model arrangement was used. An execution tool's returned model/settings and the dispatch belong in the handoff record. Model labels in Markdown alone do not change runtime settings.

## Phase states

| State | Meaning |
|---|---|
| PLANNED | No execution dispatched |
| RUNNING | Luna is implementing the assigned scope |
| CHANGES_REQUIRED | Sol found a concrete acceptance failure |
| CODE_VERIFIED_EVIDENCE_PENDING | Code is reviewed, but live provider, browser or human evidence remains outstanding |
| ACCEPTED | All phase gates are supported by recorded evidence |

If provider access is unavailable in Phase 02, Sol may allow Phase 03 to build against the reviewed offline interfaces while Phase 02 remains `CODE_VERIFIED_EVIDENCE_PENDING`. That exception never satisfies live-proposal release requirements. No such exception is currently in effect.

## Handoff format

Luna creates a handoff only after doing the work. It contains:

```text
Phase and scope
Execution model/settings actually used
Start commit and delivered commits
Files changed and interfaces added/changed
Commands run, exit codes, and observed results
Acceptance cases passed/failed
Evidence paths and provenance
Known limitations or pending external evidence
Recommended next action
```

Sol appends its review decision and the evidence supporting acceptance. Do not create empty handoffs or list planned commands as executed commands.

## Worker dispatch text

Use this text with the actual assigned phase and preceding commit supplied in the dispatch:

> Execute only the assigned Decision Drift Gate phase. Read AGENTS.md, the phase document, design specification, and the detailed plan's common contracts and assigned tasks. You own the files listed in that phase and its handoff file. You are not alone in this codebase; preserve others' changes and adapt to accepted previous work. Implement the task requirements, run the specified meaningful checks, and report actual outcomes. Make focused local commits. Do not edit PHASES.md or STATUS.md, broaden scope, publish remotely, or begin the next phase. If an interface or design change is needed, report it to the orchestrator. Never fabricate live AI evidence or measurements.

## Completion promise

The final demonstration must show a decision change becoming an approved check, a later regression failing with observed duplicate jobs, an unseen variation failing, and a legitimate exception passing. Source, documentation and honest live/recorded evidence must reproduce from the submitted repository. The 50% review-time target remains unmeasured until evaluation supplies actual data.
