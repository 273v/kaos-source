"""Tests for eCFR MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from kaos_core import KaosRuntime

from kaos_source.apis.ecfr.client import get_latest_date
from kaos_source.apis.ecfr.models import ECFRStructureNode, ECFRTitle
from kaos_source.tools_ecfr import (
    ECFRContentTool,
    ECFRListTitlesTool,
    ECFRSearchTool,
    ECFRStructureTool,
    register_ecfr_tools,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_TITLES = [
    ECFRTitle(number=1, name="General Provisions", latest_amended_on="2024-01-15"),
    ECFRTitle(number=40, name="Protection of Environment", latest_amended_on="2024-06-01"),
    ECFRTitle(number=50, name="Wildlife and Fisheries", reserved=True),
]

_SAMPLE_STRUCTURE = ECFRStructureNode(
    identifier="40",
    type="title",
    label="Title 40 - Protection of Environment",
    children=[
        ECFRStructureNode(
            identifier="82",
            type="part",
            label="Part 82 - Protection of Stratospheric Ozone",
            children=[
                ECFRStructureNode(
                    identifier="82.1",
                    type="section",
                    label="§ 82.1 Purpose and scope.",
                    label_description="Purpose and scope of ozone protection.",
                ),
                ECFRStructureNode(
                    identifier="82.2",
                    type="section",
                    label="§ 82.2 Definitions.",
                    label_description="Definitions for ozone protection.",
                ),
            ],
        ),
        ECFRStructureNode(
            identifier="60",
            type="part",
            label="Part 60 - Standards of Performance for New Stationary Sources",
            children=[],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_tools(self, runtime: KaosRuntime) -> None:
        count = register_ecfr_tools(runtime)
        assert count == 4

    def test_tool_names(self, runtime: KaosRuntime) -> None:
        register_ecfr_tools(runtime)
        names = {t.metadata.name for t in runtime.tools.list_tool_objects()}
        expected = {
            "kaos-source-ecfr-titles",
            "kaos-source-ecfr-structure",
            "kaos-source-ecfr-content",
            "kaos-source-ecfr-search-structure",
        }
        assert expected.issubset(names)


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


class TestAnnotations:
    @pytest.mark.parametrize(
        "tool_cls",
        [ECFRListTitlesTool, ECFRStructureTool, ECFRContentTool, ECFRSearchTool],
    )
    def test_all_tools_annotated(self, tool_cls: type) -> None:
        tool = tool_cls()
        ann = tool.metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.openWorldHint is True


# ---------------------------------------------------------------------------
# ECFRListTitlesTool
# ---------------------------------------------------------------------------


class TestListTitles:
    @patch("kaos_source.apis.ecfr.client.get_titles", new_callable=AsyncMock)
    async def test_list_titles(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_TITLES
        tool = ECFRListTitlesTool()
        result = await tool.execute({})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] == 3
        numbers = [t["number"] for t in result.structuredContent["titles"]]
        assert 40 in numbers

    @patch("kaos_source.apis.ecfr.client.get_titles", new_callable=AsyncMock)
    async def test_titles_error(self, mock_get: AsyncMock) -> None:
        mock_get.side_effect = RuntimeError("API down")
        tool = ECFRListTitlesTool()
        result = await tool.execute({})
        assert result.isError
        assert "unavailable" in (result.text or "").lower()


class TestLatestDateFallback:
    @patch("kaos_source.apis.ecfr.client.get_titles", new_callable=AsyncMock)
    async def test_returns_none_when_titles_lookup_fails(self, mock_get: AsyncMock) -> None:
        mock_get.side_effect = RuntimeError("API down")

        value = await get_latest_date(40)

        assert value is None

    @patch("kaos_source.apis.ecfr.client.get_titles", new_callable=AsyncMock)
    async def test_returns_none_when_title_has_no_latest_issue_date(
        self, mock_get: AsyncMock
    ) -> None:
        mock_get.return_value = [ECFRTitle(number=40, name="Protection", latest_issue_date=None)]

        value = await get_latest_date(40)

        assert value is None

    @patch("kaos_source.apis.ecfr.client.get_titles", new_callable=AsyncMock)
    async def test_returns_date_when_available(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = [
            ECFRTitle(number=40, name="Protection", latest_issue_date="2026-03-15")
        ]

        value = await get_latest_date(40)

        assert value == "2026-03-15"


# ---------------------------------------------------------------------------
# ECFRStructureTool
# ---------------------------------------------------------------------------


class TestStructure:
    @patch("kaos_source.apis.ecfr.client.get_title_structure", new_callable=AsyncMock)
    async def test_get_structure(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_STRUCTURE
        tool = ECFRStructureTool()
        result = await tool.execute({"title": 40, "date": "2024-06-01"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["part_count"] == 2
        assert result.structuredContent["section_count"] == 2

    @patch("kaos_source.apis.ecfr.client.get_title_structure", new_callable=AsyncMock)
    async def test_structure_with_depth(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_STRUCTURE
        tool = ECFRStructureTool()
        result = await tool.execute({"title": 40, "depth": 1})
        assert not result.isError
        assert result.structuredContent is not None
        # At depth 1, children should show child_count instead of expanding
        tree = result.structuredContent["structure"]
        part = tree["children"][0]
        assert "child_count" in part or "children" not in part

    @patch("kaos_source.apis.ecfr.client.get_title_structure", new_callable=AsyncMock)
    async def test_structure_error(self, mock_get: AsyncMock) -> None:
        mock_get.side_effect = RuntimeError("Not found")
        tool = ECFRStructureTool()
        result = await tool.execute({"title": 99, "date": "2026-01-01"})
        assert result.isError
        assert "kaos-source-ecfr-titles" in (result.text or "")


# ---------------------------------------------------------------------------
# ECFRContentTool
# ---------------------------------------------------------------------------


class TestContent:
    @patch("kaos_source.apis.ecfr.client.get_section_content", new_callable=AsyncMock)
    async def test_get_section_content(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = "<div>Section content here</div>"
        tool = ECFRContentTool()
        result = await tool.execute({"title": 40, "section": "82.1"})
        assert not result.isError
        assert result.structuredContent is not None
        assert "Section content here" in result.structuredContent["content"]

    @patch("kaos_source.apis.ecfr.client.get_section_content", new_callable=AsyncMock)
    async def test_get_part_content(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = "<div>Part 82 full text</div>"
        tool = ECFRContentTool()
        result = await tool.execute({"title": 40, "part": "82"})
        assert not result.isError

    async def test_missing_section_and_part(self) -> None:
        tool = ECFRContentTool()
        result = await tool.execute({"title": 40})
        assert result.isError
        assert "kaos-source-ecfr-structure" in (result.text or "")

    @patch("kaos_source.apis.ecfr.client.get_section_content", new_callable=AsyncMock)
    async def test_content_xml_format(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = "<CFR><section>XML content</section></CFR>"
        tool = ECFRContentTool()
        result = await tool.execute({"title": 40, "section": "82.1", "format": "xml"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["format"] == "xml"


# ---------------------------------------------------------------------------
# ECFRSearchTool
# ---------------------------------------------------------------------------


class TestSearch:
    @patch("kaos_source.apis.ecfr.client.get_title_structure", new_callable=AsyncMock)
    async def test_search_sections(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_STRUCTURE
        tool = ECFRSearchTool()
        result = await tool.execute({"title": 40, "query": "ozone"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] >= 1
        # Should find Part 82 (ozone protection)
        labels = [r["label"] for r in result.structuredContent["results"]]
        assert any("ozone" in label.lower() for label in labels)

    @patch("kaos_source.apis.ecfr.client.get_title_structure", new_callable=AsyncMock)
    async def test_search_no_results(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = _SAMPLE_STRUCTURE
        tool = ECFRSearchTool()
        result = await tool.execute({"title": 40, "query": "nonexistent_term_xyz"})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] == 0

    async def test_search_empty_query(self) -> None:
        tool = ECFRSearchTool()
        result = await tool.execute({"title": 40, "query": ""})
        assert result.isError


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------


class TestErrorMessages:
    async def test_content_missing_ref_suggests_structure(self) -> None:
        tool = ECFRContentTool()
        result = await tool.execute({"title": 40})
        assert result.isError
        assert "kaos-source-ecfr-structure" in (result.text or "")

    @patch("kaos_source.apis.ecfr.client.get_title_structure", new_callable=AsyncMock)
    async def test_structure_error_suggests_titles(self, mock_get: AsyncMock) -> None:
        mock_get.side_effect = RuntimeError("Not found")
        tool = ECFRStructureTool()
        result = await tool.execute({"title": 99, "date": "2026-01-01"})
        assert result.isError
        assert "kaos-source-ecfr-titles" in (result.text or "")
