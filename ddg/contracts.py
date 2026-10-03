"""Strict contracts for the bounded, non-programmable check format."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any

ADAPTER_VERSION = "python_job_client_v1"
_TOP_LEVEL = {
    "schema_version", "id", "decision_id", "supersedes", "adapter",
    "scenario", "assertions", "rationale", "citations",
}
_SCENARIOS = {"commit_then_503", "reject_then_503"}
_ID = re.compile(r"^(CHK|DEC)-[A-Za-z0-9][A-Za-z0-9._-]*$")


def _json_value(value: Any) -> None:
    """Reject values which JSON would silently coerce or cannot represent."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Canonical JSON does not permit non-finite numbers")
        return
    if isinstance(value, list):
        for item in value:
            _json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Canonical JSON object keys must be strings")
            _json_value(item)
        return
    raise ValueError("Value is not JSON-compatible")


def canonical_bytes(value: dict) -> bytes:
    """Serialize a JSON object in the one canonical format used by DDG."""
    if not isinstance(value, dict):
        raise ValueError("Canonical JSON input must be an object")
    _json_value(value)
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("Value cannot be serialized as canonical JSON") from exc


def digest(value: dict) -> str:
    """Return the SHA-256 hex digest of an object's canonical JSON bytes."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _record_id(value: Any, prefix: str, field: str) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value) or not value.startswith(prefix + "-"):
        raise ValueError(f"{field} must be a valid {prefix} identifier")


def _nonblank(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonblank string")


def validate_check(value: dict) -> dict:
    """Validate a structured check and return a normalized deep copy."""
    if not isinstance(value, dict):
        raise ValueError("Check must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError("Check field names must be strings")
    if set(value) != _TOP_LEVEL:
        missing = _TOP_LEVEL - set(value)
        unknown = set(value) - _TOP_LEVEL
        raise ValueError(f"Check fields invalid (missing={sorted(missing)}, unknown={sorted(unknown)})")
    version = value["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise ValueError("schema_version must be integer 1")
    _record_id(value["id"], "CHK", "id")
    _record_id(value["decision_id"], "DEC", "decision_id")
    _record_id(value["supersedes"], "DEC", "supersedes")
    if not isinstance(value["adapter"], str) or value["adapter"] != ADAPTER_VERSION:
        raise ValueError("Unsupported adapter")
    if not isinstance(value["scenario"], str) or value["scenario"] not in _SCENARIOS:
        raise ValueError("Unsupported scenario")
    _nonblank(value["rationale"], "rationale")

    assertions = value["assertions"]
    if not isinstance(assertions, list) or len(assertions) != 2:
        raise ValueError("assertions must contain exactly two metrics")
    by_metric: dict[str, Any] = {}
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

    citations = value["citations"]
    if not isinstance(citations, list) or not citations:
        raise ValueError("citations must be a nonempty list")
    for citation in citations:
        if not isinstance(citation, dict) or set(citation) != {"decision_id", "quote"}:
            raise ValueError("Each citation must contain only decision_id and quote")
        _record_id(citation["decision_id"], "DEC", "citation decision_id")
        _nonblank(citation["quote"], "citation quote")

    return copy.deepcopy(value)



