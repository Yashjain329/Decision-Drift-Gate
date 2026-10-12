"""Model providers for the AI-assisted proposal step.

A provider turns one prompt into the model's raw text answer. Everything after that (strict schema
checks, exact-quote citation checks, calibration and human approval) is provider independent, so
a weak or hostile model can at worst produce a draft that fails validation.

Provider selection: DDG_PROVIDER (or the `--provider` flag), one of names(). DDG_MODEL selects the
model; DDG_PROVIDER_TIMEOUT overrides the per-call time limit in seconds.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Mapping

DEFAULT_PROVIDER = "gemini_api"
MIN_TIMEOUT, MAX_TIMEOUT = 1, 600
MAX_ANSWER_BYTES = 1 << 20


class ProviderError(Exception):
    """Failure that is safe to show: `code` is stable and the message never contains secrets."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(detail or code)


class Provider:
    """Interface. Subclasses set `name` and implement complete()."""

    name = "base"
    default_timeout = 30

    def __init__(self, model: str | None = None) -> None:
        self.model = model

    def describe(self) -> dict[str, str]:
        """Provenance recorded in the draft. Must not include credentials."""
        return {"provider": self.name, "model": self.model or "default",
                "client_version": self.client_version()}

    def client_version(self) -> str:
        return "unknown"

    def complete(self, prompt: str, schema: dict, timeout: float) -> str:
        raise NotImplementedError


Factory = Callable[[Mapping[str, str], "str | None"], Provider]
_FACTORIES: dict[str, Factory] = {}


def register(name: str, factory: Factory) -> None:
    _FACTORIES[name] = factory


def names() -> list[str]:
    _load_builtin()
    return sorted(_FACTORIES)


def timeout_seconds(provider: Provider, env: Mapping[str, str]) -> int:
    raw = env.get("DDG_PROVIDER_TIMEOUT", "").strip()
    if not raw:
        return int(provider.default_timeout)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProviderError("provider_config", "DDG_PROVIDER_TIMEOUT must be an integer") from exc
    if not MIN_TIMEOUT <= value <= MAX_TIMEOUT:
        raise ProviderError("provider_config", f"DDG_PROVIDER_TIMEOUT must be {MIN_TIMEOUT}-{MAX_TIMEOUT}")
    return value


def create(name: str | None = None, model: str | None = None,
           env: Mapping[str, str] | None = None) -> Provider:
    """Build the provider named by `name`, DDG_PROVIDER, or the default."""
    _load_builtin()
    env = os.environ if env is None else env
    chosen = (name or env.get("DDG_PROVIDER") or DEFAULT_PROVIDER).strip().lower().replace("-", "_")
    factory = _FACTORIES.get(chosen)
    if factory is None:
        raise ProviderError("provider_config", f"Unknown provider {chosen!r}; choose one of {sorted(_FACTORIES)}")
    chosen_model = (model or env.get("DDG_MODEL") or "").strip() or None
    return factory(env, chosen_model)


def _load_builtin() -> None:
    if _FACTORIES:
        return
    from . import anthropic_api, bedrock, cli, gemini_api, openai_api  # noqa: F401 (they register)


def require_env(env: Mapping[str, str], key: str, provider: str) -> str:
    value = (env.get(key) or "").strip()
    if not value:
        raise ProviderError("provider_config", f"{key} is required for the {provider} provider")
    return value


def clean_answer(text: Any) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ProviderError("provider_response_invalid", "Provider returned no text")
    if len(text.encode("utf-8", "replace")) > MAX_ANSWER_BYTES:
        raise ProviderError("provider_response_invalid", "Provider answer exceeded the size limit")
    return text
