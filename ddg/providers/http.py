"""Small JSON POST helper shared by the HTTP providers. Stdlib only, no redirects, size capped."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import ProviderError

MAX_RESPONSE_BYTES = 1 << 20
Transport = Callable[[str, dict[str, str], dict[str, Any], float], "tuple[int, dict[str, Any]]"]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None  # never forward credentials to another host


_OPENER = build_opener(_NoRedirect())


def check_url(url: str, *, allow_http_local: bool = True) -> str:
    """Require https, except plain http to a loopback host (local model servers)."""
    parts = urlsplit(url)
    local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if parts.scheme == "https" or (parts.scheme == "http" and local and allow_http_local):
        return url
    raise ProviderError("provider_config", "Provider URL must use https (http only for localhost)")


def post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
    request = Request(url, data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
                      headers=headers, method="POST")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
    except HTTPError as error:
        try:
            return error.code, {}
        finally:
            error.close()
    except TimeoutError as error:
        raise ProviderError("provider_timeout", "Provider request timed out") from error
    except (URLError, OSError) as error:
        reason = getattr(error, "reason", None)
        code = "provider_timeout" if isinstance(reason, TimeoutError) else "provider_unavailable"
        raise ProviderError(code, "Provider is unreachable") from error
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProviderError("provider_response_invalid", "Provider response exceeded the size limit")
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ProviderError("provider_response_invalid", "Provider returned malformed JSON") from error
    if not isinstance(parsed, dict):
        raise ProviderError("provider_response_invalid", "Provider returned a non-object")
    return status, parsed


def raise_for_status(status: int) -> None:
    """Map an HTTP status to a stable code. Response bodies are never echoed (they can hold secrets)."""
    if status == 200:
        return
    if status in {401, 403}:
        raise ProviderError("provider_auth_failed", f"Provider rejected the credentials (HTTP {status})")
    if status == 429:
        raise ProviderError("provider_rate_limited", "Provider rate limit reached (HTTP 429)")
    if status == 408 or status >= 500:
        raise ProviderError("provider_unavailable", f"Provider unavailable (HTTP {status})")
    raise ProviderError("provider_rejected", f"Provider rejected the request (HTTP {status})")
