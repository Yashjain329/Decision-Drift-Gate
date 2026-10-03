"""Run the deterministic Decision Drift Gate acceptance case matrix."""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ddg.engine import compare
from ddg.gitio import resolve_commit

TIMING_FIELDS = ["reviewer_id", "condition", "task_id", "order", "setup_seconds",
                 "review_seconds", "correct_verdict", "correct_reason", "notes"]
_METRICS = ("status", "unique_jobs", "returned_job_exists", "submit_calls", "returned_job_id", "error")

# Each case records its expected outcome before running the engine. It does not
# alter the inputs or rewrite observed values to make the expected result pass.
CASES: list[dict[str, Any]] = [
    {"id": "regression", "base_ref": "approved-base", "head_ref": "regression",
     "aggregate": "FAILED", "verdict": "VIOLATION_INTRODUCED", "warning_codes": [],
     "metrics": {"base": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True},
                 "head": {"status": "FAIL", "unique_jobs": 2, "returned_job_exists": True}}},
    {"id": "unseen_regression", "base_ref": "approved-base", "head_ref": "unseen-regression",
     "aggregate": "FAILED", "verdict": "VIOLATION_INTRODUCED", "warning_codes": [],
     "metrics": {"base": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True},
                 "head": {"status": "FAIL", "unique_jobs": 2, "returned_job_exists": True}}},
    {"id": "corrected", "base_ref": "approved-base", "head_ref": "corrected",
     "aggregate": "PASSED_CHECKS", "verdict": "CHECK_PASSED", "warning_codes": [],
     "metrics": {"base": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True},
                 "head": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True}}},
    {"id": "exception", "base_ref": "approved-base", "head_ref": "exception",
     "aggregate": "PASSED_CHECKS", "verdict": "CHECK_PASSED", "warning_codes": [],
     "metrics": {"base": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True},
                 "head": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True}}},
    {"id": "unrelated", "base_ref": "approved-base", "head_ref": "unrelated",
     "aggregate": "PASSED_CHECKS", "verdict": "CHECK_PASSED", "warning_codes": [],
     "metrics": {"base": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True},
                 "head": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True}}},
    {"id": "abort", "base_ref": "approved-base", "head_ref": "approved-abort",
     "aggregate": "FAILED", "verdict": "VIOLATION_INTRODUCED", "warning_codes": [],
     "metrics": {"base": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True},
                 "head": {"status": "FAIL", "unique_jobs": 1, "returned_job_exists": False}}},
    {"id": "crashing", "base_ref": "approved-base", "head_ref": "approved-crashing",
     "aggregate": "INCOMPLETE", "verdict": "NOT_CHECKED", "warning_codes": ["EXECUTION_ERROR", "ORDINARY_TEST_ERROR"],
     "metrics": {"base": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True},
                 "head": {"status": "ERROR", "unique_jobs": None, "returned_job_exists": None}}},
    {"id": "timing_out", "base_ref": "approved-base", "head_ref": "approved-timing-out",
     "aggregate": "INCOMPLETE", "verdict": "NOT_CHECKED", "warning_codes": ["EXECUTION_ERROR", "ORDINARY_TEST_ERROR"],
     "metrics": {"base": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True},
                 "head": {"status": "ERROR", "unique_jobs": None, "returned_job_exists": None}}},
    {"id": "missing_entrypoint", "base_ref": "approved-base", "head_ref": "approved-missing-entrypoint",
     "aggregate": "INCOMPLETE", "verdict": "NOT_CHECKED", "warning_codes": ["EXECUTION_ERROR", "ORDINARY_TEST_ERROR"],
     "metrics": {"base": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True},
                 "head": {"status": "ERROR", "unique_jobs": None, "returned_job_exists": None}}},
    {"id": "policy_edit", "base_ref": "approved-base", "head_ref": "policy-edit",
     "aggregate": "INCOMPLETE", "verdict": "CHECK_PASSED", "warning_codes": ["POLICY_REVIEW_REQUIRED"],
     "metrics": {"base": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True},
                 "head": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True}}},
    {"id": "preexisting_failure", "base_ref": "preexisting-base", "head_ref": "preexisting-head",
     "aggregate": "FAILED", "verdict": "PRE_EXISTING_FAILURE", "warning_codes": [],
     "metrics": {"base": {"status": "FAIL", "unique_jobs": 2, "returned_job_exists": True},
                 "head": {"status": "FAIL", "unique_jobs": 2, "returned_job_exists": True}}},
    {"id": "resolved", "base_ref": "preexisting-base", "head_ref": "resolved",
     "aggregate": "PASSED_CHECKS", "verdict": "RESOLVED", "warning_codes": [],
     "metrics": {"base": {"status": "FAIL", "unique_jobs": 2, "returned_job_exists": True},
                 "head": {"status": "PASS", "unique_jobs": 1, "returned_job_exists": True}}},
]

_AUTHORITY_CASES = [
    {"id": "zero_authority", "base_ref": "calibration-good", "head_ref": "regression",
     "aggregate": "INCOMPLETE", "expected_verdicts": {},
     "warning_codes": ["MISSING_APPROVED_COVERAGE", "NO_ACTIVE_APPROVED_CHECKS", "POLICY_REVIEW_REQUIRED"], "metrics": {},
     "fixture_kind": "existing_unapproved_revision"},
]


def _safe_destination(repo: Path, output: Path) -> Path:
    target = Path(output).expanduser().resolve()
    try:
        target.relative_to(repo)
    except ValueError:
        return target
    raise ValueError("Evaluation output must stay outside the input repository")


def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                                text=True, encoding="utf-8", check=False, timeout=15, env=env)
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise ValueError("Could not prepare temporary authority fixtures") from exc
    if result.returncode:
        raise ValueError("Could not prepare temporary authority fixtures")
    return result.stdout.strip()


def _authority_fixture_cases(repo: Path, temporary_root: Path) -> list[dict]:
    """Create missing/forged bundle commits in a disposable clone, never in input."""
    approved_base = resolve_commit(repo, "approved-base")
    regression = resolve_commit(repo, "regression")
    clone = temporary_root / "repo"
    try:
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(repo), str(clone)],
                       capture_output=True, text=True, encoding="utf-8", check=True, timeout=30)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ValueError("Could not create disposable authority-fixture clone") from exc
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "DDG Evaluation Fixture", "GIT_AUTHOR_EMAIL": "ddg-eval@example.invalid",
                "GIT_COMMITTER_NAME": "DDG Evaluation Fixture", "GIT_COMMITTER_EMAIL": "ddg-eval@example.invalid",
                "GIT_AUTHOR_DATE": "2026-10-04T12:00:00+05:30",
                "GIT_COMMITTER_DATE": "2026-10-04T12:00:00+05:30"})

    _git(clone, "checkout", "--quiet", "--detach", approved_base)
    _git(clone, "rm", "--quiet", "--", ".ddg/approvals/CHK-001.json")
    _git(clone, "-c", "user.name=DDG Evaluation Fixture", "-c", "user.email=ddg-eval@example.invalid",
         "commit", "--quiet", "-m", "Evaluation fixture missing approval", env=env)
    missing_sha = _git(clone, "rev-parse", "HEAD")

    _git(clone, "checkout", "--quiet", "--detach", approved_base)
    approval_path = clone / ".ddg" / "approvals" / "CHK-001.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["bundle_digest"] = "0" * 64
    approval_path.write_text(json.dumps(approval, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
    _git(clone, "add", "--", ".ddg/approvals/CHK-001.json")
    _git(clone, "-c", "user.name=DDG Evaluation Fixture", "-c", "user.email=ddg-eval@example.invalid",
         "commit", "--quiet", "-m", "Evaluation fixture forged approval", env=env)
    forged_sha = _git(clone, "rev-parse", "HEAD")

    return [
        {"id": "missing_bundle", "base_ref": missing_sha, "head_ref": regression,
         "_repo_path": clone,
         "aggregate": "INCOMPLETE", "expected_verdicts": {"CHK-001": "NOT_CHECKED"},
         "warning_codes": ["INVALID_APPROVAL_BUNDLE", "MISSING_APPROVED_COVERAGE", "NO_ACTIVE_APPROVED_CHECKS", "POLICY_REVIEW_REQUIRED"],
         "metrics": {"base": {"status": "ERROR", "unique_jobs": None, "returned_job_exists": None},
                     "head": {"status": "ERROR", "unique_jobs": None, "returned_job_exists": None}},
         "fixture_kind": "disposable_clone_missing_approval"},
        {"id": "forged_bundle", "base_ref": forged_sha, "head_ref": regression,
         "_repo_path": clone,
         "aggregate": "INCOMPLETE", "expected_verdicts": {"CHK-001": "NOT_CHECKED"},
         "warning_codes": ["INVALID_APPROVAL_BUNDLE", "MISSING_APPROVED_COVERAGE", "NO_ACTIVE_APPROVED_CHECKS", "POLICY_REVIEW_REQUIRED"],
         "metrics": {"base": {"status": "ERROR", "unique_jobs": None, "returned_job_exists": None},
                     "head": {"status": "ERROR", "unique_jobs": None, "returned_job_exists": None}},
         "fixture_kind": "disposable_clone_forged_digest"},
    ]


def _metrics(observation: Any) -> dict | None:
    if not isinstance(observation, dict):
        return None
    return {key: observation.get(key) for key in _METRICS}


def _evaluate_case(repo: Path, spec: dict) -> dict:
    expected_verdicts = spec.get("expected_verdicts", {"CHK-001": spec.get("verdict")})
    record = {
        "case_id": spec["id"], "base_ref": spec["base_ref"], "head_ref": spec["head_ref"],
        "fixture_kind": spec.get("fixture_kind", "approved_demo"),
        "expected_aggregate": spec["aggregate"], "expected_verdicts": expected_verdicts,
        "expected_metrics": spec["metrics"], "expected_warning_codes": list(spec["warning_codes"]),
        "observed_aggregate": None, "observed_verdicts": {}, "observed_warning_codes": [],
        "warnings": [], "base_sha": None, "head_sha": None, "run_at": None,
        "ordinary_tests": None, "check_results": [], "error": None,
    }
    try:
        report = compare(Path(spec.get("_repo_path", repo)), spec["base_ref"], spec["head_ref"])
    except Exception as exc:
        record["observed_aggregate"] = "ERROR"
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:300] or "Comparison failed"}
        record["warnings"] = [{"code": "EVALUATION_ERROR", "message": record["error"]["message"]}]
        record["observed_warning_codes"] = ["EVALUATION_ERROR"]
        record["aggregate_match"] = False
        record["verdicts_match"] = False
        record["metrics_match"] = False
        record["warning_codes_match"] = False
        record["matches_expectation"] = False
        return record

    record.update({"observed_aggregate": report.get("aggregate"), "base_sha": report.get("base_sha"),
                   "head_sha": report.get("head_sha"), "run_at": report.get("run_at"),
                   "ordinary_tests": report.get("ordinary_tests"), "warnings": report.get("warnings", [])})
    warning_codes = sorted(warning.get("code", "UNKNOWN") for warning in record["warnings"]
                           if isinstance(warning, dict))
    record["observed_warning_codes"] = warning_codes

    for item in report.get("checks", []):
        if not isinstance(item, dict):
            continue
        check_id = item.get("check_id")
        verdict = item.get("verdict")
        if isinstance(check_id, str):
            record["observed_verdicts"][check_id] = verdict
        record["check_results"].append({
            "check_id": check_id,
            "expected_verdict": expected_verdicts.get(check_id),
            "observed_verdict": verdict,
            "check_digest": item.get("check_digest"),
            "base_metrics": _metrics(item.get("base")),
            "head_metrics": _metrics(item.get("head")),
            "error": item.get("error"),
        })

    record["aggregate_match"] = record["observed_aggregate"] == spec["aggregate"]
    record["verdicts_match"] = record["observed_verdicts"] == expected_verdicts
    record["metrics_match"] = all(
        any(check.get(f"{side}_metrics") is not None and
            all(check[f"{side}_metrics"].get(key) == value for key, value in expected.items())
            for check in record["check_results"])
        for side, expected in spec["metrics"].items()
    )
    record["warning_codes_match"] = warning_codes == sorted(spec["warning_codes"])
    record["matches_expectation"] = all(record[key] for key in
                                         ("aggregate_match", "verdicts_match", "metrics_match", "warning_codes_match"))
    return record


def _source_metadata() -> dict:
    try:
        commit = resolve_commit(PROJECT_ROOT, "HEAD")
    except ValueError:
        commit = None
    try:
        status = subprocess.run(["git", "-C", str(PROJECT_ROOT), "status", "--porcelain"],
                                capture_output=True, text=True, encoding="utf-8", check=False, timeout=10)
        dirty = status.returncode != 0 or bool(status.stdout.strip())
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        dirty = None
    return {"commit": commit, "working_tree_dirty": dirty}


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{path.name}.", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ValueError("Could not write evaluation output") from exc


def evaluate(repo: Path, output: Path, cases: list[dict] | None = None) -> dict:
    """Run cases in order and write machine-readable outcomes plus an empty CSV template."""
    repo = Path(repo).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError("Input repository directory does not exist")
    destination = _safe_destination(repo, output)
    if destination.exists() and not destination.is_dir():
        raise ValueError("Evaluation output must be a directory")
    selected = CASES if cases is None else cases
    if not isinstance(selected, list) or any(not isinstance(item, dict) or
                                             not {"id", "base_ref", "head_ref", "aggregate", "warning_codes", "metrics"}.issubset(item)
                                             or ("verdict" not in item and "expected_verdicts" not in item)
                                             for item in selected):
        raise ValueError("Evaluation case definitions are invalid")
    fixture_context = tempfile.TemporaryDirectory(prefix="ddg-eval-authority-") if cases is None else None
    if cases is None:
        selected = copy.deepcopy(CASES + _AUTHORITY_CASES)
        selected.extend(_authority_fixture_cases(repo, Path(fixture_context.name)))
    seen: set[str] = set()
    for item in selected:
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in seen:
            raise ValueError("Evaluation case ids must be unique nonempty strings")
        seen.add(item["id"])

    try:
        results = [_evaluate_case(repo, spec) for spec in selected]
    finally:
        if fixture_context is not None:
            fixture_context.cleanup()
    try:
        source_head = resolve_commit(PROJECT_ROOT, "HEAD")
    except ValueError:
        source_head = None
    output_record = {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "input_repo": str(repo),
        "input_head": resolve_commit(repo, "HEAD"),
        "evaluator_source": _source_metadata(),
        "cases": results,
        "summary": {"case_count": len(results),
                    "matched_expectations": sum(bool(item["matches_expectation"]) for item in results),
                    "mismatches": [item["case_id"] for item in results if not item["matches_expectation"]]},
    }
    # Keep an explicit source ref even if filesystem status collection is unavailable.
    output_record["evaluator_source"]["commit"] = source_head
    encoded = (json.dumps(output_record, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    csv_buffer = io.StringIO(newline="")
    csv.writer(csv_buffer, lineterminator="\n").writerow(TIMING_FIELDS)
    csv_payload = csv_buffer.getvalue().encode("utf-8")
    timing_path = destination / "timing.csv"
    if timing_path.exists() and not timing_path.is_file():
        raise ValueError("Timing output path must be a file")

    destination.mkdir(parents=True, exist_ok=True)
    _atomic_write(destination / "case_results.json", encoded)
    if not timing_path.exists():
        _atomic_write(timing_path, csv_payload)
    return output_record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Decision Drift Gate acceptance cases")
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.repo, args.out)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    summary = result["summary"]
    print(json.dumps({"case_count": summary["case_count"],
                      "matched_expectations": summary["matched_expectations"],
                      "output": str(Path(args.out).expanduser().resolve())}, ensure_ascii=False, sort_keys=True))
    return 0 if not summary["mismatches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
