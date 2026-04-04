"""Tests for Federal Register MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from kaos_core import KaosRuntime

from kaos_source.connectors.federal_register import FRAgency, FRDocument, FRSearchResult
from kaos_source.tools_federal_register import (
    FRAgenciesTool,
    FRGetContentTool,
    FRGetDocumentTool,
    FRSearchTool,
    register_federal_register_tools,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_DOC = FRDocument(
    document_number="2024-12345",
    title="Regulation of Widget Safety Standards",
    type="RULE",
    publication_date="2024-06-15",
    citation="89 FR 12345",
    abstract="This rule establishes safety standards for widgets.",
    agencies=[{"name": "Consumer Product Safety Commission", "slug": "cpsc"}],
    agency_names=["Consumer Product Safety Commission"],
    start_page=12345,
    end_page=12360,
    page_length=15,
    html_url="https://www.federalregister.gov/documents/2024/06/15/2024-12345/test",
    pdf_url="https://www.govinfo.gov/content/pkg/FR-2024-06-15/pdf/2024-12345.pdf",
    raw_text_url="https://www.federalregister.gov/documents/full_text/text/2024-12345",
)

_SAMPLE_SEARCH = FRSearchResult(
    documents=[_SAMPLE_DOC],
    count=1,
    total_pages=1,
    next_page_url=None,
)

_SAMPLE_AGENCIES = [
    FRAgency(
        id=1,
        name="Environmental Protection Agency",
        short_name="EPA",
        slug="environmental-protection-agency",
    ),
    FRAgency(
        id=2,
        name="Securities and Exchange Commission",
        short_name="SEC",
        slug="securities-and-exchange-commission",
    ),
    FRAgency(id=3, name="Department of Justice", short_name="DOJ", slug="department-of-justice"),
]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_tools(self, runtime: KaosRuntime) -> None:
        count = register_federal_register_tools(runtime)
        assert count == 4

    def test_tool_names(self, runtime: KaosRuntime) -> None:
        register_federal_register_tools(runtime)
        names = {t.metadata.name for t in runtime.tools.list_tool_objects()}
        expected = {
            "kaos-source-fr-search",
            "kaos-source-fr-get-document",
            "kaos-source-fr-get-content",
            "kaos-source-fr-agencies",
        }
        assert expected.issubset(names)


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


class TestAnnotations:
    @pytest.mark.parametrize(
        "tool_cls", [FRSearchTool, FRGetDocumentTool, FRGetContentTool, FRAgenciesTool]
    )
    def test_all_tools_have_annotations(self, tool_cls: type) -> None:
        tool = tool_cls()
        ann = tool.metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.openWorldHint is True
        assert ann.destructiveHint is False
        assert ann.idempotentHint is True


# ---------------------------------------------------------------------------
# FRSearchTool
# ---------------------------------------------------------------------------


class TestFRSearch:
    @patch("kaos_source.connectors.federal_register.search_documents", new_callable=AsyncMock)
    async def test_basic_search(self, mock_search: AsyncMock) -> None:
        mock_search.return_value = _SAMPLE_SEARCH
        tool = FRSearchTool()
        result = await tool.execute({"term": "widget safety"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] == 1
        assert len(result.structuredContent["results"]) == 1
        assert result.structuredContent["results"][0]["document_number"] == "2024-12345"

    @patch("kaos_source.connectors.federal_register.search_documents", new_callable=AsyncMock)
    async def test_search_with_filters(self, mock_search: AsyncMock) -> None:
        mock_search.return_value = _SAMPLE_SEARCH
        tool = FRSearchTool()
        result = await tool.execute(
            {
                "term": "safety",
                "doc_type": "RULE",
                "agency": "cpsc",
                "date_from": "2024-01-01",
                "date_to": "2024-12-31",
            }
        )
        assert not result.isError
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args[1]
        assert call_kwargs["doc_type"] == "RULE"
        assert call_kwargs["agencies"] == "cpsc"

    @patch("kaos_source.connectors.federal_register.search_documents", new_callable=AsyncMock)
    async def test_search_pagination(self, mock_search: AsyncMock) -> None:
        result_with_more = FRSearchResult(
            documents=[_SAMPLE_DOC],
            count=100,
            total_pages=5,
            next_page_url="https://example.com/next",
        )
        mock_search.return_value = result_with_more
        tool = FRSearchTool()
        result = await tool.execute({"term": "test", "per_page": 20, "page": 1})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["has_more"] is True
        assert result.structuredContent["count"] == 100

    @patch("kaos_source.connectors.federal_register.search_documents", new_callable=AsyncMock)
    async def test_search_error(self, mock_search: AsyncMock) -> None:
        mock_search.side_effect = RuntimeError("Connection timeout")
        tool = FRSearchTool()
        result = await tool.execute({"term": "test"})
        assert result.isError
        assert "Connection timeout" in (result.text or "")

    @patch("kaos_source.connectors.federal_register.search_documents", new_callable=AsyncMock)
    async def test_empty_search(self, mock_search: AsyncMock) -> None:
        mock_search.return_value = FRSearchResult(documents=[], count=0, total_pages=0)
        tool = FRSearchTool()
        result = await tool.execute({})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] == 0


# ---------------------------------------------------------------------------
# FRGetDocumentTool
# ---------------------------------------------------------------------------


class TestFRGetDocument:
    @patch("kaos_source.connectors.federal_register.get_document", new_callable=AsyncMock)
    async def test_get_document(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_DOC
        tool = FRGetDocumentTool()
        result = await tool.execute({"document_number": "2024-12345"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["title"] == "Regulation of Widget Safety Standards"

    async def test_missing_document_number(self) -> None:
        tool = FRGetDocumentTool()
        result = await tool.execute({"document_number": ""})
        assert result.isError
        assert "kaos-source-fr-search" in (result.text or "")

    @patch("kaos_source.connectors.federal_register.get_document", new_callable=AsyncMock)
    async def test_document_not_found(self, mock_get: AsyncMock) -> None:
        mock_get.side_effect = RuntimeError("404 Not Found")
        tool = FRGetDocumentTool()
        result = await tool.execute({"document_number": "0000-00000"})
        assert result.isError
        assert "kaos-source-fr-search" in (result.text or "")


# ---------------------------------------------------------------------------
# FRGetContentTool
# ---------------------------------------------------------------------------


class TestFRGetContent:
    @patch("kaos_source.connectors.federal_register.fetch_document_content", new_callable=AsyncMock)
    @patch("kaos_source.connectors.federal_register.get_document", new_callable=AsyncMock)
    async def test_get_text_content(self, mock_get: AsyncMock, mock_fetch: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_DOC
        mock_fetch.return_value = "This is the full text of the regulation..."
        tool = FRGetContentTool()
        result = await tool.execute({"document_number": "2024-12345"})
        assert not result.isError
        assert result.structuredContent is not None
        assert "This is the full text" in result.structuredContent["content"]

    @patch("kaos_source.connectors.federal_register.fetch_document_content", new_callable=AsyncMock)
    @patch("kaos_source.connectors.federal_register.get_document", new_callable=AsyncMock)
    async def test_get_html_content(self, mock_get: AsyncMock, mock_fetch: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_DOC
        mock_fetch.return_value = "<html><body>Regulation text</body></html>"
        tool = FRGetContentTool()
        result = await tool.execute({"document_number": "2024-12345", "format": "html"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["format"] == "html"

    async def test_missing_document_number(self) -> None:
        tool = FRGetContentTool()
        result = await tool.execute({"document_number": ""})
        assert result.isError

    @patch("kaos_source.connectors.federal_register.get_document", new_callable=AsyncMock)
    async def test_document_not_found(self, mock_get: AsyncMock) -> None:
        mock_get.side_effect = RuntimeError("404")
        tool = FRGetContentTool()
        result = await tool.execute({"document_number": "bad-num"})
        assert result.isError


# ---------------------------------------------------------------------------
# FRAgenciesTool
# ---------------------------------------------------------------------------


class TestFRAgencies:
    @patch("kaos_source.connectors.federal_register.get_agencies", new_callable=AsyncMock)
    async def test_list_agencies(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_AGENCIES
        tool = FRAgenciesTool()
        result = await tool.execute({})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] == 3

    @patch("kaos_source.connectors.federal_register.get_agencies", new_callable=AsyncMock)
    async def test_filter_agencies(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_AGENCIES
        tool = FRAgenciesTool()
        result = await tool.execute({"search": "environmental"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] == 1
        assert result.structuredContent["agencies"][0]["slug"] == "environmental-protection-agency"

    @patch("kaos_source.connectors.federal_register.get_agencies", new_callable=AsyncMock)
    async def test_agencies_error(self, mock_get: AsyncMock) -> None:
        mock_get.side_effect = RuntimeError("API unavailable")
        tool = FRAgenciesTool()
        result = await tool.execute({})
        assert result.isError
        assert "unavailable" in (result.text or "").lower()


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------


class TestErrorMessages:
    async def test_search_error_has_guidance(self) -> None:
        tool = FRSearchTool()
        with patch(
            "kaos_source.connectors.federal_register.search_documents",
            new_callable=AsyncMock,
            side_effect=RuntimeError("timeout"),
        ):
            result = await tool.execute({"term": "test"})
        assert result.isError
        assert "no authentication" in (result.text or "").lower()

    async def test_get_doc_error_suggests_search(self) -> None:
        tool = FRGetDocumentTool()
        result = await tool.execute({"document_number": ""})
        assert result.isError
        assert "kaos-source-fr-search" in (result.text or "")
