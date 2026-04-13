"""MCP tools for eCFR (Electronic Code of Federal Regulations).

Public API — no authentication required.
Tools provide CFR title browsing, structure navigation, and content retrieval.
"""

from __future__ import annotations

from typing import Any

from kaos_core import KaosContext, KaosRuntime, KaosTool, ToolMetadata, ToolResult
from kaos_core.types.annotations import ToolAnnotations
from kaos_core.types.enums import ToolCapability, ToolCategory
from kaos_core.types.parameters import ParameterSchema

_MODULE = "kaos-source"
_VERSION = "0.1.0"

_ECFR_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


class ECFRListTitlesTool(KaosTool):
    """List all CFR titles."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-ecfr-titles",
            display_name="List CFR Titles",
            description=(
                "List all 50 titles in the Code of Federal Regulations. "
                "Returns title numbers, names, and last-amended dates. "
                "No API key required."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_ECFR_ANNOTATIONS,
            input_schema=[],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        from kaos_source.connectors.ecfr import KaosSourceECFRSettings, get_titles

        s = KaosSourceECFRSettings()
        try:
            titles = await get_titles(settings=s)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch CFR titles: {exc}. The eCFR API may be temporarily unavailable."
            )

        items = [
            {
                "number": t.number,
                "name": t.name,
                "latest_amended_on": t.latest_amended_on,
                "reserved": t.reserved,
            }
            for t in titles
        ]

        output = {"titles": items, "count": len(items)}
        return ToolResult.create_success(
            output=output,
            summary=f"{len(items)} CFR title(s)",
        )


class ECFRStructureTool(KaosTool):
    """Browse the structure of a CFR title (parts, subparts, sections)."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-ecfr-structure",
            display_name="CFR Title Structure",
            description=(
                "Get the hierarchical structure of a CFR title — parts, subparts, "
                "and sections. Use this to find section identifiers before fetching "
                "content with kaos-source-ecfr-content."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_ECFR_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="title",
                    type="integer",
                    description="CFR title number (1-50, e.g. 40 for environment).",
                    constraints={"minimum": 1, "maximum": 50},
                ),
                ParameterSchema(
                    name="date",
                    type="string",
                    description=(
                        "Date for the structure snapshot (YYYY-MM-DD). "
                        "Defaults to the latest available date from the eCFR API."
                    ),
                    required=False,
                ),
                ParameterSchema(
                    name="depth",
                    type="integer",
                    description="Max depth to show (default 2: parts only). Use 3+ for sections.",
                    required=False,
                    default=2,
                    constraints={"minimum": 1, "maximum": 5},
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        title = inputs["title"]
        max_depth = inputs.get("depth", 2)

        from kaos_source.connectors.ecfr import (
            KaosSourceECFRSettings,
            get_latest_date,
            get_title_structure,
        )

        s = KaosSourceECFRSettings()
        date_str = inputs.get("date")
        if not date_str:
            date_str = await get_latest_date(title, settings=s)
        if not date_str:
            return ToolResult.create_error(
                f"Could not determine the latest available date for CFR Title {title}. "
                "The eCFR titles API did not return a latest_issue_date. "
                "Provide an explicit 'date' parameter (YYYY-MM-DD) or retry later."
            )

        try:
            root = await get_title_structure(title, date_str, settings=s)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch structure for Title {title} (date={date_str}): {exc}. "
                "Verify the title number is valid (1-50). "
                "Use kaos-source-ecfr-titles to see all available titles."
            )

        def _node_to_dict(node: Any, current_depth: int = 0) -> dict[str, Any]:
            d: dict[str, Any] = {
                "type": node.type,
                "identifier": node.identifier,
                "label": node.label,
            }
            if node.reserved:
                d["reserved"] = True
            if current_depth < max_depth and node.children:
                d["children"] = [_node_to_dict(c, current_depth + 1) for c in node.children]
            elif node.children:
                d["child_count"] = len(node.children)
            return d

        tree = _node_to_dict(root)
        parts = root.find_parts()
        sections = root.find_sections()

        output = {
            "title": title,
            "date": date_str,
            "structure": tree,
            "part_count": len(parts),
            "section_count": len(sections),
        }

        summary = f"Title {title}: {len(parts)} part(s), {len(sections)} section(s)"
        return ToolResult.create_success(output=output, summary=summary)


class ECFRContentTool(KaosTool):
    """Get the content of a CFR section or part."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-ecfr-content",
            display_name="Get CFR Content",
            description=(
                "Fetch the text of a specific CFR section or part. "
                "Returns HTML or XML content. Use kaos-source-ecfr-structure first "
                "to find section identifiers."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.EXTRACT,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_ECFR_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="title",
                    type="integer",
                    description="CFR title number (e.g. 40).",
                    constraints={"minimum": 1, "maximum": 50},
                ),
                ParameterSchema(
                    name="section",
                    type="string",
                    description="Section identifier (e.g. '62.2'). Optional if part is provided.",
                    required=False,
                ),
                ParameterSchema(
                    name="part",
                    type="string",
                    description="Part number (e.g. '82'). Fetches entire part if no section specified.",
                    required=False,
                ),
                ParameterSchema(
                    name="date",
                    type="string",
                    description="Date for the content version (YYYY-MM-DD). Defaults to the latest available date from the eCFR API.",
                    required=False,
                ),
                ParameterSchema(
                    name="format",
                    type="string",
                    description="Content format: html (default) or xml.",
                    required=False,
                    default="html",
                    constraints={"enum": ["html", "xml"]},
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        title = inputs["title"]
        section = inputs.get("section")
        part = inputs.get("part")
        fmt = inputs.get("format", "html")

        if not section and not part:
            return ToolResult.create_error(
                "Either 'section' or 'part' is required. "
                "Use kaos-source-ecfr-structure to browse available sections."
            )

        from kaos_source.connectors.ecfr import (
            KaosSourceECFRSettings,
            get_latest_date,
            get_section_content,
        )

        s = KaosSourceECFRSettings()
        date_str = inputs.get("date")
        if not date_str:
            date_str = await get_latest_date(title, settings=s)
        if not date_str:
            return ToolResult.create_error(
                f"Could not determine the latest available date for CFR Title {title}. "
                "The eCFR titles API did not return a latest_issue_date. "
                "Provide an explicit 'date' parameter (YYYY-MM-DD) or retry later."
            )
        try:
            content = await get_section_content(
                title, date_str, section=section, part=part, format=fmt, settings=s
            )
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch content for Title {title}: {exc}. "
                "Verify the section/part identifier is correct. "
                "Use kaos-source-ecfr-structure to browse the title."
            )

        # Truncate very long content
        max_chars = 50_000
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars]

        ref = f"§{section}" if section else f"Part {part}"
        output = {
            "title": title,
            "section": section,
            "part": part,
            "date": date_str,
            "format": fmt,
            "content": content,
            "truncated": truncated,
            "length": len(content),
        }
        trunc_note = " (truncated)" if truncated else ""
        summary = f"Title {title} {ref} — {len(content)} chars ({fmt}){trunc_note}"
        return ToolResult.create_success(output=output, summary=summary)


class ECFRSearchTool(KaosTool):
    """Search for CFR parts/sections by keyword within a title's structure."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-ecfr-search-structure",
            display_name="Search CFR Structure",
            description=(
                "Search for parts and sections within a CFR title by keyword. "
                "Matches against section labels and descriptions. "
                "Use this to find specific regulations without browsing the full structure."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_ECFR_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="title",
                    type="integer",
                    description="CFR title number (e.g. 40).",
                    constraints={"minimum": 1, "maximum": 50},
                ),
                ParameterSchema(
                    name="query",
                    type="string",
                    description="Search term to match in section labels.",
                ),
                ParameterSchema(
                    name="date",
                    type="string",
                    description="Date (YYYY-MM-DD). Defaults to the latest available date from the eCFR API.",
                    required=False,
                ),
                ParameterSchema(
                    name="max_results",
                    type="integer",
                    description="Max results to return (default 20).",
                    required=False,
                    default=20,
                    constraints={"minimum": 1, "maximum": 100},
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        title = inputs["title"]
        query = inputs.get("query", "").strip().lower()
        max_results = inputs.get("max_results", 20)

        if not query:
            return ToolResult.create_error(
                "query is required. Provide a search term to match in section labels."
            )

        from kaos_source.connectors.ecfr import (
            KaosSourceECFRSettings,
            get_latest_date,
            get_title_structure,
        )

        s = KaosSourceECFRSettings()
        date_str = inputs.get("date")
        if not date_str:
            date_str = await get_latest_date(title, settings=s)
        if not date_str:
            return ToolResult.create_error(
                f"Could not determine the latest available date for CFR Title {title}. "
                "The eCFR titles API did not return a latest_issue_date. "
                "Provide an explicit 'date' parameter (YYYY-MM-DD) or retry later."
            )

        try:
            root = await get_title_structure(title, date_str, settings=s)
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch structure for Title {title}: {exc}. "
                "Verify the title number (1-50)."
            )

        # Search all nodes
        matches = []
        for node in root.flatten():
            if node.type in ("title",):
                continue
            text = f"{node.label} {node.label_description}".lower()
            if query in text:
                matches.append(
                    {
                        "type": node.type,
                        "identifier": node.identifier,
                        "label": node.label,
                        "description": node.label_description,
                    }
                )
                if len(matches) >= max_results:
                    break

        output = {
            "title": title,
            "query": query,
            "results": matches,
            "count": len(matches),
            "has_more": len(matches) >= max_results,
        }
        summary = f"Found {len(matches)} match(es) in Title {title} for '{query}'"
        return ToolResult.create_success(output=output, summary=summary)


def register_ecfr_tools(runtime: KaosRuntime) -> int:
    """Register all eCFR tools with the runtime. Returns count."""
    tools: list[KaosTool] = [
        ECFRListTitlesTool(),
        ECFRStructureTool(),
        ECFRContentTool(),
        ECFRSearchTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)
