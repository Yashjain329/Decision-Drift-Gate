"""Gemini through the optional google-genai SDK (the original provider)."""

from __future__ import annotations

import importlib.metadata
from typing import Any

from . import Provider, ProviderError, clean_answer, register, require_env


class GeminiApi(Provider):
    name = "gemini_api"

    def __init__(self, model: str, api_key: str | None = None, client: Any = None) -> None:
        super().__init__(model)
        self._key, self._client = api_key, client

    def client_version(self) -> str:
        try:
            return importlib.metadata.version("google-genai")
        except importlib.metadata.PackageNotFoundError:
            return "google-genai (not installed)"

    def _sdk(self, timeout: float) -> Any:
        if self._client is None:
            try:
                from google import genai
                from google.genai import types
                self._client = genai.Client(api_key=self._key,
                                            http_options=types.HttpOptions(timeout=int(timeout * 1000)))
            except Exception as exc:
                raise ProviderError("provider_config", "Could not initialize the Gemini client") from exc
        return self._client

    def complete(self, prompt: str, schema: dict, timeout: float) -> str:
        result = self._sdk(timeout).interactions.create(
            model=self.model, input=prompt,
            response_format={"type": "text", "mime_type": "application/json", "schema": schema},
            timeout=timeout)
        return clean_answer(getattr(result, "output_text", None))


def _factory(env, model):
    chosen = model or (env.get("DDG_GEMINI_MODEL") or "").strip()
    if not chosen:
        raise ProviderError("provider_config", "DDG_GEMINI_MODEL (or DDG_MODEL) is required for the gemini_api provider")
    return GeminiApi(chosen, require_env(env, "GEMINI_API_KEY", "gemini_api"))


register("gemini_api", _factory)
