"""One-shot subprocess entry point for the trusted synthetic job adapter."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from pathlib import Path


def _response(status: str, events: list[dict], *, jobs: int | None = None,
              returned_id: str | None = None, exists: bool | None = None,
              calls: int | None = None, error: str | None = None) -> dict:
    return {
        "status": status,
        "unique_jobs": jobs,
        "returned_job_exists": exists,
        "returned_job_id": returned_id,
        "submit_calls": calls,
        "events": events,
        "error": error,
    }


def run(module_path: Path, request: dict) -> dict:
    # This script is launched by absolute path, so add only the trusted source
    # root needed to import the runner's own FakeService implementation.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ddg.harness import FakeService  # noqa: PLC0415

    service = FakeService(request.get("scenario"))
    try:
        with contextlib.redirect_stdout(sys.stderr):
            spec = importlib.util.spec_from_file_location("ddg_target_job_client", module_path)
            if spec is None or spec.loader is None:
                raise ImportError("Target module could not be loaded")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            submit_job = getattr(module, "submit_job", None)
            if not callable(submit_job):
                raise AttributeError("Target module has no callable submit_job entrypoint")
            returned = submit_job(service, {"task": "synthetic"}, "operation-001")
        returned_id = returned if isinstance(returned, str) else None
        exists = returned_id is not None and any(job["job_id"] == returned_id for job in service.jobs)
        result = {
            "status": "PASS",
            "unique_jobs": len(service.jobs),
            "returned_job_exists": exists,
            "returned_job_id": returned_id,
            "submit_calls": service._create_calls,
            "events": service.events,
            "error": None,
        }
        return result
    except BaseException as exc:
        # Avoid traceback text and module stdout contaminating the JSON protocol.
        # The exception class and message are useful diagnostics and contain no
        # parent process environment values.
        return _response("ERROR", service.events, error=f"{type(exc).__name__}: {exc}")


def main() -> int:
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="strict")
            except (AttributeError, OSError, ValueError):
                # StringIO-like streams used by embedders may not support a
                # codec change; the real subprocess streams do.
                pass
    try:
        if len(sys.argv) != 2:
            raise ValueError("worker expects exactly one snapshot path")
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("worker request must be an object")
        result = run(Path(sys.argv[1]), request)
    except BaseException as exc:
        result = _response("ERROR", [], error=f"{type(exc).__name__}: {exc}")
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
