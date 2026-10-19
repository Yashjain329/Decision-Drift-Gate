"""Portable JSON and readable Markdown reports bound to pinned revisions."""

from __future__ import annotations

import html
import json
import os
import re
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

from .contracts import canonical_bytes
from .gitio import resolve_commit

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+!|~>])")
_BACKTICKS = re.compile(r"`+")
_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)
_MIN_SECRET_LENGTH = 8
_REPLACE_ATTEMPTS = 60


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


def _visible(text: str) -> str:
    """Spell out invisible/format characters (bidi overrides, zero-width, controls, NUL)."""
    return "".join(
        f"\\u{ord(char):04x}" if char not in "\n\t" and unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}
        else char
        for char in text
    )


def _escaped(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = _json_text(value)
    elif value is None:
        text = "Not recorded"
    else:
        text = str(value)
    return html.escape(_visible(text), quote=False)


def _inline(value: Any) -> str:
    """One line of plain Markdown text: no structure can be introduced by the value."""
    return _MD_SPECIAL.sub(r"\\\1", " ".join(_escaped(value).split()))


def _code(value: Any) -> str:
    """Value for an inline code span; backticks are replaced so the span cannot close."""
    return " ".join(_escaped(value).replace("`", "'").split())


def _fence(language: str, value: Any) -> list[str]:
    """A fenced block whose fence is longer than any backtick run inside the content."""
    body = _escaped(value)
    longest = max((len(run) for run in _BACKTICKS.findall(body)), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence + language, body, fence, ""]


def _image_line(value) -> str:
    if not isinstance(value, dict) or not value.get("image"):
        return "none (no container)" if isinstance(value, dict) else "not recorded"
    return f"`{_code(value['image'])}` ({'digest-pinned' if value.get('pinned') is True else 'NOT digest-pinned'})"


def _markdown(report: dict) -> str:
    sandbox = report.get("sandbox")
    lines = [
        "# Decision Drift Gate report",
        "",
        f"**Result:** {_inline(report.get('aggregate'))}",
        f"**Base commit:** `{_code(report.get('base_sha'))}`",
        f"**Head commit:** `{_code(report.get('head_sha'))}`",
        f"**Adapter:** {_inline(report.get('adapter_version'))}",
        f"**Isolation:** {_inline(sandbox if sandbox is not None else 'not recorded')}"
        + (" (UNSAFE: reviewed code ran on the host)" if sandbox == "host" else ""),
        f"**Sandbox image:** {_image_line(report.get('sandbox_image'))}",
        f"**Run time (UTC):** {_inline(report.get('run_at'))}",
        "",
        "This report records approved-check observations for the two commits above.",
        "",
        "## Ordinary tests",
        "",
        *_fence("json", report.get("ordinary_tests", {})),
    ]
    active_decisions = report.get("active_decisions", [])
    lines.extend(["## Active base decisions", ""])
    if active_decisions:
        for decision in active_decisions:
            if not isinstance(decision, dict):
                continue
            lines.extend([
                f"### {_inline(decision.get('id', 'Unknown decision'))}",
                "",
                f"**Scope:** {_inline(decision.get('scope'))}",
                "",
                *_fence("json", {"rule": decision.get("rule"), "exceptions": decision.get("exceptions", [])}),
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
            f"## Check {index}: {_inline(item.get('check_id', ''))}",
            "",
            f"**Verdict:** {_inline(item.get('verdict'))}",
            f"**Governing decision:** {_inline(decision_id)}",
            "",
            *_fence("json", decision_text),
            f"**Check digest:** `{_code(item.get('check_digest'))}`",
            "",
            "### Base observation",
            "",
            *_fence("json", item.get("base", {})),
            "### Head observation",
            "",
            *_fence("json", item.get("head", {})),
            "### Approval and validation provenance",
            "",
            *_fence("json", {"approval": item.get("approval"), "validation": item.get("validation")}),
            "### Changed-line context",
            "",
            *_fence("diff", item.get("diff", "")),
        ])
    warnings = report.get("warnings", [])
    lines.extend(["## Warnings", ""])
    if warnings:
        for warning in warnings:
            if isinstance(warning, dict):
                lines.append(f"- **{_inline(warning.get('code', 'WARNING'))}:** {_inline(warning.get('message', ''))}")
            else:
                lines.append(f"- {_inline(warning)}")
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def _redact(text: str) -> str:
    """Defense in depth: never let an environment secret reach a report file."""
    for name, value in os.environ.items():
        if len(value) >= _MIN_SECRET_LENGTH and _SECRET_NAME.search(name):
            text = text.replace(value, "[REDACTED]")
    return text


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{path.name}.", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                # Windows refuses os.replace while a concurrent replace/reader holds the target.
                if attempt == _REPLACE_ATTEMPTS - 1 or path.is_dir():
                    raise
                time.sleep(0.01 * min(attempt + 1, 10))
    except (OSError, ValueError) as exc:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise ValueError("Could not write report files") from exc


def write_report(report: dict, destination: Path) -> None:
    """Write the immutable JSON evidence and an HTML-escaped Markdown sidecar."""
    if not isinstance(report, dict):
        raise ValueError("Report must be a JSON object")
    canonical_bytes(report)
    try:
        path = Path(destination).expanduser().resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        raise ValueError("Report destination is invalid") from exc
    if path.suffix.lower() != ".json":
        raise ValueError("Report destination must use a .json suffix")
    json_payload = _redact(_json_text(report) + "\n").encode("utf-8")
    markdown_payload = _redact(_markdown(report)).encode("utf-8")
    _atomic_write(path.with_suffix(".md"), markdown_payload)
    _atomic_write(path, json_payload)
