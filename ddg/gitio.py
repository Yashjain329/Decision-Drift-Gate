"""Safe, fixed-revision Git reads used by the decision gate."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise ValueError("Git operation failed") from exc
    if result.returncode:
        raise ValueError("Git operation failed")
    return result.stdout


def resolve_commit(repo: Path, ref: str) -> str:
    """Resolve a user-facing ref once and return a full SHA-1 commit id."""
    if not isinstance(ref, str) or not ref or ref.startswith("-") or "\x00" in ref:
        raise ValueError("Invalid revision")
    resolved = _git(Path(repo), "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    if not _FULL_SHA.fullmatch(resolved):
        raise ValueError("Revision did not resolve to a full SHA-1 commit")
    return resolved.lower()


def _require_sha(sha: str) -> str:
    if not isinstance(sha, str) or not _FULL_SHA.fullmatch(sha):
        raise ValueError("Revision must be a full SHA-1 commit id")
    return sha.lower()


def _require_path(path: str) -> str:
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ValueError("Invalid repository path")
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or any(p in ("", ".", "..") for p in parts):
        raise ValueError("Invalid repository path")
    return normalized


def read_at(repo: Path, sha: str, path: str) -> str:
    """Read a file from a full, immutable commit id."""
    commit = _require_sha(sha)
    safe_path = _require_path(path)
    return _git(Path(repo), "show", f"{commit}:{safe_path}")


def list_at(repo: Path, sha: str, prefix: str) -> list[str]:
    """List tracked files below a fixed repository-relative prefix at a commit."""
    commit = _require_sha(sha)
    safe_prefix = _require_path(prefix.rstrip("/\\"))
    output = _git(Path(repo), "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", commit, "--", safe_prefix)
    paths = [line for line in output.splitlines() if line]
    if any(not path.startswith(safe_prefix + "/") for path in paths):
        raise ValueError("Git returned a path outside the requested prefix")
    return sorted(paths)


def diff_at(repo: Path, base_sha: str, head_sha: str) -> str:
    """Return source-code context between two full commit ids."""
    base = _require_sha(base_sha)
    head = _require_sha(head_sha)
    return _git(Path(repo), "diff", "--unified=3", base, head, "--", "src/job_client.py")
