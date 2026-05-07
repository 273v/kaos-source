"""MCP tools for GovInfo (Government Publishing Office).

Requires API key: set ``KAOS_SOURCE_GOVINFO_API_KEY`` or
``GOVINFO_API_KEY``. Get a free key at https://api.data.gov/signup/.
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

_GOVINFO_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _clean_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Remove empty values for cleaner output."""
    return {k: v for k, v in d.items() if v != "" and v != [] and v != {} and v != 0}


class GovInfoSearchTool(KaosTool):
    """Search across all GovInfo government publications."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-govinfo-search",
            display_name="Search GovInfo",
            description=(
                "Search the Government Publishing Office for bills, regulations, "
                "congressional records, CFR, Federal Register entries, and more. "
                "Requires KAOS_SOURCE_GOVINFO_API_KEY (free at api.data.gov/signup)."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_GOVINFO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="query",
                    type="string",
                    description="Search query string.",
                ),
                ParameterSchema(
                    name="collection",
                    type="string",
                    description=(
                        "Collection code to filter (e.g. 'FR', 'BILLS', 'CFR', 'CREC', 'USCODE'). "
                        "Use kaos-source-govinfo-collections to see all codes."
                    ),
                    required=False,
                ),
                ParameterSchema(
                    name="page_size",
                    type="integer",
                    description="Results per page (default 20, max 100).",
                    required=False,
                    default=20,
                    constraints={"minimum": 1, "maximum": 100},
                ),
                ParameterSchema(
                    name="offset_mark",
                    type="string",
                    description='Pagination cursor ("*" for first page, from previous result).',
                    required=False,
                    default="*",
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        query = inputs.get("query", "").strip()
        if not query:
            return ToolResult.create_error("query is required. Provide a search term.")

        from kaos_source.apis.govinfo.client import search
        from kaos_source.settings.govinfo import KaosSourceGovInfoSettings

        s = KaosSourceGovInfoSettings()
        try:
            result = await search(
                query,
                collection=inputs.get("collection"),
                page_size=min(inputs.get("page_size", 20), 100),
                offset_mark=inputs.get("offset_mark", "*"),
                settings=s,
            )
        except ValueError as exc:
            return ToolResult.create_error(
                f"GovInfo search failed for query '{query}': {exc}. "
                "Check that your API key is set (KAOS_SOURCE_GOVINFO_API_KEY or "
                "GOVINFO_API_KEY). Get a free key at https://api.data.gov/signup/. "
                "Alternative: use kaos-source-fr-search for Federal Register documents."
            )
        except Exception as exc:
            return ToolResult.create_error(
                f"GovInfo search failed: {exc}. "
                "Check your API key is set (KAOS_SOURCE_GOVINFO_API_KEY) "
                "and the GovInfo API is reachable."
            )

        docs = [_clean_dict(asdict(r)) for r in result.results]
        output = {
            "results": docs,
            "count": result.count,
            "returned": len(docs),
            "has_more": result.next_offset is not None,
        }

        summary = f"Found {result.count} GovInfo result(s), showing {len(docs)}"
        return ToolResult.create_success(output=output, summary=summary)


class GovInfoGetPackageTool(KaosTool):
    """Get metadata for a specific GovInfo package."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-govinfo-package",
            display_name="Get GovInfo Package",
            description=(
                "Get detailed metadata for a GovInfo package by its package ID. "
                "Use kaos-source-govinfo-search to find package IDs."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.EXTRACT,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_GOVINFO_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="package_id",
                    type="string",
                    description="GovInfo package ID (from search results).",
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        package_id = inputs.get("package_id", "").strip()
        if not package_id:
            return ToolResult.create_error(
                "package_id is required. Use kaos-source-govinfo-search to find package IDs."
            )

        from kaos_source.apis.govinfo.client import get_package
        from kaos_source.settings.govinfo import KaosSourceGovInfoSettings

        s = KaosSourceGovInfoSettings()
        try:
            pkg = await get_package(package_id, settings=s)
        except ValueError as exc:
            return ToolResult.create_error(
                f"Failed to fetch GovInfo package '{package_id}': {exc}. "
                "Verify the package ID is correct and your API key is set "
                "(KAOS_SOURCE_GOVINFO_API_KEY). "
                "Use kaos-source-govinfo-search to find valid package IDs."
            )
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch package '{package_id}': {exc}. "
                "Verify the package ID is correct. "
                "Use kaos-source-govinfo-search to find valid IDs."
            )

        output = _clean_dict(asdict(pkg))
        summary = f"{pkg.title} ({pkg.collection_code})"
        return ToolResult.create_success(output=output, summary=summary)


class GovInfoCollectionsTool(KaosTool):
    """List all GovInfo collections (BILLS, FR, CFR, etc.)."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-govinfo-collections",
            display_name="List GovInfo Collections",
            description=(
                "List all GovInfo collection codes (BILLS, FR, CFR, CREC, etc.) "
                "with package and granule counts. Use collection codes to filter searches."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_GOVINFO_ANNOTATIONS,
            input_schema=[],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        from kaos_source.apis.govinfo.client import get_collections
        from kaos_source.settings.govinfo import KaosSourceGovInfoSettings

        s = KaosSourceGovInfoSettings()
        try:
            collections = await get_collections(settings=s)
        except ValueError as exc:
            return ToolResult.create_error(
                f"Failed to list GovInfo collections: {exc}. "
                "Check that your API key is set (KAOS_SOURCE_GOVINFO_API_KEY or "
                "GOVINFO_API_KEY). Get a free key at https://api.data.gov/signup/. "
                "Alternative: use kaos-source-govinfo-search to search across all collections."
            )
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch collections: {exc}. "
                "Check your API key (KAOS_SOURCE_GOVINFO_API_KEY)."
            )

        items = [
            {
                "code": c.collection_code,
                "name": c.collection_name,
                "packages": c.package_count,
                "granules": c.granule_count,
            }
            for c in collections
        ]

        output = {"collections": items, "count": len(items)}
        return ToolResult.create_success(
            output=output,
            summary=f"{len(items)} GovInfo collection(s)",
        )


def register_govinfo_tools(runtime: KaosRuntime) -> int:
    """Register all GovInfo tools with the runtime. Returns count."""
    tools: list[KaosTool] = [
        GovInfoSearchTool(),
        GovInfoGetPackageTool(),
        GovInfoCollectionsTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)


__all__ = [
    "GovInfoCollectionsTool",
    "GovInfoGetPackageTool",
    "GovInfoSearchTool",
    "register_govinfo_tools",
]
