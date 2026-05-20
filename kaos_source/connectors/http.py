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
from kaos_core.exceptions import UnsafeURLError
from kaos_core.logging import get_logger
from kaos_core.security import KaosSecuritySettings, validate_outbound_url

from kaos_source.connectors.base import (
    SourceConnector,
    assert_roots_allow_uri,
    decode_cursor,
    guess_mime_type,
)
from kaos_source.errors import (
    SourceAccessError,
    SourceAntiBotChallengeError,
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
from kaos_source.settings.http import DEFAULT_BROWSER_HEADERS, DEFAULT_HTTP_UA

logger = get_logger(__name__)

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

# Issue #444 — explicit anti-bot/refusal HTTP status codes that should
# trigger the Playwright fallback path even if the body is empty.
_ANTI_BOT_STATUS_CODES = {403, 451}

# Substrings (lowercased) we look for in the first ``_FINGERPRINT_SNIFF_BYTES``
# of an HTML response body to flag an anti-bot interstitial. Each tuple
# is ``(label, needle)``; the label is surfaced in the structured error
# so operators can audit false positives.
#
# Keep the needles narrow on purpose — broad strings like ``"bot"`` or
# ``"verify"`` would false-positive on legitimate cybersecurity, fraud,
# and authentication content. Every needle here is a phrase that
# Cloudflare / Akamai / hCaptcha / reCAPTCHA / DataDome / PerimeterX
# interstitials emit verbatim.
_ANTI_BOT_FINGERPRINTS: tuple[tuple[str, str], ...] = (
    ("cloudflare_just_a_moment", "<title>just a moment..."),
    ("cloudflare_challenge", "checking your browser before accessing"),
    ("cloudflare_attention", "attention required! | cloudflare"),
    ("cloudflare_ray", "cloudflare ray id:"),
    ("cf_chl", "cf-chl-bypass"),
    ("hcaptcha", "hcaptcha-challenge"),
    ("recaptcha_solve", "please solve the captcha"),
    ("recaptcha_challenge", 'class="g-recaptcha"'),
    ("perimeterx", "px-captcha"),
    ("datadome", "datadome-captcha"),
    ("akamai_bm", "<title>access denied</title>"),
    ("generic_captcha_title", "<title>captcha</title>"),
)

# Only sniff the first chunk — challenge HTML is always tiny.
_FINGERPRINT_SNIFF_BYTES = 16_384


class HttpConnector(SourceConnector):
    kind = SourceKind.HTTP
    name = "http"

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_concurrent_per_domain: int = 2,
        header_allowlist: tuple[str, ...] = _DEFAULT_ALLOWED_HEADERS,
        user_agent: str = DEFAULT_HTTP_UA,
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

    def _settings_for(self, context: KaosContext) -> Any:
        """Load typed HTTP settings from context, falling back to constructor defaults."""
        from kaos_source.settings import KaosSourceHttpSettings

        # Build overrides from constructor args that differ from class defaults
        overrides: dict[str, Any] = {}
        if self._max_concurrent_per_domain != 2:
            overrides["max_concurrent_per_domain"] = self._max_concurrent_per_domain
        if self._user_agent != DEFAULT_HTTP_UA:
            overrides["user_agent"] = self._user_agent
        if not self._verify_ssl:
            overrides["verify_ssl"] = self._verify_ssl
        if not self._follow_redirects:
            overrides["follow_redirects"] = self._follow_redirects
        if self._http2:
            overrides["http2"] = self._http2
        return KaosSourceHttpSettings.from_context(context, **overrides)

    async def describe(self, locator: SourceLocator, context: KaosContext) -> SourceDescriptor:
        url = self._require_url(locator)
        self._assert_policy(url, context)
        logger.debug("Describing HTTP source %s", url)

        async def load(client: httpx.AsyncClient) -> SourceDescriptor:
            head_response = await client.request("HEAD", url)
            if head_response.status_code in _HEAD_FALLBACK_STATUS_CODES:
                logger.debug(
                    "HEAD returned %d for %s, falling back to range GET",
                    head_response.status_code,
                    url,
                )
                range_headers = {"range": "bytes=0-0"}
                get_response = await client.request("GET", url, headers=range_headers)
                self._raise_for_anti_bot_status(get_response, url)
                self._raise_for_status(get_response, url)
                return self._descriptor_from_response(locator, get_response)

            self._raise_for_anti_bot_status(head_response, url)
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
        logger.debug("Previewing HTTP source %s (max_bytes=%d)", url, options.max_bytes)

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
        logger.debug("Materializing HTTP source %s", url)

        async def load(client: httpx.AsyncClient) -> SourceMaterialization:
            async with client.stream("GET", url) as response:
                self._raise_for_anti_bot_status(response, url)
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
        s = self._settings_for(context)
        parsed = urlsplit(url)
        timeout = s.timeout_seconds
        retry_limit = s.retry_limit
        # KSRC-04: validate every outbound request — including each
        # redirect hop — against the SSRF guard. httpx invokes this
        # hook before sending the request, so a malicious 302 to
        # http://169.254.169.254 is blocked before httpx connects.
        sec_settings = self._security_settings(context)

        async def _ssrf_request_hook(request: httpx.Request) -> None:
            try:
                validate_outbound_url(str(request.url), settings=sec_settings)
            except UnsafeURLError as exc:
                raise SourcePolicyError(
                    "HTTP redirect blocked by SSRF guard",
                    locator=str(request.url),
                    reason=exc.reason,
                    host=exc.host,
                ) from exc

        async with self._domain_request_gate(parsed.netloc, context, s):
            for attempt in range(retry_limit + 1):
                try:
                    async with httpx.AsyncClient(
                        follow_redirects=s.follow_redirects,
                        headers=self._request_headers(s, url=url),
                        verify=s.verify_ssl,
                        http2=s.http2,
                        timeout=timeout,
                        transport=self._transport,
                        event_hooks={"request": [_ssrf_request_hook]},
                    ) as client:
                        return await operation(client)
                except SourceTransientError as exc:
                    if attempt >= retry_limit:
                        logger.warning(
                            "HTTP request failed after %d attempts: %s — %s", attempt + 1, url, exc
                        )
                        raise
                    logger.info(
                        "Retrying %s (attempt %d/%d): %s", url, attempt + 2, retry_limit + 1, exc
                    )
                    await asyncio.sleep(self._retry_delay_seconds(attempt, exc.details, s))
                except httpx.TimeoutException as exc:
                    if attempt >= retry_limit:
                        logger.warning(
                            "HTTP request timed out after %d attempts: %s", attempt + 1, url
                        )
                        raise SourceTransientError(
                            "HTTP source request timed out",
                            locator=url,
                            timeout_seconds=timeout,
                        ) from exc
                    logger.info(
                        "Retrying %s after timeout (attempt %d/%d)",
                        url,
                        attempt + 2,
                        retry_limit + 1,
                    )
                    await asyncio.sleep(self._retry_delay_seconds(attempt, {}, s))
                except httpx.RequestError as exc:
                    if attempt >= retry_limit:
                        logger.warning(
                            "HTTP request failed after %d attempts: %s — %s", attempt + 1, url, exc
                        )
                        raise SourceTransientError(
                            "HTTP source request failed",
                            locator=url,
                            error=str(exc),
                        ) from exc
                    logger.info(
                        "Retrying %s after error (attempt %d/%d): %s",
                        url,
                        attempt + 2,
                        retry_limit + 1,
                        exc,
                    )
                    await asyncio.sleep(self._retry_delay_seconds(attempt, {}, s))
        raise SourceTransientError("HTTP source request failed unexpectedly", locator=url)

    def _assert_policy(self, url: str, context: KaosContext) -> None:
        assert_roots_allow_uri(url, context.roots, schemes={"http", "https"})
        # KSRC-04: kaos-core SSRF guard — blocks private networks,
        # loopback, and known cloud metadata services by default.
        # Configurable via KAOS_SECURITY_* env vars or the
        # KaosSecuritySettings instance the caller injected. Layered
        # *under* the explicit allowed_hosts allowlist below so the
        # operator can opt internal hosts back in when they need to.
        try:
            validate_outbound_url(url, settings=self._security_settings(context))
        except UnsafeURLError as exc:
            raise SourcePolicyError(
                "HTTP source URL blocked by SSRF guard",
                locator=url,
                reason=exc.reason,
                host=exc.host,
            ) from exc
        s = self._settings_for(context)
        allowed_hosts = s.allowed_hosts
        if not allowed_hosts:
            return
        host = urlsplit(url).hostname or ""
        if any(self._host_matches_pattern(host, pattern) for pattern in allowed_hosts):
            return
        raise SourcePolicyError("HTTP source host is not allowed", locator=url, host=host)

    def _security_settings(self, context: KaosContext) -> KaosSecuritySettings:
        """Resolve KaosSecuritySettings, allowing the connector's own
        allowed_hosts to flow into the SSRF guard's allowlist.

        KSRC-04: this is the integration point for per-context overrides
        of the SSRF guard. The default :class:`KaosSecuritySettings` is
        env-derived; we union its ``allowed_hosts`` with the connector's
        ``HttpSettings.allowed_hosts`` so an operator who allowlists a
        host for routing also allowlists it for the SSRF guard.
        """
        from kaos_source.settings import KaosSourceHttpSettings

        try:
            http_s = KaosSourceHttpSettings.from_context(context)
        except Exception:  # pragma: no cover — context wiring fallback
            http_s = None

        # Start from env-derived strict defaults, then merge in the
        # HTTP connector's allowed_hosts so allowlisted internal hosts
        # don't get rejected by the SSRF guard's private-network block.
        sec = KaosSecuritySettings()
        merged_hosts = list(sec.allowed_hosts)
        if http_s is not None and http_s.allowed_hosts:
            for entry in http_s.allowed_hosts:
                if entry and entry not in merged_hosts:
                    merged_hosts.append(entry)
        return sec.model_copy(update={"allowed_hosts": merged_hosts})

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
    async def _domain_request_gate(self, netloc: str, context: KaosContext, s: Any = None):
        if s is None:
            s = self._settings_for(context)
        limit = s.max_concurrent_per_domain
        key = (netloc.lower(), max(limit, 1))
        semaphore = self._domain_semaphores.setdefault(key, asyncio.Semaphore(key[1]))
        async with semaphore:
            min_interval = s.min_interval_seconds
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

    def _request_headers(self, s: Any, *, url: str | None = None) -> dict[str, str]:
        """Build request headers from connector + typed-settings + per-domain overrides.

        Layering (later layers win):

        1. ``DEFAULT_BROWSER_HEADERS`` — Accept / Accept-Language /
           Sec-Fetch-* paired with the realistic Chrome UA so the
           default request shape isn't an obvious bot.
        2. Constructor ``default_headers``.
        3. ``s.headers`` (typed settings global headers).
        4. ``User-Agent`` from ``s.user_agent``.
        5. Per-domain overrides from ``s.domain_overrides`` (issue #444)
           — keyed by host suffix match. These win because they're the
           most specific layer.
        6. ``X-Kaos-Source`` is forced on so an operator's outbound log
           can always attribute traffic to this connector.
        """
        headers: dict[str, str] = dict(DEFAULT_BROWSER_HEADERS)
        headers.update(self._default_headers)
        configured_headers = s.headers
        if isinstance(configured_headers, Mapping):
            headers.update({str(key): str(value) for key, value in configured_headers.items()})
        headers["User-Agent"] = s.user_agent

        # Per-domain overrides apply last so they beat the global UA / Accept.
        if url is not None:
            domain_headers = self._domain_overrides_for(url, s)
            if domain_headers:
                headers.update(domain_headers)

        headers["X-Kaos-Source"] = "1"
        return headers

    @staticmethod
    def _domain_overrides_for(url: str, s: Any) -> dict[str, str]:
        """Resolve per-domain header overrides for ``url`` against settings.

        Matching is suffix-based on the URL hostname:

        - exact match (``"reuters.com"`` matches ``"reuters.com"``)
        - subdomain match (``"reuters.com"`` matches ``"www.reuters.com"``
          and ``"feeds.reuters.com"``)

        On ambiguous matches the longest key wins so a more specific
        override (``"investor.example.com"``) beats a broader one
        (``"example.com"``).
        """
        overrides_map = getattr(s, "domain_overrides", None) or {}
        if not overrides_map:
            return {}
        host = (urlsplit(url).hostname or "").lower()
        if not host:
            return {}
        matched: tuple[str, dict[str, str]] | None = None
        for raw_key, raw_value in overrides_map.items():
            if not isinstance(raw_value, Mapping):
                continue
            key = str(raw_key).lower().lstrip(".")
            if not key:
                continue
            if (host == key or host.endswith("." + key)) and (
                matched is None or len(key) > len(matched[0])
            ):
                matched = (
                    key,
                    {str(name): str(value) for name, value in raw_value.items()},
                )
        return matched[1] if matched is not None else {}

    def _retry_delay_seconds(
        self, attempt: int, details: Mapping[str, object], settings: Any
    ) -> float:
        explicit_retry_after = details.get("retry_after_seconds")
        if isinstance(explicit_retry_after, (int, float)):
            return max(0.0, float(explicit_retry_after))
        return min(settings.retry_initial_delay * (2**attempt), settings.retry_max_delay)

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
        # Issue #444 — only sniff HTML bodies, since challenge pages
        # are always HTML. Saves CPU on PDF / ZIP / image responses.
        sniff_for_antibot = self._is_html_like(descriptor.mime_type)
        try:
            if target_disk_path is not None:
                bytes_written = await self._write_response_to_disk(
                    response,
                    target_disk_path,
                    context=context,
                    total_size=expected_size,
                    url=str(descriptor.locator.uri),
                    status_code=response.status_code,
                    sniff_for_antibot=sniff_for_antibot,
                )
            else:
                payload = await self._read_response_bytes(
                    response,
                    context=context,
                    total_size=expected_size,
                    url=str(descriptor.locator.uri),
                    status_code=response.status_code,
                    sniff_for_antibot=sniff_for_antibot,
                )
                bytes_written = len(payload)
                await context.vfs.write(
                    target_relative_path, payload, context_id=context.session_id
                )
        except OSError as exc:
            logger.warning(
                "Failed to write HTTP source to VFS: %s — %s", descriptor.locator.uri, exc
            )
            raise SourceMaterializationError(
                "Failed to materialize HTTP source into VFS",
                locator=descriptor.locator.uri,
                target_path=target_relative_path,
            ) from exc

        logger.debug("Materialized %s (%d bytes)", descriptor.locator.uri, bytes_written)
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
        url: str,
        status_code: int,
        sniff_for_antibot: bool,
    ) -> int:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        sniff_buffer = bytearray()
        sniffed = not sniff_for_antibot
        with target_path.open("wb") as handle:
            async for chunk in response.aiter_bytes():
                if not sniffed:
                    sniff_buffer.extend(chunk)
                    if len(sniff_buffer) >= _FINGERPRINT_SNIFF_BYTES:
                        self._check_antibot_body(
                            bytes(sniff_buffer),
                            url=url,
                            status_code=status_code,
                            target_path=target_path,
                        )
                        sniffed = True
                handle.write(chunk)
                written += len(chunk)
                await context.report_progress(written, total_size, f"Downloading {response.url}")
        # Stream ended before we hit the sniff threshold — check the
        # buffer we did collect (the whole body, for tiny challenge
        # pages typical of Cloudflare interstitials).
        if not sniffed:
            self._check_antibot_body(
                bytes(sniff_buffer),
                url=url,
                status_code=status_code,
                target_path=target_path,
            )
        return written

    async def _read_response_bytes(
        self,
        response: httpx.Response,
        *,
        context: KaosContext,
        total_size: int | None,
        url: str,
        status_code: int,
        sniff_for_antibot: bool,
    ) -> bytes:
        payload = bytearray()
        sniffed = not sniff_for_antibot
        async for chunk in response.aiter_bytes():
            payload.extend(chunk)
            if not sniffed and len(payload) >= _FINGERPRINT_SNIFF_BYTES:
                self._check_antibot_body(
                    bytes(payload[:_FINGERPRINT_SNIFF_BYTES]),
                    url=url,
                    status_code=status_code,
                )
                sniffed = True
            await context.report_progress(len(payload), total_size, f"Downloading {response.url}")
        if not sniffed:
            self._check_antibot_body(bytes(payload), url=url, status_code=status_code)
        return bytes(payload)

    @staticmethod
    def _is_html_like(mime_type: str | None) -> bool:
        if not mime_type:
            return False
        mt = mime_type.lower()
        return mt.startswith("text/html") or mt.startswith("application/xhtml")

    @staticmethod
    def _check_antibot_body(
        body: bytes,
        *,
        url: str,
        status_code: int,
        target_path: Path | None = None,
    ) -> None:
        """Raise :class:`SourceAntiBotChallengeError` if ``body`` matches a fingerprint.

        On match we also unlink ``target_path`` (if provided) so the
        partially written challenge HTML doesn't get materialised as
        an artifact — the caller's Playwright fallback will overwrite it.
        """
        try:
            sample = body.decode("utf-8", errors="ignore").lower()
        except Exception:  # pragma: no cover — bytes.decode with errors="ignore" cannot raise
            return
        for label, needle in _ANTI_BOT_FINGERPRINTS:
            if needle in sample:
                if target_path is not None:
                    try:
                        target_path.unlink(missing_ok=True)
                    except OSError:  # pragma: no cover — best-effort cleanup
                        logger.debug("Anti-bot cleanup: could not unlink %s", target_path)
                raise SourceAntiBotChallengeError(
                    "HTTP source returned an anti-bot challenge body",
                    locator=url,
                    http_status=status_code,
                    fingerprint=label,
                )

    @staticmethod
    def _raise_for_anti_bot_status(response: httpx.Response, url: str) -> None:
        """Convert explicit anti-bot HTTP refusals (403, 451) into a structured signal.

        Issue #444 — these codes are commonly emitted by hosts that
        decline to serve obvious bot traffic (Reuters, Bloomberg) or
        that are geofenced (451 = Unavailable For Legal Reasons). The
        FetchURL tool catches this and tries Playwright; if the host
        also refuses Playwright the error surfaces to the agent.
        """
        if response.status_code in _ANTI_BOT_STATUS_CODES:
            raise SourceAntiBotChallengeError(
                "HTTP source returned an anti-bot refusal status",
                locator=url,
                http_status=response.status_code,
                fingerprint=f"http_{response.status_code}",
            )

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
