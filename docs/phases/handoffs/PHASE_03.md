# Phase 03 accepted engine and CLI

Delivered commits: `bfbe1d2` (engine), `ff631c4` (CLI and reports).

Root's independent fresh `python -m unittest discover -s tests -v` passed **96 tests in 200.840 seconds**, exit 0. Sol High found no remaining important or critical blocker after independently checking authority, all-check execution, incomplete coverage, policy edits, provenance, CLI codes, output preflight and immutable stale-report evidence.

Root independently executed the main CLI reveal against the actual recorded Gemini demo. It returned exit 1, FAILED / VIOLATION_INTRODUCED, one unique job at base and two at head, while ordinary observations passed on both revisions. That local CLI invocation took **1.432 seconds**. This is a single execution measurement, not timed human pitch or a general performance guarantee.

Full report interfaces and real commands are in [engine handoff](PHASE_03_ENGINE.md) and [CLI handoff](PHASE_03_CLI.md). Reports contain full revisions, checks, active base decisions, warnings, UTC run time, adapter version and ordinary observations. All browser outcomes must call these same functions.

Head policy changes cannot replace target authority. Invalid bundles do not execute. Every active approved check executes against both revisions, including unrelated changes. Historical checks are retained but skipped; missing successor coverage remains incomplete. Missing required diff evidence is also incomplete.

Root's ignored `.ddg-demo` is ready for a fresh fast reveal using a disclosed Recorded proposal. Its local approval is labeled `Codex integration reviewer`, not counted as a human evaluation participant. A new empty demo destination supports the full proposal/calibration/approval lifecycle.
