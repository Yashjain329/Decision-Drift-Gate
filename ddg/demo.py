"""Build a small, reproducible Git history for the behavioral proof."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .gitio import resolve_commit

_BAD = '''def submit_job(service, payload, operation_id):
    response = service.create(payload, operation_id)
    if response.status == 503:
        response = service.create(payload, operation_id)
    return response.job_id
'''

_GOOD = '''def submit_job(service, payload, operation_id):
    response = service.create(payload, operation_id)
    if response.status == 503:
        existing = service.lookup(operation_id)
        if existing is not None:
            return existing
        response = service.create(payload, operation_id)
    return response.job_id
'''

_EXCEPTION = '''def submit_job(service, payload, operation_id):
    response = service.create(payload, operation_id, idempotency_key=operation_id)
    if response.status == 503:
        response = service.create(payload, operation_id, idempotency_key=operation_id)
    return response.job_id
'''

_ABORT = '''def submit_job(service, payload, operation_id):
    response = service.create(payload, operation_id)
    if response.status == 503:
        return None
    return response.job_id
'''

_CRASH = '''def submit_job(service, payload, operation_id):
    raise RuntimeError("synthetic client crash")
'''

_TIMEOUT = '''def submit_job(service, payload, operation_id):
    while True:
        pass
'''

_DECISION_1 = {
    "schema_version": 1,
    "id": "DEC-001",
    "status": "superseded",
    "supersedes": None,
    "scope": "src/job_client.py",
    "rule": "Retry a submission after a 503 response.",
    "exceptions": [],
}
_DECISION_2 = {
    "schema_version": 1,
    "id": "DEC-002",
    "status": "active",
    "supersedes": "DEC-001",
    "scope": "src/job_client.py",
    "rule": "A submission must not create duplicate jobs when the first submission succeeds but its acknowledgement fails. Reconcile by operation ID, or retry using a stable idempotency key supported by the service. Returning a fabricated success or silently abandoning the operation is invalid.",
    "exceptions": ["A retry is permitted when the service rejected the first submission before creating a job."],
}


def _json_bytes(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _run(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True,
            encoding="utf-8",
            check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise ValueError("Could not construct demo Git history") from exc
    if result.returncode:
        raise ValueError("Could not construct demo Git history")
    return result.stdout.strip()


def _write(repo: Path, relative: str, content: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _commit(repo: Path, message: str) -> str:
    _run(repo, "add", "-A")
    _run(repo, "-c", "user.name=Decision Drift Gate Demo", "-c",
         "user.email=ddg-demo@example.invalid", "commit", "--quiet", "-m", message)
    return resolve_commit(repo, "HEAD")


def _branch(repo: Path, branch: str, commit: str) -> None:
    _run(repo, "branch", "-f", branch, commit)


def build_demo(destination: Path) -> dict:
    """Create synthetic history without overwriting any existing content."""
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise ValueError("Demo destination must be absent or an empty directory")
    else:
        destination.mkdir(parents=True)

    _run(destination, "init", "--quiet", "--object-format=sha1")
    _write(destination, ".gitignore", ".ddg-demo.json\n")
    _write(destination, ".ddg/decisions/DEC-001.json", _json_bytes({**_DECISION_1, "status": "active"}))
    _write(destination, "src/job_client.py", _BAD)
    first = _commit(destination, "Initial retry policy and client")

    _write(destination, ".ddg/decisions/DEC-001.json", _json_bytes(_DECISION_1))
    _write(destination, ".ddg/decisions/DEC-002.json", _json_bytes(_DECISION_2))
    policy = _commit(destination, "Replace retry rule with duplicate prevention")

    refs: dict[str, str] = {}
    _branch(destination, "calibration-bad", policy)
    refs["calibration_bad"] = policy

    _write(destination, "src/job_client.py", _GOOD)
    good = _commit(destination, "Reconcile lost acknowledgement")
    _branch(destination, "calibration-good", good)
    _branch(destination, "decision-change", good)
    refs["calibration_good"] = good
    refs["decision_change"] = good

    _write(destination, "src/job_client.py", _EXCEPTION)
    exception = _commit(destination, "Use stable idempotency key")
    _branch(destination, "calibration-exception", exception)
    refs["calibration_exception"] = exception

    _write(destination, ".ddg/decisions/DEC-002.json", _json_bytes({**_DECISION_2, "status": "superseded"}))
    _run(destination, "rm", "--quiet", ".ddg/decisions/DEC-001.json")
    missing_policy = _commit(destination, "Remove governing decision")
    _branch(destination, "missing-policy", missing_policy)
    refs["missing_policy"] = missing_policy

    for branch, key, source, message in (
        ("crashing", "crashing", _CRASH, "Synthetic crashing implementation"),
        ("timing-out", "timing_out", _TIMEOUT, "Synthetic timing out implementation"),
        ("abort", "abort", _ABORT, "Synthetic silent abort implementation"),
        ("missing-entrypoint", "missing_entrypoint", "# submit_job entrypoint intentionally absent\n", "Synthetic missing entrypoint"),
    ):
        _write(destination, "src/job_client.py", source)
        commit = _commit(destination, message)
        _branch(destination, branch, commit)
        refs[key] = commit

    refs["initial"] = first
    refs["decision_change"] = refs["calibration_good"]
    _run(destination, "checkout", "--quiet", "calibration-good")
    metadata = {"repo": str(destination), "refs": refs}
    (destination / ".ddg-demo.json").write_text(_json_bytes(metadata), encoding="utf-8", newline="\n")
    return {"repo": str(destination), "refs": refs}
