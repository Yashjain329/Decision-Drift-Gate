"""Trusted fake service and process runner for the bounded Python adapter."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ADAPTER_VERSION, validate_check
from . import sandbox
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


_MAX_LINE = 1 << 20


def _drive_worker(proc: subprocess.Popen, service: FakeService) -> dict:
    """Serve the worker's service calls; return its final message or an error."""
    def fail(message: str) -> dict:
        return {"op": "error", "error": message}

    try:
        for line in iter(lambda: proc.stdout.readline(_MAX_LINE + 1), ""):
            if len(line) > _MAX_LINE:
                return fail("Worker message exceeded the size limit")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                return fail("Worker returned malformed JSON")
            op = msg.get("op") if isinstance(msg, dict) else None
            if op == "create":
                key = msg.get("idempotency_key")
                if (not isinstance(msg.get("operation_id"), str)
                        or not (key is None or isinstance(key, str))):
                    return fail("Worker sent a malformed service call")
                reply = service.create(msg.get("payload"), msg["operation_id"], key)
                reply = {"status": reply.status, "job_id": reply.job_id}
            elif op == "lookup":
                if not isinstance(msg.get("operation_id"), str):
                    return fail("Worker sent a malformed service call")
                reply = {"job_id": service.lookup(msg["operation_id"])}
            elif op == "done":
                returned = msg.get("returned")
                return msg if returned is None or isinstance(returned, str) else fail("Worker returned an invalid job id")
            elif op == "error":
                return fail(str(msg.get("error"))[:300] or "Target execution failed")
            else:
                return fail("Worker sent an unknown message")
            proc.stdin.write(json.dumps(reply) + "\n")
            proc.stdin.flush()
    except (OSError, ValueError):
        return fail("Worker connection failed")
    return fail(f"Worker exited with status {proc.poll()} without a result")


def _observe_run(service: FakeService, outcome: dict) -> dict:
    """Build the observation from parent-owned state; the target only supplies a return value."""
    if outcome["op"] == "error":
        return _error_observation(outcome["error"], service.events)
    returned = outcome.get("returned")
    return {
        "status": "PASS",
        "unique_jobs": len(service.jobs),
        "returned_job_exists": returned is not None and any(job["job_id"] == returned for job in service.jobs),
        "returned_job_id": returned,
        "submit_calls": service._create_calls,
        "events": service.events,
        "error": None,
    }


# Best-effort static screen, not an OS sandbox: it keeps ordinary code from reaching
# the filesystem, processes or network by accident or in the obvious ways.
_DENIED_MODULES = {
    "os", "sys", "subprocess", "socket", "ctypes", "shutil", "pathlib", "io", "gc",
    "inspect", "multiprocessing", "signal", "tempfile", "urllib", "http", "ftplib",
    "smtplib", "webbrowser", "pickle", "marshal", "code", "codeop", "pty", "posix",
    "nt", "_thread", "builtins",
}
_DENIED_CALLS = {"__import__", "eval", "exec", "compile", "open", "globals", "vars"}


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
            if name in _DENIED_MODULES:
                return f"Unsupported import: {name}"
            if name in {"importlib", "runpy"}:
                return f"Unsupported dynamic import mechanism: {name}"
            if name not in sys.stdlib_module_names:
                return f"Unsupported import: {name}"
        if isinstance(node, ast.ImportFrom) and node.module == "builtins":
            if any(alias.name in {"__import__", "eval", "exec"} for alias in node.names):
                return "Unsupported dynamic execution mechanism"
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "__builtins__":
            return "Unsupported dynamic execution mechanism"
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id in _DENIED_CALLS:
            return "Unsupported dynamic execution mechanism"
        if isinstance(function, ast.Attribute) and function.attr == "import_module":
            return "Unsupported dynamic import mechanism"
    return None


_small_worker_environment = sandbox.small_environment


def _execute(repo: Path, sha: str, scenario: str, timeout: float) -> dict:
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
        service = FakeService(scenario)
        try:
            proc, runtime, container_name = sandbox.launch(worker_path, module_path, temp_root)
        except sandbox.SandboxUnavailable as exc:
            return _error_observation(str(exc))
        except (OSError, ValueError) as exc:
            return _error_observation(f"Worker could not run: {type(exc).__name__}")
        result: dict = {}
        driver = threading.Thread(target=lambda: result.update(_drive_worker(proc, service)), daemon=True)
        driver.start()
        driver.join(float(timeout))
        timed_out = driver.is_alive()
        sandbox.reap(proc, runtime, container_name)
        driver.join(2)
        if timed_out:
            return _error_observation("Target execution timed out")
        return _observe_run(service, result or {"op": "error", "error": "Worker produced no result"})


def observe(repo: Path, sha: str, check: dict, timeout: float = 10) -> dict:
    """Run a validated check against the module stored at one Git revision."""
    checked = validate_check(check)
    observation = _execute(Path(repo), sha, checked["scenario"], timeout)
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
    observation = _execute(Path(repo), sha, "none", timeout)
    if observation["status"] == "ERROR":
        return observation
    completed = isinstance(observation["returned_job_id"], str) and observation["returned_job_exists"]
    observation["status"] = "PASS" if completed and observation["unique_jobs"] == 1 else "FAIL"
    observation["error"] = None
    return observation


__all__ = ["FakeService", "Response", "observe", "observe_happy_path"]
