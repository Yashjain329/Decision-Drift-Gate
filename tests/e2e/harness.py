"""Shared helpers for the e2e suite: CLI subprocess runner, lifecycle driver, docker leftovers check."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from ddg import sandbox

ROOT = Path(__file__).resolve().parents[2]
DOCKER_OK = sandbox._usable("docker")
DOCKER_SKIP_REASON = "docker is not usable (docker info failed); container e2e skipped"


def cli(args, mode, cwd=ROOT, env=None, timeout=240):
    """Run `python -m ddg ...` as a real subprocess in the given sandbox mode."""
    environment = os.environ.copy()
    environment.update({"DDG_SANDBOX": mode, "DDG_ALLOW_UNVERIFIED_APPROVERS": "",
                        "PYTHONPATH": str(ROOT) + os.pathsep + environment.get("PYTHONPATH", "")})
    environment.update(env or {})
    return subprocess.run([sys.executable, "-m", "ddg", *map(str, args)], cwd=cwd, env=environment,
                          capture_output=True, text=True, encoding="utf-8", timeout=timeout)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def lifecycle(test, mode, base_dir):
    """demo-init -> recorded propose -> validate -> approve --commit-demo via the CLI.

    Returns (repo, state_dir). Asserts every step succeeds.
    """
    repo, state = Path(base_dir) / "repo", Path(base_dir) / "state"
    steps = [
        (["demo-init", "--destination", repo], ROOT),
        (["propose", "--repo", repo, "--mode", "recorded", "--out", state / "draft.json"], repo),
        (["validate", "--repo", repo, "--draft", state / "draft.json", "--out", state / "validation.json"], repo),
        (["approve", "--repo", repo, "--draft", state / "draft.json", "--validation", state / "validation.json",
          "--reviewer", "E2E Reviewer", "--reason", "Reviewed recorded calibration", "--commit-demo"], repo),
    ]
    for args, cwd in steps:
        result = cli(args, mode, cwd=cwd)
        test.assertEqual(result.returncode, 0, f"{args[0]} failed: {result.stdout}\n{result.stderr}")
    return repo, state


def docker_leftovers():
    result = subprocess.run(["docker", "ps", "-a", "--filter", "name=ddg-", "-q"],
                            capture_output=True, text=True)
    return result.stdout.split()


def require_docker(cls):
    return unittest.skipUnless(DOCKER_OK, DOCKER_SKIP_REASON)(cls)
