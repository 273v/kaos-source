"""MCP tools for eDiscovery and forensic analysis.

5 tools for email, image, and file metadata extraction:
- kaos-source-parse-eml — Parse EML/MIME email files
- kaos-source-parse-mbox — Parse MBOX email archives
- kaos-source-email-forensics — Forensic email header analysis
- kaos-source-image-metadata — Image EXIF/GPS extraction
- kaos-source-file-metadata — Generic file checksums and metadata
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

_FORENSIC_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


# ── 1. kaos-source-parse-eml ───────────────────────────────────────


class ParseEmlTool(KaosTool):
    """Parse an EML/MIME email file."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-parse-eml",
            display_name="Parse EML Email",
            description=(
                "Parse a .eml file (RFC 5322 MIME format) into structured data. "
                "Extracts: From, To, CC, BCC, Subject, Date, Message-ID, threading "
                "(In-Reply-To, References), body text and HTML, attachment list "
                "(with filenames, sizes, MD5 hashes), and forensic header analysis "
                "(Received chain, SPF/DKIM/DMARC results, routing path). "
                "Uses stdlib only — no external dependencies. "
                "For MBOX archives, use kaos-source-parse-mbox. "
                "For header-only forensics, use kaos-source-email-forensics."
            ),
            category=ToolCategory.DOCUMENT,
            capability=ToolCapability.EXTRACT,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_FORENSIC_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description="Path to a .eml file.",
                ),
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

        from kaos_source.parsers.eml import parse_eml_file

        try:
            result = parse_eml_file(path)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to parse EML: {exc}. Verify the file is a valid RFC 5322 email message."
            )

        output = result.model_dump(mode="json", exclude_none=True)

        parts = []
        if result.from_address:
            parts.append(f"from: {result.from_address.address}")
        if result.subject:
            parts.append(result.subject[:60])
        parts.append(f"{result.attachment_count} attachment(s)")

        return ToolResult.create_success(output, summary=" | ".join(parts))


# ── 2. kaos-source-parse-mbox ──────────────────────────────────────


class ParseMboxTool(KaosTool):
    """Parse an MBOX email archive."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-parse-mbox",
            display_name="Parse MBOX Archive",
            description=(
                "Parse an .mbox email archive into structured messages. "
                "Common export format from Gmail, Thunderbird, macOS Mail. "
                "Extracts the same fields as kaos-source-parse-eml for each message. "
                "Use 'limit' to cap the number of messages parsed (large MBOX files "
                "can contain thousands of messages)."
            ),
            category=ToolCategory.DOCUMENT,
            capability=ToolCapability.EXTRACT,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_FORENSIC_ANNOTATIONS,
            input_schema=[
                ParameterSchema(name="path", type="string", description="Path to .mbox file."),
                ParameterSchema(
                    name="limit",
                    type="integer",
                    description="Max messages to parse (default: all).",
                    required=False,
                    constraints={"minimum": 1},
                ),
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

        limit = inputs.get("limit")

        from kaos_source.parsers.mbox import parse_mbox

        try:
            result = parse_mbox(path, limit=limit)
        except Exception as exc:
            return ToolResult.create_error(f"Failed to parse MBOX: {exc}")

        output = result.model_dump(mode="json", exclude_none=True)

        summary = f"{result.message_count} messages"
        if result.errors:
            summary += f" ({len(result.errors)} errors)"
        return ToolResult.create_success(output, summary=summary)


# ── 3. kaos-source-email-forensics ─────────────────────────────────


class EmailForensicsTool(KaosTool):
    """Forensic analysis of email headers."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-email-forensics",
            display_name="Email Header Forensics",
            description=(
                "Analyze email headers for forensic investigation. Extracts: "
                "Received chain (each hop with server, IP, timestamp), "
                "authentication results (SPF/DKIM/DMARC), Return-Path, "
                "X-Originating-IP, X-Mailer, transit time between hops. "
                "Useful for: tracing email routing, detecting spoofing, "
                "verifying authenticity, establishing timeline. "
                "For full email parsing, use kaos-source-parse-eml."
            ),
            category=ToolCategory.DOCUMENT,
            capability=ToolCapability.ANALYZE,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_FORENSIC_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description="Path to .eml file. Provide either 'path' or 'headers'.",
                    required=False,
                ),
                ParameterSchema(
                    name="headers",
                    type="string",
                    description="Raw email headers as text. Provide either 'path' or 'headers'.",
                    required=False,
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs.get("path")
        headers_str = inputs.get("headers")

        if not path_str and not headers_str:
            return ToolResult.create_error("Provide either 'path' or 'headers'.")

        from kaos_source.parsers.eml import parse_eml, parse_eml_file

        try:
            if path_str:
                path = Path(path_str).expanduser().resolve()
                if not path.exists():
                    return ToolResult.create_error(f"File not found: {path_str}")
                result = parse_eml_file(path)
            else:
                result = parse_eml(headers_str, include_forensics=True)
        except Exception as exc:
            return ToolResult.create_error(f"Failed to parse email: {exc}")

        if not result.forensics:
            return ToolResult.create_error("No forensic data could be extracted.")

        output = result.forensics.model_dump(mode="json", exclude_none=True)

        parts = [f"{result.forensics.hop_count} hops"]
        if result.forensics.transit_time_seconds is not None:
            parts.append(f"{result.forensics.transit_time_seconds}s transit")
        if result.forensics.auth_results:
            auth_summary = ", ".join(
                f"{a.mechanism}={a.result}" for a in result.forensics.auth_results
            )
            parts.append(auth_summary)

        return ToolResult.create_success(output, summary=" | ".join(parts))


# ── 4. kaos-source-image-metadata ──────────────────────────────────


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
            module_name=_MODULE,
            version=_VERSION,
            annotations=_FORENSIC_ANNOTATIONS,
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

        from kaos_source.parsers.image_meta import extract_image_metadata

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


# ── 5. kaos-source-file-metadata ───────────────────────────────────


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
            module_name=_MODULE,
            version=_VERSION,
            annotations=_FORENSIC_ANNOTATIONS,
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

        from kaos_source.parsers.file_meta import extract_file_metadata

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


def register_forensics_tools(runtime: KaosRuntime) -> int:
    """Register all forensic/eDiscovery tools with the runtime. Returns count."""
    tools: list[KaosTool] = [
        ParseEmlTool(),
        ParseMboxTool(),
        EmailForensicsTool(),
        ImageMetadataTool(),
        FileMetadataTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)
