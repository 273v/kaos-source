"""MCP tools for SEC EDGAR filing search and retrieval.

No API key required — uses public SEC APIs with mandatory User-Agent.
Configure via KAOS_SOURCE_EDGAR_USER_AGENT env var.
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

_EDGAR_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _clean_dict(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v != "" and v != [] and v != {} and v != 0}


class EdgarSearchTool(KaosTool):
    """Search SEC EDGAR filings by keyword, company, or form type."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-edgar-search",
            display_name="Search EDGAR Filings",
            description=(
                "Search SEC EDGAR for filings (10-K, 10-Q, 8-K, S-1, etc.) "
                "by full-text query, company CIK, form type, and date range. "
                "No API key required. Returns filing metadata with document URLs."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_EDGAR_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="query",
                    type="string",
                    description=(
                        'Full-text search query. Supports: exact phrases ("climate risk"), '
                        "AND/OR/NOT operators. Optional if cik is provided."
                    ),
                    required=False,
                ),
                ParameterSchema(
                    name="forms",
                    type="string",
                    description=(
                        "Comma-separated form types: 10-K, 10-Q, 8-K, S-1, DEF 14A, "
                        "4, SC 13D, 13F-HR, 20-F."
                    ),
                    required=False,
                ),
                ParameterSchema(
                    name="cik",
                    type="string",
                    description=(
                        "Company CIK number. Use kaos-source-edgar-lookup to find "
                        "CIK from ticker symbol."
                    ),
                    required=False,
                ),
                ParameterSchema(
                    name="date_from",
                    type="string",
                    description="Filing date start (YYYY-MM-DD).",
                    required=False,
                ),
                ParameterSchema(
                    name="date_to",
                    type="string",
                    description="Filing date end (YYYY-MM-DD).",
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
                    name="offset",
                    type="integer",
                    description="Pagination offset (default 0).",
                    required=False,
                    default=0,
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        query = inputs.get("query", "")
        cik = inputs.get("cik")

        if not query and not cik:
            return ToolResult.create_error(
                "Either 'query' or 'cik' is required. "
                "Use kaos-source-edgar-lookup to find a company's CIK from its ticker."
            )

        from kaos_source.connectors.edgar import KaosSourceEdgarSettings, search_filings

        s = KaosSourceEdgarSettings()
        try:
            result = await search_filings(
                query=query,
                forms=inputs.get("forms"),
                cik=cik,
                date_from=inputs.get("date_from"),
                date_to=inputs.get("date_to"),
                size=min(inputs.get("per_page", 20), 100),
                offset=inputs.get("offset", 0),
                settings=s,
            )
        except Exception as exc:
            return ToolResult.create_error(
                f"EDGAR search failed: {exc}. "
                "Check the SEC EFTS API is reachable. "
                "The SEC requires 10 req/s max — try again if rate limited."
            )

        docs = [_clean_dict(asdict(f)) for f in result.filings]
        output = {
            "results": docs,
            "total": result.total,
            "returned": len(docs),
            "has_more": result.has_more,
            "offset": result.offset,
        }

        summary = f"Found {result.total} EDGAR filing(s), showing {len(docs)}"
        return ToolResult.create_success(output=output, summary=summary)


class EdgarCompanyTool(KaosTool):
    """Get company info and recent filings from EDGAR."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-edgar-company",
            display_name="Get EDGAR Company",
            description=(
                "Get company information and recent filing history from SEC EDGAR. "
                "Returns company name, ticker, SIC code, and filings list. "
                "Use kaos-source-edgar-lookup to find CIK from ticker."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.EXTRACT,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_EDGAR_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="cik",
                    type="string",
                    description="Company CIK number (e.g. '320193' for Apple).",
                ),
                ParameterSchema(
                    name="form_filter",
                    type="string",
                    description="Optional form type filter (e.g. '10-K' for annual reports only).",
                    required=False,
                ),
                ParameterSchema(
                    name="max_filings",
                    type="integer",
                    description="Max filings to return (default 20).",
                    required=False,
                    default=20,
                    constraints={"minimum": 1, "maximum": 100},
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        cik = inputs.get("cik", "").strip()
        if not cik:
            return ToolResult.create_error(
                "cik is required. "
                "Use kaos-source-edgar-lookup to find a company's CIK from its ticker."
            )

        from kaos_source.connectors.edgar import KaosSourceEdgarSettings, get_company

        s = KaosSourceEdgarSettings()
        try:
            company = await get_company(
                cik,
                max_filings=inputs.get("max_filings", 20),
                form_filter=inputs.get("form_filter"),
                settings=s,
            )
        except Exception as exc:
            return ToolResult.create_error(
                f"Failed to fetch company CIK {cik}: {exc}. "
                "Verify the CIK is correct. "
                "Use kaos-source-edgar-lookup to find CIK from ticker."
            )

        filings_data = [_clean_dict(asdict(f)) for f in company.filings]
        output = {
            "cik": company.cik,
            "name": company.name,
            "ticker": company.ticker,
            "exchange": company.exchange,
            "sic": company.sic,
            "sic_description": company.sic_description,
            "category": company.category,
            "filings": filings_data,
            "filing_count": len(filings_data),
        }

        ticker_str = f" ({company.ticker})" if company.ticker else ""
        summary = f"{company.name}{ticker_str} — {len(filings_data)} filing(s)"
        return ToolResult.create_success(output=output, summary=summary)


class EdgarLookupTool(KaosTool):
    """Look up a company's CIK from its ticker symbol."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="kaos-source-edgar-lookup",
            display_name="Lookup EDGAR Ticker",
            description=(
                "Look up a company's SEC CIK number from its stock ticker symbol. "
                "Use the returned CIK with kaos-source-edgar-company or "
                "kaos-source-edgar-search."
            ),
            category=ToolCategory.DATA,
            capability=ToolCapability.QUERY,
            module_name=_MODULE,
            version=_VERSION,
            annotations=_EDGAR_ANNOTATIONS,
            input_schema=[
                ParameterSchema(
                    name="ticker",
                    type="string",
                    description="Stock ticker symbol (e.g. 'AAPL', 'MSFT', 'GOOGL').",
                ),
            ],
        )

    async def execute(
        self, inputs: dict[str, Any], context: KaosContext | None = None
    ) -> ToolResult:
        ticker = inputs.get("ticker", "").strip()
        if not ticker:
            return ToolResult.create_error(
                "ticker is required. Provide a stock ticker symbol (e.g. 'AAPL')."
            )

        from kaos_source.connectors.edgar import KaosSourceEdgarSettings, lookup_ticker

        s = KaosSourceEdgarSettings()
        try:
            result = await lookup_ticker(ticker, settings=s)
        except Exception as exc:
            return ToolResult.create_error(
                f"Ticker lookup failed: {exc}. The SEC ticker file may be temporarily unavailable."
            )

        if result is None:
            return ToolResult.create_error(
                f"Ticker '{ticker.upper()}' not found in SEC EDGAR. "
                "Check the ticker is correct. Only publicly listed companies "
                "with SEC filings are included."
            )

        output = result
        summary = f"{result['title']} ({result['ticker']}) — CIK {result['cik']}"
        return ToolResult.create_success(output=output, summary=summary)


def register_edgar_tools(runtime: KaosRuntime) -> int:
    """Register all EDGAR tools with the runtime. Returns count."""
    tools: list[KaosTool] = [
        EdgarSearchTool(),
        EdgarCompanyTool(),
        EdgarLookupTool(),
    ]
    for tool in tools:
        runtime.tools.register_tool(tool)
    return len(tools)
