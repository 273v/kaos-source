from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import httpx
import pytest
from kaos_core import KaosContext, KaosRuntime
from kaos_core.protocol.roots import Root

from kaos_source import (
    BrowserConnector,
    HttpConnector,
    MemoryConnector,
    SourceDiscoverOptions,
    SourceJobStatus,
    SourceLocator,
    SourceMaterializeOptions,
    SourceNotFoundError,
    SourceOperation,
    SourcePolicyError,
    SourcePreviewOptions,
    SourceService,
)


def _context(runtime: KaosRuntime, *, roots: list[Root] | None = None) -> KaosContext:
    return KaosContext.create(session_id="source-session", runtime=runtime, roots=roots)


async def test_filesystem_connector_supports_discover_preview_materialize_and_jobs(
    tmp_path: Path,
    runtime: KaosRuntime,
) -> None:
    source_root = tmp_path / "workspace"
    source_root.mkdir()
    (source_root / "alpha.txt").write_text("alpha", encoding="utf-8")
    (source_root / ".hidden.txt").write_text("hidden", encoding="utf-8")
    nested = source_root / "nested"
    nested.mkdir()
    large_file = nested / "beta.txt"
    large_file.write_text("0123456789" * 100, encoding="utf-8")

    service = SourceService()
    context = _context(runtime, roots=[Root(uri=source_root.resolve().as_uri(), name="workspace")])
    locator = SourceLocator.filesystem(source_root)

    first_page = await service.discover(
        locator,
        context,
        SourceDiscoverOptions(limit=1, recursive=True, patterns=["*.txt"]),
    )
    second_page = await service.discover(
        locator,
        context,
        SourceDiscoverOptions(
            limit=1,
            recursive=True,
            patterns=["*.txt"],
            cursor=first_page.next_cursor,
        ),
    )

    assert [item.name for item in first_page.items] == ["alpha.txt"]
    assert first_page.next_cursor is not None
    assert [item.name for item in second_page.items] == ["beta.txt"]

    preview = await service.preview(
        SourceLocator.filesystem(large_file),
        context,
        SourcePreviewOptions(max_bytes=32),
    )
    assert preview.text_preview == "01234567890123456789012345678901"
    assert preview.truncated is True

    materialization = await service.materialize(
        SourceLocator.filesystem(large_file),
        context,
        SourceMaterializeOptions(artifact_name="beta-preview"),
    )
    assert materialization.manifest.name == "beta-preview"
    assert materialization.descriptor.name == "beta.txt"
    assert await runtime.artifacts.read_text(
        materialization.manifest.artifact_id
    ) == large_file.read_text(encoding="utf-8")

    job = await service.start_job(
        SourceLocator.filesystem(large_file),
        context,
        operation=SourceOperation.MATERIALIZE,
    )
    finished = await service.wait_for_job(job.job_id)
    assert finished.status is SourceJobStatus.SUCCEEDED
    assert finished.result is not None
    assert finished.result.materialization is not None


async def test_filesystem_connector_enforces_roots(
    tmp_path: Path,
    runtime: KaosRuntime,
) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("blocked", encoding="utf-8")

    service = SourceService()
    context = _context(runtime, roots=[Root(uri=allowed_root.resolve().as_uri(), name="allowed")])

    with pytest.raises(SourcePolicyError):
        await service.describe(SourceLocator.filesystem(outside_file), context)


async def test_memory_connector_supports_discover_preview_and_materialize(
    runtime: KaosRuntime,
) -> None:
    service = SourceService()
    locator = service.register_memory_bytes(
        "payload.json",
        b'{"hello": "world"}',
        mime_type="application/json",
        metadata={"kind": "fixture"},
    )
    context = _context(runtime)

    page = await service.discover(SourceLocator.memory(), context, SourceDiscoverOptions(limit=10))
    descriptor = await service.describe(locator, context)
    preview = await service.preview(locator, context, SourcePreviewOptions(max_bytes=8))
    materialization = await service.materialize(locator, context)

    assert [item.name for item in page.items] == ["payload.json"]
    assert descriptor.metadata["kind"] == "fixture"
    assert preview.text_preview == '{"hello"'
    assert materialization.manifest.mime_type == "application/json"
    assert (
        await runtime.artifacts.read_text(materialization.manifest.artifact_id)
        == '{"hello": "world"}'
    )


async def test_archive_connector_supports_member_discovery_preview_and_materialize(
    tmp_path: Path,
    runtime: KaosRuntime,
) -> None:
    archive_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("docs/readme.txt", "archive-body")
        archive.writestr("docs/data.bin", b"\x00\x01\x02")

    service = SourceService()
    context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])

    page = await service.discover(
        SourceLocator.archive(archive_path),
        context,
        SourceDiscoverOptions(limit=10, recursive=True, patterns=["*.txt"]),
    )
    descriptor = page.items[0]
    preview = await service.preview(descriptor.locator, context, SourcePreviewOptions(max_bytes=6))
    materialization = await service.materialize(descriptor.locator, context)

    assert [item.name for item in page.items] == ["readme.txt"]
    assert descriptor.locator.member_path == "docs/readme.txt"
    assert preview.text_preview == "archiv"
    assert preview.truncated is True
    assert await runtime.artifacts.read_text(materialization.manifest.artifact_id) == "archive-body"


async def test_job_cancellation_is_idempotent(runtime: KaosRuntime) -> None:
    class SlowMemoryConnector(MemoryConnector):
        async def preview(
            self,
            locator: SourceLocator,
            context: KaosContext,
            options: SourcePreviewOptions | None = None,
        ):
            await asyncio.sleep(0.25)
            return await super().preview(locator, context, options)

    connector = SlowMemoryConnector()
    connector.put_bytes("slow.txt", b"slow-data")
    service = SourceService(connectors=[connector])
    context = _context(runtime)

    job = await service.start_job(
        SourceLocator.memory("slow.txt"),
        context,
        operation=SourceOperation.PREVIEW,
    )
    cancelled = await service.cancel_job(job.job_id)
    cancelled_again = await service.cancel_job(job.job_id)

    assert cancelled.status is SourceJobStatus.CANCELLED
    assert cancelled_again.status is SourceJobStatus.CANCELLED


async def test_http_connector_supports_describe_preview_materialize_and_redirects(
    runtime: KaosRuntime,
) -> None:
    transport = _StaticHttpTransport(
        {
            ("HEAD", "https://example.com/final.txt"): _http_response(
                200,
                b"",
                headers={"content-type": "text/plain", "content-length": "11"},
            ),
            ("HEAD", "https://example.com/redirect"): _http_response(
                302,
                b"",
                headers={"location": "https://example.com/final.txt"},
            ),
            ("GET", "https://example.com/final.txt"): _http_response(
                200,
                b"hello world",
                headers={"content-type": "text/plain", "content-length": "11"},
            ),
            ("GET", "https://example.com/redirect"): _http_response(
                302,
                b"",
                headers={"location": "https://example.com/final.txt"},
            ),
        }
    )
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)
    locator = SourceLocator.http("https://example.com/redirect")

    descriptor = await service.describe(locator, context)
    preview = await service.preview(locator, context, SourcePreviewOptions(max_bytes=5))
    materialization = await service.materialize(locator, context)

    assert descriptor.metadata["final_url"] == "https://example.com/final.txt"
    assert descriptor.mime_type == "text/plain"
    assert descriptor.size == 11
    assert preview.text_preview == "hello"
    assert preview.truncated is True
    assert await runtime.artifacts.read_text(materialization.manifest.artifact_id) == "hello world"


async def test_http_connector_enforces_http_roots_and_host_policy(
    runtime: KaosRuntime,
) -> None:
    transport = _StaticHttpTransport(
        {
            ("HEAD", "https://allowed.example.com/base/report.txt"): _http_response(
                200,
                b"",
                headers={"content-type": "text/plain", "content-length": "6"},
            ),
        }
    )
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    roots = [Root(uri="https://allowed.example.com/base/", name="allowed-http")]
    context = _context(runtime, roots=roots)

    descriptor = await service.describe(
        SourceLocator.http("https://allowed.example.com/base/report.txt"),
        context,
    )
    assert descriptor.name == "report.txt"

    with pytest.raises(SourcePolicyError):
        await service.describe(SourceLocator.http("https://allowed.example.com/other.txt"), context)

    restricted_context = _context(runtime)
    restricted_context.set_config("source_http_allowed_hosts", ["allowed.example.com"])
    with pytest.raises(SourcePolicyError):
        await service.describe(
            SourceLocator.http("https://blocked.example.com/base/report.txt"),
            restricted_context,
        )


async def test_http_connector_retries_transient_failures(runtime: KaosRuntime) -> None:
    transport = _RetryTransport()
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)

    preview = await service.preview(
        SourceLocator.http("https://example.com/retry.txt"),
        context,
        SourcePreviewOptions(max_bytes=7),
    )

    assert preview.text_preview == "retried"
    assert transport.attempts == 2


async def test_http_connector_applies_user_agent_and_headers(runtime: KaosRuntime) -> None:
    transport = _HeaderCaptureTransport(
        {
            ("HEAD", "https://example.com/headers.txt"): _http_response(
                200,
                b"",
                headers={"content-type": "text/plain", "content-length": "4"},
            ),
        }
    )
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)
    context.set_config("source_http_user_agent", "KAOS-Test-Agent/1.0")
    context.set_config("source_http_headers", {"Accept-Language": "en-US"})

    await service.describe(SourceLocator.http("https://example.com/headers.txt"), context)

    assert transport.seen_headers[0]["user-agent"] == "KAOS-Test-Agent/1.0"
    assert transport.seen_headers[0]["accept-language"] == "en-US"
    assert transport.seen_headers[0]["x-kaos-source"] == "1"


async def test_http_connector_respects_retry_after_header(runtime: KaosRuntime) -> None:
    transport = _RetryAfterTransport()
    service = SourceService(connectors=[HttpConnector(transport=transport)])
    context = _context(runtime)

    descriptor = await service.describe(
        SourceLocator.http("https://example.com/backoff.txt"), context
    )

    assert descriptor.name == "backoff.txt"
    assert transport.attempts == 2


async def test_http_connector_reports_not_found(runtime: KaosRuntime) -> None:
    transport = _StaticHttpTransport(
        {
            ("HEAD", "https://example.com/missing.txt"): _http_response(404, b""),
        }
    )
    service = SourceService(connectors=[HttpConnector(transport=transport)])

    with pytest.raises(SourceNotFoundError):
        await service.describe(
            SourceLocator.http("https://example.com/missing.txt"), _context(runtime)
        )


async def test_http_connector_limits_concurrency_per_domain(runtime: KaosRuntime) -> None:
    transport = _ConcurrencyTransport()
    connector = HttpConnector(transport=transport, max_concurrent_per_domain=1)
    service = SourceService(connectors=[connector], max_concurrent_operations=2)
    context = _context(runtime)
    first = SourceLocator.http("https://example.com/one.txt")
    second = SourceLocator.http("https://example.com/two.txt")

    await asyncio.gather(
        service.preview(first, context, SourcePreviewOptions(max_bytes=3)),
        service.preview(second, context, SourcePreviewOptions(max_bytes=3)),
    )

    assert transport.max_active == 1


async def test_browser_connector_supports_preview_and_materialize_with_screenshot(
    runtime: KaosRuntime,
) -> None:
    service = SourceService(
        connectors=[
            BrowserConnector(
                playwright_factory=lambda: _FakePlaywrightManager(
                    {
                        "https://example.com/app": _FakePageState(
                            final_url="https://example.com/app",
                            status=200,
                            title="Rendered App",
                            html="<html><body><main>Rendered body</main></body></html>",
                            headers={"content-type": "text/html; charset=utf-8"},
                            screenshot=b"\x89PNGfake",
                        )
                    }
                )
            )
        ]
    )
    context = _context(runtime)
    locator = SourceLocator.browser("https://example.com/app")

    descriptor = await service.describe(locator, context)
    preview = await service.preview(locator, context, SourcePreviewOptions(max_bytes=24))
    materialization = await service.materialize(locator, context)

    assert descriptor.metadata["title"] == "Rendered App"
    assert preview.text_preview == "<html><body><main>Render"
    assert materialization.manifest.mime_type == "text/html"
    assert len(materialization.related_artifacts) == 1
    screenshot_ref = materialization.related_artifacts[0]
    assert await runtime.artifacts.read_text(materialization.manifest.artifact_id) == (
        "<html><body><main>Rendered body</main></body></html>"
    )
    assert await runtime.artifacts.read_body(screenshot_ref.artifact_id) == b"\x89PNGfake"


async def test_browser_connector_enforces_policy(runtime: KaosRuntime) -> None:
    service = SourceService(
        connectors=[
            BrowserConnector(
                playwright_factory=lambda: _FakePlaywrightManager(
                    {
                        "https://allowed.example.com/app": _FakePageState(
                            final_url="https://allowed.example.com/app",
                            status=200,
                            title="Allowed",
                            html="<html>ok</html>",
                            headers={"content-type": "text/html"},
                            screenshot=b"",
                        )
                    }
                ),
                take_screenshot=False,
            )
        ]
    )
    roots = [Root(uri="https://allowed.example.com/", name="allowed-http")]
    context = _context(runtime, roots=roots)

    descriptor = await service.describe(
        SourceLocator.browser("https://allowed.example.com/app"), context
    )
    assert descriptor.name == "app"

    with pytest.raises(SourcePolicyError):
        await service.describe(SourceLocator.browser("https://blocked.example.com/app"), context)


def _http_response(
    status_code: int,
    body: bytes,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    return status_code, body, headers or {}


class _StaticHttpTransport(httpx.AsyncBaseTransport):
    def __init__(self, routes: dict[tuple[str, str], tuple[int, bytes, dict[str, str]]]) -> None:
        self._routes = routes
        self.seen_headers: list[dict[str, str]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.seen_headers.append({key.lower(): value for key, value in request.headers.items()})
        response = self._routes.get((request.method, str(request.url)))
        if response is None:
            return httpx.Response(404, request=request)
        status_code, body, headers = response
        return httpx.Response(status_code, headers=headers, content=body, request=request)


class _HeaderCaptureTransport(_StaticHttpTransport):
    pass


class _RetryAfterTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.attempts = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        if self.attempts == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "0"},
                request=request,
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/plain", "content-length": "2"},
            content=b"ok",
            request=request,
        )


class _RetryTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.attempts = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        if self.attempts == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/plain", "content-length": "7"},
            content=b"retried",
            request=request,
        )


class _ConcurrencyTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.05)
            return httpx.Response(
                200,
                headers={"content-type": "text/plain", "content-length": "6"},
                content=b"abcdef",
                request=request,
            )
        finally:
            self.active -= 1


class _FakePageState:
    def __init__(
        self,
        *,
        final_url: str,
        status: int,
        title: str,
        html: str,
        headers: dict[str, str],
        screenshot: bytes,
    ) -> None:
        self.final_url = final_url
        self.status = status
        self.title = title
        self.html = html
        self.headers = headers
        self.screenshot = screenshot


class _FakePlaywrightManager:
    def __init__(self, routes: dict[str, _FakePageState]) -> None:
        self._routes = routes

    async def __aenter__(self) -> _FakePlaywright:
        return _FakePlaywright(self._routes)

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb


class _FakePlaywright:
    def __init__(self, routes: dict[str, _FakePageState]) -> None:
        self.chromium = _FakeBrowserType(routes)
        self.firefox = _FakeBrowserType(routes)
        self.webkit = _FakeBrowserType(routes)


class _FakeBrowserType:
    def __init__(self, routes: dict[str, _FakePageState]) -> None:
        self._routes = routes

    async def launch(self, *, headless: bool) -> _FakeBrowser:
        return _FakeBrowser(self._routes, headless=headless)


class _FakeBrowser:
    def __init__(self, routes: dict[str, _FakePageState], *, headless: bool) -> None:
        self._routes = routes
        self._headless = headless

    async def new_context(
        self,
        *,
        user_agent: str,
        extra_http_headers: dict[str, str],
        ignore_https_errors: bool,
    ) -> _FakeBrowserContext:
        return _FakeBrowserContext(
            self._routes,
            user_agent=user_agent,
            extra_http_headers=extra_http_headers,
            ignore_https_errors=ignore_https_errors,
        )

    async def close(self) -> None:
        return None


class _FakeBrowserContext:
    def __init__(
        self,
        routes: dict[str, _FakePageState],
        *,
        user_agent: str,
        extra_http_headers: dict[str, str],
        ignore_https_errors: bool,
    ) -> None:
        self._routes = routes
        self._user_agent = user_agent
        self._extra_http_headers = extra_http_headers
        self._ignore_https_errors = ignore_https_errors

    async def new_page(self) -> _FakePage:
        return _FakePage(self._routes)

    async def close(self) -> None:
        return None


class _FakePage:
    def __init__(self, routes: dict[str, _FakePageState]) -> None:
        self._routes = routes
        self.url = "about:blank"
        self._current: _FakePageState | None = None

    async def goto(self, url: str, *, wait_until: str, timeout: int) -> _FakeBrowserResponse:
        del wait_until, timeout
        self._current = self._routes[url]
        self.url = self._current.final_url
        return _FakeBrowserResponse(status=self._current.status, headers=self._current.headers)

    async def title(self) -> str:
        assert self._current is not None
        return self._current.title

    async def content(self) -> str:
        assert self._current is not None
        return self._current.html

    async def screenshot(self, *, full_page: bool, type: str) -> bytes:
        del full_page, type
        assert self._current is not None
        return self._current.screenshot


class _FakeBrowserResponse:
    def __init__(self, *, status: int, headers: dict[str, str]) -> None:
        self.status = status
        self.headers = headers
