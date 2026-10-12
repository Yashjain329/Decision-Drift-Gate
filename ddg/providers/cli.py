"""Agent CLIs that use a subscription login instead of an API key.

claude_cli : Claude Code (`claude -p`), tools disabled, minimal system prompt.
codex_cli  : Codex CLI (`codex exec`), read-only sandbox, ephemeral session.
custom_cli : any command in DDG_CLI_COMMAND (JSON array; `{model}` is replaced). The prompt is sent
             on stdin and the answer is read from stdout. Use this for Gemini CLI and others.

Every CLI runs in an empty temporary directory, so the agent sees none of the repository. The model
only proposes a check; calibration and human approval still decide whether it is ever used.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Mapping

from . import Provider, ProviderError, clean_answer, register, require_env

SYSTEM = "You output only the JSON object the user asks for. No prose, no code fences, no tool use."
_ENV_KEEP = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "HOME",
             "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "LANG", "LC_ALL", "XDG_CONFIG_HOME",
             "XDG_DATA_HOME", "XDG_CACHE_HOME", "USER", "USERNAME", "SHELL", "NO_COLOR"}
_ENV_PREFIXES = ("CLAUDE_", "ANTHROPIC_", "CODEX_", "OPENAI_", "GEMINI_", "GOOGLE_", "CLOUDSDK_", "AWS_")


def cli_environment(env: Mapping[str, str]) -> dict[str, str]:
    """Pass what a logged-in CLI needs (home, config dirs, its own vendor variables); nothing else."""
    return {k: v for k, v in env.items() if k.upper() in _ENV_KEEP or k.upper().startswith(_ENV_PREFIXES)}


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15, check=False)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired, ProcessLookupError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


class CliProvider(Provider):
    name = "cli"
    default_timeout = 180

    def __init__(self, executable: str, build: Callable[[str | None, Path, Path], list[str]],
                 parse: Callable[[str, Path], str], model: str | None = None,
                 env: Mapping[str, str] | None = None) -> None:
        super().__init__(model)
        found = shutil.which(executable)
        if found is None:
            raise ProviderError("provider_config", f"Executable {executable!r} was not found on PATH")
        self._exe, self._build, self._parse = found, build, parse
        self._env = cli_environment(os.environ if env is None else env)
        self._version: str | None = None

    def client_version(self) -> str:
        if self._version is None:
            try:
                done = subprocess.run([self._exe, "--version"], capture_output=True, text=True, timeout=30,
                                      env=self._env, check=False)
                self._version = (done.stdout or done.stderr).strip().splitlines()[0][:80] or "unknown"
            except (OSError, subprocess.TimeoutExpired, IndexError):
                self._version = "unknown"
        return self._version

    def complete(self, prompt: str, schema: dict, timeout: float) -> str:
        with tempfile.TemporaryDirectory(prefix="ddg-cli-") as folder:
            work = Path(folder)
            argv = [self._exe, *self._build(self.model, work, work / "answer.txt")]
            try:
                proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8", errors="replace", cwd=work, env=self._env,
                                        start_new_session=(sys.platform != "win32"))
            except OSError as exc:
                raise ProviderError("provider_unavailable", f"Could not start {Path(self._exe).name}") from exc
            try:
                stdout, _stderr = proc.communicate(prompt, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                _kill_tree(proc)
                proc.communicate()
                raise ProviderError("provider_timeout", f"{Path(self._exe).name} timed out after {int(timeout)}s") from exc
            finally:
                if proc.poll() is None:
                    _kill_tree(proc)
            if proc.returncode != 0:
                raise ProviderError("provider_unavailable",
                                    f"{Path(self._exe).name} exited with status {proc.returncode}")
            return clean_answer(self._parse(stdout, work / "answer.txt"))


# ---- Claude Code -----------------------------------------------------------------------------
def _claude_build(model, _work, _out):
    argv = ["-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
            "--disable-slash-commands", "--strict-mcp-config", "--setting-sources", "",
            "--system-prompt", SYSTEM]
    return argv + (["--model", model] if model else [])


def _claude_parse(stdout, _out):
    try:
        data = json.loads(stdout)
    except ValueError as exc:
        raise ProviderError("provider_response_invalid", "claude did not return JSON") from exc
    if not isinstance(data, dict):
        raise ProviderError("provider_response_invalid", "claude returned a non-object")
    result = data.get("result")
    if data.get("is_error"):
        text = str(result or "").lower()
        code = "provider_auth_failed" if "login" in text or "auth" in text else "provider_unavailable"
        raise ProviderError(code, "claude reported an error" + (" (not logged in; run `claude` and /login)" if code == "provider_auth_failed" else ""))
    return result


# ---- Codex CLI -------------------------------------------------------------------------------
def _codex_build(model, work, out):
    argv = ["exec", "--sandbox", "read-only", "--ephemeral", "--skip-git-repo-check", "--color", "never",
            "-C", str(work), "-o", str(out)]
    return argv + (["-m", model] if model else []) + ["-"]


def _codex_parse(_stdout, out):
    try:
        return out.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProviderError("provider_response_invalid", "codex wrote no answer file") from exc


# ---- generic command -------------------------------------------------------------------------
def _custom_command(env: Mapping[str, str]) -> list[str]:
    raw = require_env(env, "DDG_CLI_COMMAND", "custom_cli")
    try:
        argv = json.loads(raw)
    except ValueError as exc:
        raise ProviderError("provider_config", "DDG_CLI_COMMAND must be a JSON array of strings") from exc
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) for a in argv):
        raise ProviderError("provider_config", "DDG_CLI_COMMAND must be a non-empty JSON array of strings")
    return argv


def _claude_factory(env, model):
    return CliProvider("claude", _claude_build, _claude_parse, model, env)


def _codex_factory(env, model):
    return CliProvider("codex", _codex_build, _codex_parse, model, env)


def _custom_factory(env, model):
    argv = _custom_command(env)
    return CliProvider(argv[0], lambda m, _w, _o: [a.replace("{model}", m or "") for a in argv[1:]],
                       lambda stdout, _o: stdout, model, env)


class _Named:
    """Give each CLI factory a distinct provider name in provenance."""

    def __init__(self, name: str, factory) -> None:
        self.name, self.factory = name, factory

    def __call__(self, env, model):
        provider = self.factory(env, model)
        provider.name = self.name
        return provider


register("claude_cli", _Named("claude_cli", _claude_factory))
register("codex_cli", _Named("codex_cli", _codex_factory))
register("custom_cli", _Named("custom_cli", _custom_factory))
