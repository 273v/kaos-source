"""MCP tool definitions for source discovery and materialization.

KaosTool implementations wrapping SourceService connectors.
Each tool delegates to the existing SourceService for protocol-agnostic
source operations (filesystem, archive, HTTP, browser, memory).
"""

from __future__ import annotations

from typing import Any

from kaos_core import KaosContext, KaosRuntime, KaosTool, ToolMetadata, ToolResult
from kaos_core.types.annotations import ToolAnnotations
from kaos_core.types.enums import ToolCapability, ToolCategory
from kaos_core.types.parameters import ParameterSchema

from kaos_source._path_resolver import (
    InputPathResolutionError,
    ResolvedOrigin,
    resolve_source_input,
)

_KAOS_URI_PREFIX = "kaos://"

_MODULE = "kaos-source"
_VERSION = "0.1.0"

# Read-only local tools (filesystem, archive) — no external network
_LOCAL_RO_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# Materialize writes to artifact store — not destructive, but not read-only
_MATERIALIZE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# HTTP fetch — read-only but hits external network
_NETWORK_RO_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

# HTTP materialize — writes artifact + hits network
_NETWORK_WRITE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _get_service() -> Any:
    """Get or create a shared SourceService singleton (lazy import)."""
    from kaos_source.runtime.service import SourceService

    return SourceService()


def _descriptor_to_dict(desc: Any) -> dict[str, Any]:
    """Convert a SourceDescriptor to a JSON-friendly dict."""
    return {
        "source_id": desc.source_id,
        "name": desc.name,
        "mime_type": desc.mime_type,
        "size": desc.size,
        "source_kind": str(desc.source_kind),
        "uri": desc.locator.uri,
        "created_at": desc.created_at,
        "modified_at": desc.modified_at,
        "can_materialize": desc.can_materialize,
        "preview_available": desc.preview_available,
        "metadata": desc.metadata,
    }


def _format_size(size: int | None) -> str:
    """Format byte size for display."""
    if size is None:
        return "unknown size"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


class DiscoverSourcesTool(KaosTool):
    """Discover files in a directory with optional filtering."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-discover",
            display_name="Discover Sources",
            description=(
                "List files in a directory or archive with optional glob filtering. "
                "Returns metadata (name, size, MIME type) without reading file contents. "
                "Use this to explore directories before previewing or materializing specific files."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            tags=["forensics"],
            module_name=_MODULE,
            version=_VERSION,
            annotations=_LOCAL_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description=(
                        "Directory or archive file path to explore. Accepts an "
                        "absolute filesystem path, a kaos://artifacts/<id> URI for "
                        "a previously materialised artifact, or a relative path / "
                        "kaos:// URI that resolves inside the session VFS (e.g. files "
                        "uploaded through the host UI)."
                    ),
                ),
                ParameterSchema(
                    name="recursive",
                    type="boolean",
                    description="Recurse into subdirectories (default true).",
                    required=False,
                    default=True,
                ),
                ParameterSchema(
                    name="limit",
                    type="integer",
                    description="Maximum items to return (default 50, max 500).",
                    required=False,
                    default=50,
                    constraints={"minimum": 1, "maximum": 500},
                ),
                ParameterSchema(
                    name="patterns",
                    type="array",
                    description='Glob patterns to filter files (e.g. ["*.pdf", "*.docx"]).',
                    required=False,
                    constraints={"items": {"type": "string"}},
                ),
                ParameterSchema(
                    name="cursor",
                    type="string",
                    description="Pagination cursor from a previous result.",
                    required=False,
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs.get("path", "")
        try:
            async with resolve_source_input(path_str, context) as resolved:
                path = resolved.path

                from kaos_source.models import SourceLocator
                from kaos_source.options import SourceDiscoverOptions

                # Auto-detect: archive file vs directory
                if path.is_file() and path.suffix.lower() in {
                    ".zip",
                    ".tar",
                    ".gz",
                    ".bz2",
                    ".tgz",
                    ".xz",
                }:
                    locator = SourceLocator.archive(path)
                elif path.is_dir():
                    locator = SourceLocator.filesystem(path)
                else:
                    return ToolResult.create_error(
                        f"'{path_str}' is a file, not a directory or archive. "
                        "Use 'kaos-source-describe' for file metadata or "
                        "'kaos-source-preview' for content."
                    )

                service = _get_service()
                ctx = context or KaosContext.create(
                    session_id="tools", runtime=KaosRuntime.default()
                )

                options = SourceDiscoverOptions(
                    recursive=inputs.get("recursive", True),
                    limit=min(inputs.get("limit", 50), 500),
                    patterns=inputs.get("patterns") or [],
                    cursor=inputs.get("cursor"),
                )

                try:
                    page = await service.discover(locator, ctx, options)
                except Exception as exc:
                    return ToolResult.create_error(
                        f"Discovery failed for '{path_str}': {exc}. "
                        "Check that the path is accessible and not corrupted."
                    )

                items = [_descriptor_to_dict(item) for item in page.items]
                result = {
                    "path": str(path),
                    "items": items,
                    "count": len(items),
                    "next_cursor": page.next_cursor,
                    "has_more": page.next_cursor is not None,
                }
                if page.total_count is not None:
                    result["total_count"] = page.total_count

                summary = f"Found {len(items)} item(s) in {path.name}"
                if page.next_cursor:
                    summary += " (more available)"

                return ToolResult.create_success(output=result, summary=summary)
        except InputPathResolutionError as exc:
            return ToolResult.create_error(exc.to_agent_message())


class DescribeSourceTool(KaosTool):
    """Get metadata for a file without reading its content."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-describe",
            display_name="Describe Source",
            description=(
                "Get metadata (name, size, MIME type, timestamps) for a file "
                "without reading its content. Use this to check a file before "
                "previewing or materializing it."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            tags=["forensics"],
            module_name=_MODULE,
            version=_VERSION,
            annotations=_LOCAL_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description=(
                        "File path to describe. Accepts an absolute filesystem path, "
                        "a kaos://artifacts/<id> URI, or a relative path / kaos:// URI "
                        "that resolves inside the session VFS."
                    ),
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs.get("path", "")
        try:
            async with resolve_source_input(path_str, context) as resolved:
                path = resolved.path

                if not path.is_file():
                    return ToolResult.create_error(
                        f"'{path_str}' is a directory, not a file. "
                        "Use 'kaos-source-discover' to list directory contents."
                    )

                from kaos_source.models import SourceLocator

                locator = SourceLocator.filesystem(path)
                service = _get_service()
                ctx = context or KaosContext.create(
                    session_id="tools", runtime=KaosRuntime.default()
                )

                try:
                    desc = await service.describe(locator, ctx)
                except Exception as exc:
                    return ToolResult.create_error(
                        f"Failed to describe '{path_str}': {exc}. "
                        "The file may be inaccessible or have permission issues."
                    )

                result = _descriptor_to_dict(desc)
                summary = (
                    f"{desc.name} — {desc.mime_type or 'unknown type'}, {_format_size(desc.size)}"
                )
                return ToolResult.create_success(output=result, summary=summary)
        except InputPathResolutionError as exc:
            return ToolResult.create_error(exc.to_agent_message())


class PreviewSourceTool(KaosTool):
    """Preview the content of a file (bounded read)."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-preview",
            display_name="Preview Source",
            description=(
                "Read a bounded preview of a file's content (default 1 KB). "
                "Returns text for text files, base64 for binary files. "
                "Use this to quickly inspect a file before full materialization."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.EXTRACT,
            tags=["forensics"],
            module_name=_MODULE,
            version=_VERSION,
            annotations=_LOCAL_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description=(
                        "File path to preview. Accepts an absolute filesystem path, "
                        "a kaos://artifacts/<id> URI, or a relative path / kaos:// URI "
                        "that resolves inside the session VFS."
                    ),
                ),
                ParameterSchema(
                    name="max_bytes",
                    type="integer",
                    description="Maximum bytes to read (default 1024, max 32768).",
                    required=False,
                    default=1024,
                    constraints={"minimum": 1, "maximum": 32768},
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs.get("path", "")
        try:
            async with resolve_source_input(path_str, context) as resolved:
                path = resolved.path

                if not path.is_file():
                    return ToolResult.create_error(
                        f"'{path_str}' is a directory. Use 'kaos-source-discover' to list contents."
                    )

                from kaos_source.models import SourceLocator
                from kaos_source.options import SourcePreviewOptions

                locator = SourceLocator.filesystem(path)
                service = _get_service()
                ctx = context or KaosContext.create(
                    session_id="tools", runtime=KaosRuntime.default()
                )
                max_bytes = min(inputs.get("max_bytes", 1024), 32768)
                options = SourcePreviewOptions(max_bytes=max_bytes)

                try:
                    preview = await service.preview(locator, ctx, options)
                except Exception as exc:
                    return ToolResult.create_error(
                        f"Preview failed for '{path_str}': {exc}. "
                        "The file may be inaccessible or corrupted."
                    )

                result: dict[str, Any] = {
                    "source_id": preview.source_id,
                    "truncated": preview.truncated,
                    "size": preview.size,
                    "mime_type": preview.mime_type,
                }
                if preview.text_preview is not None:
                    result["text"] = preview.text_preview
                    content_len = len(preview.text_preview)
                else:
                    result["binary_base64"] = preview.binary_preview_base64
                    content_len = len(preview.binary_preview_base64 or "")

                trunc = " (truncated)" if preview.truncated else ""
                summary = f"Preview of {path.name}: {content_len} chars{trunc}"
                return ToolResult.create_success(output=result, summary=summary)
        except InputPathResolutionError as exc:
            return ToolResult.create_error(exc.to_agent_message())


class MaterializeSourceTool(KaosTool):
    """Materialize a file into the artifact store."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-materialize",
            display_name="Materialize Source",
            description=(
                "Copy a file into the KAOS artifact store, making it available "
                "for processing by other tools (PDF extraction, tabular analysis, etc.). "
                "Returns an artifact ID and resource URI for subsequent operations."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.EXTRACT,
            tags=["forensics"],
            module_name=_MODULE,
            version=_VERSION,
            annotations=_MATERIALIZE_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description=(
                        "File path to materialize. Accepts an absolute filesystem "
                        "path or a relative path / kaos:// URI that resolves inside "
                        "the session VFS. Passing a kaos://artifacts/<id> URI for a "
                        "file that has already been materialised is a no-op: the "
                        "existing manifest is returned unchanged."
                    ),
                ),
                ParameterSchema(
                    name="name",
                    type="string",
                    description="Optional artifact name (defaults to filename).",
                    required=False,
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs.get("path", "")

        if context is None or context.runtime is None:
            return ToolResult.create_error(
                "No runtime context available. "
                "MaterializeSource requires a KaosRuntime with artifact storage. "
                "Use 'kaos-source-preview' for a quick look at file content without runtime."
            )

        try:
            async with resolve_source_input(path_str, context) as resolved:
                path = resolved.path

                if not path.is_file():
                    return ToolResult.create_error(
                        f"'{path_str}' is a directory. "
                        "Materialize individual files, not directories."
                    )

                # Short-circuit: if the input was already an artifact URI, the
                # artifact store already holds the bytes — return the existing
                # manifest instead of double-materialising into a new artifact.
                if resolved.origin is ResolvedOrigin.ARTIFACT and resolved.artifact_id is not None:
                    artifacts = context.runtime.artifacts
                    manifest = await artifacts._resolve_async(  # type: ignore[attr-defined]
                        resolved.artifact_id,
                        caller_session_id=context.session_id,
                    )
                    summary = (
                        f"Already materialised: {manifest.name or path.name} "
                        f"({_format_size(resolved.size)})"
                    )
                    return manifest.to_tool_result(
                        summary=summary,
                        structured_content={
                            "artifact_id": manifest.artifact_id,
                            "name": manifest.name,
                            "mime_type": manifest.mime_type,
                            "size": manifest.size,
                            "bytes_written": 0,
                            "body_uri": getattr(manifest, "body_uri", None)
                            or f"kaos://artifacts/{manifest.artifact_id}",
                            "already_materialized": True,
                        },
                    )

                from kaos_source.models import SourceLocator
                from kaos_source.options import SourceMaterializeOptions

                locator = SourceLocator.filesystem(path)
                service = _get_service()
                options = SourceMaterializeOptions(artifact_name=inputs.get("name"))

                try:
                    result = await service.materialize(locator, context, options)
                except Exception as exc:
                    return ToolResult.create_error(
                        f"Materialization failed for '{path_str}': {exc}. "
                        "The file may be inaccessible or the artifact store "
                        "may be unavailable."
                    )

                return result.manifest.to_tool_result(
                    summary=f"Materialized {path.name} ({_format_size(result.bytes_written)})",
                    structured_content={
                        "artifact_id": result.artifact_ref.artifact_id,
                        "name": result.descriptor.name,
                        "mime_type": result.descriptor.mime_type,
                        "size": result.descriptor.size,
                        "bytes_written": result.bytes_written,
                        "body_uri": result.manifest.body_uri,
                        "retention_policy": str(result.retention_policy),
                    },
                )
        except InputPathResolutionError as exc:
            return ToolResult.create_error(exc.to_agent_message())


class FetchURLTool(KaosTool):
    """Fetch content from an HTTP/HTTPS URL."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-fetch-url",
            display_name="Fetch URL",
            description=(
                "Fetch content from an HTTP/HTTPS URL and materialize it as an artifact. "
                "Returns metadata and artifact ID. Sends a realistic desktop Chrome "
                "User-Agent + browser-shaped headers by default; on anti-bot refusals "
                "(HTTP 403/451 or Cloudflare/captcha challenge HTML) falls back to a "
                "Playwright-driven fetch when the [browser] extra is installed. "
                "For web page extraction with readability and HTML-to-AST, use "
                "kaos-web tools instead."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.EXTRACT,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_NETWORK_WRITE_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="url",
                    type="string",
                    description="HTTP or HTTPS URL to fetch.",
                ),
                ParameterSchema(
                    name="name",
                    type="string",
                    description="Optional artifact name (defaults to URL filename).",
                    required=False,
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        url = inputs["url"]

        # SES2 fix: ``kaos://`` is an internal artifact / VFS URI scheme,
        # not an HTTP URL. Without this short-circuit the URL validator
        # below rejects ``kaos://artifacts/<id>`` with an unhelpful
        # "must use http or https" error and the agent has no idea
        # which tool to try next. See issue #402 / Stage 4 of the
        # vfs-blind-tools-audit-and-fix plan in kaos-modules.
        if isinstance(url, str) and url.strip().lower().startswith(_KAOS_URI_PREFIX):
            return ToolResult.create_error(
                f"{url!r} is an internal artifact / VFS URI, not an HTTP URL. "
                "To read VFS artifacts use the kaos-content-* tools with the "
                "artifact_id. To materialize a VFS file as an artifact use "
                "kaos-source-materialize. To fetch an external web page use "
                "kaos-source-fetch-url with an https:// URL."
            )

        if context is None or context.runtime is None:
            return ToolResult.create_error(
                "No runtime context available. "
                "FetchURL requires a KaosRuntime with artifact storage."
            )

        from kaos_source.models import SourceLocator
        from kaos_source.options import SourceMaterializeOptions

        try:
            locator = SourceLocator.http(url)
        except Exception as exc:
            return ToolResult.create_error(
                f"Invalid URL: {url}. {exc}. URL must use http:// or https:// scheme."
            )

        service = _get_service()
        options = SourceMaterializeOptions(artifact_name=inputs.get("name"))

        from kaos_source.errors import SourceAntiBotChallengeError
        from kaos_source.settings import KaosSourceHttpSettings

        try:
            result = await service.materialize(locator, context, options)
        except SourceAntiBotChallengeError as exc:
            # Issue #444 — host either returned an explicit refusal
            # status (403 / 451) or HTML matching a known anti-bot
            # interstitial fingerprint. Fall back to a Playwright
            # browser fetch if the operator opted in.
            http_settings = KaosSourceHttpSettings.from_context(context)
            if not http_settings.enable_browser_fallback:
                return ToolResult.create_error(
                    f"Fetch failed for '{url}': blocked by anti-bot challenge "
                    f"(fingerprint={exc.details.get('fingerprint')!r}, "
                    f"http_status={exc.details.get('http_status')}). "
                    "Browser fallback is disabled "
                    "(KAOS_SOURCE_HTTP_ENABLE_BROWSER_FALLBACK=0). "
                    "Re-enable it or use kaos-web browser tools."
                )
            return await self._fetch_via_browser(
                url=url,
                inputs=inputs,
                context=context,
                trigger=exc,
            )
        except Exception as exc:
            return ToolResult.create_error(
                f"Fetch failed for '{url}': {exc}. "
                "Check the URL is correct and the server is reachable. "
                "For JavaScript-rendered pages, use kaos-web browser tools instead."
            )

        return result.manifest.to_tool_result(
            summary=f"Fetched {locator.name} ({_format_size(result.bytes_written)})",
            structured_content={
                "artifact_id": result.artifact_ref.artifact_id,
                "url": url,
                "name": result.descriptor.name,
                "mime_type": result.descriptor.mime_type,
                "size": result.descriptor.size,
                "bytes_written": result.bytes_written,
                "body_uri": result.manifest.body_uri,
                "fetch_path": "httpx",
            },
        )

    async def _fetch_via_browser(
        self,
        *,
        url: str,
        inputs: dict[str, Any],
        context: KaosContext,
        trigger: Any,
    ) -> ToolResult:
        """Playwright fallback path for the FetchURL tool.

        Builds a one-shot :class:`BrowserConnector`-backed service,
        re-runs ``materialize`` against the same URL, and surfaces a
        clear error if the optional ``[browser]`` extra isn't
        installed (the Playwright import fails inside the connector).
        """
        fp_value = "anti-bot"
        details = getattr(trigger, "details", None)
        if isinstance(details, dict):
            raw_fp = details.get("fingerprint")
            if isinstance(raw_fp, str):
                fp_value = raw_fp

        try:
            import importlib

            importlib.import_module("playwright.async_api")
        except ImportError:
            return ToolResult.create_error(
                f"Fetch failed for '{url}': blocked by anti-bot challenge "
                f"(fingerprint={fp_value!r}). Playwright is required to bypass "
                "this kind of refusal, but the [browser] extra is not "
                "installed.\n\n"
                "Install it with:\n\n"
                "    pip install 'kaos-source[browser]'\n"
                "    python -m playwright install chromium\n\n"
                "Then retry the same kaos-source-fetch-url call. The "
                "host can still legitimately refuse Playwright; if so, "
                "the next error will state that explicitly."
            )

        from kaos_source.connectors.browser import BrowserConnector
        from kaos_source.models import SourceLocator
        from kaos_source.options import SourceMaterializeOptions
        from kaos_source.runtime.service import SourceService

        browser_service = SourceService(connectors=[BrowserConnector()])
        browser_locator = SourceLocator.browser(url)
        options = SourceMaterializeOptions(artifact_name=inputs.get("name"))

        try:
            result = await browser_service.materialize(browser_locator, context, options)
        except Exception as exc:
            return ToolResult.create_error(
                f"Fetch failed for '{url}': httpx hit an anti-bot challenge "
                f"(fingerprint={fp_value!r}) and the Playwright fallback also "
                f"failed: {exc}. The host may be blocking automated access "
                "regardless of browser type, or Playwright's browser binaries "
                "may not be installed (run `python -m playwright install chromium`)."
            )

        return result.manifest.to_tool_result(
            summary=f"Fetched {browser_locator.name} via browser fallback "
            f"({_format_size(result.bytes_written)})",
            structured_content={
                "artifact_id": result.artifact_ref.artifact_id,
                "url": url,
                "name": result.descriptor.name,
                "mime_type": result.descriptor.mime_type,
                "size": result.descriptor.size,
                "bytes_written": result.bytes_written,
                "body_uri": result.manifest.body_uri,
                "fetch_path": "playwright",
                "fallback_reason": fp_value,
            },
        )


class InspectArchiveTool(KaosTool):
    """List the contents of an archive file (ZIP, TAR, etc.)."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-inspect-archive",
            display_name="Inspect Archive",
            description=(
                "List the members of a ZIP, TAR, or compressed archive file. "
                "Returns member names, sizes, and MIME types without extracting. "
                "Use this before materializing specific archive members."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            tags=["forensics"],
            module_name=_MODULE,
            version=_VERSION,
            annotations=_LOCAL_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description=(
                        "Path to the archive file (ZIP, TAR, TAR.GZ, etc.). "
                        "Accepts an absolute filesystem path, a kaos://artifacts/<id> "
                        "URI, or a relative path / kaos:// URI that resolves inside "
                        "the session VFS."
                    ),
                ),
                ParameterSchema(
                    name="limit",
                    type="integer",
                    description="Maximum members to list (default 100, max 500).",
                    required=False,
                    default=100,
                    constraints={"minimum": 1, "maximum": 500},
                ),
                ParameterSchema(
                    name="patterns",
                    type="array",
                    description='Glob patterns to filter members (e.g. ["*.pdf"]).',
                    required=False,
                    constraints={"items": {"type": "string"}},
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs.get("path", "")
        try:
            async with resolve_source_input(path_str, context) as resolved:
                path = resolved.path

                if not path.is_file():
                    return ToolResult.create_error(
                        f"'{path_str}' is a directory, not an archive. "
                        "Use 'kaos-source-discover' for directories."
                    )

                from kaos_source.models import SourceLocator
                from kaos_source.options import SourceDiscoverOptions

                locator = SourceLocator.archive(path)
                service = _get_service()
                ctx = context or KaosContext.create(
                    session_id="tools", runtime=KaosRuntime.default()
                )

                options = SourceDiscoverOptions(
                    recursive=True,
                    limit=min(inputs.get("limit", 100), 500),
                    patterns=inputs.get("patterns") or [],
                )

                try:
                    page = await service.discover(locator, ctx, options)
                except Exception as exc:
                    return ToolResult.create_error(
                        f"Failed to inspect archive '{path_str}': {exc}. "
                        "The file may not be a valid archive or may be corrupted."
                    )

                members = [_descriptor_to_dict(item) for item in page.items]
                result = {
                    "archive": str(path),
                    "members": members,
                    "count": len(members),
                    "has_more": page.next_cursor is not None,
                }

                summary = f"{path.name}: {len(members)} member(s)"
                if page.next_cursor:
                    summary += " (more available)"

                return ToolResult.create_success(output=result, summary=summary)
        except InputPathResolutionError as exc:
            return ToolResult.create_error(exc.to_agent_message())


def register_source_web_tools(runtime: KaosRuntime) -> int:
    """Register the online (network-accessing) source tools.

    The 17 tools that fetch bytes or query a remote API over HTTP:

    - ``kaos-source-fetch-url`` (generic HTTP/HTTPS GET → artifact)
    - Federal Register API (4 tools)
    - eCFR API (4 tools)
    - GovInfo API (3 tools)
    - SEC EDGAR API (3 tools)
    - GLEIF LEI API (2 tools)

    Pins the SessionToolSet ``web`` group entry point for kaos-source.
    A session that opts into the ``web`` group (network egress
    allowed) gets exactly these tools.
    """
    from kaos_source.apis.ecfr.tools import register_ecfr_tools
    from kaos_source.apis.edgar.tools import register_edgar_tools
    from kaos_source.apis.federal_register.tools import register_federal_register_tools
    from kaos_source.apis.gleif.tools import register_gleif_tools
    from kaos_source.apis.govinfo.tools import register_govinfo_tools

    runtime.tools.register_tool(FetchURLTool())
    count = 1
    count += register_federal_register_tools(runtime)
    count += register_ecfr_tools(runtime)
    count += register_govinfo_tools(runtime)
    count += register_edgar_tools(runtime)
    count += register_gleif_tools(runtime)
    return count


def register_source_forensics_tools(runtime: KaosRuntime) -> int:
    """Register the offline (local byte-processing) source tools.

    The 13 tools that operate on already-local bytes — no network
    egress:

    - Core filesystem discovery (5 tools): ``discover``, ``describe``,
      ``preview``, ``materialize``, ``inspect-archive``
    - PACER docket parser (2 tools)
    - vCard parser (1 tool)
    - Email parser bundle (3 tools): ``parse-eml``, ``parse-mbox``,
      ``email-forensics``
    - File + image metadata extractors (2 tools)

    Pins the SessionToolSet ``forensics`` group entry point for
    kaos-source. Default-on at the ceiling because these are
    read-only operations on bytes the session already controls.
    """
    from kaos_source.parsers import register_forensics_tools as _register_email_metadata
    from kaos_source.parsers.pacer.tools import register_pacer_tools
    from kaos_source.parsers.vcard.tools import register_vcard_tools

    core_tools: list[KaosTool] = [
        DiscoverSourcesTool(),
        DescribeSourceTool(),
        PreviewSourceTool(),
        MaterializeSourceTool(),
        InspectArchiveTool(),
    ]
    for tool in core_tools:
        runtime.tools.register_tool(tool)
    count = len(core_tools)
    count += register_pacer_tools(runtime)
    count += register_vcard_tools(runtime)
    count += _register_email_metadata(runtime)
    return count


def register_source_tools(runtime: KaosRuntime) -> int:
    """Register all source tools with the runtime. Returns count.

    Backward-compatible union of :func:`register_source_web_tools`
    (17 online tools) and :func:`register_source_forensics_tools`
    (13 offline tools). This is the function called by
    ``kaos-mcp serve --module source``; existing callers see the
    same 30 tools as before.
    """
    count = register_source_web_tools(runtime)
    count += register_source_forensics_tools(runtime)
    return count
