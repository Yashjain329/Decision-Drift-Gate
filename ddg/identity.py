"""Approver identity: who authored the commits that introduced an approved bundle.

Authority is the allowlist stored at the *base* revision. A bundle is trusted only
if every commit that ever touched its three artifacts was authored by an allowed
approver, touched nothing but those artifacts, and (when required) carries a good
signature (`git log %G?` == G). Author email alone is forgeable; set
`require_signed` and configure `gpg.ssh.allowedSignersFile` / a GPG keyring in CI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .gitio import commit_identity, commits_touching, entry_mode_at, read_at

POLICY_PATH = ".ddg/approvers.json"
_ARTIFACT_PREFIXES = (".ddg/checks/", ".ddg/validations/", ".ddg/approvals/")


class IdentityError(ValueError):
    pass


def unverified_allowed() -> bool:
    return os.environ.get("DDG_ALLOW_UNVERIFIED_APPROVERS") == "1"


def load_policy(repo: Path, base_sha: str) -> dict | None:
    try:
        if entry_mode_at(repo, base_sha, POLICY_PATH) is None:
            return None  # genuinely absent; anything present but unreadable must fail closed below
        raw = read_at(repo, base_sha, POLICY_PATH)
    except ValueError as exc:
        raise IdentityError(f"Approver policy is unreadable: {exc}") from exc
    try:
        policy = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IdentityError("Approver policy is not valid JSON") from exc
    if (not isinstance(policy, dict) or set(policy) != {"schema_version", "require_signed", "approvers"}
            or policy["schema_version"] != 1 or not isinstance(policy["require_signed"], bool)
            or not isinstance(policy["approvers"], list) or not policy["approvers"]
            or any(not isinstance(e, str) or "@" not in e for e in policy["approvers"])):
        raise IdentityError("Approver policy has an invalid shape")
    return {"require_signed": policy["require_signed"],
            "approvers": {e.strip().lower() for e in policy["approvers"]}}


def verify_approver(repo: Path, base_sha: str, check_id: str) -> dict:
    """Return identity evidence for a check's bundle, or raise IdentityError."""
    policy = load_policy(repo, base_sha)
    if policy is None:
        if unverified_allowed():
            return {"verified": False, "reason": "no approver policy (unverified mode)"}
        raise IdentityError("No .ddg/approvers.json at base; approver identity cannot be verified")
    artifacts = [f"{prefix}{check_id}.json" for prefix in _ARTIFACT_PREFIXES]
    commits: list[str] = []
    for artifact in artifacts:
        try:
            found = commits_touching(repo, base_sha, artifact)
        except ValueError as exc:
            raise IdentityError(f"Cannot read approval history for {artifact}: {exc}") from exc
        if not found:
            raise IdentityError(f"No commit history for {artifact}")
        commits.extend(c for c in found if c not in commits)
    evidence = []
    for commit in commits:
        try:
            info = commit_identity(repo, commit)
        except ValueError as exc:
            raise IdentityError(f"Cannot read identity of commit {commit[:12]}: {exc}") from exc
        if info["author_email"] not in policy["approvers"]:
            raise IdentityError(f"Commit {commit[:12]} author is not an allowed approver")
        if any(not p.startswith(_ARTIFACT_PREFIXES) for p in info["paths"]):
            raise IdentityError(f"Commit {commit[:12]} mixes approval artifacts with other changes")
        if policy["require_signed"] and info["signature"] != "G":
            raise IdentityError(f"Commit {commit[:12]} lacks a good signature (status {info['signature']})")
        evidence.append({"commit": commit, "author_email": info["author_email"],
                         "signature": info["signature"], "signer": info["signer"]})
    return {"verified": True, "require_signed": policy["require_signed"], "commits": evidence}
