"""Tests for EDGAR MCP tools (mocked — no network)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from kaos_core import KaosRuntime

from kaos_source.connectors.edgar import EdgarCompany, EdgarFiling, EdgarSearchResponse
from kaos_source.tools_edgar import (
    EdgarCompanyTool,
    EdgarLookupTool,
    EdgarSearchTool,
    register_edgar_tools,
)

_SAMPLE_FILING = EdgarFiling(
    accession_number="0000320193-24-000123",
    form="10-K",
    filing_date="2024-10-31",
    company_name="Apple Inc. (AAPL)",
    cik="320193",
    primary_document="aapl-20240928.htm",
    file_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
)

_SAMPLE_SEARCH = EdgarSearchResponse(
    filings=[_SAMPLE_FILING],
    total=1,
    offset=0,
    has_more=False,
)

_SAMPLE_COMPANY = EdgarCompany(
    cik="0000320193",
    name="Apple Inc.",
    ticker="AAPL",
    exchange="Nasdaq",
    sic="3571",
    sic_description="Electronic Computers",
    filings=[_SAMPLE_FILING],
    total_filings=1,
)


class TestRegistration:
    def test_register_tools(self, runtime: KaosRuntime) -> None:
        count = register_edgar_tools(runtime)
        assert count == 3

    def test_tool_names(self, runtime: KaosRuntime) -> None:
        register_edgar_tools(runtime)
        names = {t.metadata.name for t in runtime.tools.list_tool_objects()}
        assert {
            "kaos-source-edgar-search",
            "kaos-source-edgar-company",
            "kaos-source-edgar-lookup",
        }.issubset(names)


class TestAnnotations:
    @pytest.mark.parametrize("tool_cls", [EdgarSearchTool, EdgarCompanyTool, EdgarLookupTool])
    def test_all_annotated(self, tool_cls: type) -> None:
        ann = tool_cls().metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.openWorldHint is True


class TestEdgarSearch:
    @patch("kaos_source.apis.edgar.client.search_filings", new_callable=AsyncMock)
    async def test_search_by_query(self, mock_search: AsyncMock) -> None:
        mock_search.return_value = _SAMPLE_SEARCH
        tool = EdgarSearchTool()
        result = await tool.execute({"query": "climate risk", "forms": "10-K"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["total"] == 1

    async def test_missing_query_and_cik(self) -> None:
        tool = EdgarSearchTool()
        result = await tool.execute({})
        assert result.isError
        assert "kaos-source-edgar-lookup" in (result.text or "")


class TestEdgarCompany:
    @patch("kaos_source.apis.edgar.client.get_company", new_callable=AsyncMock)
    async def test_get_company(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_COMPANY
        tool = EdgarCompanyTool()
        result = await tool.execute({"cik": "320193"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["name"] == "Apple Inc."
        assert result.structuredContent["ticker"] == "AAPL"

    async def test_missing_cik(self) -> None:
        tool = EdgarCompanyTool()
        result = await tool.execute({"cik": ""})
        assert result.isError


class TestEdgarLookup:
    @patch("kaos_source.apis.edgar.client.lookup_ticker", new_callable=AsyncMock)
    async def test_lookup_found(self, mock_lookup: AsyncMock) -> None:
        mock_lookup.return_value = {"cik": "0000320193", "ticker": "AAPL", "title": "Apple Inc."}
        tool = EdgarLookupTool()
        result = await tool.execute({"ticker": "AAPL"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["cik"] == "0000320193"

    @patch("kaos_source.apis.edgar.client.lookup_ticker", new_callable=AsyncMock)
    async def test_lookup_not_found(self, mock_lookup: AsyncMock) -> None:
        mock_lookup.return_value = None
        tool = EdgarLookupTool()
        result = await tool.execute({"ticker": "XYZABC"})
        assert result.isError
        assert "not found" in (result.text or "").lower()

    async def test_missing_ticker(self) -> None:
        tool = EdgarLookupTool()
        result = await tool.execute({"ticker": ""})
        assert result.isError
