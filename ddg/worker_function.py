"""Sandbox entry point for the python_function_v1 adapter.

Reads one JSON request on stdin ({"function": str, "cases": [{"args": [...]}]}), imports the module
snapshot, calls the function once per case and writes one JSON result line to the real stdout.
Observation is built by the parent from this line only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _jsonable(value):
    try:
        json.dumps(value, allow_nan=False)
        return value, True
    except (TypeError, ValueError):
        return repr(value)[:200], False


def main() -> int:
    out = sys.stdout
    sys.stdout = sys.stderr  # stray prints from the target must not reach the protocol stream
    try:
        out.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        pass
    try:
        request = json.loads(sys.stdin.read())
        spec = importlib.util.spec_from_file_location("ddg_target_module", Path(sys.argv[1]))
        if spec is None or spec.loader is None:
            raise ImportError("Target module could not be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        function = getattr(module, request["function"], None)
        if not callable(function):
            raise AttributeError("Target module has no callable " + str(request["function"]))
        results = []
        for case in request["cases"]:
            try:
                value, ok = _jsonable(function(*case["args"]))
                results.append({"outcome": "returned", "value": value, "serializable": ok})
            except Exception as exc:  # the behaviour under test may legitimately raise
                results.append({"outcome": "raised", "exception": type(exc).__name__})
        payload = {"ok": True, "results": results}
    except BaseException as exc:
        payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    out.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
