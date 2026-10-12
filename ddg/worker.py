"""One-shot subprocess entry point for the synthetic job adapter.

The fake service and every recorded observation live in the parent process.
This worker only imports the revision under test and forwards its service
calls as JSON lines over stdin/stdout, so the code under test cannot edit the
evidence that is judged.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _Response:
    status: int
    job_id: str | None


class _ServiceProxy:
    """The only service surface the code under test can reach."""

    def __init__(self, send, receive) -> None:
        self._send = send
        self._receive = receive

    def create(self, payload, operation_id, idempotency_key=None):
        reply = self._rpc({"op": "create", "payload": payload,
                           "operation_id": operation_id, "idempotency_key": idempotency_key})
        return _Response(reply["status"], reply["job_id"])

    def lookup(self, operation_id):
        return self._rpc({"op": "lookup", "operation_id": operation_id})["job_id"]

    def _rpc(self, message: dict) -> dict:
        self._send(message)
        return self._receive()


def run(module_path: Path, send, receive) -> None:
    """Load the target, call submit_job, and report only its return value."""
    service = _ServiceProxy(send, receive)
    try:
        spec = importlib.util.spec_from_file_location("ddg_target_job_client", module_path)
        if spec is None or spec.loader is None:
            raise ImportError("Target module could not be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        submit_job = getattr(module, "submit_job", None)
        if not callable(submit_job):
            raise AttributeError("Target module has no callable submit_job entrypoint")
        returned = submit_job(service, {"task": "synthetic"}, "operation-001")
        send({"op": "done", "returned": returned if isinstance(returned, str) else None})
    except BaseException as exc:
        send({"op": "error", "error": f"{type(exc).__name__}: {exc}"})


def main() -> int:
    protocol_out = sys.stdout
    protocol_in = sys.stdin
    for stream in (protocol_in, protocol_out):
        try:
            stream.reconfigure(encoding="utf-8", errors="strict")
        except (AttributeError, OSError, ValueError):
            pass
    # Stray prints from the target must not be mistaken for protocol messages.
    sys.stdout = sys.stderr

    def send(message: dict) -> None:
        protocol_out.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
        protocol_out.flush()

    def receive() -> dict:
        line = protocol_in.readline()
        if not line:
            raise EOFError("Runner closed the connection")
        return json.loads(line)

    if len(sys.argv) != 2:
        send({"op": "error", "error": "worker expects exactly one snapshot path"})
        return 0
    run(Path(sys.argv[1]), send, receive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
