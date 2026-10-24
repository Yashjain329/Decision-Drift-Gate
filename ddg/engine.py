"""Pinned, base-authorized comparison of approved behavioral checks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import adapters, identity, sandbox
from .approval import verify_bundle
from .contracts import ADAPTER_VERSION, digest, validate_check, validate_decisions
from .gitio import changed_paths_at, diff_at, list_at, read_at, resolve_commit
from .proposal import input_digest, load_context, validate_citations

RUNNER_TIMEOUT_SECONDS = 10.0
_VERDICTS = {
    ("PASS", "FAIL"): "VIOLATION_INTRODUCED",
    ("FAIL", "FAIL"): "PRE_EXISTING_FAILURE",
    ("FAIL", "PASS"): "RESOLVED",
    ("PASS", "PASS"): "CHECK_PASSED",
}
_ERROR_OBSERVATION_FIELDS = {
    "status": "ERROR",
    "unique_jobs": None,
    "returned_job_exists": None,
    "returned_job_id": None,
    "submit_calls": None,
    "events": [],
}


def _observation_error(message: str) -> dict:
    return {**_ERROR_OBSERVATION_FIELDS, "events": [], "error": message}


def _verdict(base: dict, head: dict) -> str:
    if base.get("status") == "ERROR" or head.get("status") == "ERROR":
        return "NOT_CHECKED"
    return _VERDICTS.get((base.get("status"), head.get("status")), "NOT_CHECKED")


def _read_json(repo: Path, revision: str, path: str) -> Any:
    try:
        return json.loads(read_at(repo, revision, path))
    except (ValueError, json.JSONDecodeError, TypeError, UnicodeError) as exc:
        raise ValueError(f"Could not read JSON artifact at {path}") from exc


def _policy_changed(repo: Path, base_sha: str, head_sha: str) -> bool | None:
    try:
        return any(path == ".ddg" or path.startswith(".ddg/")
                   for path in changed_paths_at(repo, base_sha, head_sha))
    except (OSError, ValueError, UnicodeError):
        # If policy state at head cannot be read, the result cannot be green.
        return None


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _empty_check_entry(check_id: str, error: str, diff: str) -> dict:
    return {
        "check_id": check_id,
        "verdict": "NOT_CHECKED",
        "base": _observation_error(error),
        "head": _observation_error(error),
        "decision": None,
        "check": None,
        "check_digest": None,
        "approval": None,
        "validation": None,
        "diff": diff,
        "error": error,
    }


def _authority(repo: Path, base_sha: str, warnings: list[dict]) -> tuple[list[dict], bool, list[dict]]:
    """Load and validate all authority from base; return eligible checks and coverage state."""
    decision_paths = list_at(repo, base_sha, ".ddg/decisions")
    check_paths = list_at(repo, base_sha, ".ddg/checks")
    validation_paths = list_at(repo, base_sha, ".ddg/validations")
    approval_paths = list_at(repo, base_sha, ".ddg/approvals")

    decisions: dict[str, dict] = {}
    raw_decisions: list[dict] = []
    graph_error: str | None = None
    try:
        for path in decision_paths:
            record = _read_json(repo, base_sha, path)
            if (not isinstance(record, dict) or Path(path).stem != record.get("id")
                    or path != f".ddg/decisions/{record.get('id')}.json"):
                raise ValueError(f"Decision path does not match record id: {path}")
            raw_decisions.append(record)
        decisions = validate_decisions(raw_decisions)
    except (ValueError, TypeError, KeyError) as exc:
        graph_error = str(exc) or "Decision graph is invalid"
        warnings.append(_warning("INVALID_DECISION_GRAPH", graph_error))

    by_artifact: dict[str, dict] = {}
    for paths, folder, label in (
        (validation_paths, ".ddg/validations", "validation"),
        (approval_paths, ".ddg/approvals", "approval"),
    ):
        for path in paths:
            identifier = Path(path).stem
            try:
                record = _read_json(repo, base_sha, path)
                if (not isinstance(record, dict) or record.get("check_id") != identifier
                        or path != f"{folder}/{identifier}.json"):
                    raise ValueError(f"{label.title()} path does not match its check id: {path}")
                by_artifact[f"{folder}/{identifier}.json"] = record
            except (ValueError, TypeError, KeyError) as exc:
                warnings.append(_warning("INVALID_APPROVAL_BUNDLE", str(exc)))

    active_decisions = {key: record for key, record in decisions.items() if record["status"] == "active"}
    decision_evidence = list(active_decisions.values()) if not graph_error else [
        record for record in raw_decisions
        if isinstance(record, dict) and record.get("status") == "active"
    ]
    entries: list[dict] = []
    covered: set[str] = set()
    incomplete = graph_error is not None
    for path in check_paths:
        check_id = Path(path).stem
        try:
            check = validate_check(_read_json(repo, base_sha, path))
            if check["id"] != check_id or path != f".ddg/checks/{check_id}.json":
                raise ValueError(f"Check path does not match record id: {path}")
            decision = decisions.get(check["decision_id"])
            if graph_error:
                raise ValueError("Decision graph is invalid")
            if decision is None:
                raise ValueError("Check names a missing base decision")
            if decision["status"] == "superseded":
                historical = {
                    "check_id": check_id,
                    "verdict": "HISTORICAL_CHECK_IGNORED",
                    "base": None,
                    "head": None,
                    "decision": decision,
                    "check": check,
                    "check_digest": digest(check),
                    "approval": by_artifact.get(f".ddg/approvals/{check_id}.json"),
                    "validation": by_artifact.get(f".ddg/validations/{check_id}.json"),
                    "diff": "",
                    "error": None,
                    "_authorized": False,
                }
                entries.append(historical)
                warnings.append(_warning(
                    "HISTORICAL_CHECK_IGNORED",
                    f"{check_id} names superseded decision {decision['id']} and was not executed.",
                ))
                continue
            validate_citations(check, decisions)
            validation_path = f".ddg/validations/{check_id}.json"
            approval_path = f".ddg/approvals/{check_id}.json"
            validation = by_artifact.get(validation_path)
            approval = by_artifact.get(approval_path)
            if validation is None or approval is None:
                raise ValueError("Approved check is missing its validation or approval record")
            if not verify_bundle(check, decision, validation, approval):
                raise ValueError("Approved check bundle digest or calibration evidence is invalid")
            source_sha = str(validation.get("source_sha"))
            try:
                inputs = load_context(repo, decision["id"], source_sha, check["adapter"])
                inputs["old_decision"] = decisions[decision["supersedes"]]  # base's record, not the pinned one
                inputs["new_decision"] = decision
                inputs_ok = input_digest(inputs) == validation["input_digest"]
            except (ValueError, KeyError, TypeError) as exc:
                # Fail closed, but say why: a missing commit (squash, rebase, unpushed branch, shallow clone)
                # reads differently from missing decision records or an unreadable target module.
                raise ValueError(f"Proposal source commit {source_sha[:12]} cannot be used: {str(exc) or type(exc).__name__}. "
                                 "It must be reachable in this clone (not squashed, rebased away or shallow) "
                                 "and hold both decision records and the target module.") from exc
            if not inputs_ok:  # binds the superseded predecessor and source the check was proposed from
                raise ValueError("Approved proposal inputs differ from the repository record they were pinned to")
            try:
                approver = identity.verify_approver(repo, base_sha, check_id)
            except identity.IdentityError as exc:
                warnings.append(_warning("APPROVER_NOT_VERIFIED", f"{check_id}: {exc}"))
                raise ValueError(f"Approver identity not verified: {exc}") from exc
            entry = {
                "check_id": check_id,
                "verdict": "NOT_CHECKED",
                "base": None,
                "head": None,
                "decision": decision,
                "check": check,
                "check_digest": digest(check),
                "approval": approval,
                "validation": validation,
                "diff": "",
                "error": None,
                "approver": approver,
                "_authorized": True,
            }
            entries.append(entry)
            covered.add(decision["id"])
        except (ValueError, TypeError, KeyError) as exc:
            incomplete = True
            message = str(exc) or "Approved check authority is invalid"
            warnings.append(_warning("INVALID_APPROVAL_BUNDLE", f"{check_id}: {message}"))
            entry = _empty_check_entry(check_id, message, "")
            entry["_authorized"] = False
            # Preserve whatever base artifacts can safely be represented for review.
            try:
                candidate = _read_json(repo, base_sha, path)
                if isinstance(candidate, dict):
                    entry["check"] = candidate
                    entry["check_digest"] = digest(candidate)
                    decision_id = candidate.get("decision_id")
                    entry["decision"] = decisions.get(decision_id)
                    entry["validation"] = by_artifact.get(f".ddg/validations/{check_id}.json")
                    entry["approval"] = by_artifact.get(f".ddg/approvals/{check_id}.json")
            except (ValueError, TypeError):
                pass
            entries.append(entry)

    missing_coverage = sorted(set(active_decisions) - covered)
    if missing_coverage:
        incomplete = True
        warnings.append(_warning(
            "MISSING_APPROVED_COVERAGE",
            "Active base decisions lack an approved check: " + ", ".join(missing_coverage),
        ))
    if not entries:
        incomplete = True
        warnings.append(_warning("NO_ACTIVE_APPROVED_CHECKS", "No active approved checks were found in base."))
    if not covered:
        incomplete = True
        if entries:
            warnings.append(_warning("NO_ACTIVE_APPROVED_CHECKS", "No approved checks govern an active decision in base."))
    return entries, incomplete, decision_evidence


def _sandbox_mode() -> str:
    try:
        return sandbox.resolve()
    except sandbox.SandboxUnavailable:
        return "unavailable"


def _sandbox_image() -> dict:
    """Which container image ran head code, and whether it is digest-pinned (None image on host/unavailable)."""
    described = sandbox.describe()
    return {"image": described["image"], "pinned": described["pinned"]}


def compare(repo: Path, base: str, head: str) -> dict:
    """Compare two pinned revisions using only base's validated approved checks."""
    repo = Path(repo).expanduser().resolve()
    base_sha = resolve_commit(repo, base)
    head_sha = resolve_commit(repo, head)
    warnings: list[dict[str, str]] = []
    changed_policy = _policy_changed(repo, base_sha, head_sha)
    if changed_policy is True:
        warnings.append(_warning(
            "POLICY_REVIEW_REQUIRED",
            "Head changes .ddg policy artifacts; authority remains pinned to base.",
        ))
    elif changed_policy is None:
        warnings.append(_warning(
            "POLICY_STATE_UNAVAILABLE",
            "Could not determine whether head changed .ddg policy artifacts.",
        ))
    diff_unavailable = False
    try:
        entries, authority_incomplete, active_decisions = _authority(repo, base_sha, warnings)
    except (OSError, ValueError, UnicodeError) as exc:
        authority_incomplete = True
        entries = []
        active_decisions = []
        warnings.append(_warning("AUTHORITY_UNAVAILABLE", f"Could not load base policy artifacts: {type(exc).__name__}"))
    diffs: dict[str, str] = {}

    def diff_for(path: str) -> str:
        nonlocal diff_unavailable
        if path not in diffs:
            try:
                diffs[path] = diff_at(repo, base_sha, head_sha, path)
            except (ValueError, OSError, UnicodeError) as exc:
                diffs[path] = ""
                diff_unavailable = True
                warnings.append(_warning("DIFF_UNAVAILABLE", f"Could not read source diff: {type(exc).__name__}"))
        return diffs[path]

    in_play: set[str] = set()
    job_targets: set[str] = set()
    for entry in entries:
        authorized = entry.pop("_authorized", False)
        check = entry.get("check")
        if not authorized or not isinstance(check, dict) or not entry.get("approval") or not entry.get("validation"):
            entry["diff"] = ""  # no trusted target module to diff
            continue
        target = None
        try:
            adapter = adapters.get(check["adapter"])
            in_play.add(adapter.NAME)
            target = adapter.source_path(check, entry.get("decision"))
            if adapter.NAME == ADAPTER_VERSION:
                job_targets.add(target)
            entry["base"] = adapter.observe(repo, base_sha, check, RUNNER_TIMEOUT_SECONDS, target)
        except Exception as exc:
            entry["base"] = _observation_error(f"Base execution failed: {type(exc).__name__}")
        try:
            entry["head"] = adapters.get(check["adapter"]).observe(repo, head_sha, check, RUNNER_TIMEOUT_SECONDS, target)
        except Exception as exc:
            entry["head"] = _observation_error(f"Head execution failed: {type(exc).__name__}")
        entry["verdict"] = _verdict(entry["base"], entry["head"])
        entry["diff"] = diff_for(target) if target else ""
        if entry["verdict"] == "NOT_CHECKED":
            warnings.append(_warning("EXECUTION_ERROR", f"{entry['check_id']} could not be evaluated on both revisions."))

    # The ordinary-test observation is defined only for the job adapter, on an approved check's target module.
    # ponytail: one target (the first by path); per-target ordinary tests if repos govern several job clients.
    ordinary_tests = {}
    if job_targets:
        job_adapter, target = adapters.get(ADAPTER_VERSION), sorted(job_targets)[0]
        ordinary_tests = {
            "base": job_adapter.ordinary(repo, base_sha, RUNNER_TIMEOUT_SECONDS, target),
            "head": job_adapter.ordinary(repo, head_sha, RUNNER_TIMEOUT_SECONDS, target),
        }
    ordinary_error = any(item["status"] == "ERROR" for item in ordinary_tests.values())
    if ordinary_error:
        warnings.append(_warning("ORDINARY_TEST_ERROR", "The no-fault submission observation errored on at least one revision."))

    verdicts = [entry["verdict"] for entry in entries if entry["verdict"] != "HISTORICAL_CHECK_IGNORED"]
    if changed_policy is not False or diff_unavailable or authority_incomplete or ordinary_error or "NOT_CHECKED" in verdicts:
        aggregate = "INCOMPLETE"
    elif any(verdict in {"VIOLATION_INTRODUCED", "PRE_EXISTING_FAILURE"} for verdict in verdicts):
        aggregate = "FAILED"
    elif verdicts and all(verdict in {"CHECK_PASSED", "RESOLVED"} for verdict in verdicts):
        aggregate = "PASSED_CHECKS"
    else:
        aggregate = "INCOMPLETE"

    return {
        "aggregate": aggregate,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "checks": entries,
        "active_decisions": active_decisions,
        "warnings": warnings,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "adapter_version": ",".join(sorted(in_play)) or ADAPTER_VERSION,
        "ordinary_tests": ordinary_tests,
        "sandbox": _sandbox_mode(),
        "sandbox_image": _sandbox_image(),
    }


__all__ = ["compare"]
