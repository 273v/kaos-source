"""Shared HTTP helpers for kaos-source API connectors.

Centralizes two cross-cutting concerns that every kaos-source API client
needs to handle uniformly:

- **KSRC-02** — response size cap. Outbound JSON responses go through
  :func:`kaos_core.security.read_capped_json` with the global
  ``KAOS_SECURITY_RESPONSE_MAX_BYTES`` budget.
- **KSRC-07** — typed retryable errors. 429 / 5xx responses surface as
  :class:`kaos_source.errors.SourceTransientError` with
  ``retry_after_seconds`` populated from the ``Retry-After`` header
  (delta-seconds and HTTP-date forms both honored), instead of httpx's
  generic ``HTTPStatusError``. Lets upstream backoff logic do the right
  thing.

Both helpers are duck-typed against ``httpx.AsyncClient`` so they
compose with whatever client config (timeout, headers, follow_redirects)
each API client picked.
"""

from __future__ import annotations

from typing import Any

import httpx
from kaos_core.security import KaosSecuritySettings, read_capped_bytes, read_capped_json

from kaos_source.errors import SourceAccessError, SourceNotFoundError, SourceTransientError

# KSRC-07: status codes for which we surface SourceTransientError with
# retry_after_seconds rather than the generic SourceAccessError. Mirrors
# the HttpConnector's retryable set.
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def raise_api_status(resp: httpx.Response, *, locator: str, api: str) -> None:
    """Translate an HTTP response into a typed kaos-source error.

    No-op on 2xx. 404 → :class:`SourceNotFoundError`. Retryable status
    codes → :class:`SourceTransientError` with ``retry_after_seconds``
    parsed from the ``Retry-After`` header. Everything else →
    :class:`SourceAccessError`.

    Args:
        resp: The httpx response (may be a streaming response — only
            headers and status code are read).
        locator: The URL or identifier the caller will surface in the
            error envelope so the agent can self-correct.
        api: Short API name for the error message (e.g. ``"EDGAR"``).
    """
    status = resp.status_code
    if 200 <= status < 300:
        return
    if status == 404:
        raise SourceNotFoundError(f"{api} resource not found", locator=locator, http_status=404)
    if status in _RETRYABLE_STATUS:
        # Reuse HttpConnector's parser so we honor both delta-seconds and
        # HTTP-date forms of Retry-After.
        from kaos_source.connectors.http import HttpConnector

        retry_after = HttpConnector._retry_after_seconds(resp.headers.get("retry-after"))
        raise SourceTransientError(
            f"{api} returned a retryable status",
            locator=locator,
            http_status=status,
            retry_after_seconds=retry_after,
        )
    raise SourceAccessError(
        f"{api} request failed",
        locator=locator,
        http_status=status,
    )


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    api: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json: Any | None = None,
    security_settings: KaosSecuritySettings | None = None,
) -> Any:
    """Streamed JSON fetch with size cap + typed retryable errors.

    Composes :func:`kaos_core.security.read_capped_json` with
    :func:`raise_api_status`. Use in place of the
    ``resp = await client.get(url); resp.raise_for_status(); resp.json()``
    pattern that the audit flagged as missing both response-size and
    Retry-After handling.

    Per ``KaosSecuritySettings.response_max_bytes`` (env
    ``KAOS_SECURITY_RESPONSE_MAX_BYTES``, default 100 MB) — pre-flight
    ``Content-Length`` check + streaming budget on ``aiter_bytes``.
    """
    async with client.stream(method, url, params=params, json=json) as resp:
        raise_api_status(resp, locator=url, api=api)
        return await read_capped_json(resp, settings=security_settings)


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    api: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    security_settings: KaosSecuritySettings | None = None,
) -> str:
    """Streamed text fetch with size cap + typed retryable errors.

    Like :func:`fetch_json` but returns a decoded string.
    """
    async with client.stream(method, url, params=params) as resp:
        raise_api_status(resp, locator=url, api=api)
        body = await read_capped_bytes(resp, settings=security_settings)
        return body.decode(resp.encoding or "utf-8", errors="replace")
