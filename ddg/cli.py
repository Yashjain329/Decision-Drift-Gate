"""Command-line interface for the decision drift gate."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import adapters, sandbox
from .approval import approve, validate_draft
from .contracts import ADAPTER_VERSION
from .demo import build_demo
from .gitio import resolve_commit
from .proposal import load_context, propose
from .report import is_stale, write_report

EXIT_USAGE = 3  # usage or infrastructure error; 1 and 2 are reserved for run verdicts
EPILOG = """exit codes (ddg run):
  0  PASSED_CHECKS  every approved check held
  1  FAILED         a check detected a violation (also: validate not eligible, status stale)
  2  INCOMPLETE     the gate could not prove the change safe (never treat as pass)
  3  usage/infra    bad arguments, missing repo, unreadable file, no container runtime
"""

try:  # resource_root() locates web/ and evidence/ in installed layouts; else use the checkout
    from . import resource_root as _resource_root
    PROJECT_ROOT = Path(_resource_root())
except ImportError:
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


_CAL_FLAGS = ("calibration_bad", "calibration_good", "calibration_exception")


def _calibration_refs(repo: Path, args: argparse.Namespace) -> dict:
    """Explicit --calibration-* revisions win; otherwise use the demo marker."""
    given = {key: getattr(args, key) for key in _CAL_FLAGS}
    if any(given.values()):
        if not all(given.values()):
            raise ValueError("Give all of --calibration-bad, --calibration-good and --calibration-exception")
        return {key: resolve_commit(repo, value) for key, value in given.items()}
    if not (repo / ".ddg-demo.json").exists():
        raise ValueError("Calibration revisions required: pass --calibration-bad, --calibration-good "
                         "and --calibration-exception (no demo marker found)")
    return _refs(repo)


def _git_email(repo: Path) -> str | None:
    import subprocess

    try:
        out = subprocess.run(["git", "-C", str(repo), "config", "user.email"], capture_output=True,
                             text=True, encoding="utf-8", timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def _init_repo(repo: Path, approvers: list[str]) -> dict:
    if not (repo / ".git").exists():
        raise ValueError("Not a Git repository (run git init first)")
    policy = repo / ".ddg" / "approvers.json"
    if policy.exists():
        raise ValueError("Refusing to overwrite existing .ddg/approvers.json")
    approvers = approvers or [e for e in [_git_email(repo)] if e]
    if not approvers or any("@" not in a for a in approvers):
        raise ValueError("Give approver emails with --approver, or set git config user.email")
    (repo / ".ddg" / "decisions").mkdir(parents=True, exist_ok=True)
    _write_json({"schema_version": 1, "require_signed": False, "approvers": approvers}, policy)
    return {"created": [str(policy)], "approvers": approvers,
            "next": "add .ddg/decisions/<ID>.json records, then commit .ddg/ on your base branch"}


def _emit_report(report: dict, output: Path, fmt: str) -> Path:
    """Write the requested report file(s); return the primary path actually written."""
    if fmt == "both":
        write_report(report, output)
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    # staged beside the target so the final replace is atomic
    with tempfile.TemporaryDirectory(prefix=".ddg-report-", dir=output.parent) as scratch:
        staged = Path(scratch) / "report.json"
        write_report(report, staged)
        source, target = (staged, output) if fmt == "json" else (staged.with_suffix(".md"), output.with_suffix(".md"))
        source.replace(target)
    return target


def _read_boundary(path: str) -> Any:
    return _json_load(Path(path).expanduser())


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse would exit 2, which means INCOMPLETE for `run`
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m ddg", description="Run decision-linked behavioral checks",
                     epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("init", help="create the .ddg/ skeleton in a Git repository")
    setup.add_argument("--repo", type=Path, default=Path("."))
    setup.add_argument("--approver", action="append", default=[], metavar="EMAIL",
                       help="allowed approver email (repeatable; default: git config user.email)")

    init = commands.add_parser("demo-init", help="create a new synthetic demo repository")
    init.add_argument("--destination", required=True, type=Path)

    proposal = commands.add_parser("propose", help="draft a manual, recorded, or live check")
    proposal.add_argument("--repo", required=True, type=Path)
    proposal.add_argument("--adapter", default=ADAPTER_VERSION, choices=adapters.names(),
                          help="check adapter; any other than the default needs --mode manual --check FILE")
    proposal.add_argument("--decision", default="DEC-002")
    proposal.add_argument("--revision")
    proposal.add_argument("--mode", choices=("live", "recorded", "manual"), default="live")
    proposal.add_argument("--capture", type=Path, default=DEFAULT_CAPTURE)
    proposal.add_argument("--check", type=Path, help="explicit JSON body required for manual mode")
    proposal.add_argument("--provider", help="live mode: model provider (see `ddg providers`); default DDG_PROVIDER or gemini_api")
    proposal.add_argument("--model", help="live mode: model name or id for the provider (default DDG_MODEL)")
    proposal.add_argument("--out", required=True, type=Path)

    commands.add_parser("providers", help="list the model providers available for live proposals")

    validate = commands.add_parser("validate", help="calibrate a draft against known bad, good, and exception cases")
    validate.add_argument("--repo", required=True, type=Path)
    validate.add_argument("--draft", required=True, type=Path)
    validate.add_argument("--out", required=True, type=Path)
    for flag in ("bad", "good", "exception"):
        validate.add_argument(f"--calibration-{flag}", metavar="REV",
                              help=f"revision for the {flag} calibration case (default: demo marker)")

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
    run.add_argument("--out", required=True, type=Path, help="report path, must end in .json")
    run.add_argument("--format", choices=("json", "md", "both"), default="both")
    run.add_argument("--sandbox", choices=("auto", "docker", "podman", "host"),
                     help="isolation for reviewed code (default: $DDG_SANDBOX or auto); host is unsafe")

    status = commands.add_parser("status", help="check whether report refs have moved")
    status.add_argument("--repo", required=True, type=Path)
    status.add_argument("--report", required=True, type=Path)
    status.add_argument("--base", required=True)
    status.add_argument("--head", required=True)

    serve = commands.add_parser("serve", help="start the local browser interface")
    serve.add_argument("--repo", required=True, type=Path)
    serve.add_argument("--state-dir", required=True, type=Path)
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--base", help="real repositories only: commit whose approved .ddg records to show (default HEAD)")
    serve.add_argument("--report", type=Path, help="real repositories only: a ddg run JSON report to show")
    return parser


def _execute(args: argparse.Namespace) -> int:
    if args.command == "demo-init":
        result = build_demo(args.destination)
        print(_json_output(result))
        return 0

    if args.command == "providers":
        from . import providers
        print(_json_output({"providers": providers.names(), "default": providers.DEFAULT_PROVIDER,
                            "select": "DDG_PROVIDER or --provider; model via DDG_MODEL or --model"}))
        return 0

    repo = Path(args.repo).expanduser().resolve()
    if args.command == "init":
        print(_json_output(_init_repo(repo, args.approver)))
        return 0
    if args.command == "propose":
        output = _outside_governed_records(repo, args.out)
        metadata_path = repo / ".ddg-demo.json"
        revision = args.revision
        if revision is None and metadata_path.exists():
            revision = _metadata(repo).get("refs", {}).get("decision_change")
        if args.adapter != ADAPTER_VERSION and (args.mode != "manual" or args.check is None):
            raise ValueError(f"Adapter {args.adapter} supports only --mode manual with --check FILE")
        context = load_context(repo, decision_id=args.decision, revision=revision, adapter=args.adapter)
        local_env = Path.cwd() / ".env"  # provider settings: cwd first, then the install/source root
        context["env_file"] = local_env if local_env.is_file() else PROJECT_ROOT / ".env"
        if args.mode == "recorded":
            context["capture"] = _read_boundary(str(args.capture))
        elif args.mode == "manual":
            if args.check is None:
                raise ValueError("Manual mode requires --check with an explicit JSON check body")
            context["manual_check"] = _read_boundary(str(args.check))
        if args.provider:
            context["provider"] = args.provider
        if args.model:
            context["model"] = args.model
        draft = propose(context, mode=args.mode)
        _write_json(draft, output)
        print(_json_output({"draft_digest": draft["draft_digest"], "proposal_mode": draft["proposal_mode"],
                            "output": str(output)}))
        return 0

    if args.command == "validate":
        output = _outside_governed_records(repo, args.out)
        draft = _read_boundary(str(args.draft))
        result = validate_draft(repo, draft, _calibration_refs(repo, args))
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
        shown = result
        if not args.commit_demo:
            written = [str(repo / ".ddg" / d / f"{result['check_id']}.json")
                       for d in ("checks", "validations", "approvals")]
            shown = {**result, "written": written,
                     "next": "commit exactly these files as an allowed approver; ddg does not commit"}
        print(_json_output(shown))
        return 0

    if args.command == "run":
        output = _outside_governed_records(repo, args.out)
        if args.sandbox:
            os.environ["DDG_SANDBOX"] = args.sandbox
        try:
            runtime = sandbox.resolve()
        except sandbox.SandboxUnavailable as exc:
            raise ValueError(str(exc)) from exc
        if runtime == "host":
            print("warning: DDG_SANDBOX=host runs reviewed code UNSANDBOXED on this machine", file=sys.stderr)
        from .engine import compare

        report = compare(repo, args.base, args.head)
        written = _emit_report(report, output, args.format)
        print(_json_output({"aggregate": report["aggregate"], "base_sha": report["base_sha"],
                            "head_sha": report["head_sha"], "report": str(written)}))
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
        report = _read_boundary(str(args.report)) if args.report else None
        server = create_server(repo, args.state_dir, port=args.port, base=args.base, report=report)
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
        return EXIT_USAGE
    except (OSError, json.JSONDecodeError):
        print("error: command could not read or write the requested data", file=sys.stderr)
        return EXIT_USAGE
    except Exception:
        print("error: command failed", file=sys.stderr)
        return EXIT_USAGE
