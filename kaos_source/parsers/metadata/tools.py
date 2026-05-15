"""MCP tools for filesystem + image metadata extraction.

Track 1 chunk 8e split these out of the legacy
``kaos_source/tools_forensics.py`` into a per-parser-family location.
The remaining 3 forensics tools (eml, mbox, email-forensics) live in
:mod:`kaos_source.parsers.email.tools`.

Tools (2):

- ``kaos-source-image-metadata`` — :class:`ImageMetadataTool`
- ``kaos-source-file-metadata``  — :class:`FileMetadataTool`
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

_METADATA_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


# ── kaos-source-image-metadata ─────────────────────────────────────


class ImageMetadataTool(KaosTool):
    """Extract EXIF/GPS metadata from an image."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-image-metadata",
            display_name="Image EXIF Metadata",
            description=(
                "Extract EXIF metadata from JPEG, TIFF, PNG, or WebP images. "
                "Returns: camera make/model, date taken, GPS coordinates (with "
                "Google Maps link), software, author, copyright, exposure settings, "
                "orientation, and all other EXIF tags. "
                "Requires Pillow (pip install Pillow). "
                "For generic file metadata, use kaos-source-file-metadata."
            ),
            category=ToolCategory.DOCUMENT,
            capability=ToolCapability.EXTRACT,
            tags=["forensics"],
            module_name=_MODULE,
            version=_VERSION,
            annotations=_METADATA_ANNOTATIONS,
            input_schema=[
                ParameterSchema(name="path", type="string", description="Path to image file."),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs.get("path", "")
        if not path_str:
            return ToolResult.create_error("Parameter 'path' is required.")

        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            return ToolResult.create_error(f"File not found: {path_str}")

        from kaos_source.parsers.metadata.image import extract_image_metadata

        try:
            result = extract_image_metadata(path)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to extract image metadata: {exc}. "
                "Verify the file is a valid image (JPEG, PNG, TIFF, WebP)."
            )

        output = result.model_dump(mode="json", exclude_none=True)

        parts = []
        if result.format:
            parts.append(result.format)
        if result.width and result.height:
            parts.append(f"{result.width}x{result.height}")
        if result.camera_model:
            parts.append(result.camera_model)
        if result.datetime_original:
            parts.append(result.datetime_original[:10])
        if result.gps:
            parts.append(f"GPS: {result.gps.latitude:.4f},{result.gps.longitude:.4f}")

        return ToolResult.create_success(
            output, summary=" | ".join(parts) if parts else f"Image: {path.name}"
        )


# ── kaos-source-file-metadata ──────────────────────────────────────


class FileMetadataTool(KaosTool):
    """Extract file-level metadata and checksums."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-file-metadata",
            display_name="File Metadata",
            description=(
                "Extract filesystem metadata for any file: size, timestamps "
                "(created, modified, accessed), MIME type, file type detection "
                "via magic bytes, and cryptographic checksums (MD5, SHA-256). "
                "Useful for chain of custody, deduplication, and integrity "
                "verification in eDiscovery. No external dependencies. "
                "For image-specific EXIF data, use kaos-source-image-metadata."
            ),
            category=ToolCategory.DOCUMENT,
            capability=ToolCapability.EXTRACT,
            tags=["forensics"],
            module_name=_MODULE,
            version=_VERSION,
            annotations=_METADATA_ANNOTATIONS,
            input_schema=[
                ParameterSchema(name="path", type="string", description="Path to any file."),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs.get("path", "")
        if not path_str:
            return ToolResult.create_error("Parameter 'path' is required.")

        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            return ToolResult.create_error(f"File not found: {path_str}")
        if not path.is_file():
            return ToolResult.create_error(f"Not a file: {path_str}")

        from kaos_source.parsers.metadata.file import extract_file_metadata

        try:
            result = extract_file_metadata(path)
        except Exception as exc:
            return ToolResult.create_error(f"Failed to extract file metadata: {exc}")

        output = result.model_dump(mode="json", exclude_none=True)

        parts = [result.name]
        if result.mime_type:
            parts.append(result.mime_type)
        if result.size_bytes is not None:
            if result.size_bytes < 1024:
                parts.append(f"{result.size_bytes} B")
            elif result.size_bytes < 1024 * 1024:
                parts.append(f"{result.size_bytes / 1024:.1f} KB")
            else:
                parts.append(f"{result.size_bytes / (1024 * 1024):.1f} MB")

        return ToolResult.create_success(output, summary=" | ".join(parts))


# ── Registration ────────────────────────────────────────────────────


def register_metadata_tools(runtime: KaosRuntime) -> int:
    """Register the 2 file/image metadata MCP tools. Returns count."""
    tools: list[KaosTool] = [
        ImageMetadataTool(),
        FileMetadataTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)
