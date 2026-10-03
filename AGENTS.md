# Decision Drift Gate Agent Instructions

## Required model roles

The user selected this execution arrangement:

- **Orchestrator:** GPT 6.1 Sol, reasoning effort High. Model identifier: `gpt-6.1-sol`.
- **Execution agent:** GPT 6 Luna. Model identifier: `gpt-6-luna`. No separate reasoning effort was requested; preserve the execution environment's inherited setting.

These are required settings for future execution, not a claim that writing these files changed the active chat's model. The orchestrator model is selected on the orchestration chat; each execution agent must be explicitly dispatched with the Luna model.

## Execution authority and scope

The user has now requested execution and parallel subagents. The orchestrator can dispatch, review, request fixes, and advance through the authorized phases without repeatedly asking for permission.

Use [PHASES.md](PHASES.md) as the execution roadmap, [the design](docs/superpowers/specs/2026-10-03-decision-drift-gate-design.md) as the behavior contract, and [the detailed plan](docs/superpowers/plans/2026-10-03-decision-drift-gate.md) for task-level code/test instructions. Phase documents organize that plan; they do not replace its requirements.

## Orchestrator responsibility

Own scope, dependencies, task dispatch, interface decisions, review, acceptance, and status reporting. Review the actual diff and verification evidence before accepting a phase. Keep `docs/phases/STATUS.md` current. Parallel Luna workers may implement independent parts of the current phase with disjoint file ownership and agreed interfaces. Dependent phases remain gated. Serialize Git staging/commits through the orchestrator while workers share the checkout. Use subagents within this chat rather than creating new sidebar chats.

Delegate source implementation and routine fixes to GPT 6 Luna. If a design/interface change is needed, decide and document it before dispatching revised instructions. Never accept a phase solely because the execution agent reports completion.

## Execution agent responsibility

Read the assigned phase, the design, the detailed plan's common contracts, and its assigned tasks before editing. Own only the files/responsibilities explicitly assigned by the orchestrator. You are not alone in the codebase: preserve others' edits and adapt to accepted preceding work. Do not revert unrelated changes or broaden the product scope.

Implement and test the assigned phase, create focused local commits as directed, and write a handoff with actual commands, results, commits, and limitations. Do not edit the roadmap/status or start the next phase. Return issues to the orchestrator for disposition.

## Shared requirements

- Distinguish application code completion from live AI evidence, browser verification, and human evaluation.
- Keep tests offline except the separately labeled real-provider verification.
- Never fabricate model captures, test outcomes, timings, participant feedback, or achieved savings.
- Keep provider secrets and generated demo repositories out of source Git.
- Read/write only this source repository and explicitly created task-owned demo/temp paths for implementation.
- Local source commits are allowed during authorized execution. Remote publishing follows the user's implementation/submission authorization; creating phase documents does not publish.
