"""Adapter for a job client: submit_job(service, payload, operation_id) -> job id.

The module under test is the governing decision's `scope`, which must be a repo .py path
(for example "src/job_client.py"). The scope is part of the approved input digest.
"""

from __future__ import annotations

from pathlib import Path

NAME = "python_job_client_v1"
SCENARIOS = {"commit_then_503", "reject_then_503"}
_OBSERVATION_FIELDS = {
    "status", "unique_jobs", "returned_job_exists", "returned_job_id", "submit_calls", "events", "error",
}


def validate_body(value: dict) -> None:
    """Validate the scenario and assertions of a job-client check."""
    if not isinstance(value["scenario"], str) or value["scenario"] not in SCENARIOS:
        raise ValueError("Unsupported scenario")
    assertions = value["assertions"]
    if not isinstance(assertions, list) or len(assertions) != 2:
        raise ValueError("assertions must contain exactly two metrics")
    by_metric: dict = {}
    for assertion in assertions:
        if not isinstance(assertion, dict) or set(assertion) != {"metric", "equals"}:
            raise ValueError("Each assertion must contain only metric and equals")
        metric = assertion["metric"]
        if not isinstance(metric, str) or metric not in {"unique_jobs", "returned_job_exists"}:
            raise ValueError("Unsupported assertion metric")
        if metric in by_metric:
            raise ValueError("Assertion metrics must be distinct")
        expected = assertion["equals"]
        if metric == "unique_jobs":
            if isinstance(expected, bool) or not isinstance(expected, int) or expected not in (0, 1, 2):
                raise ValueError("unique_jobs equals must be integer 0, 1, or 2")
        elif not isinstance(expected, bool):
            raise ValueError("returned_job_exists equals must be boolean")
        by_metric[metric] = expected
    if set(by_metric) != {"unique_jobs", "returned_job_exists"}:
        raise ValueError("Both required assertion metrics must be present")


def target_path(decision: dict | None) -> str:
    """The module under test: the decision scope, which must be a repo .py path."""
    from .python_function import valid_module_path
    scope = decision.get("scope") if isinstance(decision, dict) else None
    if not valid_module_path(scope):
        raise ValueError(f"{NAME} needs the decision scope to be the repo .py file that defines submit_job "
                         f"(for example src/job_client.py); got {str(scope)[:120]!r}")
    return scope


def source_path(check: dict, decision: dict | None = None) -> str:
    return target_path(decision)


def observe(repo: Path, sha: str, check: dict, timeout: float, target: str | None = None) -> dict:
    from ..harness import observe as run
    if target is None:
        raise ValueError(f"{NAME} needs the target module path (the decision scope)")
    return run(repo, sha, check, timeout=timeout, path=target)


def ordinary(repo: Path, sha: str, timeout: float, target: str | None = None) -> dict:
    from ..harness import observe_happy_path
    if target is None:
        raise ValueError(f"{NAME} needs the target module path (the decision scope)")
    return observe_happy_path(repo, sha, timeout=timeout, path=target)


def expected_case(case: str, observation: dict, check: dict) -> bool:
    if not isinstance(observation, dict) or set(observation) != _OBSERVATION_FIELDS:
        return False
    if not isinstance(observation["status"], str) or observation["status"] not in {"PASS", "FAIL"} or observation["error"] is not None:
        return False
    if (isinstance(observation["unique_jobs"], bool) or not isinstance(observation["unique_jobs"], int)
            or observation["unique_jobs"] < 0
            or not isinstance(observation["returned_job_exists"], bool)
            or isinstance(observation["submit_calls"], bool) or not isinstance(observation["submit_calls"], int)
            or observation["submit_calls"] < 0
            or (observation["returned_job_id"] is not None and not isinstance(observation["returned_job_id"], str))
            or not isinstance(observation["events"], list)
            or any(not isinstance(event, dict) for event in observation["events"])):
        return False
    if any(event.get("event") == "accepted" and not isinstance(event.get("job_id"), str)
           for event in observation["events"]):
        return False
    accepted = [event.get("job_id") for event in observation["events"]
                if isinstance(event, dict) and event.get("event") == "accepted"]
    submitted = [event for event in observation["events"]
                 if isinstance(event, dict) and event.get("event") == "submit"]
    if (len(set(accepted)) != observation["unique_jobs"]
            or len(submitted) != observation["submit_calls"]
            or observation["returned_job_exists"] != (observation["returned_job_id"] in accepted)):
        return False
    complete = observation["returned_job_exists"] and isinstance(observation["returned_job_id"], str)
    assertions_pass = all(observation.get(item["metric"]) == item["equals"] for item in check["assertions"])
    expected_status = "PASS" if complete and assertions_pass else "FAIL"
    if observation["status"] != expected_status:
        return False
    if case == "bad":
        return observation["status"] == "FAIL" and observation["unique_jobs"] == 2
    return observation["status"] == "PASS" and observation["unique_jobs"] == 1 and complete
