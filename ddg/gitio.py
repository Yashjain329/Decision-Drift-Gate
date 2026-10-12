"""Safe, fixed-revision Git reads used by the decision gate."""

from __future__ import annotations

import codecs
import os
import re
import subprocess
from pathlib import Path

_FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_BLOB_MODES = frozenset({"100644", "100755"})
DIFF_CAP_BYTES = 200 * 1024
DIFF_TRUNCATION_MARKER = "\n[DDG: diff truncated at 204800 bytes]\n"
_SHA256_MESSAGE = "SHA-256 repositories are not supported; use a SHA-1 repository"

# Repository-local config must never be able to run code. -c beats .git/config, and the
# per-command --no-ext-diff/--no-textconv flags cover diff drivers named in .gitattributes.
_HARDENING = (
    "--no-optional-locks",
    "-c", "core.fsmonitor=false",
    "-c", f"core.hooksPath={os.devnull}",
    "-c", "core.pager=cat",
    "-c", "gpg.program=gpg",
    "-c", "gpg.openpgp.program=gpg",
    "-c", "gpg.x509.program=gpgsm",
    "-c", "gpg.ssh.program=ssh-keygen",
)


def _git_bytes(repo: Path, *args: str) -> bytes:
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_EXTERNAL_DIFF", "GIT_PAGER", "GIT_ASKPASS")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", *_HARDENING, "-C", str(repo), *args],
            capture_output=True,
            check=False,
            timeout=10,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Git operation failed") from exc
    if result.returncode:
        raise ValueError("Git operation failed")
    return result.stdout


def _git(repo: Path, *args: str) -> str:
    try:
        return _git_bytes(repo, *args).decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Git output is not valid UTF-8") from exc


def _require_full_history(repo: Path) -> None:
    if _git(repo, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise ValueError("Shallow clone: commit history is incomplete (fetch with full depth)")


def _tree_entries(repo: Path, commit: str, path: str, recursive: bool) -> list[tuple[str, str, str, str]]:
    args = ["ls-tree", "-z", "--full-tree", *(("-r",) if recursive else ()), commit, "--", path]
    entries = []
    for record in _git(repo, *args).split("\0"):
        if record:
            meta, _, name = record.partition("\t")
            mode, kind, obj = meta.split(" ")
            entries.append((mode, kind, obj, name))
    return entries


def resolve_commit(repo: Path, ref: str) -> str:
    """Resolve a user-facing ref once and return a full SHA-1 commit id."""
    if not isinstance(ref, str) or not ref or ref.startswith("-") or "\x00" in ref:
        raise ValueError("Invalid revision")
    resolved = _git(Path(repo), "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    if _SHA256.fullmatch(resolved):
        raise ValueError(_SHA256_MESSAGE)
    if not _FULL_SHA.fullmatch(resolved):
        raise ValueError("Revision did not resolve to a full SHA-1 commit")
    return resolved.lower()


def _require_sha(sha: str) -> str:
    if isinstance(sha, str) and _SHA256.fullmatch(sha):
        raise ValueError(_SHA256_MESSAGE)
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
    """Read a regular file from a full, immutable commit id; symlinks, submodules and trees are rejected."""
    commit = _require_sha(sha)
    safe_path = _require_path(path)
    entries = _tree_entries(Path(repo), commit, safe_path, False)
    if len(entries) != 1 or entries[0][3] != safe_path or entries[0][1] != "blob" or entries[0][0] not in _BLOB_MODES:
        raise ValueError("Path is not a regular file at this revision")
    return _git(Path(repo), "cat-file", "blob", entries[0][2])


def entry_mode_at(repo: Path, sha: str, path: str) -> str | None:
    """Git mode of the tree entry at path (e.g. 100644, 120000, 160000), or None if absent."""
    safe_path = _require_path(path)
    entries = _tree_entries(Path(repo), _require_sha(sha), safe_path, False)
    return entries[0][0] if len(entries) == 1 and entries[0][3] == safe_path else None


def list_at(repo: Path, sha: str, prefix: str) -> list[str]:
    """List tracked regular files below a fixed prefix; any symlink or submodule entry is an error."""
    commit = _require_sha(sha)
    safe_prefix = _require_path(prefix.rstrip("/\\"))
    entries = _tree_entries(Path(repo), commit, safe_prefix, True)
    if any(kind != "blob" or mode not in _BLOB_MODES for mode, kind, _obj, _name in entries):
        raise ValueError("Symlink or submodule entry under the requested prefix")
    paths = [name for _mode, _kind, _obj, name in entries]
    if any(not path.startswith(safe_prefix + "/") for path in paths):
        raise ValueError("Git returned a path outside the requested prefix")
    return sorted(paths)


def diff_at(repo: Path, base_sha: str, head_sha: str, path: str = "src/job_client.py") -> str:
    """Return source-code context between two full commit ids, capped at DIFF_CAP_BYTES.

    The text is display context only (verdicts come from execution), so undecodable bytes are
    replaced and an over-long diff ends with DIFF_TRUNCATION_MARKER.
    """
    base = _require_sha(base_sha)
    head = _require_sha(head_sha)
    raw = _git_bytes(Path(repo), "diff", "--unified=3", "--no-ext-diff", "--no-textconv", "--no-renames",
                     base, head, "--", _require_path(path))
    # Incremental decoding keeps a multi-byte character cut by the cap from becoming a replacement char.
    text = codecs.getincrementaldecoder("utf-8")("replace").decode(raw[:DIFF_CAP_BYTES])
    return text + DIFF_TRUNCATION_MARKER if len(raw) > DIFF_CAP_BYTES else text


def changed_paths_at(repo: Path, base_sha: str, head_sha: str) -> list[str]:
    """Return paths changed between two full revisions, including mode changes."""
    base = _require_sha(base_sha)
    head = _require_sha(head_sha)
    output = _git(Path(repo), "diff", "-z", "--name-only", "--no-renames", "--no-ext-diff", "--no-textconv",
                  base, head, "--")
    return [path for path in output.split("\0") if path]


def commits_touching(repo: Path, sha: str, path: str) -> list[str]:
    """Every commit reachable from sha (through all merge parents) that changed path, newest first."""
    commit = _require_sha(sha)
    safe_path = _require_path(path)
    _require_full_history(Path(repo))
    out = _git(Path(repo), "log", "--format=%H", "--full-history", "--no-renames", commit, "--", safe_path)
    return [line for line in out.split() if _FULL_SHA.fullmatch(line)]


def commit_identity(repo: Path, commit: str) -> dict:
    """Author email, signature status code and signer of one commit, plus the paths it changed.

    For merge commits the paths are the union of the diffs against every parent.
    """
    sha = _require_sha(commit)
    meta = _git(Path(repo), "show", "-s", "--format=%ae%x00%G?%x00%GS", sha).rstrip("\n").split("\x00")
    if len(meta) != 3:
        raise ValueError("Unexpected commit metadata")
    paths = _git(Path(repo), "diff-tree", "-z", "-m", "--root", "--no-commit-id", "--name-only", "-r",
                 "--no-renames", "--no-ext-diff", sha).split("\0")
    return {"author_email": meta[0].strip().lower(), "signature": meta[1], "signer": meta[2],
            "paths": sorted({p for p in paths if p})}
