"""Portable JSON and readable Markdown reports bound to pinned revisions."""

from __future__ import annotations

import html
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .contracts import canonical_bytes
from .gitio import resolve_commit


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def is_stale(repo: Path, report: dict, base: str, head: str) -> bool:
    """Return whether refs no longer point at the exact commits in a saved report."""
    if not isinstance(report, dict) or not _sha(report.get("base_sha")) or not _sha(report.get("head_sha")):
        raise ValueError("Report does not contain canonical full commit ids")
    if any(not isinstance(ref, str) or not ref or ref.startswith("-") or "\x00" in ref for ref in (base, head)):
        raise ValueError("Invalid revision")
    try:
        current_base = resolve_commit(Path(repo), base)
        current_head = resolve_commit(Path(repo), head)
    except ValueError:
        return True
    return current_base != report["base_sha"] or current_head != report["head_sha"]


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def _escaped(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = _json_text(value)
    elif value is None:
        text = "Not recorded"
    else:
        text = str(value)
    return html.escape(text, quote=False)


def _markdown(report: dict) -> str:
    lines = [
        "# Decision Drift Gate report",
        "",
        f"**Result:** {_escaped(report.get('aggregate'))}",
        f"**Base commit:** `{_escaped(report.get('base_sha'))}`",
        f"**Head commit:** `{_escaped(report.get('head_sha'))}`",
        f"**Adapter:** {_escaped(report.get('adapter_version'))}",
        f"**Run time (UTC):** {_escaped(report.get('run_at'))}",
        "",
        "This report records approved-check observations for the two commits above.",
        "",
        "## Ordinary tests",
        "",
        "```json",
        _escaped(report.get("ordinary_tests", {})),
        "```",
        "",
    ]
    active_decisions = report.get("active_decisions", [])
    lines.extend(["## Active base decisions", ""])
    if active_decisions:
        for decision in active_decisions:
            if not isinstance(decision, dict):
                continue
            lines.extend([
                f"### {_escaped(decision.get('id', 'Unknown decision'))}",
                "",
                f"**Scope:** {_escaped(decision.get('scope'))}",
                "",
                _escaped({"rule": decision.get("rule"), "exceptions": decision.get("exceptions", [])}),
                "",
            ])
    else:
        lines.extend(["No active base decisions were established.", ""])
    for index, item in enumerate(report.get("checks", []), 1):
        if not isinstance(item, dict):
            continue
        decision = item.get("decision")
        if isinstance(decision, dict):
            decision_id = decision.get("id", "Unknown decision")
            decision_text = {"scope": decision.get("scope"), "rule": decision.get("rule"),
                             "exceptions": decision.get("exceptions", [])}
        else:
            decision_id = item.get("decision_id", "Unknown decision")
            decision_text = decision if isinstance(decision, str) else ""
        lines.extend([
            f"## Check {index}: {_escaped(item.get('check_id', ''))}",
            "",
            f"**Verdict:** {_escaped(item.get('verdict'))}",
            f"**Governing decision:** {_escaped(decision_id)}",
            "",
            _escaped(decision_text),
            "",
            f"**Check digest:** `{_escaped(item.get('check_digest'))}`",
            "",
            "### Base observation",
            "",
            "```json",
            _escaped(item.get("base", {})),
            "```",
            "",
            "### Head observation",
            "",
            "```json",
            _escaped(item.get("head", {})),
            "```",
            "",
            "### Approval and validation provenance",
            "",
            "```json",
            _escaped({"approval": item.get("approval"), "validation": item.get("validation")}),
            "```",
            "",
            "### Changed-line context",
            "",
            "```diff",
            _escaped(item.get("diff", "")),
            "```",
            "",
        ])
    warnings = report.get("warnings", [])
    lines.extend(["## Warnings", ""])
    if warnings:
        for warning in warnings:
            if isinstance(warning, dict):
                lines.append(f"- **{_escaped(warning.get('code', 'WARNING'))}:** {_escaped(warning.get('message', ''))}")
            else:
                lines.append(f"- {_escaped(warning)}")
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        raise ValueError("Could not write report files") from exc


def write_report(report: dict, destination: Path) -> None:
    """Write the immutable JSON evidence and an HTML-escaped Markdown sidecar."""
    if not isinstance(report, dict):
        raise ValueError("Report must be a JSON object")
    canonical_bytes(report)
    path = Path(destination).expanduser().resolve()
    if path.suffix.lower() != ".json":
        raise ValueError("Report destination must use a .json suffix")
    json_payload = (_json_text(report) + "\n").encode("utf-8")
    markdown_payload = _markdown(report).encode("utf-8")
    _atomic_write(path, json_payload)
    _atomic_write(path.with_suffix(".md"), markdown_payload)
