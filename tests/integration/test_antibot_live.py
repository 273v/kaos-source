"""Issue #444 — live integration test for the anti-bot fetch fallback.

Hits real public endpoints. Gated by BOTH ``live`` and
``requires_browser`` markers so normal CI deselects it:

    uv run pytest tests/integration/test_antibot_live.py \
        -m "live and requires_browser" -v

Prereqs:

    pip install 'kaos-source[browser]'
    python -m playwright install chromium

Targets:

- ``httpbin.org/status/403`` — guarantees a 403 so the structured
  :class:`SourceAntiBotChallengeError` fires and the FetchURL tool
  attempts the Playwright fallback. ``httpbin`` serves a real
  ``403 FORBIDDEN`` HTML body so the browser fetch also returns
  content (status 403 page) — we assert the structured_content
  reports ``fetch_path == "playwright"``.
- ``https://www.sec.gov/`` — sanity-check that SEC.gov accepts the
  realistic Chrome UA on the httpx path. EDGAR specifically
  recommends a contact-string UA, so this is best-effort.
"""

from __future__ import annotations

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

pytestmark = [pytest.mark.live, pytest.mark.requires_browser]


def _context(runtime: KaosRuntime) -> KaosContext:
    return KaosContext.create(session_id="antibot-live", runtime=runtime)


async def test_httpbin_403_triggers_playwright_fallback(runtime: KaosRuntime) -> None:
    """End-to-end: httpx hits a real 403, Playwright fallback completes."""
    tool = FetchURLTool()
    context = _context(runtime)
    result = await tool.execute(
        {"url": "https://httpbin.org/status/403", "name": "httpbin-403"},
        context,
    )

    # The Playwright fallback should succeed (httpbin returns 403 HTML
    # which Playwright renders without itself raising).
    assert result.isError is False, result.text or "no error text"
    sc = result.structuredContent or {}
    assert sc.get("fetch_path") == "playwright"
    assert sc.get("fallback_reason") in {"http_403", "http_451"} or str(
        sc.get("fallback_reason", "")
    ).startswith("http_")


async def test_httpbin_403_without_fallback_raises_antibot(runtime: KaosRuntime) -> None:
    """Without the tool layer, the connector raises the structured signal."""
    service = SourceService(connectors=[HttpConnector()])
    context = _context(runtime)
    with pytest.raises(SourceAntiBotChallengeError) as excinfo:
        await service.materialize(
            SourceLocator.http("https://httpbin.org/status/403"),
            context,
            SourceMaterializeOptions(artifact_name="httpbin-403-raw"),
        )
    assert excinfo.value.details.get("http_status") == 403
    assert excinfo.value.details.get("fingerprint") == "http_403"
