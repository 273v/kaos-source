"""Integration tests for EDGAR API — hits real SEC API.

Run with: pytest tests/integration/test_edgar.py -v
Skip in CI: pytest -m "not integration"
"""

from __future__ import annotations

import pytest

from kaos_source.connectors.edgar import get_company, lookup_ticker, search_filings
from kaos_source.tools_edgar import EdgarCompanyTool, EdgarLookupTool, EdgarSearchTool

pytestmark = pytest.mark.integration


class TestEdgarAPILive:
    async def test_search_10k(self) -> None:
        result = await search_filings(query="annual report", forms="10-K", size=5)
        assert result.total > 0
        assert len(result.filings) > 0
        assert result.filings[0].form == "10-K"

    async def test_search_by_cik(self) -> None:
        # Apple's CIK
        result = await search_filings(cik="320193", forms="10-K", size=3)
        assert result.total > 0
        assert result.filings[0].cik == "320193"

    async def test_get_company(self) -> None:
        company = await get_company("320193", max_filings=5)
        assert company.name == "Apple Inc."
        assert company.ticker == "AAPL"
        assert len(company.filings) > 0

    async def test_get_company_filtered(self) -> None:
        company = await get_company("320193", max_filings=100, form_filter="10-K")
        for f in company.filings:
            assert f.form == "10-K"

    async def test_lookup_ticker(self) -> None:
        result = await lookup_ticker("AAPL")
        assert result is not None
        assert result["ticker"] == "AAPL"
        assert "320193" in result["cik"]

    async def test_lookup_ticker_not_found(self) -> None:
        result = await lookup_ticker("XYZNONEXISTENT123")
        assert result is None


class TestEdgarToolsLive:
    async def test_search_tool(self) -> None:
        tool = EdgarSearchTool()
        result = await tool.execute({"query": "climate risk", "forms": "10-K", "per_page": 5})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["total"] > 0

    async def test_company_tool(self) -> None:
        tool = EdgarCompanyTool()
        result = await tool.execute({"cik": "320193", "max_filings": 5})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["name"] == "Apple Inc."

    async def test_lookup_tool(self) -> None:
        tool = EdgarLookupTool()
        result = await tool.execute({"ticker": "MSFT"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["ticker"] == "MSFT"
