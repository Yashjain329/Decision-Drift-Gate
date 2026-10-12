"""OpenAI Chat Completions, and anything that speaks it: Azure OpenAI gateways, OpenRouter, LiteLLM,
vLLM, Ollama, LM Studio. Set OPENAI_BASE_URL (for example http://localhost:11434/v1 for Ollama)."""

from __future__ import annotations

from . import Provider, ProviderError, clean_answer, register, require_env
from .http import Transport, check_url, post_json, raise_for_status

DEFAULT_BASE = "https://api.openai.com/v1"
SYSTEM = "You output only the JSON object the user asks for. No prose, no code fences."


class OpenAICompatible(Provider):
    name = "openai_api"

    def __init__(self, model: str, api_key: str | None, base_url: str = DEFAULT_BASE,
                 max_tokens: int = 4096, transport: Transport = post_json) -> None:
        super().__init__(model)
        self._key, self._base, self._max_tokens, self._transport = api_key, base_url.rstrip("/"), max_tokens, transport

    def client_version(self) -> str:
        return "chat-completions"

    def complete(self, prompt: str, schema: dict, timeout: float) -> str:
        url = check_url(self._base + "/chat/completions")
        body = {"model": self.model, "max_tokens": self._max_tokens,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
        headers = {"content-type": "application/json"}
        if self._key:
            headers["authorization"] = "Bearer " + self._key
        status, response = self._transport(url, headers, body, timeout)
        raise_for_status(status)
        choices = response.get("choices")
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise ProviderError("provider_response_invalid", "Missing message in choices")
        return clean_answer(message.get("content"))


def _factory(env, model):
    base = (env.get("OPENAI_BASE_URL") or DEFAULT_BASE).strip()
    key = (env.get("OPENAI_API_KEY") or "").strip() or None
    if key is None and base == DEFAULT_BASE:
        require_env(env, "OPENAI_API_KEY", "openai_api")  # the hosted API always needs a key
    return OpenAICompatible(model or require_env(env, "DDG_MODEL", "openai_api"), key, base)


register("openai_api", _factory)
