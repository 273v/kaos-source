"""MCP tools for the email parser cluster (eml, mbox, header forensics).

Track 1 chunk 8e split these out of the legacy
``kaos_source/tools_forensics.py`` into the email parser family. The
sibling 2 metadata tools (image-metadata, file-metadata) live in
:mod:`kaos_source.parsers.metadata.tools`.

Tools (3):

- ``kaos-source-parse-eml``         — :class:`ParseEmlTool`
- ``kaos-source-parse-mbox``        — :class:`ParseMboxTool`
- ``kaos-source-email-forensics``   — :class:`EmailForensicsTool`
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


# ── kaos-source-parse-eml ──────────────────────────────────────────


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

        from kaos_source.parsers.email.eml import parse_eml_file

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


# ── kaos-source-parse-mbox ─────────────────────────────────────────


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

        from kaos_source.parsers.email.mbox import parse_mbox

        try:
            result = parse_mbox(path, limit=limit)
        except Exception as exc:
            return ToolResult.create_error(f"Failed to parse MBOX: {exc}")

        output = result.model_dump(mode="json", exclude_none=True)

        summary = f"{result.message_count} messages"
        if result.errors:
            summary += f" ({len(result.errors)} errors)"
        return ToolResult.create_success(output, summary=summary)


# ── kaos-source-email-forensics ────────────────────────────────────


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

        from kaos_source.parsers.email.eml import parse_eml, parse_eml_file

        try:
            if path_str:
                path = Path(path_str).expanduser().resolve()
                if not path.exists():
                    return ToolResult.create_error(f"File not found: {path_str}")
                result = parse_eml_file(path)
            elif isinstance(headers_str, str | bytes):
                result = parse_eml(headers_str, include_forensics=True)
            else:
                return ToolResult.create_error("'headers' must be a string.")
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


# ── Registration ────────────────────────────────────────────────────


def register_email_tools(runtime: KaosRuntime) -> int:
    """Register the 3 email-family MCP tools. Returns count."""
    tools: list[KaosTool] = [
        ParseEmlTool(),
        ParseMboxTool(),
        EmailForensicsTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)
