"""Tests for GovInfo MCP tools (mocked — no API key required)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from kaos_core import KaosRuntime

from kaos_source.apis.govinfo.tools import (
    GovInfoCollectionsTool,
    GovInfoGetPackageTool,
    GovInfoSearchTool,
    register_govinfo_tools,
)
from kaos_source.connectors.govinfo import (
    GovInfoCollection,
    GovInfoPackage,
    GovInfoSearchResponse,
    GovInfoSearchResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_RESULT = GovInfoSearchResult(
    title="Clean Air Act Amendments",
    package_id="FR-2024-06-15-DOC-2024-12345",
    collection_code="FR",
    date_issued="2024-06-15",
)

_SAMPLE_SEARCH = GovInfoSearchResponse(
    results=[_SAMPLE_RESULT],
    count=1,
    offset=0,
)

_SAMPLE_PACKAGE = GovInfoPackage(
    package_id="FR-2024-06-15-DOC-2024-12345",
    title="Clean Air Act Amendments",
    collection_code="FR",
    date_issued="2024-06-15",
    pages=15,
)

_SAMPLE_COLLECTIONS = [
    GovInfoCollection(
        collection_code="FR",
        collection_name="Federal Register",
        package_count=1000,
        granule_count=50000,
    ),
    GovInfoCollection(
        collection_code="BILLS",
        collection_name="Congressional Bills",
        package_count=500,
    ),
]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_tools(self, runtime: KaosRuntime) -> None:
        count = register_govinfo_tools(runtime)
        assert count == 3

    def test_tool_names(self, runtime: KaosRuntime) -> None:
        register_govinfo_tools(runtime)
        names = {t.metadata.name for t in runtime.tools.list_tool_objects()}
        expected = {
            "kaos-source-govinfo-search",
            "kaos-source-govinfo-package",
            "kaos-source-govinfo-collections",
        }
        assert expected.issubset(names)


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


class TestAnnotations:
    @pytest.mark.parametrize(
        "tool_cls",
        [GovInfoSearchTool, GovInfoGetPackageTool, GovInfoCollectionsTool],
    )
    def test_all_tools_annotated(self, tool_cls: type) -> None:
        tool = tool_cls()
        ann = tool.metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.openWorldHint is True


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    @patch("kaos_source.apis.govinfo.client.search", new_callable=AsyncMock)
    async def test_basic_search(self, mock_search: AsyncMock) -> None:
        mock_search.return_value = _SAMPLE_SEARCH
        tool = GovInfoSearchTool()
        result = await tool.execute({"query": "clean air"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] == 1

    @patch("kaos_source.apis.govinfo.client.search", new_callable=AsyncMock)
    async def test_search_with_collection(self, mock_search: AsyncMock) -> None:
        mock_search.return_value = _SAMPLE_SEARCH
        tool = GovInfoSearchTool()
        result = await tool.execute({"query": "test", "collection": "FR"})
        assert not result.isError
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args
        assert call_kwargs[1]["collection"] == "FR"

    async def test_empty_query(self) -> None:
        tool = GovInfoSearchTool()
        result = await tool.execute({"query": ""})
        assert result.isError

    @patch("kaos_source.apis.govinfo.client.search", new_callable=AsyncMock)
    async def test_search_api_key_error(self, mock_search: AsyncMock) -> None:
        mock_search.side_effect = ValueError("API key not set")
        tool = GovInfoSearchTool()
        result = await tool.execute({"query": "test"})
        assert result.isError
        assert "api key" in (result.text or "").lower() or "API key" in (result.text or "")


# ---------------------------------------------------------------------------
# Get Package
# ---------------------------------------------------------------------------


class TestGetPackage:
    @patch("kaos_source.apis.govinfo.client.get_package", new_callable=AsyncMock)
    async def test_get_package(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_PACKAGE
        tool = GovInfoGetPackageTool()
        result = await tool.execute({"package_id": "FR-2024-06-15-DOC-2024-12345"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["title"] == "Clean Air Act Amendments"

    async def test_missing_package_id(self) -> None:
        tool = GovInfoGetPackageTool()
        result = await tool.execute({"package_id": ""})
        assert result.isError
        assert "kaos-source-govinfo-search" in (result.text or "")


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


class TestCollections:
    @patch("kaos_source.apis.govinfo.client.get_collections", new_callable=AsyncMock)
    async def test_list_collections(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_COLLECTIONS
        tool = GovInfoCollectionsTool()
        result = await tool.execute({})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] == 2
        codes = [c["code"] for c in result.structuredContent["collections"]]
        assert "FR" in codes

    @patch("kaos_source.apis.govinfo.client.get_collections", new_callable=AsyncMock)
    async def test_collections_api_error(self, mock_get: AsyncMock) -> None:
        mock_get.side_effect = ValueError("API key not set")
        tool = GovInfoCollectionsTool()
        result = await tool.execute({})
        assert result.isError
