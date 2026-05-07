"""MCP tools for GLEIF LEI (Legal Entity Identifier) lookups.

Searches and retrieves legal entity data from the public GLEIF API.
No authentication required.
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

_GLEIF_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _entity_to_dict(entity: Any) -> dict[str, Any]:
    """Convert LEIEntity dataclass to JSON-safe dict."""
    d = asdict(entity)
    # Convert nested LEIAddress dataclasses
    for key in ("legal_address", "headquarters_address"):
        if d.get(key) is not None:
            d[key] = asdict(d[key]) if hasattr(d[key], "__dataclass_fields__") else d[key]
    # Remove None values for cleaner output
    return {k: v for k, v in d.items() if v is not None}


class GleifSearchTool(KaosTool):
    """Search for legal entities by name in the GLEIF database."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-gleif-search",
            display_name="GLEIF Entity Search",
            description=(
                "Search the GLEIF database for legal entities by name. Returns "
                "LEI, legal name, jurisdiction, registered address, headquarters, "
                "entity status, and registration authority. Covers all entities "
                "with Legal Entity Identifiers (financial institutions, public "
                "companies, funds, etc.). No API key required. "
                "For a specific LEI lookup, use kaos-source-gleif-get."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_GLEIF_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="name",
                    type="string",
                    description="Legal entity name to search for.",
                ),
                ParameterSchema(
                    name="country",
                    type="string",
                    description=(
                        "ISO 3166-1 alpha-2 country code to filter by "
                        "(e.g. 'US', 'GB', 'DE'). Optional."
                    ),
                    required=False,
                ),
                ParameterSchema(
                    name="per_page",
                    type="integer",
                    description="Results per page (default 10, max 200).",
                    required=False,
                    default=10,
                    constraints={"minimum": 1, "maximum": 200},
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        name = inputs.get("name", "")
        if not name:
            return ToolResult.create_error(
                "Parameter 'name' is required. Provide the legal entity name to search for."
            )

        country = inputs.get("country")
        per_page = inputs.get("per_page", 10)

        from kaos_source.apis.gleif.client import search_lei, search_lei_by_country

        try:
            if country:
                entities, total = await search_lei_by_country(country, name=name, per_page=per_page)
            else:
                entities, total = await search_lei(name, per_page=per_page)
        except Exception as exc:
            return ToolResult.create_error(
                f"GLEIF search failed: {exc}. The GLEIF API may be temporarily unavailable."
            )

        output = {
            "query": name,
            "total": total,
            "results": [_entity_to_dict(e) for e in entities],
        }
        return ToolResult.create_success(
            output,
            summary=f"GLEIF: {total} entities matching '{name}' ({len(entities)} shown)",
        )


class GleifGetTool(KaosTool):
    """Look up a specific Legal Entity Identifier (LEI)."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-gleif-get",
            display_name="GLEIF LEI Lookup",
            description=(
                "Look up a specific Legal Entity Identifier (LEI) in the GLEIF "
                "database. Returns full entity details: legal name, jurisdiction, "
                "registered and headquarters addresses, entity status, registration "
                "authority, and dates. LEIs are 20-character alphanumeric codes "
                "assigned to entities that engage in financial transactions. "
                "To find an LEI by name, use kaos-source-gleif-search."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_GLEIF_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="lei",
                    type="string",
                    description="The 20-character LEI code (e.g. '5493006MHB84DD0ZWV18').",
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        lei = inputs.get("lei", "").strip().upper()
        if not lei:
            return ToolResult.create_error(
                "Parameter 'lei' is required. Provide the 20-character LEI code."
            )
        if len(lei) != 20:
            return ToolResult.create_error(
                f"LEI must be exactly 20 characters, got {len(lei)}. "
                "Example: '5493006MHB84DD0ZWV18'. "
                "To search by name, use kaos-source-gleif-search."
            )

        from kaos_source.apis.gleif.client import get_lei

        try:
            entity = await get_lei(lei)
        except Exception as exc:
            return ToolResult.create_error(f"GLEIF lookup failed: {exc}.")

        if entity is None:
            return ToolResult.create_error(
                f"LEI '{lei}' not found in GLEIF database. "
                "Verify the code or search by name with kaos-source-gleif-search."
            )

        output = _entity_to_dict(entity)

        parts = [entity.legal_name]
        if entity.jurisdiction:
            parts.append(entity.jurisdiction)
        if entity.entity_status:
            parts.append(entity.entity_status)

        return ToolResult.create_success(
            output,
            summary=f"LEI {lei}: {' | '.join(parts)}",
        )


def register_gleif_tools(runtime: KaosRuntime) -> int:
    """Register all GLEIF tools with the runtime. Returns count."""
    tools: list[KaosTool] = [
        GleifSearchTool(),
        GleifGetTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)


__all__ = [
    "GleifGetTool",
    "GleifSearchTool",
    "register_gleif_tools",
]
