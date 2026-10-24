"""Calibration, approval, and immutable bundle verification."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import adapters
from .contracts import ADAPTER_VERSION, canonical_bytes, digest, validate_check
from .demo import activate_demo
from .gitio import resolve_commit
from .proposal import input_digest, load_context, validate_citations

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_DRAFT_FIELDS = {
    "check", "draft_digest", "input_digest", "decision", "proposal_mode", "model",
    "captured_at", "source_sha", "adapter_version", "sdk_version", "capture_source_sha",
    "request_metadata", "provider_response", "attempts",
}
_VALIDATION_FIELDS = {
    "schema_version", "check_id", "draft_digest", "check_digest", "decision_digest",
    "input_digest", "adapter_version", "proposal_mode", "model", "sdk_version", "source_sha",
    "proposal", "cases", "calibration_hashes", "eligible", "validated_at",
}
_APPROVAL_FIELDS = {
    "schema_version", "check_id", "bundle_digest", "reviewer", "reason", "approved_at",
    "validation_digest", "calibration_hashes",
}
_CALIBRATION = {
    "bad": "calibration_bad",
    "good": "calibration_good",
    "exception": "calibration_exception",
}
_OBSERVATION_FIELDS = {
    "status", "unique_jobs", "returned_job_exists", "returned_job_id", "submit_calls", "events", "error",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA1.fullmatch(value) is not None


def _provenance_valid(draft: dict) -> bool:
    mode = draft["proposal_mode"]
    attempts = draft["attempts"]
    request, response = draft["request_metadata"], draft["provider_response"]
    if not isinstance(attempts, list) or len(attempts) > 2:
        return False
    allowed_results = {"manual_input", "accepted", "schema_or_citation_rejected", "recorded_capture"}
    if any(not isinstance(item, dict) or set(item) != {"attempt", "result"}
           or type(item.get("attempt")) is not int or item.get("attempt") not in (1, 2)
           or not isinstance(item.get("result"), str) or item.get("result") not in allowed_results for item in attempts):
        return False
    if mode == "manual":
        return (draft["model"] is None and draft["captured_at"] is None
                and draft["sdk_version"] is None and draft["capture_source_sha"] is None
                and request is None and response is None
                and (attempts == [] or attempts == [{"attempt": 1, "result": "manual_input"}]))
    if (not isinstance(draft["model"], str) or not draft["model"].strip()
            or not isinstance(draft["sdk_version"], str) or not draft["sdk_version"].strip()
            or not _valid_iso_time(draft["captured_at"])
            or not isinstance(request, dict) or not isinstance(response, dict)):
        return False
    required_request = {"model", "prompt_version", "input_digest", "request_count", "response_format", "timeout_seconds"}
    provider_name = request.get("provider")
    if (provider_name is not None and (not isinstance(provider_name, str)
                                       or not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", provider_name))):
        return False
    if (set(request) - {"provider"} != required_request or request["model"] != draft["model"]
            or request["input_digest"] != draft["input_digest"]
            or not isinstance(request["prompt_version"], str) or not request["prompt_version"].strip()
            or isinstance(request["request_count"], bool) or request["request_count"] not in (1, 2)
            or request["response_format"] != "application/json"
            or type(request["timeout_seconds"]) is not int or not 1 <= request["timeout_seconds"] <= 600
            or set(response) != {"status", "reason"} or response["status"] != "DRAFT"
            or not isinstance(response["reason"], str)):
        return False
    if mode == "live":
        return (draft["capture_source_sha"] is None and 1 <= len(attempts) <= 2
                and request["request_count"] == len(attempts)
                and attempts[-1]["result"] == "accepted")
    if mode == "recorded":
        return (_is_sha(draft["capture_source_sha"])
                and attempts == [{"attempt": 1, "result": "recorded_capture"}])
    return False


def _check_draft(repo: Path, draft: dict) -> tuple[dict, dict]:
    if not isinstance(draft, dict) or set(draft) != _DRAFT_FIELDS:
        raise ValueError("Draft envelope fields are invalid")
    check = validate_check(draft["check"])
    if draft["draft_digest"] != digest({key: value for key, value in draft.items() if key != "draft_digest"}):
        raise ValueError("Draft digest does not match its proposal envelope")
    if not isinstance(draft["input_digest"], str) or not re.fullmatch(r"[0-9a-f]{64}", draft["input_digest"]):
        raise ValueError("Draft input digest is invalid")
    if not _is_sha(draft["source_sha"]):
        raise ValueError("Draft source revision must be a full SHA-1 commit id")
    if not isinstance(draft["proposal_mode"], str) or draft["proposal_mode"] not in {"live", "recorded", "manual"}:
        raise ValueError("Draft proposal mode is invalid")
    if draft["adapter_version"] != check["adapter"]:
        raise ValueError("Draft adapter version is unsupported")
    if draft["capture_source_sha"] is not None and not _is_sha(draft["capture_source_sha"]):
        raise ValueError("Draft capture source revision is invalid")
    attempts = draft["attempts"]
    if not isinstance(attempts, list) or len(attempts) > 2:
        raise ValueError("Draft attempt provenance is invalid")
    allowed_results = {"manual_input", "accepted", "schema_or_citation_rejected", "recorded_capture"}
    for item in attempts:
        if (not isinstance(item, dict) or set(item) != {"attempt", "result"}
                or type(item["attempt"]) is not int or item["attempt"] not in (1, 2)
                or not isinstance(item["result"], str) or item["result"] not in allowed_results):
            raise ValueError("Draft attempt provenance is invalid")
    if not _provenance_valid(draft):
        raise ValueError("Draft mode does not carry complete, consistent provenance")

    source_sha = resolve_commit(repo, draft["source_sha"])
    if source_sha != draft["source_sha"]:
        raise ValueError("Draft source revision is not canonical")
    context = load_context(repo, decision_id=draft["decision"].get("id") if isinstance(draft["decision"], dict) else "", revision=source_sha,
                           adapter=check["adapter"])
    if draft["decision"] != context["new_decision"]:
        raise ValueError("Draft decision differs from its pinned repository record")
    if draft["source_sha"] != context["source_sha"] or draft["adapter_version"] != context["adapter_version"]:
        raise ValueError("Draft provenance does not match its pinned proposal inputs")
    if draft["input_digest"] != input_digest(context):
        raise ValueError("Draft input digest does not match its pinned proposal inputs")
    input_decisions = {context["old_decision"]["id"]: context["old_decision"],
                       context["new_decision"]["id"]: context["new_decision"]}
    grounded = validate_citations(check, input_decisions)
    if grounded != check:
        raise ValueError("Draft check is not normalized")
    if check["decision_id"] != draft["decision"]["id"]:
        raise ValueError("Draft check is not governed by its selected decision")
    return check, context["new_decision"]


def _expected_case(case: str, observation: dict, check: dict) -> bool:
    return adapters.get(check["adapter"]).expected_case(case, observation, check)


def _calibration(repo: Path, check: dict, refs: dict, decision: dict) -> tuple[dict, dict, bool]:
    adapter = adapters.get(check["adapter"])
    target = adapter.source_path(check, decision)
    cases: dict[str, dict] = {}
    hashes: dict[str, str] = {}
    eligible = True
    for case, ref_key in _CALIBRATION.items():
        sha = refs.get(ref_key)
        if not _is_sha(sha):
            raise ValueError(f"Missing full SHA for calibration fixture {ref_key}")
        sha = resolve_commit(repo, sha)
        hashes[case] = sha
        try:
            observation = adapter.observe(repo, sha, check, 10, target)
        except Exception as exc:
            observation = {
                "status": "ERROR", "unique_jobs": None, "returned_job_exists": None,
                "returned_job_id": None, "submit_calls": None, "events": [],
                "error": f"{type(exc).__name__}: calibration execution failed",
            }
        cases[case] = {"sha": sha, "observation": observation}
        eligible = _expected_case(case, observation, check) and eligible
    return cases, hashes, eligible


def validate_draft(repo: Path, draft: dict, refs: dict) -> dict:
    """Run the mandatory bad, good, and exception calibration matrix."""
    repo = Path(repo).expanduser().resolve()
    check, decision = _check_draft(repo, draft)
    if not isinstance(refs, dict):
        raise ValueError("Calibration refs must be an object")
    cases, hashes, eligible = _calibration(repo, check, refs, decision)
    return {
        "schema_version": 1,
        "check_id": check["id"],
        "draft_digest": draft["draft_digest"],
        "check_digest": digest(check),
        "decision_digest": digest(decision),
        "input_digest": draft["input_digest"],
        "adapter_version": draft["adapter_version"],
        "proposal_mode": draft["proposal_mode"],
        "model": draft["model"],
        "sdk_version": draft["sdk_version"],
        "source_sha": draft["source_sha"],
        "proposal": copy.deepcopy(draft),
        "cases": cases,
        "calibration_hashes": hashes,
        "eligible": eligible,
        "validated_at": _now(),
    }


def bundle_digest(check: dict, decision: dict, adapter_version: str, validation: dict) -> str:
    """Digest the precise check/decision/adapter/validation bundle."""
    return digest({"check": check, "decision": decision,
                   "adapter_version": adapter_version, "validation": validation})


def _valid_iso_time(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _verify_validation(check: dict, decision: dict, validation: dict) -> bool:
    try:
        if not isinstance(validation, dict) or set(validation) != _VALIDATION_FIELDS:
            return False
        normalized = validate_check(check)
        if normalized != check or not isinstance(decision, dict):
            return False
        expected_decision_fields = {"schema_version", "id", "status", "supersedes", "scope", "rule", "exceptions"}
        if (set(decision) != expected_decision_fields or type(decision.get("schema_version")) is not int
                or decision.get("schema_version") != 1 or decision.get("status") != "active"
                or decision.get("id") != check.get("decision_id")
                or decision.get("supersedes") != check.get("supersedes")
                or not isinstance(decision.get("scope"), str) or not isinstance(decision.get("rule"), str)
                or not isinstance(decision.get("exceptions"), list)
                or any(not isinstance(item, str) for item in decision["exceptions"])):
            return False
        if (type(validation["schema_version"]) is not int or validation["schema_version"] != 1
                or validation["check_id"] != check["id"] or validation["draft_digest"] != validation["proposal"]["draft_digest"]
                or validation["check_digest"] != digest(check) or validation["decision_digest"] != digest(decision)
                or validation["adapter_version"] != check["adapter"]
                or not isinstance(validation["input_digest"], str) or not re.fullmatch(r"[0-9a-f]{64}", validation["input_digest"])
                or not _is_sha(validation["source_sha"])
                or validation["eligible"] is not True or not _valid_iso_time(validation["validated_at"])):
            return False
        proposal = validation["proposal"]
        if not isinstance(proposal, dict) or set(proposal) != _DRAFT_FIELDS:
            return False
        if not _provenance_valid(proposal):
            return False
        computed_proposal_digest = digest({key: value for key, value in proposal.items() if key != "draft_digest"})
        if (proposal["draft_digest"] != computed_proposal_digest or proposal["check"] != check
                or proposal["decision"] != decision or proposal["input_digest"] != validation["input_digest"]
                or proposal["adapter_version"] != validation["adapter_version"]
                or proposal["proposal_mode"] != validation["proposal_mode"]
                or proposal["model"] != validation["model"] or proposal["sdk_version"] != validation["sdk_version"]
                or proposal["source_sha"] != validation["source_sha"] or not _is_sha(proposal["source_sha"])):
            return False
        hashes, cases = validation["calibration_hashes"], validation["cases"]
        if not isinstance(hashes, dict) or set(hashes) != set(_CALIBRATION) or not isinstance(cases, dict) or set(cases) != set(_CALIBRATION):
            return False
        for case in _CALIBRATION:
            record = cases[case]
            if (not isinstance(record, dict) or set(record) != {"sha", "observation"}
                    or not _is_sha(record["sha"]) or record["sha"] != hashes[case]
                    or not _expected_case(case, record["observation"], check)):
                return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def verify_bundle(check: dict, decision: dict, validation: dict, approval: dict) -> bool:
    """Verify stored artifacts and their calibration semantics without trusting stored digests."""
    try:
        if not _verify_validation(check, decision, validation):
            return False
        if not isinstance(approval, dict) or set(approval) != _APPROVAL_FIELDS:
            return False
        if (type(approval["schema_version"]) is not int or approval["schema_version"] != 1
                or approval["check_id"] != check["id"]
                or approval["bundle_digest"] != bundle_digest(check, decision, check["adapter"], validation)
                or approval["validation_digest"] != digest(validation)
                or approval["calibration_hashes"] != validation["calibration_hashes"]
                or not isinstance(approval["reviewer"], str) or not approval["reviewer"].strip()
                or not isinstance(approval["reason"], str) or not approval["reason"].strip()
                or not _valid_iso_time(approval["approved_at"])):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _validate_approval_request(repo: Path, draft: dict, validation: dict,
                               reviewer: str, reason: str, commit_demo: bool) -> tuple[dict, dict]:
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("Reviewer name is required")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Approval reason is required")
    check, decision = _check_draft(repo, draft)
    if not isinstance(validation, dict) or set(validation) != _VALIDATION_FIELDS or not validation.get("eligible"):
        raise ValueError("A successful, complete calibration is required")
    if validation.get("proposal") != draft or not _verify_validation(check, decision, validation):
        raise ValueError("Validation is stale or its calibration evidence is invalid")
    if commit_demo:
        marker = repo / ".ddg-demo.json"
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Demo activation requires a generated-demo marker") from exc
        if not isinstance(metadata, dict) or metadata.get("repo") != str(repo.resolve()):
            raise ValueError("Generated-demo marker does not match the repository")
        if metadata.get("approved_base") or _run_git(repo, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("Demo activation requires a clean, not-yet-approved demo")
        if resolve_commit(repo, "HEAD") != metadata.get("refs", {}).get("calibration_good"):
            raise ValueError("Demo activation requires the corrected calibration checkout")
        branch_output = _run_git(repo, "branch", "--list")
        existing = {line.strip().lstrip("* ") for line in branch_output.splitlines() if line.strip()}
        reserved = {"approved-base", "regression", "unseen-regression", "corrected", "exception", "unrelated", "approved-abort", "approved-crashing", "approved-timing-out", "approved-missing-entrypoint", "policy-edit", "preexisting-base", "preexisting-head", "resolved"}
        if existing.intersection(reserved):
            raise ValueError("A review branch already exists")
    for relative in (f".ddg/checks/{check['id']}.json", f".ddg/validations/{check['id']}.json", f".ddg/approvals/{check['id']}.json"):
        if (repo / relative).exists():
            raise ValueError("An approved artifact already exists; refusing to overwrite it")
    return check, decision


def _run_git(repo: Path, *args: str) -> str:
    import subprocess

    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                                text=True, encoding="utf-8", timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise ValueError("Git operation failed") from exc
    if result.returncode:
        raise ValueError("Git operation failed")
    return result.stdout


def _write_bundle(repo: Path, check: dict, validation: dict, approval: dict) -> None:
    payloads = {
        f".ddg/checks/{check['id']}.json": check,
        f".ddg/validations/{check['id']}.json": validation,
        f".ddg/approvals/{check['id']}.json": approval,
    }
    staged: list[tuple[Path, Path]] = []
    try:
        for relative, value in payloads.items():
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{target.name}.", suffix=".tmp",
                                             dir=target.parent, delete=False) as stream:
                stream.write(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8") + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
                staged.append((Path(stream.name), target))
        for temporary, target in staged:
            temporary.replace(target)
    except OSError as exc:
        for temporary, _ in staged:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise ValueError("Could not atomically write approved bundle") from exc


def approve(repo: Path, draft: dict, validation: dict, reviewer: str, reason: str,
            commit_demo: bool = False) -> dict:
    """Approve exact calibrated bytes; optionally activate review commits in a generated demo."""
    repo = Path(repo).expanduser().resolve()
    check, decision = _validate_approval_request(repo, draft, validation, reviewer, reason, commit_demo)
    # Re-run calibration to reject edited observations even when their digests were recomputed.
    fresh = validate_draft(repo, draft, {
        "calibration_bad": validation["calibration_hashes"]["bad"],
        "calibration_good": validation["calibration_hashes"]["good"],
        "calibration_exception": validation["calibration_hashes"]["exception"],
    })
    if fresh["cases"] != validation["cases"] or fresh["calibration_hashes"] != validation["calibration_hashes"] or not fresh["eligible"]:
        raise ValueError("Calibration evidence changed or cannot be reproduced")
    approval = {
        "schema_version": 1,
        "check_id": check["id"],
        "bundle_digest": bundle_digest(check, decision, check["adapter"], validation),
        "reviewer": reviewer.strip(),
        "reason": reason.strip(),
        "approved_at": _now(),
        "validation_digest": digest(validation),
        "calibration_hashes": copy.deepcopy(validation["calibration_hashes"]),
    }
    if not verify_bundle(check, decision, validation, approval):
        raise ValueError("Approval bundle failed local verification")
    _write_bundle(repo, check, validation, approval)
    if commit_demo:
        activated = activate_demo(repo, check["id"])
        return {**approval, "base_sha": activated["approved_base"], "refs": activated["refs"], "repo": str(repo)}
    return approval


__all__ = ["approve", "bundle_digest", "validate_draft", "verify_bundle"]
