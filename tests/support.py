"""Test-only proposal and approved-demo builders."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

from ddg.approval import approve, validate_draft
from ddg.contracts import digest
from ddg.demo import build_demo
from ddg.gitio import resolve_commit
from ddg.proposal import load_context, wrap_draft


def refingerprint(draft: dict) -> dict:
    """Recompute the envelope digest after a test deliberately edits it."""
    updated = copy.deepcopy(draft)
    updated.pop("draft_digest", None)
    updated["draft_digest"] = digest(updated)
    return updated


def make_manual_draft(repo: Path, refs: dict) -> dict:
    """Create a clearly manual draft grounded in the current demo inputs."""
    context = load_context(repo, decision_id="DEC-002", revision=refs["decision_change"])
    check = json.loads(Path("examples/manual_check.json").read_text(encoding="utf-8"))
    return wrap_draft(context, check, mode="manual")


def make_approved_demo(destination: Path) -> dict:
    """Build and activate a synthetic demo using an explicitly manual check."""
    demo = build_demo(destination)
    repo = Path(demo["repo"])
    draft = make_manual_draft(repo, demo["refs"])
    validation = validate_draft(repo, draft, demo["refs"])
    approval = approve(repo, draft, validation, "Test Developer", "Reviewed manual sample", commit_demo=True)
    refs = approval.get("refs", demo["refs"])
    return {"repo": str(repo), "refs": refs, "approval": approval, "draft": draft,
            "validation": validation}


def commit_fixture(repo: Path, parent: str, files: dict[str, str | None], message: str) -> str:
    """Commit a test-only variant without touching any source checkout."""
    repo = Path(repo).resolve()
    subprocess.run(["git", "-C", str(repo), "checkout", "--quiet", "--detach", parent],
                   check=True, capture_output=True, text=True, encoding="utf-8")
    for relative, content in files.items():
        target = (repo / relative).resolve()
        if not target.is_relative_to(repo):
            raise ValueError("Fixture path escaped its generated repository")
        if content is None:
            subprocess.run(["git", "-C", str(repo), "rm", "--quiet", "--ignore-unmatch", "--", relative],
                           check=True, capture_output=True, text=True, encoding="utf-8")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True,
                   text=True, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=DDG Test", "-c",
                    "user.email=ddg-test@example.invalid", "commit", "--quiet", "-m", message],
                   check=True, capture_output=True, text=True, encoding="utf-8")
    return resolve_commit(repo, "HEAD")
