"""Integration tests for eCFR API — hits real API.

Run with: pytest tests/integration/test_ecfr.py -v
Skip in CI: pytest -m "not integration"
"""

from __future__ import annotations

import pytest

from kaos_source.apis.ecfr.tools import (
    ECFRContentTool,
    ECFRListTitlesTool,
    ECFRSearchTool,
    ECFRStructureTool,
)
from kaos_source.connectors.ecfr import (
    get_agencies,
    get_section_content,
    get_title_structure,
    get_titles,
)

pytestmark = pytest.mark.integration


class TestECFRAPILive:
    async def test_get_titles(self) -> None:
        titles = await get_titles()
        assert len(titles) >= 40
        numbers = {t.number for t in titles}
        assert 40 in numbers  # Protection of Environment

    async def test_get_agencies(self) -> None:
        agencies = await get_agencies()
        assert len(agencies) > 50
        names = {a.name for a in agencies}
        assert "Environmental Protection Agency" in names

    async def test_get_title_structure(self) -> None:
        root = await get_title_structure(1, "2024-01-01")
        assert root.type == "title"
        assert root.identifier == "1"
        parts = root.find_parts()
        assert len(parts) > 0

    async def test_get_section_html(self) -> None:
        content = await get_section_content(1, "2024-01-01", part="1")
        assert len(content) > 100
        assert "<" in content  # HTML tags


class TestECFRToolsLive:
    async def test_titles_tool(self) -> None:
        tool = ECFRListTitlesTool()
        result = await tool.execute({})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] >= 40

    async def test_structure_tool(self) -> None:
        tool = ECFRStructureTool()
        result = await tool.execute({"title": 1, "date": "2024-01-01", "depth": 2})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["part_count"] > 0

    async def test_content_tool(self) -> None:
        tool = ECFRContentTool()
        result = await tool.execute({"title": 1, "part": "1", "date": "2024-01-01"})
        assert not result.isError
        assert result.structuredContent is not None
        assert len(result.structuredContent["content"]) > 100

    async def test_search_tool(self) -> None:
        tool = ECFRSearchTool()
        result = await tool.execute({"title": 40, "query": "ozone", "date": "2024-01-01"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] > 0
