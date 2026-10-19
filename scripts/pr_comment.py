#!/usr/bin/env python3
"""Render a DDG JSON report as a PR comment (stdlib only).

Default: write Markdown to stdout. With --post, upsert one comment via `gh api`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MARKER = "<!-- ddg-report -->"
MAX_CHARS = 60000
CONCLUSIONS = {"PASSED_CHECKS": "success", "FAILED": "failure", "INCOMPLETE": "neutral"}
ICONS = {"PASSED_CHECKS": "PASS", "FAILED": "FAIL", "INCOMPLETE": "INCOMPLETE"}


def esc(value, limit: int = 300) -> str:
    """Neutralise untrusted text for inline Markdown/HTML (also safe inside table cells)."""
    text = "Not recorded" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit] + "..."
    for char in "\\`*{}[]()#|~":
        text = text.replace(char, "\\" + char)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("@", "&#64;")


def code(value, limit: int = 80) -> str:
    """Inline code span: inert, so no further escaping needed beyond backticks/pipes/angles."""
    text = " ".join(("Not recorded" if value is None else str(value)).split())[:limit]
    return "`" + text.replace("`", "'").replace("|", "/").replace("<", "&lt;").replace(">", "&gt;") + "`"


def fence(value, limit: int = 3000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str)
    text = text[:limit].replace("`", "'").replace("<", "&lt;").replace(">", "&gt;")
    return "```text\n" + text + "\n```"


def conclusion(report: dict) -> str:
    return CONCLUSIONS.get(report.get("aggregate") if isinstance(report, dict) else None, "neutral")


def _sandbox(report: dict) -> str:
    value = report.get("sandbox", report.get("sandbox_mode"))
    if isinstance(value, dict):
        value = value.get("mode")
    return value if isinstance(value, str) and value else "unknown"


def _approver(item) -> str:
    """Summarise ddg.identity evidence: {"verified": bool, "reason"|"commits": [...]}."""
    evidence = item.get("approver")
    if not isinstance(evidence, dict):
        return "Not recorded"
    if evidence.get("verified") is not True:
        return f"UNVERIFIED ({evidence.get('reason') or 'no reason recorded'})"
    commits = [c for c in evidence.get("commits") or [] if isinstance(c, dict)]
    who = sorted({str(c.get("signer") or c.get("author_email") or "?") for c in commits})
    return "verified: " + ", ".join(who) if who else "verified"


def render(report) -> str:
    if not isinstance(report, dict):
        report = {}
    aggregate = report.get("aggregate")
    sandbox = _sandbox(report)
    lines = [MARKER, f"## Decision Drift Gate: {ICONS.get(aggregate, 'INCOMPLETE')} ({code(aggregate or 'no result')})", ""]
    if sandbox == "host":
        lines += ["> **UNSAFE: sandbox mode is `host`.** Untrusted PR code ran directly on this machine without a container. "
                  "Do not trust this result for untrusted contributions.", ""]
    elif sandbox == "unknown":
        lines += ["> **Warning:** sandbox mode was not recorded in this report.", ""]
    if aggregate not in CONCLUSIONS:
        lines += ["> Report is missing or malformed; treating as INCOMPLETE.", ""]
    image = report.get("sandbox_image") if isinstance(report.get("sandbox_image"), dict) else {}
    lines += [f"- **Sandbox:** `{esc(sandbox)}`"
              + (f" · image {code(image['image'], 160)} ({'digest-pinned' if image.get('pinned') is True else 'NOT digest-pinned'})"
                 if image.get("image") else ""),
              f"- **Base:** `{esc(report.get('base_sha'), 40)}`",
              f"- **Head:** `{esc(report.get('head_sha'), 40)}`",
              f"- **Check conclusion:** {conclusion(report)}", ""]
    checks = [c for c in report.get("checks") or [] if isinstance(c, dict)]
    if checks:
        lines += ["| Check | Verdict | Decision | Approver |", "|---|---|---|---|"]
        for item in checks:
            decision = item.get("decision")
            decision_id = decision.get("id") if isinstance(decision, dict) else item.get("decision_id")
            lines.append(f"| {code(item.get('check_id'))} | {code(item.get('verdict'), 40)} | "
                         f"{code(decision_id)} | {esc(_approver(item), 120)} |")
        lines.append("")
    else:
        lines += ["No approved checks were evaluated.", ""]
    warnings = [w for w in report.get("warnings") or []]
    if warnings:
        lines += ["### Warnings", ""]
        for w in warnings[:50]:
            if isinstance(w, dict):
                lines.append(f"- **{esc(w.get('code'), 60)}**: {esc(w.get('message'))}")
            else:
                lines.append(f"- {esc(w)}")
        lines.append("")
    errors = [(c.get("check_id"), c.get("error")) for c in checks if c.get("error")]
    if errors:
        lines += ["### Errors", ""] + [f"- {esc(i, 80)}: {esc(e)}" for i, e in errors[:50]] + [""]
    for item in checks:
        lines += [f"<details><summary>{esc(item.get('check_id'), 80)} details</summary>", "",
                  fence({"base": item.get("base"), "head": item.get("head"), "decision": item.get("decision")}), "",
                  "</details>", ""]
    lines.append(f"<sub>Run at {esc(report.get('run_at'), 40)}</sub>")
    text = "\n".join(lines)
    if len(text) > MAX_CHARS:
        # Cut at a closed <details> block (details are the only large part); fall back to a hard cut.
        head = text[:MAX_CHARS - 200]
        cut = head.rfind("</details>")
        head = head[:cut + len("</details>")] if cut > 0 else head.split("<details>")[0]
        text = head + "\n\n*Report truncated; see the uploaded ddg-report artifact.*\n"
    return text


def _gh(*args: str, stdin: str | None = None) -> str:
    done = subprocess.run(["gh", "api", *args], input=stdin, capture_output=True, text=True, encoding="utf-8", check=True)
    return done.stdout


def post(body: str) -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    number = event["pull_request"]["number"]
    base = f"repos/{repo}/issues/{number}/comments"
    existing = json.loads(_gh("--paginate", "--slurp", base) or "[]")
    flat = [c for page in existing for c in (page if isinstance(page, list) else [page])]
    found = next((c["id"] for c in flat if MARKER in (c.get("body") or "")
                  and (c.get("user") or {}).get("type") == "Bot"), None)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump({"body": body}, handle)
    try:
        if found:
            _gh("--method", "PATCH", f"repos/{repo}/issues/comments/{found}", "--input", handle.name)
        else:
            _gh("--method", "POST", base, "--input", handle.name)
    finally:
        os.unlink(handle.name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--post", action="store_true", help="upsert the PR comment via gh api")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = None  # fail closed: renders as INCOMPLETE
    body = render(report)
    if args.post:
        try:
            post(body)
        except Exception as exc:  # posting is best-effort; never changes the gate result
            print(f"warning: could not post comment: {type(exc).__name__} {getattr(exc, 'stderr', '')}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(body)
    print(f"conclusion={conclusion(report or {})}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
