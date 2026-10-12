"""Build a small, reproducible Git history for the behavioral proof."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .gitio import read_at, resolve_commit

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


_UNSEEN_REGRESSION = '''def _retry(service, payload, operation_id):
    return service.create(payload, operation_id).job_id

def submit_job(service, payload, operation_id):
    first = service.create(payload, operation_id)
    if first.status == 503:
        return _retry(service, payload, operation_id)
    return first.job_id
'''


def _fixture_commit(repo: Path, branch: str, parent: str, files: dict[str, str], message: str) -> str:
    _run(repo, "checkout", "--quiet", "-B", branch, parent)
    for relative, content in files.items():
        _write(repo, relative, content)
    return _commit(repo, message)


def _write_demo_metadata(repo: Path, marker: dict) -> None:
    target = repo / ".ddg-demo.json"
    temp = repo / ".ddg-demo.json.tmp"
    temp.write_text(_json_bytes(marker), encoding="utf-8", newline="\n")
    temp.replace(target)


def activate_demo(repo: Path, check_id: str = "CHK-001") -> dict:
    """Commit an approved bundle in a marked demo and create review branches."""
    repo = Path(repo).expanduser().resolve()
    if not isinstance(check_id, str) or not re.fullmatch(r"CHK-[A-Za-z0-9][A-Za-z0-9._-]*", check_id):
        raise ValueError("Invalid check identifier for demo activation")
    marker_path = repo / ".ddg-demo.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("Repository is not a marked DDG demo") from exc
    if not isinstance(marker, dict) or marker.get("repo") != str(repo) or not isinstance(marker.get("refs"), dict):
        raise ValueError("DDG demo marker does not match this repository")
    refs = dict(marker["refs"])
    if "approved_base" in refs:
        raise ValueError("This demo already has an approved base")
    expected = refs.get("calibration_good")
    if not isinstance(expected, str) or resolve_commit(repo, "HEAD") != expected:
        raise ValueError("Demo must be checked out at its corrected calibration revision")
    status = _run(repo, "status", "--porcelain", "--untracked-files=all")
    artifacts = [f".ddg/checks/{check_id}.json", f".ddg/validations/{check_id}.json",
                 f".ddg/approvals/{check_id}.json"]
    expected_status = {"?? " + path for path in artifacts}
    if set(status.splitlines()) != expected_status:
        raise ValueError("Only the approved bundle may be pending in the demo working tree")
    for relative in artifacts:
        path = repo / relative
        if not path.is_file():
            raise ValueError("Approved bundle is incomplete")
    existing = _run(repo, "branch", "--list")
    branches = {line.strip().lstrip("* ") for line in existing.splitlines() if line.strip()}
    branch_names = {"approved-base", "regression", "unseen-regression", "corrected", "exception", "unrelated", "approved-abort", "approved-crashing", "approved-timing-out", "approved-missing-entrypoint", "policy-edit", "preexisting-base", "preexisting-head", "resolved"}
    if branches.intersection(branch_names):
        raise ValueError("Review branch already exists")

    _run(repo, "checkout", "--quiet", "--detach", expected)
    _run(repo, "add", "--", *artifacts)
    _run(repo, "-c", "user.name=Decision Drift Gate Demo", "-c",
         "user.email=ddg-demo@example.invalid", "commit", "--quiet", "-m", "Approve DEC-002 behavioral check")
    approved_base = resolve_commit(repo, "HEAD")
    _branch(repo, "approved-base", approved_base)

    refs["calibration_abort"] = refs.get("abort")
    refs.update({
        "approved_base": approved_base,
        "corrected": approved_base,
        "regression": _fixture_commit(repo, "regression", approved_base, {"src/job_client.py": _BAD}, "Seeded retry regression"),
        "unseen_regression": _fixture_commit(repo, "unseen-regression", approved_base, {"src/job_client.py": _UNSEEN_REGRESSION}, "Unseen helper retry regression"),
        "exception": _fixture_commit(repo, "exception", approved_base, {"src/job_client.py": _EXCEPTION}, "Use stable idempotency key"),
        "unrelated": _fixture_commit(repo, "unrelated", approved_base, {"src/job_client.py": "# unrelated documentation-only source comment\n" + _GOOD}, "Unrelated source comment"),
        "abort": _fixture_commit(repo, "approved-abort", approved_base, {"src/job_client.py": _ABORT}, "Silently abandon after 503"),
    })
    _branch(repo, "corrected", approved_base)
    refs["review_abort"] = refs["abort"]
    refs["review_crashing"] = _fixture_commit(repo, "approved-crashing", approved_base,
                                              {"src/job_client.py": _CRASH}, "Approved-base crashing client")
    refs["review_timing_out"] = _fixture_commit(repo, "approved-timing-out", approved_base,
                                                {"src/job_client.py": _TIMEOUT}, "Approved-base timing out client")
    refs["review_missing_entrypoint"] = _fixture_commit(
        repo, "approved-missing-entrypoint", approved_base,
        {"src/job_client.py": "# submit_job entrypoint intentionally absent\n"},
        "Approved-base missing entrypoint",
    )

    active_decision = json.loads(read_at(repo, approved_base, ".ddg/decisions/DEC-002.json"))
    changed_decision = dict(active_decision)
    changed_decision["rule"] = active_decision["rule"] + " This candidate policy edit requires review."
    refs["policy_edit"] = _fixture_commit(repo, "policy-edit", approved_base,
                                          {".ddg/decisions/DEC-002.json": _json_bytes(changed_decision)},
                                          "Edit active decision policy")
    preexisting_base = _fixture_commit(repo, "preexisting-base", approved_base,
                                       {"src/job_client.py": _BAD}, "Preexisting faulty baseline")
    refs["preexisting_base"] = preexisting_base
    refs["preexisting_head"] = _fixture_commit(repo, "preexisting-head", preexisting_base,
                                               {"src/job_client.py": "# unrelated while faulty\n" + _BAD},
                                               "Keep preexisting failure with comment")
    refs["resolved"] = _fixture_commit(repo, "resolved", preexisting_base,
                                       {"src/job_client.py": _GOOD}, "Resolve preexisting retry failure")

    _run(repo, "checkout", "--quiet", "approved-base")
    marker["refs"] = refs
    marker["approved_base"] = approved_base
    _write_demo_metadata(repo, marker)
    if _run(repo, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Demo activation left unexpected working tree changes")
    return {"repo": str(repo), "refs": refs, "approved_base": approved_base}


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
    _write(destination, ".ddg/approvers.json", _json_bytes({
        "schema_version": 1, "require_signed": False, "approvers": ["ddg-demo@example.invalid"]}))
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
