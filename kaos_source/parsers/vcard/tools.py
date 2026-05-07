"""MCP tools for vCard/VCF parsing.

Parses vCard content from a string or local file — no network access
required.  Supports vCard 2.1, 3.0, and 4.0 (RFC 6350 / RFC 2426).
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

_VCARD_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _vcard_to_dict(vcard: Any) -> dict[str, Any]:
    """Serialize a VCardModel to a JSON-safe dict."""
    data = vcard.model_dump(exclude_none=True, mode="json")
    # Drop raw_properties from output — they are noise for consumers.
    data.pop("raw_properties", None)
    return data


class VCardParseTool(KaosTool):
    """Parse vCard content from a string or file."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-vcard-parse",
            display_name="Parse VCard",
            description=(
                "Parse vCard/VCF content into structured contact data. "
                "Extracts name, emails, phones, addresses, organization, "
                "title, social profiles, photo, and more. Accepts either "
                "raw vCard text via 'content' or a file path via 'path'. "
                "Supports vCard 2.1, 3.0, and 4.0 (RFC 6350). "
                "For web-based contact extraction, use kaos-web-get-metadata."
            ),
            category=ToolCategory.DOCUMENT,
            capability=ToolCapability.EXTRACT,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_VCARD_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="content",
                    type="string",
                    description=(
                        "Raw vCard/VCF text content. Provide either 'content' or 'path', not both."
                    ),
                    required=False,
                ),
                ParameterSchema(
                    name="path",
                    type="string",
                    description=(
                        "Path to a .vcf file. Provide either 'content' or 'path', not both."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        content = inputs.get("content")
        path_str = inputs.get("path")

        if not content and not path_str:
            return ToolResult.create_error(
                "Either 'content' (raw vCard text) or 'path' (path to .vcf file) "
                "is required. Provide one of them."
            )
        if content and path_str:
            return ToolResult.create_error("Provide either 'content' or 'path', not both.")

        if path_str:
            path = Path(path_str).expanduser().resolve()
            if not path.exists():
                return ToolResult.create_error(
                    f"File not found: {path_str}. Verify the path is correct."
                )
            if not path.is_file():
                return ToolResult.create_error(
                    f"'{path_str}' is not a file. Provide a path to a .vcf file."
                )
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                return ToolResult.create_error(f"Failed to read file '{path_str}': {exc}.")

        from kaos_source.parsers.vcard.parser import parse_vcard

        try:
            status, vcard, errors = parse_vcard(content)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        except Exception as exc:
            return ToolResult.create_error(
                f"VCard parsing failed: {exc}. "
                "Verify the input is valid vCard/VCF format "
                "(must start with BEGIN:VCARD)."
            )

        if vcard is None:
            error_detail = "; ".join(errors) if errors else "Unknown error"
            return ToolResult.create_error(
                f"Invalid vCard: {error_detail}. "
                "Ensure the content follows RFC 6350 format "
                "(BEGIN:VCARD, VERSION, FN, END:VCARD are required)."
            )

        output = {
            "status": status.value,
            "vcard": _vcard_to_dict(vcard),
            "errors": errors,
        }

        name = vcard.formatted_name
        parts = []
        if vcard.organization:
            parts.append(vcard.organization.name)
        if vcard.title:
            parts.append(vcard.title)
        detail = f" ({', '.join(parts)})" if parts else ""

        return ToolResult.create_success(
            output=output,
            summary=f"Parsed vCard: {name}{detail}",
        )


def register_vcard_tools(runtime: KaosRuntime) -> int:
    """Register all vCard tools with the runtime. Returns count."""
    tools: list[KaosTool] = [
        VCardParseTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)
