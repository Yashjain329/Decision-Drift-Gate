"""Test-only proposal and approved-demo builders."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from ddg.approval import approve, validate_draft
from ddg.contracts import digest
from ddg.demo import build_demo
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
