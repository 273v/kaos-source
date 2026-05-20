"""Issue #444 — anti-bot fetch hardening unit tests.

Covers:

- Realistic Chrome UA + browser-shaped headers go out by default.
- ``domain_overrides`` win over connector defaults for matching hosts.
- HTTP 403 / 451 trip the structured :class:`SourceAntiBotChallengeError`.
- HTML body fingerprints (Cloudflare, captcha, etc.) trip the same error.
- ``FetchURLTool`` falls back to Playwright when the [browser] extra is
  importable, and surfaces a clear install hint when it isn't.

All transports / Playwright surfaces are mocked — unit tier does not
go to the live internet.
"""

from __future__ import annotations

import sys
from typing import Any

import httpx
import pytest
from kaos_core import KaosContext, KaosRuntime

from kaos_source import (
    HttpConnector,
    SourceAntiBotChallengeError,
    SourceLocator,
    SourceMaterializeOptions,
    SourceService,
)
from kaos_source.runtime.tools import FetchURLTool
from kaos_source.settings.http import DEFAULT_HTTP_UA


def _context(runtime: KaosRuntime) -> KaosContext:
    return KaosContext.create(session_id="antibot-session", runtime=runtime)


# ---------------------------------------------------------------------------
# Header-shaping transports
# ---------------------------------------------------------------------------


class _HeaderCapturingTransport(httpx.AsyncBaseTransport):
    """Returns 200 OK for every URL; records headers for assertion."""

    def __init__(self, body: bytes = b"hello world", content_type: str = "text/plain") -> None:
        self.calls: list[dict[str, str]] = []
        self._body = body
        self._content_type = content_type

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append({k.lower(): v for k, v in request.headers.items()})
        return httpx.Response(
            200,
            headers={
                "content-type": self._content_type,
                "content-length": str(len(self._body)),
            },
            content=self._body,
            request=request,
        )


class _StatusTransport(httpx.AsyncBaseTransport):
    """Returns a fixed status code + body for every request."""

    def __init__(self, status: int, body: bytes = b"", content_type: str = "text/html") -> None:
        self._status = status
        self._body = body
        self._content_type = content_type
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(
            self._status,
            headers={
                "content-type": self._content_type,
                "content-length": str(len(self._body)),
            },
            content=self._body,
            request=request,
        )


# ---------------------------------------------------------------------------
# Realistic UA + browser-shaped headers
# ---------------------------------------------------------------------------


async def test_default_user_agent_is_realistic_chrome(runtime: KaosRuntime) -> None:
    transport = _HeaderCapturingTransport()
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)

    await service.describe(SourceLocator.http("https://example.com/file.txt"), context)

    sent = transport.calls[0]
    assert sent["user-agent"] == DEFAULT_HTTP_UA
    # Browser-shaped headers ride along by default so the request
    # looks less like a scraper.
    assert "accept-language" in sent
    assert "sec-fetch-mode" in sent
    assert sent["x-kaos-source"] == "1"


async def test_domain_overrides_win_for_matching_host(runtime: KaosRuntime) -> None:
    transport = _HeaderCapturingTransport()
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)
    # Subdomain match: 'reuters.com' should catch 'www.reuters.com'.
    context.set_config(
        "source_http_domain_overrides",
        {
            "reuters.com": {
                "User-Agent": "ReutersResearch/1.0",
                "Accept": "text/html",
            }
        },
    )

    await service.describe(SourceLocator.http("https://www.reuters.com/article/abc"), context)

    sent = transport.calls[0]
    assert sent["user-agent"] == "ReutersResearch/1.0"
    assert sent["accept"] == "text/html"


async def test_domain_overrides_no_match_keeps_default_ua(runtime: KaosRuntime) -> None:
    transport = _HeaderCapturingTransport()
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)
    context.set_config(
        "source_http_domain_overrides",
        {"reuters.com": {"User-Agent": "ReutersResearch/1.0"}},
    )

    await service.describe(SourceLocator.http("https://example.com/file.txt"), context)

    assert transport.calls[0]["user-agent"] == DEFAULT_HTTP_UA


async def test_domain_overrides_longest_key_wins(runtime: KaosRuntime) -> None:
    transport = _HeaderCapturingTransport()
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)
    context.set_config(
        "source_http_domain_overrides",
        {
            "example.com": {"User-Agent": "Broad/1.0"},
            "research.example.com": {"User-Agent": "Specific/1.0"},
        },
    )

    await service.describe(SourceLocator.http("https://research.example.com/x"), context)

    assert transport.calls[0]["user-agent"] == "Specific/1.0"


# ---------------------------------------------------------------------------
# Anti-bot status-code detection (403 / 451)
# ---------------------------------------------------------------------------


async def test_403_raises_antibot_challenge_error(runtime: KaosRuntime) -> None:
    transport = _StatusTransport(403, b"forbidden", content_type="text/plain")
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)

    with pytest.raises(SourceAntiBotChallengeError) as excinfo:
        await service.materialize(
            SourceLocator.http("https://example.com/x"),
            context,
            SourceMaterializeOptions(),
        )

    assert excinfo.value.details.get("http_status") == 403
    assert excinfo.value.details.get("fingerprint") == "http_403"


async def test_451_raises_antibot_challenge_error(runtime: KaosRuntime) -> None:
    transport = _StatusTransport(451, b"unavailable for legal reasons")
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)

    with pytest.raises(SourceAntiBotChallengeError) as excinfo:
        await service.materialize(SourceLocator.http("https://example.com/x"), context)

    assert excinfo.value.details.get("fingerprint") == "http_451"


# ---------------------------------------------------------------------------
# Anti-bot body fingerprint detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "body"),
    [
        (
            "cloudflare_just_a_moment",
            b"<html><head><title>Just a moment...</title></head><body>...</body></html>",
        ),
        (
            "cloudflare_attention",
            b"<html><title>Attention Required! | Cloudflare</title></html>",
        ),
        (
            "recaptcha_challenge",
            b'<html><body><div class="g-recaptcha"></div></body></html>',
        ),
        (
            "hcaptcha",
            b'<html><body><div class="hcaptcha-challenge"></div></body></html>',
        ),
    ],
)
async def test_html_fingerprints_trigger_antibot(
    runtime: KaosRuntime, label: str, body: bytes
) -> None:
    transport = _StatusTransport(200, body, content_type="text/html")
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)

    with pytest.raises(SourceAntiBotChallengeError) as excinfo:
        await service.materialize(SourceLocator.http("https://example.com/page"), context)

    assert excinfo.value.details.get("fingerprint") == label


async def test_benign_html_does_not_trip_fingerprint(runtime: KaosRuntime) -> None:
    body = (
        b"<html><head><title>Quarterly Report</title></head>"
        b"<body><p>Revenue up 12%.</p></body></html>"
    )
    transport = _StatusTransport(200, body, content_type="text/html")
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)

    result = await service.materialize(SourceLocator.http("https://example.com/q"), context)

    assert result.bytes_written == len(body)


async def test_non_html_response_skips_fingerprint_sniff(runtime: KaosRuntime) -> None:
    # A PDF whose bytes happen to spell out a fingerprint substring
    # should NOT trip — we only sniff HTML-like content types.
    body = b"%PDF-1.7\n...checking your browser before accessing..."
    transport = _StatusTransport(200, body, content_type="application/pdf")
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)

    result = await service.materialize(SourceLocator.http("https://example.com/x.pdf"), context)
    assert result.bytes_written == len(body)


# ---------------------------------------------------------------------------
# FetchURLTool Playwright fallback wiring
# ---------------------------------------------------------------------------


async def test_fetchurl_tool_returns_install_hint_when_playwright_missing(
    runtime: KaosRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When httpx hits a challenge AND playwright isn't installed, the
    tool returns a clear ToolResult error pointing at the [browser] extra.
    """
    # Force the playwright import to fail even if it's installed in dev.
    monkeypatch.setitem(sys.modules, "playwright.async_api", None)

    # Stand up a service whose default HTTP connector hits a 403.
    transport = _StatusTransport(403, b"forbidden", content_type="text/plain")

    # Patch the module-level _get_service to return our transport.
    from kaos_source.runtime import tools as tools_mod

    monkeypatch.setattr(
        tools_mod,
        "_get_service",
        lambda: SourceService(connectors=[HttpConnector(transport=transport)]),
    )

    tool = FetchURLTool()
    context = _context(runtime)
    result = await tool.execute({"url": "https://example.com/blocked"}, context)

    assert result.isError is True
    err = result.text or ""
    assert "pip install 'kaos-source[browser]'" in err
    assert "playwright" in err.lower()


async def test_fetchurl_tool_falls_back_to_browser_on_antibot(
    runtime: KaosRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy-path fallback: httpx hits a 403, the tool re-fetches via a
    mocked Playwright connector, and the structured_content reports
    ``fetch_path=playwright``.
    """
    # Mocked Playwright surface — reuse the fakes from the connector
    # smoke test rather than dragging Playwright into the unit lane.
    from tests.unit._fake_playwright import FakePageState, FakePlaywrightManager

    pages = {
        "https://example.com/blocked": FakePageState(
            final_url="https://example.com/blocked",
            status=200,
            title="Real Content",
            html="<html><body><h1>real content delivered by browser</h1></body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
            screenshot=b"\x89PNGfake",
        )
    }

    # Sentinel so the FetchURLTool's "is playwright importable?" probe
    # succeeds even on CI without the [browser] extra installed.
    import types

    fake_module = types.ModuleType("playwright.async_api")
    setattr(  # noqa: B010 — dynamic attr on a synthetic ModuleType
        fake_module,
        "async_playwright",
        lambda: FakePlaywrightManager(pages),
    )
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_module)

    # First-pass httpx fetch trips a 403.
    transport = _StatusTransport(403, b"blocked", content_type="text/plain")
    from kaos_source.connectors import browser as browser_mod
    from kaos_source.runtime import tools as tools_mod

    monkeypatch.setattr(
        tools_mod,
        "_get_service",
        lambda: SourceService(connectors=[HttpConnector(transport=transport)]),
    )

    # Patch the BrowserConnector instantiation inside the fallback to
    # use our fake playwright factory rather than the (absent) real one.
    original_browser_init = browser_mod.BrowserConnector.__init__

    def _patched_init(self: Any, **kwargs: Any) -> None:
        kwargs["playwright_factory"] = lambda: FakePlaywrightManager(pages)
        kwargs["take_screenshot"] = False  # keep the fallback artifact set small
        original_browser_init(self, **kwargs)

    monkeypatch.setattr(browser_mod.BrowserConnector, "__init__", _patched_init)

    tool = FetchURLTool()
    context = _context(runtime)
    result = await tool.execute({"url": "https://example.com/blocked"}, context)

    assert result.isError is False, result.text or "no error text"
    sc = result.structuredContent or {}
    assert sc.get("fetch_path") == "playwright"
    assert sc.get("fallback_reason") == "http_403"
