from __future__ import annotations

import asyncio
import importlib
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from kaos_core import KaosContext
from kaos_core.logging import get_logger

from kaos_source.connectors.base import SourceConnector, assert_roots_allow_uri, decode_cursor
from kaos_source.errors import SourceAccessError, SourcePolicyError, SourceValidationError
from kaos_source.models import (
    SourceDescriptor,
    SourceKind,
    SourceLocator,
    SourceMaterialization,
    SourcePage,
    SourcePreview,
)
from kaos_source.options import (
    SourceDiscoverOptions,
    SourceMaterializeOptions,
    SourcePreviewOptions,
)

logger = get_logger(__name__)


class BrowserPlaywrightFactory(Protocol):
    def __call__(self) -> Any: ...


class BrowserConnector(SourceConnector):
    kind = SourceKind.BROWSER
    name = "browser"

    def __init__(
        self,
        *,
        playwright_factory: BrowserPlaywrightFactory | None = None,
        browser_type: str = "chromium",
        headless: bool = True,
        timeout_ms: int = 30_000,
        wait_until: str = "networkidle",
        user_agent: str = "kaos-source-browser/0.1",
        extra_headers: Mapping[str, str] | None = None,
        take_screenshot: bool = True,
        screenshot_full_page: bool = True,
        max_concurrent_per_domain: int = 1,
    ) -> None:
        self._playwright_factory = playwright_factory
        self._browser_type = browser_type
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._wait_until = wait_until
        self._user_agent = user_agent
        self._extra_headers = dict(extra_headers or {})
        self._take_screenshot = take_screenshot
        self._screenshot_full_page = screenshot_full_page
        self._max_concurrent_per_domain = max_concurrent_per_domain
        self._domain_semaphores: dict[tuple[str, int], asyncio.Semaphore] = {}

    async def describe(self, locator: SourceLocator, context: KaosContext) -> SourceDescriptor:
        return await self._with_page(
            locator,
            context,
            lambda page, response: self._descriptor_from_page(locator, page, response),
        )

    async def discover(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceDiscoverOptions | None = None,
    ) -> SourcePage:
        options = options or SourceDiscoverOptions()
        if decode_cursor(options.cursor) > 0:
            return SourcePage(items=[])
        descriptor = await self.describe(locator, context)
        return SourcePage(items=[descriptor], total_count=1)

    async def preview(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourcePreviewOptions | None = None,
    ) -> SourcePreview:
        options = options or SourcePreviewOptions()

        async def run(page: Any, response: Any) -> SourcePreview:
            descriptor = await self._descriptor_from_page(locator, page, response)
            content = await page.content()
            content_bytes = content.encode("utf-8")
            payload = content_bytes[: options.max_bytes]
            truncated = len(content_bytes) > len(payload)
            return self._decode_preview_payload(
                payload,
                source_id=descriptor.source_id,
                size=len(content_bytes),
                mime_type=descriptor.mime_type,
                encoding=options.encoding,
                truncated_override=truncated,
            )

        return await self._with_page(locator, context, run)

    async def materialize(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceMaterializeOptions | None = None,
    ) -> SourceMaterialization:
        options = options or SourceMaterializeOptions()

        async def run(page: Any, response: Any) -> SourceMaterialization:
            descriptor = await self._descriptor_from_page(locator, page, response)
            html = await page.content()
            primary = await self._materialize_bytes(
                payload=html.encode("utf-8"),
                context=context,
                descriptor=descriptor,
                options=options,
                mime_type="text/html",
            )

            related_artifacts = list(primary.related_artifacts)
            total_bytes = primary.bytes_written
            logger.debug(
                "Materialized browser HTML for %s (%d bytes)", locator.uri, primary.bytes_written
            )
            if self._take_screenshot_for(context):
                screenshot = await page.screenshot(
                    full_page=self._screenshot_full_page_for(context),
                    type="png",
                )
                screenshot_descriptor = SourceDescriptor(
                    source_id=f"{locator.uri}#screenshot",
                    source_kind=self.kind,
                    locator=locator,
                    name=f"{descriptor.name}.png",
                    mime_type="image/png",
                    size=len(screenshot),
                    metadata={
                        "kind": "browser_screenshot",
                        "final_url": descriptor.metadata.get("final_url"),
                        "title": descriptor.metadata.get("title"),
                    },
                    provenance=self._provenance(
                        locator,
                        request_metadata={
                            "derived_kind": "screenshot",
                            "final_url": descriptor.metadata.get("final_url"),
                        },
                        parent_artifact_id=primary.manifest.artifact_id,
                    ),
                    can_materialize=False,
                    preview_available=False,
                )
                screenshot_materialization = await self._materialize_bytes(
                    payload=screenshot,
                    context=context,
                    descriptor=screenshot_descriptor,
                    options=options,
                    artifact_name=f"{descriptor.name}-screenshot",
                    target_path=self._default_target_path(f"{descriptor.name}.png", self.kind),
                    mime_type="image/png",
                    metadata={
                        **options.metadata,
                        "kind": "browser_screenshot",
                        "parent_artifact_id": primary.manifest.artifact_id,
                    },
                )
                related_artifacts.append(screenshot_materialization.artifact_ref)
                total_bytes += screenshot_materialization.bytes_written

            return SourceMaterialization(
                descriptor=primary.descriptor,
                manifest=primary.manifest,
                artifact_ref=primary.artifact_ref,
                bytes_written=total_bytes,
                retention_policy=primary.retention_policy,
                related_artifacts=related_artifacts,
            )

        return await self._with_page(locator, context, run)

    async def _with_page(
        self,
        locator: SourceLocator,
        context: KaosContext,
        operation: Callable[[Any, Any], Awaitable[Any]],
    ) -> Any:
        url = self._require_url(locator)
        self._assert_policy(url, context)
        logger.debug("Navigating browser to %s", url)
        parsed = urlsplit(url)
        async with (
            self._domain_gate(parsed.netloc, context),
            self._playwright_context() as playwright,
        ):
            browser_launcher = getattr(playwright, self._browser_type, None)
            if browser_launcher is None:
                raise SourceValidationError(
                    "Unsupported browser type",
                    browser_type=self._browser_type,
                )
            browser = await browser_launcher.launch(headless=self._headless_for(context))
            browser_context = await browser.new_context(
                user_agent=self._user_agent_for(context),
                extra_http_headers=self._extra_headers_for(context),
                ignore_https_errors=self._ignore_https_errors_for(context),
            )
            page = await browser_context.new_page()
            try:
                response = await page.goto(
                    url,
                    wait_until=self._wait_until_for(context),
                    timeout=self._timeout_ms_for(context),
                )
                if response is None:
                    logger.warning("Browser navigation returned no response for %s", url)
                    raise SourceAccessError(
                        "Browser navigation did not return a response", locator=url
                    )
                status = getattr(response, "status", None)
                logger.debug("Browser loaded %s (status=%s)", url, status)
                return await operation(page, response)
            finally:
                await browser_context.close()
                await browser.close()

    def _descriptor_from_response(
        self,
        locator: SourceLocator,
        page: Any,
        response: Any,
        title: str,
        headers: Mapping[str, str],
    ) -> SourceDescriptor:
        final_url = getattr(page, "url", locator.uri)
        mime_type = headers.get("content-type", "text/html").split(";", 1)[0].strip()
        return SourceDescriptor(
            source_id=locator.uri,
            source_kind=self.kind,
            locator=locator,
            name=Path(urlsplit(final_url).path).name or (urlsplit(final_url).hostname or "page"),
            mime_type=mime_type or "text/html",
            metadata={
                "kind": "browser_page",
                "url": locator.uri,
                "final_url": final_url,
                "title": title,
                "status_code": getattr(response, "status", None),
                "headers": headers,
                "browser_type": self._browser_type,
            },
            provenance=self._provenance(
                locator,
                request_metadata={
                    "url": locator.uri,
                    "final_url": final_url,
                    "title": title,
                    "status_code": getattr(response, "status", None),
                },
            ),
            can_materialize=True,
            preview_available=True,
        )

    async def _descriptor_from_page(
        self, locator: SourceLocator, page: Any, response: Any
    ) -> SourceDescriptor:
        title = await page.title()
        headers = await self._headers_from_response(response)
        return self._descriptor_from_response(locator, page, response, title, headers)

    async def _headers_from_response(self, response: Any) -> Mapping[str, str]:
        headers = getattr(response, "headers", None)
        if isinstance(headers, Mapping):
            return {str(key).lower(): str(value) for key, value in headers.items()}

        all_headers = getattr(response, "all_headers", None)
        if callable(all_headers):
            result = await all_headers()
            if isinstance(result, Mapping):
                return {str(key).lower(): str(value) for key, value in result.items()}
        return {}

    def _assert_policy(self, url: str, context: KaosContext) -> None:
        assert_roots_allow_uri(url, context.roots, schemes={"http", "https"})
        allowed_hosts = context.get_config("source_browser_allowed_hosts")
        if allowed_hosts is None:
            allowed_hosts = context.get_config("source_http_allowed_hosts")
        if not allowed_hosts:
            return
        host = urlsplit(url).hostname or ""
        if any(fnmatch(host, pattern) for pattern in allowed_hosts):
            return
        raise SourcePolicyError("Browser source host is not allowed", locator=url, host=host)

    def _require_url(self, locator: SourceLocator) -> str:
        if locator.source_kind is not SourceKind.BROWSER:
            raise SourceValidationError(
                "Browser connector requires a browser locator", locator=locator.uri
            )
        parsed = urlsplit(locator.uri)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SourceValidationError("Invalid browser source locator", locator=locator.uri)
        return locator.uri

    @asynccontextmanager
    async def _playwright_context(self) -> Any:
        if self._playwright_factory is not None:
            async with self._playwright_factory() as playwright:
                yield playwright
            return
        try:
            async_api = importlib.import_module("playwright.async_api")
        except ImportError as exc:
            logger.warning("Playwright not installed — browser connector unavailable")
            raise SourceValidationError(
                "Playwright is required for browser sources. Install the browser extra first."
            ) from exc
        async with async_api.async_playwright() as playwright:
            yield playwright

    @asynccontextmanager
    async def _domain_gate(self, netloc: str, context: KaosContext):
        limit = int(
            context.get_config(
                "source_browser_max_concurrent_per_domain", self._max_concurrent_per_domain
            )
        )
        key = (netloc.lower(), max(1, limit))
        semaphore = self._domain_semaphores.setdefault(key, asyncio.Semaphore(key[1]))
        async with semaphore:
            yield

    def _user_agent_for(self, context: KaosContext) -> str:
        return str(context.get_config("source_browser_user_agent", self._user_agent))

    def _extra_headers_for(self, context: KaosContext) -> dict[str, str]:
        headers = dict(self._extra_headers)
        configured_headers = context.get_config("source_browser_headers", {})
        if isinstance(configured_headers, Mapping):
            headers.update({str(key): str(value) for key, value in configured_headers.items()})
        headers.setdefault("X-Kaos-Source", "1")
        return headers

    def _headless_for(self, context: KaosContext) -> bool:
        return bool(context.get_config("source_browser_headless", self._headless))

    def _timeout_ms_for(self, context: KaosContext) -> int:
        return int(context.get_config("source_browser_timeout_ms", self._timeout_ms))

    def _wait_until_for(self, context: KaosContext) -> str:
        return str(context.get_config("source_browser_wait_until", self._wait_until))

    def _take_screenshot_for(self, context: KaosContext) -> bool:
        return bool(context.get_config("source_browser_take_screenshot", self._take_screenshot))

    def _screenshot_full_page_for(self, context: KaosContext) -> bool:
        return bool(
            context.get_config("source_browser_screenshot_full_page", self._screenshot_full_page)
        )

    def _ignore_https_errors_for(self, context: KaosContext) -> bool:
        return bool(context.get_config("source_browser_ignore_https_errors", False))
