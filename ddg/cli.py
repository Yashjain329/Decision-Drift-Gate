"""Command-line interface for the decision drift gate."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .approval import approve, validate_draft
from .demo import build_demo
from .proposal import load_context, propose
from .report import is_stale, write_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAPTURE = PROJECT_ROOT / "evidence" / "gemini-proposal.json"


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def _json_load(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON file: {Path(path).name}") from exc


def _json_output(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _write_json(value: Any, destination: Path) -> None:
    from .contracts import canonical_bytes

    canonical_bytes(value)
    path = Path(destination).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
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
        raise ValueError("Could not write output file") from exc


def _outside_governed_records(repo: Path, destination: Path) -> Path:
    target = Path(destination).expanduser().resolve()
    governed = (Path(repo).expanduser().resolve() / ".ddg").resolve()
    try:
        target.relative_to(governed)
    except ValueError:
        return target
    raise ValueError("Drafts, validations, and reports must stay outside the repository .ddg records")


def _metadata(repo: Path) -> dict:
    marker = _json_load(Path(repo) / ".ddg-demo.json")
    if not isinstance(marker, dict) or not isinstance(marker.get("refs"), dict):
        raise ValueError("Repository has no usable generated-demo metadata")
    return marker


def _refs(repo: Path) -> dict:
    refs = _metadata(repo).get("refs")
    if not isinstance(refs, dict):
        raise ValueError("Generated demo has no fixture references")
    return refs


def _read_boundary(path: str) -> Any:
    return _json_load(Path(path).expanduser())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ddg", description="Run decision-linked behavioral checks")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("demo-init", help="create a new synthetic demo repository")
    init.add_argument("--destination", required=True, type=Path)

    proposal = commands.add_parser("propose", help="draft a manual, recorded, or live check")
    proposal.add_argument("--repo", required=True, type=Path)
    proposal.add_argument("--decision", default="DEC-002")
    proposal.add_argument("--revision")
    proposal.add_argument("--mode", choices=("live", "recorded", "manual"), default="live")
    proposal.add_argument("--capture", type=Path, default=DEFAULT_CAPTURE)
    proposal.add_argument("--check", type=Path, help="explicit JSON body required for manual mode")
    proposal.add_argument("--out", required=True, type=Path)

    validate = commands.add_parser("validate", help="calibrate a draft against known bad, good, and exception cases")
    validate.add_argument("--repo", required=True, type=Path)
    validate.add_argument("--draft", required=True, type=Path)
    validate.add_argument("--out", required=True, type=Path)

    approval = commands.add_parser("approve", help="record explicit reviewer approval after calibration")
    approval.add_argument("--repo", required=True, type=Path)
    approval.add_argument("--draft", required=True, type=Path)
    approval.add_argument("--validation", required=True, type=Path)
    approval.add_argument("--reviewer", required=True)
    approval.add_argument("--reason", required=True)
    approval.add_argument("--commit-demo", action="store_true")
    approval.add_argument("--out", type=Path)

    run = commands.add_parser("run", help="compare approved checks on two revisions")
    run.add_argument("--repo", required=True, type=Path)
    run.add_argument("--base", required=True)
    run.add_argument("--head", required=True)
    run.add_argument("--out", required=True, type=Path)

    status = commands.add_parser("status", help="check whether report refs have moved")
    status.add_argument("--repo", required=True, type=Path)
    status.add_argument("--report", required=True, type=Path)
    status.add_argument("--base", required=True)
    status.add_argument("--head", required=True)

    serve = commands.add_parser("serve", help="start the local browser interface")
    serve.add_argument("--repo", required=True, type=Path)
    serve.add_argument("--state-dir", required=True, type=Path)
    serve.add_argument("--port", type=int, default=8765)
    return parser


def _execute(args: argparse.Namespace) -> int:
    if args.command == "demo-init":
        result = build_demo(args.destination)
        print(_json_output(result))
        return 0

    repo = Path(args.repo).expanduser().resolve()
    if args.command == "propose":
        output = _outside_governed_records(repo, args.out)
        metadata_path = repo / ".ddg-demo.json"
        revision = args.revision
        if revision is None and metadata_path.exists():
            revision = _metadata(repo).get("refs", {}).get("decision_change")
        context = load_context(repo, decision_id=args.decision, revision=revision)
        context["env_file"] = PROJECT_ROOT / ".env"
        if args.mode == "recorded":
            context["capture"] = _read_boundary(str(args.capture))
        elif args.mode == "manual":
            if args.check is None:
                raise ValueError("Manual mode requires --check with an explicit JSON check body")
            context["manual_check"] = _read_boundary(str(args.check))
        draft = propose(context, mode=args.mode)
        _write_json(draft, output)
        print(_json_output({"draft_digest": draft["draft_digest"], "proposal_mode": draft["proposal_mode"],
                            "output": str(output)}))
        return 0

    if args.command == "validate":
        output = _outside_governed_records(repo, args.out)
        draft = _read_boundary(str(args.draft))
        result = validate_draft(repo, draft, _refs(repo))
        _write_json(result, output)
        print(_json_output({"eligible": result["eligible"], "draft_digest": result["draft_digest"],
                            "output": str(output)}))
        return 0 if result["eligible"] else 1

    if args.command == "approve":
        draft = _read_boundary(str(args.draft))
        validation = _read_boundary(str(args.validation))
        output = _outside_governed_records(repo, args.out) if args.out else None
        result = approve(repo, draft, validation, args.reviewer, args.reason, commit_demo=args.commit_demo)
        if output:
            _write_json(result, output)
        print(_json_output(result))
        return 0

    if args.command == "run":
        output = _outside_governed_records(repo, args.out)
        from .engine import compare

        report = compare(repo, args.base, args.head)
        write_report(report, output)
        print(_json_output({"aggregate": report["aggregate"], "base_sha": report["base_sha"],
                            "head_sha": report["head_sha"], "report": str(output)}))
        return {"PASSED_CHECKS": 0, "FAILED": 1, "INCOMPLETE": 2}[report["aggregate"]]

    if args.command == "status":
        report = _read_boundary(str(args.report))
        stale = is_stale(repo, report, args.base, args.head)
        status = "STALE" if stale else "CURRENT"
        output = {"status": status, "rerun_required": stale,
                  "message": "Rerun required" if stale else "Report matches current refs",
                  "base_sha": report["base_sha"], "head_sha": report["head_sha"]}
        print(_json_output(output))
        return 1 if stale else 0

    if args.command == "serve":
        try:
            from .web import create_server
        except ImportError as exc:
            raise ValueError("Local browser interface is not installed") from exc
        server = create_server(repo, args.state_dir, port=args.port)
        try:
            address, port = server.server_address[:2]
            print(_json_output({"serving": f"http://{address}:{port}"}), flush=True)
            server.serve_forever()
        finally:
            server.server_close()
        return 0

    raise ValueError("Unknown command")


def main(argv: list[str] | None = None) -> int:
    _configure_utf8()
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        return _execute(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError):
        print("error: command could not read or write the requested data", file=sys.stderr)
        return 2
    except Exception:
        print("error: command failed", file=sys.stderr)
        return 2
