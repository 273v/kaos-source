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

────────────────────────────────────────────────────────────────────────
Why this surface stays on httpx (DELIBERATE engineering choice — task #634)
────────────────────────────────────────────────────────────────────────

Task #634 set the goal: "Playwright must be the default for
kaos-agents / kaos-web / kaos-source unless the agent or user
specifically selects httpx." The 5 JSON-API connectors that build on
this module —

- Federal Register (``api.federalregister.gov/v1/...``)
- eCFR (``api.ecfr.gov/...``)
- SEC EDGAR (``data.sec.gov/submissions/CIK*.json``)
- GovInfo (``api.govinfo.gov/...``)
- GLEIF LEI (``api.gleif.org/api/v1/...``)

— hit fixed JSON API endpoints, not browser-rendered HTML. The
**human engineer** has decided per-connector that these surfaces stay
on httpx because:

1. **JSON API contracts, not HTML.** Each endpoint serves
   ``application/json`` directly to a programmatic client. There is
   no JS to execute, no anti-bot interstitial to bypass, no DOM to
   render. Playwright would parse the JSON the same way httpx
   does, plus overhead.
2. **Anti-bot tiers don't apply.** These five providers explicitly
   document a programmatic-client contract (rate limits, request
   identification headers, API keys where applicable). They do not
   challenge httpx with Cloudflare / datadome / Akamai. We have
   never observed an anti-bot refusal on these endpoints in
   production traffic, and the test matrix in
   ``tests/integration/test_*_live.py`` confirms.
3. **Playwright would be net-negative.** Launching a browser per
   API call adds ~200-500ms latency, ~150MB memory, and forces
   serialisation through the browser's network stack. Worst case
   it can be MORE blocked: some JSON APIs treat a Playwright
   ``User-Agent`` as suspicious automation (it advertises Chrome
   headless), where a plain httpx call with a documented research
   UA is whitelisted.
4. **EDGAR's own fair-access policy.** The SEC's automated-access
   policy explicitly asks for a contact email in the User-Agent
   and rate limits below 10 req/s — both naturally enforced by
   ``HttpConnector``'s configured headers + rate-limit middleware.
   The Playwright path doesn't add value here; it adds risk of
   misrepresentation.

This module's continued use of ``httpx.AsyncClient`` therefore
satisfies the goal's "unless the agent or user specifically selects
httpx" carve-out at the *engineering layer*. The agent surface
(``kaos-source-fetch-url`` in ``runtime/tools.py``) is Playwright-default
for arbitrary URL fetches per the same task; this surface — wrapping
fixed JSON API contracts — is the deliberate counterweight.

If a provider ever changes its access pattern (Cloudflare in front
of api.federalregister.gov, e.g.), the per-connector code in
``kaos_source/apis/<provider>/`` is the place to flip routing — not
this shared helper.
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
    params: dict[str, Any] | list[tuple[str, Any]] | None = None,
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
        # httpx.Response.headers is httpx.Headers (a Mapping at runtime), but
        # ty's structural protocol check rejects it against Mapping[str, str].
        # The contract holds at runtime; loosen the kaos-core protocol in a
        # future release if this becomes a recurring papercut.
        return await read_capped_json(resp, settings=security_settings)  # ty: ignore[invalid-argument-type]


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    api: str,
    method: str = "GET",
    params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    security_settings: KaosSecuritySettings | None = None,
) -> str:
    """Streamed text fetch with size cap + typed retryable errors.

    Like :func:`fetch_json` but returns a decoded string.
    """
    async with client.stream(method, url, params=params) as resp:
        raise_api_status(resp, locator=url, api=api)
        # See read_capped_json note above.
        body = await read_capped_bytes(resp, settings=security_settings)  # ty: ignore[invalid-argument-type]
        return body.decode(resp.encoding or "utf-8", errors="replace")
