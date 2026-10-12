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


def diff_at(repo: Path, base_sha: str, head_sha: str, path: str = "src/job_client.py") -> str:
    """Return source-code context between two full commit ids."""
    base = _require_sha(base_sha)
    head = _require_sha(head_sha)
    return _git(Path(repo), "diff", "--unified=3", base, head, "--", _require_path(path))


def changed_paths_at(repo: Path, base_sha: str, head_sha: str) -> list[str]:
    """Return paths changed between two full revisions, including mode changes."""
    base = _require_sha(base_sha)
    head = _require_sha(head_sha)
    output = _git(Path(repo), "-c", "core.quotePath=false", "diff", "--name-only", "--no-renames", base, head, "--")
    return [path for path in output.splitlines() if path]


def commits_touching(repo: Path, sha: str, path: str) -> list[str]:
    """Every commit reachable from sha that changed path (newest first)."""
    commit = _require_sha(sha)
    safe_path = _require_path(path)
    out = _git(Path(repo), "log", "--format=%H", "--no-renames", commit, "--", safe_path)
    return [line for line in out.split() if _FULL_SHA.fullmatch(line)]


def commit_identity(repo: Path, commit: str) -> dict:
    """Author email, signature status code and signer of one commit, plus the paths it changed."""
    sha = _require_sha(commit)
    meta = _git(Path(repo), "show", "-s", "--format=%ae%x00%G?%x00%GS", sha).rstrip("\n").split("\x00")
    if len(meta) != 3:
        raise ValueError("Unexpected commit metadata")
    paths = _git(Path(repo), "-c", "core.quotePath=false", "diff-tree", "--root", "--no-commit-id",
                 "--name-only", "-r", "--no-renames", sha).splitlines()
    return {"author_email": meta[0].strip().lower(), "signature": meta[1], "signer": meta[2],
            "paths": [p for p in paths if p]}
