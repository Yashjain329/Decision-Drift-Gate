"""Generic adapter: call one pure-ish function of a single stdlib-only module and assert on results.

scenario:   {"path": "pkg/rules.py", "function": "discount"}
assertions: [{"args": [100, "GOLD"], "expect": {"returns": 80}},
             {"args": [-1, "GOLD"], "expect": {"raises": "ValueError"}}]
Limits: one module, stdlib imports only, JSON-serializable arguments and return values.
"""

from __future__ import annotations

import json
import re
import tempfile
import threading
from pathlib import Path

NAME = "python_function_v1"
MAX_CASES = 50
MAX_BYTES = 1 << 20
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*\.py$")


def _json_ok(value) -> bool:
    try:
        json.dumps(value, allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


def validate_body(value: dict) -> None:
    scenario = value["scenario"]
    if (not isinstance(scenario, dict) or set(scenario) != {"path", "function"}
            or not isinstance(scenario["path"], str) or not _PATH.fullmatch(scenario["path"])
            or ".." in scenario["path"].split("/") or "//" in scenario["path"]
            or not isinstance(scenario["function"], str) or not _IDENT.fullmatch(scenario["function"])
            or scenario["function"].startswith("__")):
        raise ValueError("scenario must be {path: <repo .py file>, function: <identifier>}")
    cases = value["assertions"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError(f"assertions must contain 1 to {MAX_CASES} cases")
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"args", "expect"}:
            raise ValueError("Each case must contain only args and expect")
        if not isinstance(case["args"], list) or not _json_ok(case["args"]):
            raise ValueError("args must be a JSON array")
        expect = case["expect"]
        if not isinstance(expect, dict) or len(expect) != 1 or next(iter(expect)) not in {"returns", "raises"}:
            raise ValueError("expect must be exactly one of returns or raises")
        if "returns" in expect and not _json_ok(expect["returns"]):
            raise ValueError("returns must be JSON-compatible")
        if "raises" in expect and (not isinstance(expect["raises"], str) or not _IDENT.fullmatch(expect["raises"])):
            raise ValueError("raises must be an exception class name")


def source_path(check: dict) -> str:
    return check["scenario"]["path"]


def _error(message: str) -> dict:
    return {"status": "ERROR", "results": [], "error": message}


def _matches(expect: dict, result: dict) -> bool:
    if "returns" in expect:
        return (result.get("outcome") == "returned" and result.get("serializable") is True
                and result.get("value") == expect["returns"]
                and type(result.get("value")) is type(expect["returns"]))
    return result.get("outcome") == "raised" and result.get("exception") == expect["raises"]


def observe(repo: Path, sha: str, check: dict, timeout: float = 10) -> dict:
    from .. import harness, sandbox
    from ..contracts import validate_check
    from ..gitio import read_at, resolve_commit

    checked = validate_check(check)
    try:
        pinned = resolve_commit(Path(repo), sha)
        source = read_at(Path(repo), pinned, checked["scenario"]["path"])
    except Exception as exc:
        return _error(f"Unable to read pinned target module: {type(exc).__name__}")
    unsupported = harness._external_import_error(source)
    if unsupported:
        return _error(unsupported)
    request = json.dumps({"function": checked["scenario"]["function"],
                          "cases": [{"args": c["args"]} for c in checked["assertions"]]})
    with tempfile.TemporaryDirectory(prefix="ddg-fn-") as temp_name:
        temp_root = Path(temp_name).resolve()
        module_path = temp_root / "src" / "target.py"
        module_path.parent.mkdir(parents=True)
        module_path.write_text(source, encoding="utf-8")
        worker = Path(__file__).resolve().parents[1] / "worker_function.py"
        try:
            proc, runtime, name = sandbox.launch(worker, module_path, temp_root)
        except sandbox.SandboxUnavailable as exc:
            return _error(str(exc))
        except (OSError, ValueError) as exc:
            return _error(f"Worker could not run: {type(exc).__name__}")
        box: dict = {}

        def talk() -> None:
            try:
                proc.stdin.write(request)
                proc.stdin.close()
                box["line"] = proc.stdout.readline(MAX_BYTES + 1)
            except (OSError, ValueError):
                box["line"] = ""

        thread = threading.Thread(target=talk, daemon=True)
        thread.start()
        thread.join(float(timeout))
        timed_out = thread.is_alive()
        sandbox.reap(proc, runtime, name)
        thread.join(2)
    if timed_out:
        return _error("Target execution timed out")
    line = box.get("line", "")
    if not line or len(line) > MAX_BYTES:
        return _error("Worker produced no result or exceeded the size limit")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return _error("Worker returned malformed JSON")
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return _error(str(payload.get("error") if isinstance(payload, dict) else "Invalid worker result")[:300])
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != len(checked["assertions"]) \
            or any(not isinstance(r, dict) for r in results):
        return _error("Worker results have an invalid shape")
    matched = [_matches(case["expect"], r) for case, r in zip(checked["assertions"], results)]
    return {"status": "PASS" if all(matched) else "FAIL", "results": results, "matched": matched, "error": None}


def ordinary(repo: Path, sha: str, timeout: float):
    return None  # no adapter-independent happy path exists for arbitrary functions


def expected_case(case: str, observation: dict, check: dict) -> bool:
    """bad must FAIL, good and exception must PASS; the observation must be internally consistent."""
    if not isinstance(observation, dict) or set(observation) != {"status", "results", "matched", "error"}:
        return False
    if observation["error"] is not None or observation["status"] not in {"PASS", "FAIL"}:
        return False
    results, matched = observation["results"], observation["matched"]
    if (not isinstance(results, list) or not isinstance(matched, list)
            or len(results) != len(check["assertions"]) or len(matched) != len(results)):
        return False
    recomputed = [isinstance(r, dict) and _matches(c["expect"], r) for c, r in zip(check["assertions"], results)]
    if matched != recomputed or (observation["status"] == "PASS") != all(recomputed):
        return False
    return observation["status"] == ("FAIL" if case == "bad" else "PASS")
