"""MCP tools for PACER docket parsing.

Parses saved PACER docket HTML files — no network access required.
Requires lxml (already a dependency of kaos-web).
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from kaos_core import KaosContext, KaosRuntime, KaosTool, ToolMetadata, ToolResult
from kaos_core.types.annotations import ToolAnnotations
from kaos_core.types.enums import ToolCapability, ToolCategory
from kaos_core.types.parameters import ParameterSchema

_MODULE = "kaos-source"
_VERSION = "0.1.0"

_PACER_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,  # local parsing only
)


class PacerParseDocketTool(KaosTool):
    """Parse a saved PACER docket HTML file."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-pacer-parse",
            display_name="Parse PACER Docket",
            description=(
                "Parse a saved PACER docket HTML file into structured data. "
                "Extracts case info (parties, judge, dates, nature of suit) "
                "and all docket entries with document links. "
                "Operates locally — no PACER account needed."
            ),
            category=ToolCategory.DOCUMENT,
            capability=ToolCapability.EXTRACT,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_PACER_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description="Path to the saved PACER docket HTML file.",
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs.get("path", "")
        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            return ToolResult.create_error(
                f"File not found: {path_str}. Verify the path is correct."
            )
        if not path.is_file():
            return ToolResult.create_error(
                f"'{path_str}' is not a file. Provide a path to a saved PACER HTML file."
            )

        try:
            html_content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return ToolResult.create_error(f"Failed to read file '{path_str}': {exc}.")

        from kaos_source.parsers.pacer import parse_docket

        try:
            docket = parse_docket(html_content)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to parse docket from '{path.name}': {exc}. "
                "Verify this is a valid PACER docket HTML file."
            )

        # Convert to dict, handling dates
        entries = []
        for entry in docket.docket_entries:
            d = asdict(entry)
            d["date_filed"] = str(d["date_filed"])
            if d.get("filing_info") and d["filing_info"].get("filed_date"):
                d["filing_info"]["filed_date"] = str(d["filing_info"]["filed_date"])
            if d.get("filing_info") and d["filing_info"].get("entered_date"):
                d["filing_info"]["entered_date"] = str(d["filing_info"]["entered_date"])
            entries.append(d)

        output = {
            "case_number": docket.case_number,
            "case_title": docket.case_title,
            "plaintiff": docket.plaintiff,
            "defendant": docket.defendant,
            "date_filed": str(docket.date_filed),
            "date_terminated": str(docket.date_terminated) if docket.date_terminated else None,
            "assigned_judge": docket.assigned_judge,
            "nature_of_suit": docket.nature_of_suit,
            "cause_of_action": docket.cause_of_action,
            "jurisdiction": docket.jurisdiction,
            "entry_count": docket.entry_count,
            "docket_entries": entries,
            "warnings": docket.warnings,
        }

        summary = f"{docket.case_number}: {docket.case_title} — {docket.entry_count} entries"
        if docket.warnings:
            summary += f" ({len(docket.warnings)} warnings)"
        return ToolResult.create_success(output=output, summary=summary)


class PacerFilterEntriesTool(KaosTool):
    """Filter docket entries from a parsed PACER docket."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-pacer-filter-entries",
            display_name="Filter PACER Entries",
            description=(
                "Parse a PACER docket and filter entries by type, date range, "
                "or text search. Returns matching entries with document links."
            ),
            category=ToolCategory.DOCUMENT,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_PACER_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="path",
                    type="string",
                    description="Path to the saved PACER docket HTML file.",
                ),
                ParameterSchema(
                    name="entry_type",
                    type="string",
                    description=("Filter by entry type: Motion, Order, Notice, Complaint, etc."),
                    required=False,
                ),
                ParameterSchema(
                    name="text_search",
                    type="string",
                    description="Filter entries containing this text (case-insensitive).",
                    required=False,
                ),
                ParameterSchema(
                    name="has_documents",
                    type="boolean",
                    description="If true, only return entries with document links.",
                    required=False,
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        path_str = inputs.get("path", "")
        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            return ToolResult.create_error(
                f"File not found: {path_str}. Verify the path is correct."
            )

        try:
            html_content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return ToolResult.create_error(f"Failed to read file: {exc}.")

        from kaos_source.parsers.pacer import parse_docket

        try:
            docket = parse_docket(html_content)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to parse docket: {exc}. Verify this is a valid PACER docket HTML file."
            )

        entries = docket.docket_entries
        entry_type = inputs.get("entry_type")
        text_search = inputs.get("text_search", "").lower()
        has_documents = inputs.get("has_documents")

        if entry_type:
            entries = [e for e in entries if e.entry_type == entry_type]
        if text_search:
            entries = [e for e in entries if text_search in e.docket_text.lower()]
        if has_documents:
            entries = [e for e in entries if e.document_links]

        result_entries = []
        for entry in entries:
            d = asdict(entry)
            d["date_filed"] = str(d["date_filed"])
            if d.get("filing_info") and d["filing_info"].get("filed_date"):
                d["filing_info"]["filed_date"] = str(d["filing_info"]["filed_date"])
            if d.get("filing_info") and d["filing_info"].get("entered_date"):
                d["filing_info"]["entered_date"] = str(d["filing_info"]["entered_date"])
            result_entries.append(d)

        output = {
            "case_number": docket.case_number,
            "total_entries": docket.entry_count,
            "filtered_count": len(result_entries),
            "entries": result_entries,
            "warnings": docket.warnings,
        }

        summary = f"{len(result_entries)} of {docket.entry_count} entries matched"
        return ToolResult.create_success(output=output, summary=summary)


def register_pacer_tools(runtime: KaosRuntime) -> int:
    """Register all PACER tools with the runtime. Returns count."""
    tools: list[KaosTool] = [
        PacerParseDocketTool(),
        PacerFilterEntriesTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)
