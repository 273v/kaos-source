from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from kaos_core import ArtifactRetentionPolicy, KaosContext

from kaos_source.connectors.base import (
    SourceConnector,
    assert_roots_allow_uri,
    decode_cursor,
    guess_mime_type,
)
from kaos_source.errors import (
    SourceAccessError,
    SourceMaterializationError,
    SourceNotFoundError,
    SourcePolicyError,
    SourceTransientError,
    SourceValidationError,
)
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

_DEFAULT_ALLOWED_HEADERS = (
    "content-type",
    "content-length",
    "content-range",
    "etag",
    "last-modified",
    "cache-control",
    "content-disposition",
)
_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_HEAD_FALLBACK_STATUS_CODES = {403, 405, 501}


class HttpConnector(SourceConnector):
    kind = SourceKind.HTTP
    name = "http"

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_concurrent_per_domain: int = 2,
        header_allowlist: tuple[str, ...] = _DEFAULT_ALLOWED_HEADERS,
        user_agent: str = "kaos-source/0.1",
        verify_ssl: bool = True,
        follow_redirects: bool = True,
        http2: bool = False,
        default_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._transport = transport
        self._max_concurrent_per_domain = max_concurrent_per_domain
        self._header_allowlist = tuple(header.lower() for header in header_allowlist)
        self._user_agent = user_agent
        self._verify_ssl = verify_ssl
        self._follow_redirects = follow_redirects
        self._http2 = http2
        self._default_headers = dict(default_headers or {})
        self._domain_semaphores: dict[tuple[str, int], asyncio.Semaphore] = {}
        self._domain_rate_locks: dict[str, asyncio.Lock] = {}
        self._domain_last_request_at: dict[str, float] = {}

    async def describe(self, locator: SourceLocator, context: KaosContext) -> SourceDescriptor:
        url = self._require_url(locator)
        self._assert_policy(url, context)

        async def load(client: httpx.AsyncClient) -> SourceDescriptor:
            head_response = await client.request("HEAD", url)
            if head_response.status_code in _HEAD_FALLBACK_STATUS_CODES:
                range_headers = {"range": "bytes=0-0"}
                get_response = await client.request("GET", url, headers=range_headers)
                self._raise_for_status(get_response, url)
                return self._descriptor_from_response(locator, get_response)

            self._raise_for_status(head_response, url)
            return self._descriptor_from_response(locator, head_response)

        return await self._with_retries(url, context, load)

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
        url = self._require_url(locator)
        self._assert_policy(url, context)

        async def load(client: httpx.AsyncClient) -> tuple[SourceDescriptor, bytes, bool]:
            range_headers = {"range": f"bytes=0-{options.max_bytes}"}
            async with client.stream("GET", url, headers=range_headers) as response:
                self._raise_for_status(response, url)
                descriptor = self._descriptor_from_response(locator, response)
                payload, truncated = await self._read_preview_payload(response, options.max_bytes)
                return descriptor, payload, truncated

        descriptor, payload, truncated = await self._with_retries(url, context, load)
        return self._decode_preview_payload(
            payload,
            source_id=descriptor.source_id,
            size=descriptor.size,
            mime_type=descriptor.mime_type,
            encoding=options.encoding,
            truncated_override=truncated,
        )

    async def materialize(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceMaterializeOptions | None = None,
    ) -> SourceMaterialization:
        options = options or SourceMaterializeOptions()
        url = self._require_url(locator)
        self._assert_policy(url, context)

        async def load(client: httpx.AsyncClient) -> SourceMaterialization:
            async with client.stream("GET", url) as response:
                self._raise_for_status(response, url)
                descriptor = self._descriptor_from_response(locator, response)
                return await self._materialize_response(
                    response=response,
                    context=context,
                    descriptor=descriptor,
                    options=options,
                )

        return await self._with_retries(url, context, load)

    async def _with_retries(
        self,
        url: str,
        context: KaosContext,
        operation: Any,
    ) -> Any:
        parsed = urlsplit(url)
        timeout = float(
            context.get_config("source_http_timeout_seconds", context.get_config("timeout", 30.0))
        )
        retry_limit = int(
            context.get_config("source_http_retry_limit", context.get_config("retry_limit", 2))
        )
        async with self._domain_request_gate(parsed.netloc, context):
            for attempt in range(retry_limit + 1):
                try:
                    async with httpx.AsyncClient(
                        follow_redirects=self._follow_redirects_for(context),
                        headers=self._request_headers(context),
                        verify=self._verify_ssl_for(context),
                        http2=self._http2_for(context),
                        timeout=timeout,
                        transport=self._transport,
                    ) as client:
                        return await operation(client)
                except SourceTransientError as exc:
                    if attempt >= retry_limit:
                        raise
                    await asyncio.sleep(self._retry_delay_seconds(attempt, exc.details))
                except httpx.TimeoutException as exc:
                    if attempt >= retry_limit:
                        raise SourceTransientError(
                            "HTTP source request timed out",
                            locator=url,
                            timeout_seconds=timeout,
                        ) from exc
                    await asyncio.sleep(self._retry_delay_seconds(attempt, {}))
                except httpx.RequestError as exc:
                    if attempt >= retry_limit:
                        raise SourceTransientError(
                            "HTTP source request failed",
                            locator=url,
                            error=str(exc),
                        ) from exc
                    await asyncio.sleep(self._retry_delay_seconds(attempt, {}))
        raise SourceTransientError("HTTP source request failed unexpectedly", locator=url)

    def _assert_policy(self, url: str, context: KaosContext) -> None:
        assert_roots_allow_uri(url, context.roots, schemes={"http", "https"})
        allowed_hosts = context.get_config("source_http_allowed_hosts")
        if not allowed_hosts:
            return
        host = urlsplit(url).hostname or ""
        if any(self._host_matches_pattern(host, pattern) for pattern in allowed_hosts):
            return
        raise SourcePolicyError("HTTP source host is not allowed", locator=url, host=host)

    @staticmethod
    def _host_matches_pattern(host: str, pattern: str) -> bool:
        return fnmatch(host, pattern)

    def _require_url(self, locator: SourceLocator) -> str:
        if locator.source_kind is not SourceKind.HTTP:
            raise SourceValidationError(
                "HTTP connector requires an HTTP locator", locator=locator.uri
            )
        parsed = urlsplit(locator.uri)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SourceValidationError("Invalid HTTP source locator", locator=locator.uri)
        return locator.uri

    @asynccontextmanager
    async def _domain_request_gate(self, netloc: str, context: KaosContext):
        limit = int(
            context.get_config(
                "source_http_max_concurrent_per_domain", self._max_concurrent_per_domain
            )
        )
        key = (netloc.lower(), max(limit, 1))
        semaphore = self._domain_semaphores.setdefault(key, asyncio.Semaphore(key[1]))
        async with semaphore:
            min_interval = float(context.get_config("source_http_min_interval_seconds", 0.0))
            if min_interval > 0:
                domain = netloc.lower()
                rate_lock = self._domain_rate_locks.setdefault(domain, asyncio.Lock())
                async with rate_lock:
                    now = time.monotonic()
                    last_request_at = self._domain_last_request_at.get(domain)
                    if last_request_at is not None and now < last_request_at + min_interval:
                        await asyncio.sleep((last_request_at + min_interval) - now)
                    self._domain_last_request_at[domain] = time.monotonic()
            yield

    def _request_headers(self, context: KaosContext) -> dict[str, str]:
        headers = dict(self._default_headers)
        configured_headers = context.get_config("source_http_headers", {})
        if isinstance(configured_headers, Mapping):
            headers.update({str(key): str(value) for key, value in configured_headers.items()})
        headers["User-Agent"] = str(context.get_config("source_http_user_agent", self._user_agent))
        headers.setdefault("X-Kaos-Source", "1")
        return headers

    def _verify_ssl_for(self, context: KaosContext) -> bool:
        return bool(context.get_config("source_http_verify_ssl", self._verify_ssl))

    def _follow_redirects_for(self, context: KaosContext) -> bool:
        return bool(context.get_config("source_http_follow_redirects", self._follow_redirects))

    def _http2_for(self, context: KaosContext) -> bool:
        return bool(context.get_config("source_http_http2", self._http2))

    def _retry_delay_seconds(self, attempt: int, details: Mapping[str, object]) -> float:
        explicit_retry_after = details.get("retry_after_seconds")
        if isinstance(explicit_retry_after, (int, float)):
            return max(0.0, float(explicit_retry_after))
        return min(0.1 * (2**attempt), 1.0)

    def _descriptor_from_response(
        self,
        locator: SourceLocator,
        response: httpx.Response,
    ) -> SourceDescriptor:
        final_url = str(response.url)
        mime_type = self._content_type(response.headers)
        size = self._content_size(response.headers)
        name = self._name_from_url(final_url)
        filtered_headers = self._filtered_headers(response.headers)
        metadata = {
            "kind": "url",
            "url": locator.uri,
            "final_url": final_url,
            "host": response.url.host,
            "status_code": response.status_code,
            "headers": filtered_headers,
        }
        return SourceDescriptor(
            source_id=locator.uri,
            source_kind=self.kind,
            locator=locator,
            name=name,
            mime_type=mime_type or guess_mime_type(name),
            size=size,
            modified_at=filtered_headers.get("last-modified"),
            metadata=metadata,
            provenance=self._provenance(
                locator,
                request_metadata={
                    "url": locator.uri,
                    "final_url": final_url,
                    "status_code": response.status_code,
                    "headers": filtered_headers,
                },
            ),
            can_materialize=True,
            preview_available=True,
        )

    async def _read_preview_payload(
        self,
        response: httpx.Response,
        max_bytes: int,
    ) -> tuple[bytes, bool]:
        payload = bytearray()
        async for chunk in response.aiter_bytes():
            remaining = (max_bytes + 1) - len(payload)
            if remaining <= 0:
                break
            payload.extend(chunk[:remaining])
            if len(payload) > max_bytes:
                break
        truncated = len(payload) > max_bytes
        return bytes(payload[:max_bytes]), truncated

    async def _materialize_response(
        self,
        *,
        response: httpx.Response,
        context: KaosContext,
        descriptor: SourceDescriptor,
        options: SourceMaterializeOptions,
    ) -> SourceMaterialization:
        self._require_runtime(context)
        assert context.runtime is not None

        target_path = options.target_path or self._default_target_path(descriptor.name, self.kind)
        target_relative_path = context.vfs.normalize_path(target_path)
        target_disk_path = context.vfs.resolve_disk_path(
            target_relative_path, context_id=context.session_id
        )

        bytes_written = 0
        expected_size = descriptor.size
        try:
            if target_disk_path is not None:
                bytes_written = await self._write_response_to_disk(
                    response,
                    target_disk_path,
                    context=context,
                    total_size=expected_size,
                )
            else:
                payload = await self._read_response_bytes(
                    response, context=context, total_size=expected_size
                )
                bytes_written = len(payload)
                await context.vfs.write(
                    target_relative_path, payload, context_id=context.session_id
                )
        except OSError as exc:
            raise SourceMaterializationError(
                "Failed to materialize HTTP source into VFS",
                locator=descriptor.locator.uri,
                target_path=target_relative_path,
            ) from exc

        manifest = await context.runtime.artifacts.create_from_path(
            target_relative_path,
            context_id=context.session_id,
            session_id=context.session_id,
            workflow_id=options.workflow_id,
            name=options.artifact_name or descriptor.name,
            description=options.artifact_description,
            mime_type=descriptor.mime_type,
            role=options.role,
            provenance=descriptor.provenance.model_dump(mode="json"),
            retention_policy=options.retention_policy,
            metadata=options.metadata,
            checksum=options.checksum,
            ttl_seconds=options.ttl_seconds,
        )
        descriptor.size = manifest.size
        descriptor.mime_type = manifest.mime_type or descriptor.mime_type
        return SourceMaterialization(
            descriptor=descriptor,
            manifest=manifest,
            artifact_ref=manifest.to_ref(),
            bytes_written=bytes_written,
            retention_policy=ArtifactRetentionPolicy(manifest.retention_policy),
        )

    async def _write_response_to_disk(
        self,
        response: httpx.Response,
        target_path: Path,
        *,
        context: KaosContext,
        total_size: int | None,
    ) -> int:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with target_path.open("wb") as handle:
            async for chunk in response.aiter_bytes():
                handle.write(chunk)
                written += len(chunk)
                await context.report_progress(written, total_size, f"Downloading {response.url}")
        return written

    async def _read_response_bytes(
        self,
        response: httpx.Response,
        *,
        context: KaosContext,
        total_size: int | None,
    ) -> bytes:
        payload = bytearray()
        async for chunk in response.aiter_bytes():
            payload.extend(chunk)
            await context.report_progress(len(payload), total_size, f"Downloading {response.url}")
        return bytes(payload)

    def _filtered_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        return {
            name.lower(): value
            for name, value in headers.items()
            if name.lower() in self._header_allowlist
        }

    @staticmethod
    def _content_type(headers: Mapping[str, str]) -> str | None:
        content_type = headers.get("content-type")
        if content_type is None:
            return None
        return content_type.split(";", 1)[0].strip() or None

    @staticmethod
    def _content_size(headers: Mapping[str, str]) -> int | None:
        content_range = headers.get("content-range")
        if content_range and "/" in content_range:
            maybe_size = content_range.rsplit("/", 1)[-1]
            if maybe_size.isdigit():
                return int(maybe_size)
        content_length = headers.get("content-length")
        if content_length and content_length.isdigit():
            return int(content_length)
        return None

    @staticmethod
    def _name_from_url(url: str) -> str:
        parsed = urlsplit(url)
        name = Path(parsed.path).name
        return name or (parsed.hostname or "download")

    @staticmethod
    def _raise_for_status(response: httpx.Response, url: str) -> None:
        status_code = response.status_code
        if 200 <= status_code < 300:
            return
        if status_code == 404:
            raise SourceNotFoundError("HTTP source was not found", locator=url, http_status=404)
        if status_code in _RETRYABLE_STATUS_CODES:
            retry_after_seconds = HttpConnector._retry_after_seconds(
                response.headers.get("retry-after")
            )
            raise SourceTransientError(
                "HTTP source returned a retryable status",
                locator=url,
                http_status=status_code,
                retry_after_seconds=retry_after_seconds,
            )
        raise SourceAccessError(
            "HTTP source request failed",
            locator=url,
            http_status=status_code,
        )

    @staticmethod
    def _retry_after_seconds(retry_after_header: str | None) -> float | None:
        if retry_after_header is None:
            return None
        stripped = retry_after_header.strip()
        if stripped.isdigit():
            return float(stripped)
        try:
            parsed = parsedate_to_datetime(stripped)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(0.0, (parsed - datetime.now(tz=UTC)).total_seconds())
