"""Amazon Bedrock via the Converse API.

Two ways to authenticate, both without hand-written request signing:
  1. AWS_BEARER_TOKEN_BEDROCK (a Bedrock API key): plain HTTPS, stdlib only.
  2. boto3 (optional install): uses the normal AWS chain (profile, SSO, role, instance profile).
Region comes from DDG_AWS_REGION, AWS_REGION or AWS_DEFAULT_REGION. DDG_MODEL is the model id or
inference-profile id (for example `us.anthropic.claude-sonnet-4-5-20250929-v1:0`).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from . import Provider, ProviderError, clean_answer, register, require_env
from .http import Transport, check_url, post_json, raise_for_status

_REGION = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d$")
SYSTEM = [{"text": "You output only the JSON object the user asks for. No prose, no code fences."}]


def _text(response: Any) -> str:
    try:
        parts = response["output"]["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise ProviderError("provider_response_invalid", "Missing Converse output") from exc
    if not isinstance(parts, list):
        raise ProviderError("provider_response_invalid", "Missing Converse content")
    return clean_answer("".join(p["text"] for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)))


class Bedrock(Provider):
    name = "bedrock"

    def __init__(self, model: str, region: str, bearer_token: str | None = None, client: Any = None,
                 max_tokens: int = 4096, transport: Transport = post_json) -> None:
        super().__init__(model)
        if not _REGION.fullmatch(region):
            raise ProviderError("provider_config", f"Invalid AWS region {region!r}")
        self._region, self._token, self._client = region, bearer_token, client
        self._max_tokens, self._transport = max_tokens, transport

    def client_version(self) -> str:
        if self._token:
            return "converse-http"
        try:
            import boto3  # noqa: PLC0415
            return "boto3 " + boto3.__version__
        except ImportError:
            return "boto3 (not installed)"

    def _boto(self) -> Any:
        if self._client is None:
            try:
                import boto3  # noqa: PLC0415
                from botocore.config import Config  # noqa: PLC0415
            except ImportError as exc:
                raise ProviderError("provider_config", "Install boto3 or set AWS_BEARER_TOKEN_BEDROCK for Bedrock") from exc
            self._client = boto3.client("bedrock-runtime", region_name=self._region,
                                        config=Config(retries={"max_attempts": 1}))
        return self._client

    def complete(self, prompt: str, schema: dict, timeout: float) -> str:
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        inference = {"maxTokens": self._max_tokens}
        if self._token:
            url = check_url(f"https://bedrock-runtime.{self._region}.amazonaws.com/model/"
                            f"{quote(self.model, safe='')}/converse")
            status, response = self._transport(
                url, {"authorization": "Bearer " + self._token, "content-type": "application/json"},
                {"messages": messages, "system": SYSTEM, "inferenceConfig": inference}, timeout)
            raise_for_status(status)
            return _text(response)
        try:
            response = self._boto().converse(modelId=self.model, messages=messages, system=SYSTEM,
                                             inferenceConfig=inference)
        except ProviderError:
            raise
        except Exception as exc:  # boto raises many types; never echo their text (can contain ids)
            code = getattr(getattr(exc, "response", None), "get", lambda *_: None)("Error") or {}
            name = code.get("Code") if isinstance(code, dict) else None
            mapped = {"AccessDeniedException": "provider_auth_failed", "ExpiredTokenException": "provider_auth_failed",
                      "UnrecognizedClientException": "provider_auth_failed",
                      "ThrottlingException": "provider_rate_limited",
                      "ModelTimeoutException": "provider_timeout"}.get(name, "provider_unavailable")
            raise ProviderError(mapped, f"Bedrock request failed ({name or type(exc).__name__})") from exc
        return _text(response)


def _factory(env, model):
    region = (env.get("DDG_AWS_REGION") or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "").strip()
    if not region:
        raise ProviderError("provider_config", "Set DDG_AWS_REGION (or AWS_REGION) for the bedrock provider")
    token = (env.get("AWS_BEARER_TOKEN_BEDROCK") or "").strip() or None
    return Bedrock(model or require_env(env, "DDG_MODEL", "bedrock"), region, token)


register("bedrock", _factory)
