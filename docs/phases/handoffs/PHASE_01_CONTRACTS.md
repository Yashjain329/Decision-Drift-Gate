# Phase 01 handoff: structured check contracts

Implemented the Phase 01 schema contract in the assigned files:

- `ddg/contracts.py`: exports `ADAPTER_VERSION = "python_job_client_v1"`, `canonical_bytes(value: dict) -> bytes`, `digest(value: dict) -> str`, and `validate_check(value: dict) -> dict`.
- `examples/manual_check.json`: the exact disclosed DEC-002 example from the design, labeled as a manual sample by its location and use.
- `tests/test_contracts.py`: strict valid and invalid schema cases, canonical serialization and hashing, and deep-copy behavior.

The validator enforces exactly the nine specified top-level fields; schema version integer `1` (excluding booleans); CHK-/DEC-prefixed IDs; the supported adapter and two scenario values; exactly one assertion for each required metric with strict types and bounded integer values; nonblank rationale and citations; and exact nested field sets. It rejects extra command/expression/path fields. Canonical serialization sorts keys, uses compact separators, preserves Unicode, emits UTF-8, and rejects non-finite numbers and non-JSON values. Citation quote *grounding* against decision text is intentionally left to the proposal boundary, as specified by the design.

## TDD evidence

- RED: `python -m unittest tests.test_contracts -v` failed to import `ddg.contracts` (`ModuleNotFoundError`), because the module did not exist. This was the expected missing-feature failure.
- GREEN: after implementing the module and sample, `python -m unittest tests.test_contracts -v` passed all 11 tests.
- A later robustness edit rejects non-string object keys explicitly. The final rerun also passed all 11 tests.

No external provider, Git operation, or network was used. No commit was created; the orchestrator owns Git operations. Harness and worker tests await their separately assigned files.
