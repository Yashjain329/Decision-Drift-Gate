"""Container isolation for the revision under test.

Fail closed: if no container runtime is usable the run is NOT_CHECKED. Running
on the host requires an explicit DDG_SANDBOX=host and is recorded in reports.
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

DEFAULT_IMAGE = "python:3.12-slim"
IMAGE = DEFAULT_IMAGE  # kept for compatibility; use image() so DDG_SANDBOX_IMAGE is honoured
_IMAGE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:@-]*")
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
MEMORY = "128m"
CPUS = "0.5"
PIDS = "64"
SCRATCH = "16m"


class SandboxUnavailable(RuntimeError):
    pass


def image() -> str:
    """The sandbox image. DDG_SANDBOX_IMAGE must be a plain reference; unless it is pinned by
    @sha256 digest it also needs DDG_SANDBOX_ALLOW_UNPINNED=1 (a labelled dev override)."""
    ref = os.environ.get("DDG_SANDBOX_IMAGE", "").strip()
    if not ref:
        return DEFAULT_IMAGE
    if not _IMAGE_REF.fullmatch(ref):  # also blocks option injection such as "--privileged"
        raise SandboxUnavailable(f"DDG_SANDBOX_IMAGE is not a valid image reference: {ref[:80]!r}")
    if not _DIGEST.search(ref) and os.environ.get("DDG_SANDBOX_ALLOW_UNPINNED") != "1":
        raise SandboxUnavailable(
            f"DDG_SANDBOX_IMAGE {ref} is not digest-pinned (name@sha256:...); "
            "set DDG_SANDBOX_ALLOW_UNPINNED=1 to accept it as a dev override")
    return ref


def describe() -> dict:
    """Report-ready summary: mode, image and whether the image is digest-pinned. Never raises."""
    try:
        mode = resolve()
        ref = None if mode == "host" else image()
    except SandboxUnavailable as exc:
        return {"mode": "unavailable", "image": None, "pinned": False, "note": str(exc)}
    if mode == "host":
        return {"mode": "host", "image": None, "pinned": False, "note": "UNSAFE: target runs on the host, not in a container"}
    pinned = bool(_DIGEST.search(ref))
    note = "image is digest-pinned" if pinned else (
        "image is NOT digest-pinned (" + ("default tag" if ref == DEFAULT_IMAGE else "dev override") + ")")
    return {"mode": mode, "image": ref, "pinned": pinned, "note": note}


def requested() -> str:
    value = os.environ.get("DDG_SANDBOX", "auto").strip().lower()
    if value not in {"auto", "docker", "podman", "host"}:
        raise SandboxUnavailable(f"Unknown DDG_SANDBOX value: {value}")
    return value


@functools.lru_cache(maxsize=None)
def _usable(runtime: str) -> bool:
    if shutil.which(runtime) is None:
        return False
    try:
        return subprocess.run([runtime, "info"], capture_output=True, timeout=15, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def resolve() -> str:
    """Return 'docker', 'podman' or 'host'; raise if nothing safe is available."""
    choice = requested()
    if choice == "host":
        return "host"
    for runtime in ([choice] if choice != "auto" else ["docker", "podman"]):
        if _usable(runtime):
            return runtime
    wanted = choice if choice != "auto" else "docker or podman"
    raise SandboxUnavailable(
        f"No usable container runtime ({wanted} is missing or its daemon is not running); "
        "start it or set DDG_SANDBOX=host to run unsafely")


def container_argv(runtime: str, name: str, source_dir: Path, worker: Path,
                   module_name: str) -> list[str]:
    """Build the locked-down `run` command (pure function, unit tested)."""
    return [
        runtime, "run", "--rm", "-i", "--name", name,
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", PIDS, "--memory", MEMORY, "--memory-swap", MEMORY, "--cpus", CPUS,
        "--user", "65534:65534",
        "--tmpfs", f"/tmp:rw,noexec,nosuid,size={SCRATCH}",
        "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PYTHONIOENCODING=utf-8",
        "-v", f"{source_dir}:/work/src:ro", "-v", f"{worker}:/work/worker.py:ro",
        image(), "python", "/work/worker.py", f"/work/src/{module_name}",
    ]


def new_name() -> str:
    return "ddg-" + uuid.uuid4().hex[:16]


def force_remove(runtime: str, name: str) -> None:
    """Kill and remove a container; safe to call when it already exited."""
    try:
        subprocess.run([runtime, "rm", "-f", name], capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def ensure_image(runtime: str) -> None:
    """Pull the image once per (runtime, image), outside any per-run timeout."""
    _ensure_image(runtime, image())


@functools.lru_cache(maxsize=None)
def _ensure_image(runtime: str, ref: str) -> None:  # failures raise, so they are never cached
    try:
        if subprocess.run([runtime, "image", "inspect", ref], capture_output=True,
                          timeout=30, check=False).returncode == 0:
            return
        pulled = subprocess.run([runtime, "pull", ref], capture_output=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SandboxUnavailable(f"Could not prepare sandbox image {ref}") from exc
    if pulled.returncode:
        raise SandboxUnavailable(f"Could not pull sandbox image {ref}")


def small_environment() -> dict[str, str]:
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def launch(worker: Path, module_path: Path, temp_root: Path):
    """Start a worker on one module snapshot. Returns (process, runtime, container_name).

    Raises SandboxUnavailable (fail closed) or OSError/ValueError from Popen.
    """
    runtime = resolve()
    name = None
    if runtime == "host":
        argv, env = [sys.executable, str(worker), str(module_path)], small_environment()
    else:
        ensure_image(runtime)
        name = new_name()
        argv, env = container_argv(runtime, name, module_path.parent, worker, module_path.name), None
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", cwd=temp_root, env=env, shell=False)
    return proc, runtime, name


def reap(proc, runtime: str, name: str | None) -> None:
    """Kill the worker, remove its container and close pipes. Safe to call repeatedly."""
    proc.kill()
    if name:
        force_remove(runtime, name)
    proc.wait()
    for stream in (proc.stdin, proc.stdout):
        try:
            stream.close()
        except OSError:
            pass
