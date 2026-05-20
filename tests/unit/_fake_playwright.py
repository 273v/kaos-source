"""In-process Playwright stand-in for unit tests.

Mirrors the surface ``kaos_source.connectors.browser.BrowserConnector``
actually calls (``async_playwright``, ``chromium.launch``,
``new_context``, ``new_page``, ``goto``, ``title``, ``content``,
``screenshot``) so the connector + the FetchURL tool's Playwright
fallback can be exercised without the real browser binary.
"""

from __future__ import annotations

from typing import Any


class FakePageState:
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


class FakePlaywrightManager:
    def __init__(self, routes: dict[str, FakePageState]) -> None:
        self._routes = routes

    async def __aenter__(self) -> FakePlaywright:
        return FakePlaywright(self._routes)

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb


class FakePlaywright:
    def __init__(self, routes: dict[str, FakePageState]) -> None:
        self.chromium = FakeBrowserType(routes)
        self.firefox = FakeBrowserType(routes)
        self.webkit = FakeBrowserType(routes)


class FakeBrowserType:
    def __init__(self, routes: dict[str, FakePageState]) -> None:
        self._routes = routes

    async def launch(self, *, headless: bool) -> FakeBrowser:
        return FakeBrowser(self._routes, headless=headless)


class FakeBrowser:
    def __init__(self, routes: dict[str, FakePageState], *, headless: bool) -> None:
        self._routes = routes
        self._headless = headless

    async def new_context(
        self,
        *,
        user_agent: str,
        extra_http_headers: dict[str, str],
        ignore_https_errors: bool,
    ) -> FakeBrowserContext:
        return FakeBrowserContext(
            self._routes,
            user_agent=user_agent,
            extra_http_headers=extra_http_headers,
            ignore_https_errors=ignore_https_errors,
        )

    async def close(self) -> None:
        return None


class FakeBrowserContext:
    def __init__(
        self,
        routes: dict[str, FakePageState],
        *,
        user_agent: str,
        extra_http_headers: dict[str, str],
        ignore_https_errors: bool,
    ) -> None:
        self._routes = routes
        self._user_agent = user_agent
        self._extra_http_headers = extra_http_headers
        self._ignore_https_errors = ignore_https_errors

    async def new_page(self) -> FakePage:
        return FakePage(self._routes)

    async def close(self) -> None:
        return None


class FakePage:
    def __init__(self, routes: dict[str, FakePageState]) -> None:
        self._routes = routes
        self.url = "about:blank"
        self._current: FakePageState | None = None

    async def goto(self, url: str, *, wait_until: str, timeout: int) -> FakeBrowserResponse:
        del wait_until, timeout
        self._current = self._routes[url]
        self.url = self._current.final_url
        return FakeBrowserResponse(status=self._current.status, headers=self._current.headers)

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


class FakeBrowserResponse:
    def __init__(self, *, status: int, headers: dict[str, str]) -> None:
        self.status = status
        self.headers = headers


def install_async_playwright_factory(
    routes: dict[str, FakePageState],
) -> Any:
    """Return an object that mimics ``playwright.async_api.async_playwright``."""
    return lambda: FakePlaywrightManager(routes)
