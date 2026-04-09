"""Integration tests for Federal Register API — hits real API.

Run with: pytest tests/integration/test_federal_register.py -v
Skip in CI: pytest -m "not integration"
"""

from __future__ import annotations

import pytest

from kaos_source.connectors.federal_register import (
    get_agencies,
    get_document,
    search_documents,
)
from kaos_source.tools_federal_register import (
    FRAgenciesTool,
    FRGetDocumentTool,
    FRSearchTool,
)

pytestmark = pytest.mark.integration


class TestFRAPILive:
    """Test raw API functions against the live Federal Register API."""

    async def test_search_recent_rules(self) -> None:
        result = await search_documents(
            doc_type="RULE",
            per_page=5,
            order="newest",
        )
        assert result.count > 0
        assert len(result.documents) > 0
        doc = result.documents[0]
        assert doc.document_number
        assert doc.title
        assert doc.type == "Rule"
        assert doc.publication_date

    async def test_search_by_term(self) -> None:
        result = await search_documents(
            term="securities exchange commission",
            per_page=5,
        )
        assert result.count > 0
        assert len(result.documents) > 0

    async def test_search_by_agency(self) -> None:
        result = await search_documents(
            agencies="environmental-protection-agency",
            per_page=5,
            order="newest",
        )
        assert result.count > 0

    async def test_search_by_date_range(self) -> None:
        result = await search_documents(
            date_gte="2024-01-01",
            date_lte="2024-01-31",
            per_page=5,
        )
        assert result.count > 0

    async def test_get_agencies(self) -> None:
        agencies = await get_agencies()
        assert len(agencies) > 100  # There are ~500+ agencies
        # Check a well-known agency exists
        names = {a.name for a in agencies}
        assert "Environmental Protection Agency" in names

    async def test_get_specific_document(self) -> None:
        # Search for a recent rule to get a valid document number
        search = await search_documents(doc_type="RULE", per_page=1, order="newest")
        assert len(search.documents) > 0
        doc_num = search.documents[0].document_number

        # Fetch the full document
        doc = await get_document(doc_num)
        assert doc.document_number == doc_num
        assert doc.title
        assert doc.publication_date


class TestFRToolsLive:
    """Test MCP tools against the live Federal Register API."""

    async def test_search_tool(self) -> None:
        tool = FRSearchTool()
        result = await tool.execute(
            {
                "term": "climate change",
                "doc_type": "RULE",
                "per_page": 5,
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] > 0

    async def test_get_document_tool(self) -> None:
        # First search for a valid document number
        tool = FRSearchTool()
        search = await tool.execute({"per_page": 1})
        assert not search.isError
        assert search.structuredContent is not None
        doc_num = search.structuredContent["results"][0]["document_number"]

        # Then fetch it
        get_tool = FRGetDocumentTool()
        result = await get_tool.execute({"document_number": doc_num})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["document_number"] == doc_num

    async def test_agencies_tool(self) -> None:
        tool = FRAgenciesTool()
        result = await tool.execute({})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] > 100

    async def test_agencies_filter(self) -> None:
        tool = FRAgenciesTool()
        result = await tool.execute({"search": "securities"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] >= 1
        slugs = [a["slug"] for a in result.structuredContent["agencies"]]
        assert "securities-and-exchange-commission" in slugs
