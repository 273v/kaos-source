"""MCP tools for Federal Register document search and retrieval.

Public API — no authentication required.
Tools provide search, document fetch, and agency listing for the
Federal Register (https://www.federalregister.gov).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from kaos_core import KaosContext, KaosRuntime, KaosTool, ToolMetadata, ToolResult
from kaos_core.types.annotations import ToolAnnotations
from kaos_core.types.enums import ToolCapability, ToolCategory
from kaos_core.types.parameters import ParameterSchema

_MODULE = "kaos-source"
_VERSION = "0.1.0"

# All FR tools are read-only and hit external network
_FR_RO_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _doc_to_dict(doc: Any) -> dict[str, Any]:
    """Convert an FRDocument to a JSON-friendly dict."""
    d = asdict(doc)
    # Remove empty extra dict and empty strings for cleaner output
    if not d.get("extra"):
        d.pop("extra", None)
    return {k: v for k, v in d.items() if v != "" and v != [] and v != {} and v != 0}


class FRSearchTool(KaosTool):
    """Search Federal Register documents."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-fr-search",
            display_name="Search Federal Register",
            description=(
                "Search the Federal Register for rules, proposed rules, notices, "
                "and presidential documents. Supports full-text search, filtering by "
                "document type, agency, date range, CFR reference, and docket ID. "
                "No API key required."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_FR_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="term",
                    type="string",
                    description="Full-text search query.",
                    required=False,
                ),
                ParameterSchema(
                    name="doc_type",
                    type="string",
                    description="Document type: RULE, PRORULE, NOTICE, or PRESDOCU.",
                    required=False,
                    constraints={"enum": ["RULE", "PRORULE", "NOTICE", "PRESDOCU"]},
                ),
                ParameterSchema(
                    name="agency",
                    type="string",
                    description=(
                        "Agency slug (e.g. 'environmental-protection-agency', "
                        "'securities-and-exchange-commission'). "
                        "Use kaos-source-fr-agencies to find agency slugs."
                    ),
                    required=False,
                ),
                ParameterSchema(
                    name="date_from",
                    type="string",
                    description="Published on or after (YYYY-MM-DD).",
                    required=False,
                ),
                ParameterSchema(
                    name="date_to",
                    type="string",
                    description="Published on or before (YYYY-MM-DD).",
                    required=False,
                ),
                ParameterSchema(
                    name="significant",
                    type="boolean",
                    description="Filter to economically significant rules (EO 12866).",
                    required=False,
                ),
                ParameterSchema(
                    name="cfr_title",
                    type="integer",
                    description="CFR title number (e.g. 40 for EPA regulations).",
                    required=False,
                ),
                ParameterSchema(
                    name="cfr_part",
                    type="integer",
                    description="CFR part number (e.g. 82 for HFC regulations).",
                    required=False,
                ),
                ParameterSchema(
                    name="docket_id",
                    type="string",
                    description="Agency docket ID (e.g. 'EPA-HQ-OAR-2024-0503').",
                    required=False,
                ),
                ParameterSchema(
                    name="per_page",
                    type="integer",
                    description="Results per page (default 20, max 100).",
                    required=False,
                    default=20,
                    constraints={"minimum": 1, "maximum": 100},
                ),
                ParameterSchema(
                    name="page",
                    type="integer",
                    description="Page number (default 1).",
                    required=False,
                    default=1,
                    constraints={"minimum": 1, "maximum": 50},
                ),
                ParameterSchema(
                    name="order",
                    type="string",
                    description="Sort order: newest, oldest, or relevance.",
                    required=False,
                    default="newest",
                    constraints={"enum": ["newest", "oldest", "relevance"]},
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        from kaos_source.connectors.federal_register import (
            KaosSourceFRSettings,
            search_documents,
        )

        s = KaosSourceFRSettings()
        try:
            result = await search_documents(
                term=inputs.get("term", ""),
                doc_type=inputs.get("doc_type"),
                agencies=inputs.get("agency"),
                date_gte=inputs.get("date_from"),
                date_lte=inputs.get("date_to"),
                significant=inputs.get("significant"),
                cfr_title=inputs.get("cfr_title"),
                cfr_part=inputs.get("cfr_part"),
                docket_id=inputs.get("docket_id"),
                per_page=min(inputs.get("per_page", 20), 100),
                page=inputs.get("page", 1),
                order=inputs.get("order", "newest"),
                settings=s,
            )
        except Exception as exc:
            return ToolResult.create_error(
                f"Federal Register search failed: {exc}. "
                "Check your query parameters and try again. "
                "The API requires no authentication."
            )

        docs = [_doc_to_dict(d) for d in result.documents]
        output = {
            "results": docs,
            "count": result.count,
            "total_pages": result.total_pages,
            "has_more": result.next_page_url is not None,
            "returned": len(docs),
        }

        summary = f"Found {result.count} Federal Register document(s), showing {len(docs)}"
        if result.next_page_url:
            summary += f" (page {inputs.get('page', 1)} of {result.total_pages})"

        return ToolResult.create_success(output=output, summary=summary)


class FRGetDocumentTool(KaosTool):
    """Get a specific Federal Register document by document number."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-fr-get-document",
            display_name="Get FR Document",
            description=(
                "Get detailed metadata for a specific Federal Register document "
                "by its document number (e.g. '2024-12345'). Returns title, abstract, "
                "dates, agencies, CFR references, and content URLs."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.EXTRACT,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_FR_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="document_number",
                    type="string",
                    description="FR document number (e.g. '2024-12345').",
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        doc_num = inputs.get("document_number", "").strip()
        if not doc_num:
            return ToolResult.create_error(
                "document_number is required. Use kaos-source-fr-search to find document numbers."
            )

        from kaos_source.connectors.federal_register import KaosSourceFRSettings, get_document

        s = KaosSourceFRSettings()
        try:
            doc = await get_document(doc_num, settings=s)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch FR document '{doc_num}': {exc}. "
                "Verify the document number is correct. "
                "Use kaos-source-fr-search to find valid document numbers."
            )

        output = _doc_to_dict(doc)
        summary = f"{doc.title} ({doc.type}, {doc.publication_date})"
        return ToolResult.create_success(output=output, summary=summary)


class FRGetContentTool(KaosTool):
    """Fetch the full text content of a Federal Register document."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-fr-get-content",
            display_name="Get FR Content",
            description=(
                "Fetch the full text content of a Federal Register document. "
                "Supports text, XML, and HTML formats. Use this after finding a "
                "document with kaos-source-fr-search or kaos-source-fr-get-document."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.EXTRACT,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_FR_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="document_number",
                    type="string",
                    description="FR document number (e.g. '2024-12345').",
                ),
                ParameterSchema(
                    name="format",
                    type="string",
                    description="Content format: text (default), xml, or html.",
                    required=False,
                    default="text",
                    constraints={"enum": ["text", "xml", "html"]},
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        doc_num = inputs.get("document_number", "").strip()
        if not doc_num:
            return ToolResult.create_error(
                "document_number is required. Use kaos-source-fr-search to find document numbers."
            )

        fmt = inputs.get("format", "text")

        from kaos_source.connectors.federal_register import (
            KaosSourceFRSettings,
            fetch_document_content,
            get_document,
        )

        s = KaosSourceFRSettings()
        try:
            doc = await get_document(doc_num, settings=s)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch FR document '{doc_num}': {exc}. "
                "Verify the document number is correct."
            )

        try:
            content = await fetch_document_content(doc, format=fmt, settings=s)
        except ValueError as exc:
            return ToolResult.create_error(
                f"Failed to fetch {fmt} content for FR document '{doc_num}': {exc}. "
                "Verify the document number is correct and try a different format "
                "(text, xml, html). Use kaos-source-fr-search to find valid document numbers."
            )
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch {fmt} content for '{doc_num}': {exc}. "
                "The content URL may be temporarily unavailable. "
                "Try a different format (text, xml, html)."
            )

        if isinstance(content, bytes):
            return ToolResult.create_error(
                "PDF format returns binary content. "
                "Use text, xml, or html format for inline content, "
                "or use kaos-source-fetch-url with the pdf_url to materialize the PDF."
            )

        # Truncate very long content
        max_chars = 50_000
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars]

        output = {
            "document_number": doc_num,
            "title": doc.title,
            "format": fmt,
            "content": content,
            "truncated": truncated,
        }
        trunc_note = " (truncated)" if truncated else ""
        summary = f"{doc.title} — {len(content)} chars ({fmt}){trunc_note}"
        return ToolResult.create_success(output=output, summary=summary)


class FRAgenciesTool(KaosTool):
    """List Federal Register agencies."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-fr-agencies",
            display_name="List FR Agencies",
            description=(
                "List all Federal Register agencies with their slugs. "
                "Use agency slugs with kaos-source-fr-search to filter by agency."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_FR_RO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="search",
                    type="string",
                    description="Optional text to filter agencies by name.",
                    required=False,
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        from kaos_source.connectors.federal_register import KaosSourceFRSettings, get_agencies

        s = KaosSourceFRSettings()
        try:
            agencies = await get_agencies(settings=s)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch agencies: {exc}. "
                "The Federal Register API may be temporarily unavailable."
            )

        search_term = (inputs.get("search") or "").lower()
        if search_term:
            agencies = [
                a
                for a in agencies
                if search_term in a.name.lower() or search_term in (a.short_name or "").lower()
            ]

        items = [
            {
                "id": a.id,
                "name": a.name,
                "short_name": a.short_name,
                "slug": a.slug,
            }
            for a in agencies
        ]

        output = {"agencies": items, "count": len(items)}
        summary = f"{len(items)} Federal Register agency/agencies"
        return ToolResult.create_success(output=output, summary=summary)


def register_federal_register_tools(runtime: KaosRuntime) -> int:
    """Register all Federal Register tools with the runtime. Returns count."""
    tools: list[KaosTool] = [
        FRSearchTool(),
        FRGetDocumentTool(),
        FRGetContentTool(),
        FRAgenciesTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)
