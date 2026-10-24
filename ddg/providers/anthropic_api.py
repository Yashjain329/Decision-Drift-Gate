"""Anthropic Messages API through the official `anthropic` SDK (optional extra `[anthropic]`).

Model: --model or DDG_MODEL, else DDG_ANTHROPIC_MODEL, else Claude Haiku 5.5 (claude-haiku-5-5). ANTHROPIC_BASE_URL points at a gateway.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

from . import Provider, ProviderError, clean_answer, register, require_env
from .http import check_url, raise_for_status

DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_BASE = "https://api.anthropic.com"
SYSTEM = "You output only the JSON object the user asks for. No prose, no code fences."
# Haiku 5.5 thinks by default (adaptive); leave room for thinking plus the JSON answer.
MAX_TOKENS = 16000


class AnthropicApi(Provider):
    name = "anthropic_api"

    def __init__(self, model: str, api_key: str, base_url: str = DEFAULT_BASE,
                 max_tokens: int = MAX_TOKENS, client: Any = None) -> None:
        super().__init__(model)
        self._key, self._base, self._max_tokens, self._client = api_key, base_url.rstrip("/"), max_tokens, client

    def client_version(self) -> str:
        try:
            return "anthropic " + importlib.metadata.version("anthropic")
        except importlib.metadata.PackageNotFoundError:
            return "anthropic (not installed)"

    def _sdk(self, timeout: float) -> Any:
        if self._client is None:
            check_url(self._base + "/v1/messages")  # https only, except localhost gateways
            try:
                import anthropic
            except ImportError as exc:
                raise ProviderError("provider_config",
                                    'The anthropic_api provider needs the SDK: pip install anthropic (or the [anthropic] extra)') from exc
            # DDG's own deadline and repair attempt bound the call; no hidden SDK retries.
            self._client = anthropic.Anthropic(api_key=self._key, base_url=self._base, timeout=timeout, max_retries=0)
        return self._client

    def complete(self, prompt: str, schema: dict, timeout: float) -> str:
        client = self._sdk(timeout)
        import anthropic
        try:
            response = client.messages.create(
                model=self.model, max_tokens=self._max_tokens, system=SYSTEM,
                messages=[{"role": "user", "content": prompt}], timeout=timeout)
        except anthropic.APIStatusError as exc:
            raise_for_status(exc.status_code)  # bodies are never echoed: they can hold secrets
            raise ProviderError("provider_rejected", f"Provider rejected the request (HTTP {exc.status_code})") from exc
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            raise ProviderError("provider_unavailable", "Could not reach the Anthropic API") from exc
        if response.stop_reason == "refusal":
            raise ProviderError("provider_rejected", "The model declined the request (stop_reason refusal)")
        if response.stop_reason == "max_tokens":
            raise ProviderError("provider_response_invalid", "The answer was cut off at max_tokens")
        text = "".join(block.text for block in response.content
                       if block.type == "text" and isinstance(block.text, str))
        return clean_answer(text)


def _factory(env, model):
    chosen = model or (env.get("DDG_ANTHROPIC_MODEL") or "").strip() or DEFAULT_MODEL
    return AnthropicApi(chosen, require_env(env, "ANTHROPIC_API_KEY", "anthropic_api"),
                        (env.get("ANTHROPIC_BASE_URL") or DEFAULT_BASE).strip())


register("anthropic_api", _factory)
