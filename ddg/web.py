"""Local-only HTTP boundary for the browser demo."""

from __future__ import annotations

import copy
import html
import json
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .approval import approve, validate_draft, verify_bundle
from .gitio import list_at, read_at
from .proposal import load_context, propose
from .report import is_stale

_MAX_BODY = 64 * 1024

# The browser viewer is a Next.js static export in web/out. Only these file types are served, only from inside
# that directory, and never dot-files; HTML gets the per-session token injected.
_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def _static_asset(web_dir: Path, url_path: str) -> tuple[Path, str] | None:
    rel = "index.html" if url_path in ("", "/") else url_path.lstrip("/")
    parts = rel.split("/")
    if any(not p or p.startswith(".") or "\\" in p or ":" in p for p in parts):
        return None
    candidate = (web_dir / rel).resolve()
    try:
        candidate.relative_to(web_dir)
    except ValueError:
        return None
    content_type = _STATIC_TYPES.get(candidate.suffix.lower())
    if content_type is None or not candidate.is_file():
        return None
    return candidate, content_type
_SCENARIOS = {
    "regression": ("approved-base", "regression", "Retry regression"),
    "unseen_regression": ("approved-base", "unseen-regression", "Unseen helper regression"),
    "corrected": ("approved-base", "corrected", "Corrected implementation"),
    "exception": ("approved-base", "exception", "Allowed idempotency exception"),
    "unrelated": ("approved-base", "unrelated", "Unrelated source change"),
    "abort": ("approved-base", "approved-abort", "Silent abort"),
    "crashing": ("approved-base", "approved-crashing", "Crashing client"),
    "timing_out": ("approved-base", "approved-timing-out", "Timing out client"),
    "missing_entrypoint": ("approved-base", "approved-missing-entrypoint", "Missing entry point"),
    "policy_edit": ("approved-base", "policy-edit", "Policy changed at head"),
    "preexisting_failure": ("preexisting-base", "preexisting-head", "Pre-existing failure"),
    "resolved": ("preexisting-base", "resolved", "Resolved pre-existing failure"),
}
_STATE_FIELDS = {
    "mode", "lifecycle", "old_decision", "new_decision", "draft", "validation",
    "approval", "report", "report_stale", "scenarios", "busy",
}


def _json_read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Demo metadata is unavailable or malformed") from exc
    if not isinstance(value, dict):
        raise ValueError("Demo metadata is unavailable or malformed")
    return value


def _load_approved(repo: Path, metadata: dict) -> tuple[dict, dict, dict, dict] | None:
    base = metadata.get("approved_base")
    if not isinstance(base, str):
        return None
    try:
        check_paths = list_at(repo, base, ".ddg/checks")
    except ValueError:
        return None
    for path in check_paths:
        if not path.endswith(".json"):
            continue
        try:
            check = json.loads(read_at(repo, base, path))
            check_id = check["id"]
            if path != f".ddg/checks/{check_id}.json":
                continue
            decision_id = check["decision_id"]
            decision = json.loads(read_at(repo, base, f".ddg/decisions/{decision_id}.json"))
            validation = json.loads(read_at(repo, base, f".ddg/validations/{check_id}.json"))
            approval_record = json.loads(read_at(repo, base, f".ddg/approvals/{check_id}.json"))
        except (KeyError, ValueError, json.JSONDecodeError, UnicodeError, TypeError):
            continue
        if verify_bundle(check, decision, validation, approval_record):
            return check, decision, validation, approval_record
    return None


def _initial_state(repo: Path, metadata: dict) -> dict:
    state = {
        "mode": "recorded", "lifecycle": "decision_changed", "old_decision": None,
        "new_decision": None, "draft": None, "validation": None, "approval": None,
        "report": None, "report_stale": False, "scenarios": [], "busy": False,
    }
    refs = metadata.get("refs", {})
    revision = refs.get("decision_change") if isinstance(refs, dict) else None
    try:
        context = load_context(repo, revision=revision)
        state["old_decision"] = context["old_decision"]
        state["new_decision"] = context["new_decision"]
    except (ValueError, TypeError):
        pass
    bundle = _load_approved(repo, metadata)
    if bundle:
        check, decision, validation, approval_record = bundle
        state.update({
            "lifecycle": "approved", "old_decision": None,
            "new_decision": decision, "draft": validation["proposal"],
            "validation": validation, "approval": approval_record,
            "scenarios": _scenario_list(refs),
        })
        try:
            context = load_context(repo, decision_id=decision["id"], revision=decision.get("source_sha") or revision)
            state["old_decision"] = context["old_decision"]
        except (ValueError, TypeError):
            pass
    return state


def _scenario_list(refs: dict) -> list[dict[str, str]]:
    if not isinstance(refs, dict) or not isinstance(refs.get("approved_base"), str):
        return []
    return [{"id": key, "label": label} for key, (_, head, label) in _SCENARIOS.items()
            if head in {"approved-base", "regression", "unseen-regression", "corrected", "exception", "unrelated",
                        "approved-abort", "approved-crashing", "approved-timing-out",
                        "approved-missing-entrypoint", "policy-edit", "preexisting-base",
                        "preexisting-head", "resolved"}]


def _state_dir_safe(repo: Path, state_dir: Path) -> None:
    governed = (repo / ".ddg").resolve()
    target = state_dir.resolve()
    try:
        target.relative_to(governed)
    except ValueError:
        return
    raise ValueError("Session state must stay outside repository .ddg records")


def _safe_state(state: dict) -> dict:
    if not isinstance(state, dict) or set(state) != _STATE_FIELDS:
        raise ValueError("Saved session state is invalid")
    json.dumps(state, ensure_ascii=False, allow_nan=False)
    return copy.deepcopy(state)


def _persist(server: ThreadingHTTPServer, candidate: dict | None = None) -> None:
    state = _safe_state(server.ddg_state if candidate is None else candidate)
    payload = json.dumps({"repo": str(server.ddg_repo), "state": state}, ensure_ascii=False,
                         sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    server.ddg_state_dir.mkdir(parents=True, exist_ok=True)
    target = server.ddg_state_dir / "session.json"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".session.", suffix=".tmp",
                                         dir=server.ddg_state_dir, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
        temporary.replace(target)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise RuntimeError("Could not save local session state") from exc


def _load_saved_state(server: ThreadingHTTPServer, metadata: dict) -> None:
    path = server.ddg_state_dir / "session.json"
    if not path.is_file():
        return
    try:
        record = _json_read(path)
        if set(record) != {"repo", "state"} or record["repo"] != str(server.ddg_repo):
            return
        state = _safe_state(record["state"])
        if metadata.get("approved_base"):
            # The pinned repository bundle is authoritative. An unapproved local
            # session must not hide it after restart.
            canonical = _initial_state(server.ddg_repo, metadata)
            if canonical["approval"] is None or state["approval"] is None:
                return
            draft = state["draft"]
            validation = state["validation"]
            bundle = _load_approved(server.ddg_repo, metadata)
            if (not isinstance(draft, dict) or not isinstance(validation, dict) or not bundle
                    or bundle[2] != validation or bundle[3] != state["approval"]
                    or draft != validation.get("proposal")
                    or state["mode"] != draft.get("proposal_mode")
                    or state["new_decision"] != bundle[1]
                    or state["old_decision"] != canonical["old_decision"]):
                return
            # Only retain session details once they match the verified repository
            # approval. Otherwise the canonical approval state remains in memory.
        elif state["approval"] is not None:
            # A local attestation without an activated repository bundle is not
            # authority across server restarts.
            return
        state["scenarios"] = _scenario_list(metadata.get("refs", {})) if state["approval"] else []
        state["busy"] = False
        server.ddg_state = state
    except (ValueError, TypeError, KeyError):
        return


def create_server(repo: Path, state_dir: Path, port: int = 8765) -> ThreadingHTTPServer:
    """Create a loopback-only server and safely hydrate its non-secret session state."""
    repo = Path(repo).expanduser().resolve()
    state_dir = Path(state_dir).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError("Demo repository directory does not exist")
    _state_dir_safe(repo, state_dir)
    metadata = _json_read(repo / ".ddg-demo.json")
    if metadata.get("repo") != str(repo) or not isinstance(metadata.get("refs"), dict):
        raise ValueError("Generated-demo marker does not match repository")
    state_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    project_root = Path(__file__).resolve().parents[1]
    web_dir = (project_root / "web" / "out").resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "DecisionDriftGate/1"
        sys_version = ""

        def log_message(self, _format, *args):
            # Requests can contain attacker-controlled values. Keep the local console quiet.
            return

        def _send(self, status: int, payload: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-DDG-Session", token)
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, status: int, value: dict) -> None:
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                                 separators=(",", ":")).encode("utf-8")
            self._send(status, payload, "application/json; charset=utf-8")

        def _local_request(self) -> bool:
            try:
                host = urlsplit("//" + self.headers.get("Host", "")).hostname
                host_port = urlsplit("//" + self.headers.get("Host", "")).port
            except ValueError:
                return False
            if host not in {"127.0.0.1", "localhost"}:
                return False
            bound_port = self.server.server_address[1]
            if host_port != bound_port:
                return False
            origin = self.headers.get("Origin")
            if origin:
                try:
                    parsed = urlsplit(origin)
                    origin_port = parsed.port or (80 if parsed.scheme == "http" else 443)
                except ValueError:
                    return False
                if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
                        or origin_port != bound_port):
                    return False
            return True

        def _path(self) -> str:
            return urlsplit(self.path).path

        def _discard_body(self) -> None:
            """Drain modest fixed-length bodies before rejecting a request."""
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return
            try:
                length = int(raw_length)
            except ValueError:
                self.close_connection = True
                return
            if length <= 0:
                return
            if length > 4 * _MAX_BODY:
                self.close_connection = True
                return
            previous_timeout = self.connection.gettimeout()
            try:
                self.connection.settimeout(2.0)
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(remaining, 8192))
                    if not chunk:
                        self.close_connection = True
                        return
                    remaining -= len(chunk)
            except OSError:
                self.close_connection = True
            finally:
                try:
                    self.connection.settimeout(previous_timeout)
                except OSError:
                    self.close_connection = True

        def do_GET(self):
            if not self._local_request():
                self._json(403, {"error": "Only local browser requests are allowed"})
                return
            path = self._path()
            if path == "/api/state":
                state = copy.deepcopy(self.server.ddg_state)
                state["busy"] = self.server.mutation_lock.locked()
                if state.get("report") is not None:
                    base_ref = state["report"].get("base_ref")
                    head_ref = state["report"].get("head_ref")
                    state["report_stale"] = is_stale(repo, state["report"], base_ref, head_ref)
                self._json(200, {"state": state})
                return
            asset = _static_asset(web_dir, path)
            if asset is None:
                self._json(404, {"error": "Not found"})
                return
            try:
                content = asset[0].read_bytes()
            except OSError:
                self._json(404, {"error": "Browser asset is unavailable"})
                return
            if asset[1].startswith("text/html"):
                content = content.replace(b"__DDG_SESSION_TOKEN__", html.escape(token, quote=True).encode("ascii"))
            self._send(200, content, asset[1])

        def _read_body(self) -> dict:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._discard_body()
                raise _RequestError(415, "Content-Type must be application/json")
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError as exc:
                raise _RequestError(400, "Invalid request body length") from exc
            if length < 0:
                raise _RequestError(400, "Content-Length is required")
            if length > _MAX_BODY:
                # Drain a bounded oversize request so ordinary HTTP clients receive
                # the structured 413 response; close on very large bodies.
                self._discard_body()
                raise _RequestError(413, "Request body is too large")
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise _RequestError(400, "Request body must be valid UTF-8 JSON") from exc
            if not isinstance(value, dict):
                raise _RequestError(400, "Request body must be a JSON object")
            return value

        def do_POST(self):
            if not self._local_request():
                self._discard_body()
                self._json(403, {"error": "Only local browser requests are allowed"})
                return
            if self.headers.get("X-DDG-Session") != token:
                self._discard_body()
                self._json(403, {"error": "Session token is missing or invalid"})
                return
            path = self._path()
            if path not in {"/api/propose", "/api/validate", "/api/approve", "/api/run"}:
                self._discard_body()
                self._json(404, {"error": "Not found"})
                return
            try:
                body = self._read_body()
            except _RequestError as exc:
                self._json(exc.status, {"error": str(exc)})
                return
            if not self.server.mutation_lock.acquire(blocking=False):
                self._json(409, {"error": "Another session action is already running"})
                return
            try:
                self.server.ddg_state["busy"] = True
                next_state = self._mutate(path, body)
                next_state["busy"] = False
                _persist(self.server, next_state)
                self.server.ddg_state = next_state
                self._json(200, {"state": next_state})
            except _RequestError as exc:
                self._json(exc.status, {"error": str(exc)})
            except ValueError as exc:
                # Domain exceptions are intentionally reduced to stable, safe messages.
                message = str(exc)
                status = 409 if any(word in message.lower() for word in ("stale", "already", "approved", "revision")) else 400
                self._json(status, {"error": message[:240] or "Action could not be completed"})
            except Exception:
                self._json(500, {"error": "Action failed; refresh the session before retrying"})
            finally:
                self.server.mutation_lock.release()
                self.server.ddg_state["busy"] = False

        def _mutate(self, path: str, body: dict) -> dict:
            state = copy.deepcopy(self.server.ddg_state)
            metadata = _json_read(repo / ".ddg-demo.json")
            refs = metadata.get("refs", {})
            if (path in {"/api/propose", "/api/validate"}
                    and (metadata.get("approved_base") or state.get("approval") is not None)):
                raise _RequestError(409, "This demo already has an approved check")
            if path == "/api/propose":
                if set(body) != {"mode"}:
                    raise _RequestError(400, "Proposal request must contain only mode")
                mode = body["mode"]
                if not isinstance(mode, str) or mode not in {"recorded", "live"}:
                    raise _RequestError(400, "Proposal mode must be recorded or live")
                revision = refs.get("decision_change")
                context = load_context(repo, revision=revision)
                context["env_file"] = project_root / ".env"
                if mode == "recorded":
                    capture_path = project_root / "evidence" / "gemini-proposal.json"
                    context["capture"] = _json_read(capture_path)
                draft = propose(context, mode=mode)
                state.update({"mode": mode, "lifecycle": "proposed", "old_decision": context["old_decision"],
                              "new_decision": context["new_decision"], "draft": draft,
                              "validation": None, "approval": None, "scenarios": [], "report": None,
                              "report_stale": False})
                return state
            if path == "/api/validate":
                if set(body) != {"draft_digest"} or not isinstance(body["draft_digest"], str):
                    raise _RequestError(400, "Validation request must contain a draft digest")
                draft = state.get("draft")
                if not isinstance(draft, dict) or body.get("draft_digest") != draft.get("draft_digest"):
                    raise _RequestError(409, "Draft is missing or stale")
                validation = validate_draft(repo, draft, refs)
                state["validation"] = validation
                state["approval"] = None
                state["lifecycle"] = "validated" if validation["eligible"] else "ineligible"
                state["scenarios"] = []
                return state
            if path == "/api/approve":
                if (set(body) != {"draft_digest", "reviewer", "reason"}
                        or any(not isinstance(body[key], str) for key in ("draft_digest", "reviewer", "reason"))):
                    raise _RequestError(400, "Approval request fields are invalid")
                draft = state.get("draft")
                validation = state.get("validation")
                if not isinstance(draft, dict) or body.get("draft_digest") != draft.get("draft_digest"):
                    raise _RequestError(409, "Draft is missing or stale")
                if not isinstance(validation, dict) or not validation.get("eligible") or validation.get("proposal") != draft:
                    raise _RequestError(409, "A successful validation is required before approval")
                reviewer, reason = body.get("reviewer"), body.get("reason")
                if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(reason, str) or not reason.strip():
                    raise _RequestError(400, "Reviewer and reason are required")
                activated = approve(repo, draft, validation, reviewer, reason,
                                    commit_demo=not bool(metadata.get("approved_base")))
                if "base_sha" in activated:
                    metadata = _json_read(repo / ".ddg-demo.json")
                    refs = metadata.get("refs", {})
                state["approval"] = {key: value for key, value in activated.items()
                                     if key not in {"base_sha", "refs", "repo"}}
                state["lifecycle"] = "approved"
                state["scenarios"] = _scenario_list(refs)
                return state
            if set(body) != {"scenario"}:
                raise _RequestError(400, "Review request must contain only scenario")
            scenario = body["scenario"]
            if not isinstance(scenario, str) or scenario not in _SCENARIOS:
                raise _RequestError(400, "Scenario is not in the fixed review allowlist")
            if not isinstance(state.get("approval"), dict):
                raise _RequestError(409, "An approved check is required before review")
            base_ref, head_ref, _label = _SCENARIOS[scenario]
            report = _compare(repo, base_ref, head_ref)
            report["base_ref"] = base_ref
            report["head_ref"] = head_ref
            state["report"] = report
            state["report_stale"] = False
            state["lifecycle"] = "reviewed"
            return state

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.ddg_repo = repo
    server.ddg_state_dir = state_dir
    server.ddg_token = token
    server.mutation_lock = threading.Lock()
    server.ddg_state = _initial_state(repo, metadata)
    _load_saved_state(server, metadata)
    return server


def _compare(repo: Path, base_ref: str, head_ref: str) -> dict:
    from .engine import compare

    return compare(repo, base_ref, head_ref)


class _RequestError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


__all__ = ["create_server"]
