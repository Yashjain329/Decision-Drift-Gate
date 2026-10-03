"""Trusted fake service and process runner for the bounded Python adapter."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ADAPTER_VERSION, validate_check
from .gitio import read_at, resolve_commit


@dataclass(frozen=True)
class Response:
    status: int
    job_id: str | None


class FakeService:
    """A tiny service with a one-shot acknowledgement failure."""

    def __init__(self, scenario: str | None = "commit_then_503") -> None:
        if scenario not in {None, "none", "commit_then_503", "reject_then_503"}:
            raise ValueError("Unsupported fake service scenario")
        self.scenario = None if scenario == "none" else scenario
        self.jobs: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self._create_calls = 0
        self._fault_used = False
        self._keys: dict[str, str] = {}

    def create(self, payload: Any, operation_id: str, idempotency_key: str | None = None) -> Response:
        self._create_calls += 1
        call = self._create_calls
        self.events.append({
            "event": "submit",
            "call": call,
            "operation_id": operation_id,
            "idempotency_key": idempotency_key,
        })
        if idempotency_key is not None and idempotency_key in self._keys:
            job_id = self._keys[idempotency_key]
            self.events.append({"event": "deduplicated", "call": call, "job_id": job_id})
            if self._fault_pending():
                self._fault_used = True
                self.events.append({"event": "response", "call": call, "status": 503})
                return Response(503, None)
            self.events.append({"event": "response", "call": call, "status": 201, "job_id": job_id})
            return Response(201, job_id)

        fault = self._fault_pending()
        if fault and self.scenario == "reject_then_503":
            self._fault_used = True
            self.events.append({"event": "response", "call": call, "status": 503})
            return Response(503, None)

        job_id = f"job-{len(self.jobs) + 1}"
        job = {"job_id": job_id, "operation_id": operation_id, "payload": payload}
        self.jobs.append(job)
        if idempotency_key is not None:
            self._keys[idempotency_key] = job_id
        self.events.append({"event": "accepted", "call": call, "job_id": job_id, "operation_id": operation_id})
        if fault:
            self._fault_used = True
            self.events.append({"event": "response", "call": call, "status": 503})
            return Response(503, None)
        self.events.append({"event": "response", "call": call, "status": 201, "job_id": job_id})
        return Response(201, job_id)

    def lookup(self, operation_id: str) -> str | None:
        job = next((entry for entry in self.jobs if entry["operation_id"] == operation_id), None)
        job_id = None if job is None else job["job_id"]
        self.events.append({"event": "lookup", "operation_id": operation_id, "job_id": job_id})
        return job_id

    def _fault_pending(self) -> bool:
        return self.scenario is not None and not self._fault_used


def _error_observation(message: str, events: list[dict[str, Any]] | None = None) -> dict:
    return {
        "status": "ERROR",
        "unique_jobs": None,
        "returned_job_exists": None,
        "returned_job_id": None,
        "submit_calls": None,
        "events": events or [],
        "error": message,
    }


def _parse_worker_output(returncode: int, stdout: str) -> dict:
    if returncode != 0:
        return _error_observation(f"Worker exited with status {returncode}")
    try:
        result = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return _error_observation("Worker returned malformed JSON")
    if not isinstance(result, dict) or not isinstance(result.get("status"), str):
        return _error_observation("Worker returned an invalid observation")
    required = {"status", "unique_jobs", "returned_job_exists", "returned_job_id", "submit_calls", "events", "error"}
    if set(result) != required or result["status"] not in {"PASS", "FAIL", "ERROR"}:
        return _error_observation("Worker observation has an invalid shape")
    if not isinstance(result["events"], list) or any(not isinstance(event, dict) for event in result["events"]):
        return _error_observation("Worker event trace is malformed")
    if result["error"] is not None and not isinstance(result["error"], str):
        return _error_observation("Worker error detail is malformed", result["events"])
    if result["status"] == "ERROR":
        return _error_observation(result["error"] or "Target execution failed", result["events"])
    if (isinstance(result["unique_jobs"], bool) or not isinstance(result["unique_jobs"], int)
            or result["unique_jobs"] < 0
            or not isinstance(result["returned_job_exists"], bool)
            or (result["returned_job_id"] is not None and not isinstance(result["returned_job_id"], str))
            or isinstance(result["submit_calls"], bool) or not isinstance(result["submit_calls"], int)
            or result["submit_calls"] < 0):
        return _error_observation("Worker metrics are malformed", result["events"])
    return result


def _external_import_error(source: str) -> str | None:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        return f"Module could not be parsed: {type(exc).__name__}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name.split(".", 1)[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module.split(".", 1)[0]]
        else:
            continue
        for name in names:
            if name in {"importlib", "runpy"}:
                return f"Unsupported dynamic import mechanism: {name}"
            if name not in sys.stdlib_module_names:
                return f"Unsupported import: {name}"
        if isinstance(node, ast.ImportFrom) and node.module == "builtins":
            if any(alias.name in {"__import__", "eval", "exec"} for alias in node.names):
                return "Unsupported dynamic execution mechanism"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id in {"__import__", "eval", "exec"}:
            return "Unsupported dynamic execution mechanism"
        if isinstance(function, ast.Attribute) and function.attr == "import_module":
            return "Unsupported dynamic import mechanism"
    return None


def _small_worker_environment() -> dict[str, str]:
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def _execute(repo: Path, sha: str, scenario: str, check: dict | None, timeout: float) -> dict:
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError("timeout must be a positive number")
    try:
        pinned_sha = resolve_commit(Path(repo), sha)
        source = read_at(Path(repo), pinned_sha, "src/job_client.py")
    except Exception as exc:
        return _error_observation(f"Unable to read pinned target module: {type(exc).__name__}")
    unsupported = _external_import_error(source)
    if unsupported:
        return _error_observation(unsupported)

    with tempfile.TemporaryDirectory(prefix="ddg-run-") as temp_name:
        temp_root = Path(temp_name).resolve()
        module_path = (temp_root / "src" / "job_client.py").resolve()
        if not module_path.is_relative_to(temp_root):
            return _error_observation("Snapshot path escaped its temporary root")
        module_path.parent.mkdir(parents=True)
        module_path.write_text(source, encoding="utf-8")
        worker_path = Path(__file__).with_name("worker.py").resolve()
        request = json.dumps({"scenario": scenario, "check": check}, separators=(",", ":"))
        worker_env = _small_worker_environment()
        worker_env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = subprocess.run(
                [sys.executable, str(worker_path), str(module_path)],
                input=request,
                text=True,
                encoding="utf-8",
                capture_output=True,
                cwd=temp_root,
                env=worker_env,
                timeout=float(timeout),
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _error_observation("Target execution timed out")
        except (OSError, ValueError) as exc:
            return _error_observation(f"Worker could not run: {type(exc).__name__}")
        return _parse_worker_output(completed.returncode, completed.stdout)


def observe(repo: Path, sha: str, check: dict, timeout: float = 10) -> dict:
    """Run a validated check against the module stored at one Git revision."""
    checked = validate_check(check)
    observation = _execute(Path(repo), sha, checked["scenario"], checked, timeout)
    if observation["status"] == "ERROR":
        return observation
    assertions_pass = all(
        observation[item["metric"]] == item["equals"]
        for item in checked["assertions"]
    )
    # A successful adapter call must return a real job identifier. This avoids
    # treating an intentional or malformed early exit as a valid completion.
    completed = isinstance(observation["returned_job_id"], str) and observation["returned_job_exists"]
    observation["status"] = "PASS" if assertions_pass and completed else "FAIL"
    observation["error"] = None
    return observation


def observe_happy_path(repo: Path, sha: str, timeout: float = 10) -> dict:
    """Observe ordinary successful submission against a fault-free service."""
    observation = _execute(Path(repo), sha, "none", None, timeout)
    if observation["status"] == "ERROR":
        return observation
    completed = isinstance(observation["returned_job_id"], str) and observation["returned_job_exists"]
    observation["status"] = "PASS" if completed and observation["unique_jobs"] == 1 else "FAIL"
    observation["error"] = None
    return observation


__all__ = ["FakeService", "Response", "observe", "observe_happy_path"]
