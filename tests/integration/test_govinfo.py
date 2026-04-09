"""Integration tests for GovInfo API — requires GOVINFO_API_KEY.

Run with: GOVINFO_API_KEY=xxx pytest tests/integration/test_govinfo.py -v
Skip in CI: pytest -m "not integration"
"""

from __future__ import annotations

import os

import pytest

from kaos_source.connectors.govinfo import get_collections, get_package, search
from kaos_source.tools_govinfo import (
    GovInfoCollectionsTool,
    GovInfoGetPackageTool,
    GovInfoSearchTool,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GOVINFO_API_KEY"),
        reason="GOVINFO_API_KEY not set",
    ),
]


class TestGovInfoAPILive:
    async def test_get_collections(self) -> None:
        cols = await get_collections()
        assert len(cols) >= 30
        codes = {c.collection_code for c in cols}
        assert "FR" in codes
        assert "BILLS" in codes

    async def test_search(self) -> None:
        result = await search("securities exchange commission", page_size=5)
        assert result.count > 0
        assert len(result.results) > 0
        assert result.results[0].title

    async def test_search_with_collection(self) -> None:
        result = await search("climate", collection="FR", page_size=5)
        assert result.count > 0
        # Collection param influences ranking but doesn't strictly filter
        assert len(result.results) > 0

    async def test_get_package(self) -> None:
        # Search for a package first
        result = await search("budget", page_size=1)
        assert len(result.results) > 0
        pkg_id = result.results[0].package_id

        pkg = await get_package(pkg_id)
        assert pkg.package_id == pkg_id
        assert pkg.title


class TestGovInfoToolsLive:
    async def test_search_tool(self) -> None:
        tool = GovInfoSearchTool()
        result = await tool.execute({"query": "environmental protection", "page_size": 5})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] > 0

    async def test_collections_tool(self) -> None:
        tool = GovInfoCollectionsTool()
        result = await tool.execute({})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] >= 30

    async def test_package_tool(self) -> None:
        # Search first
        search_tool = GovInfoSearchTool()
        search_result = await search_tool.execute({"query": "budget", "page_size": 1})
        assert not search_result.isError
        assert search_result.structuredContent is not None
        pkg_id = search_result.structuredContent["results"][0]["package_id"]

        tool = GovInfoGetPackageTool()
        result = await tool.execute({"package_id": pkg_id})
        assert not result.isError
        assert result.structuredContent is not None
