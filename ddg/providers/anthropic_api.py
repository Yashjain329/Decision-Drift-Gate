"""Anthropic Messages API (API key). Base URL is overridable for gateways."""

from __future__ import annotations

import os

from . import Provider, ProviderError, clean_answer, register, require_env
from .http import Transport, check_url, post_json, raise_for_status

API_VERSION = "2023-06-01"
DEFAULT_BASE = "https://api.anthropic.com"
SYSTEM = "You output only the JSON object the user asks for. No prose, no code fences."


class AnthropicApi(Provider):
    name = "anthropic_api"

    def __init__(self, model: str, api_key: str, base_url: str = DEFAULT_BASE,
                 max_tokens: int = 4096, transport: Transport = post_json) -> None:
        super().__init__(model)
        self._key, self._base, self._max_tokens, self._transport = api_key, base_url.rstrip("/"), max_tokens, transport

    def client_version(self) -> str:
        return f"messages-api {API_VERSION}"

    def complete(self, prompt: str, schema: dict, timeout: float) -> str:
        url = check_url(self._base + "/v1/messages")
        body = {"model": self.model, "max_tokens": self._max_tokens, "system": SYSTEM,
                "messages": [{"role": "user", "content": prompt}]}
        headers = {"x-api-key": self._key, "anthropic-version": API_VERSION, "content-type": "application/json"}
        status, response = self._transport(url, headers, body, timeout)
        raise_for_status(status)
        blocks = response.get("content")
        if not isinstance(blocks, list):
            raise ProviderError("provider_response_invalid", "Missing content blocks")
        text = "".join(b["text"] for b in blocks if isinstance(b, dict)
                       and b.get("type") == "text" and isinstance(b.get("text"), str))
        return clean_answer(text)


def _factory(env, model):
    return AnthropicApi(model or require_env(env, "DDG_MODEL", "anthropic_api"),
                        require_env(env, "ANTHROPIC_API_KEY", "anthropic_api"),
                        (env.get("ANTHROPIC_BASE_URL") or DEFAULT_BASE).strip())


register("anthropic_api", _factory)
