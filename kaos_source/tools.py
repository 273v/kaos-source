"""MCP tool definitions for source discovery and materialization.

KaosTool implementations wrapping SourceService connectors.
Each tool delegates to the existing SourceService for protocol-agnostic
source operations (filesystem, archive, HTTP, browser, memory).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kaos_core import KaosContext, KaosRuntime, KaosTool, ToolMetadata, ToolResult
from kaos_core.types.annotations import ToolAnnotations
from kaos_core.types.enums import ToolCapability, ToolCategory
from kaos_core.types.parameters import ParameterSchema

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
    from kaos_source.service import SourceService

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
            module_name=_MODULE,
            version=_VERSION,
            annotations=_LOCAL_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description="Directory or archive file path to explore.",
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
        path_str = inputs["path"]
        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            return ToolResult.create_error(
                f"Path not found: {path_str}. "
                "Verify the path is correct. Use an absolute path or relative to the working directory."
            )

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
                "Use 'kaos-source-describe' for file metadata or 'kaos-source-preview' for content."
            )

        service = _get_service()
        ctx = context or KaosContext.create(session_id="tools", runtime=KaosRuntime.default())

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
            module_name=_MODULE,
            version=_VERSION,
            annotations=_LOCAL_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description="File path to describe.",
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs["path"]
        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            return ToolResult.create_error(
                f"File not found: {path_str}. Verify the path is correct."
            )
        if not path.is_file():
            return ToolResult.create_error(
                f"'{path_str}' is a directory, not a file. "
                "Use 'kaos-source-discover' to list directory contents."
            )

        from kaos_source.models import SourceLocator

        locator = SourceLocator.filesystem(path)
        service = _get_service()
        ctx = context or KaosContext.create(session_id="tools", runtime=KaosRuntime.default())

        try:
            desc = await service.describe(locator, ctx)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to describe '{path_str}': {exc}. "
                "The file may be inaccessible or have permission issues."
            )

        result = _descriptor_to_dict(desc)
        summary = f"{desc.name} — {desc.mime_type or 'unknown type'}, {_format_size(desc.size)}"
        return ToolResult.create_success(output=result, summary=summary)


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
            module_name=_MODULE,
            version=_VERSION,
            annotations=_LOCAL_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description="File path to preview.",
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
        path_str = inputs["path"]
        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            return ToolResult.create_error(
                f"File not found: {path_str}. Verify the path is correct."
            )
        if not path.is_file():
            return ToolResult.create_error(
                f"'{path_str}' is a directory. Use 'kaos-source-discover' to list contents."
            )

        from kaos_source.models import SourceLocator
        from kaos_source.options import SourcePreviewOptions

        locator = SourceLocator.filesystem(path)
        service = _get_service()
        ctx = context or KaosContext.create(session_id="tools", runtime=KaosRuntime.default())
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
            module_name=_MODULE,
            version=_VERSION,
            annotations=_MATERIALIZE_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description="File path to materialize.",
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
        path_str = inputs["path"]
        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            return ToolResult.create_error(
                f"File not found: {path_str}. Verify the path is correct."
            )
        if not path.is_file():
            return ToolResult.create_error(
                f"'{path_str}' is a directory. Materialize individual files, not directories."
            )

        if context is None or context.runtime is None:
            return ToolResult.create_error(
                "No runtime context available. "
                "MaterializeSource requires a KaosRuntime with artifact storage. "
                "Use 'kaos-source-preview' for a quick look at file content without runtime."
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
                "The file may be inaccessible or the artifact store may be unavailable."
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


class FetchURLTool(KaosTool):
    """Fetch content from an HTTP/HTTPS URL."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-fetch-url",
            display_name="Fetch URL",
            description=(
                "Fetch content from an HTTP/HTTPS URL and materialize it as an artifact. "
                "Returns metadata and artifact ID. For web page extraction with readability "
                "and HTML-to-AST, use kaos-web tools instead."
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

        try:
            result = await service.materialize(locator, context, options)
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
            module_name=_MODULE,
            version=_VERSION,
            annotations=_LOCAL_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description="Path to the archive file (ZIP, TAR, TAR.GZ, etc.).",
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
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs["path"]
        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            return ToolResult.create_error(
                f"Archive not found: {path_str}. Verify the path is correct."
            )
        if not path.is_file():
            return ToolResult.create_error(
                f"'{path_str}' is a directory, not an archive. "
                "Use 'kaos-source-discover' for directories."
            )

        from kaos_source.models import SourceLocator
        from kaos_source.options import SourceDiscoverOptions

        locator = SourceLocator.archive(path)
        service = _get_service()
        ctx = context or KaosContext.create(session_id="tools", runtime=KaosRuntime.default())

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


def register_source_tools(runtime: KaosRuntime) -> int:
    """Register all source tools with the runtime. Returns count."""
    tools: list[KaosTool] = [
        DiscoverSourcesTool(),
        DescribeSourceTool(),
        PreviewSourceTool(),
        MaterializeSourceTool(),
        FetchURLTool(),
        InspectArchiveTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)
