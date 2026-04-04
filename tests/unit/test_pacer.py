"""Tests for PACER docket parser and MCP tools."""

from __future__ import annotations

from pathlib import Path

import pytest
from kaos_core import KaosRuntime

from kaos_source.tools_pacer import (
    PacerFilterEntriesTool,
    PacerParseDocketTool,
    register_pacer_tools,
)

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
_DOCKET_PATH = _FIXTURE_DIR / "pacer_docket1.html"


@pytest.fixture()
def docket_path() -> Path:
    if not _DOCKET_PATH.exists():
        pytest.skip("PACER fixture not available")
    return _DOCKET_PATH


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_tools(self, runtime: KaosRuntime) -> None:
        count = register_pacer_tools(runtime)
        assert count == 2

    def test_tool_names(self, runtime: KaosRuntime) -> None:
        register_pacer_tools(runtime)
        names = {t.metadata.name for t in runtime.tools.list_tool_objects()}
        assert {"kaos-source-pacer-parse", "kaos-source-pacer-filter-entries"}.issubset(names)


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


class TestAnnotations:
    @pytest.mark.parametrize("tool_cls", [PacerParseDocketTool, PacerFilterEntriesTool])
    def test_all_annotated(self, tool_cls: type) -> None:
        ann = tool_cls().metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.openWorldHint is False  # local only


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestParser:
    def test_parse_docket(self, docket_path: Path) -> None:
        from kaos_source.parsers.pacer import parse_docket

        html = docket_path.read_text(encoding="utf-8", errors="replace")
        docket = parse_docket(html)

        assert docket.case_number
        assert docket.plaintiff
        assert docket.defendant
        assert docket.entry_count > 0
        assert len(docket.docket_entries) == docket.entry_count

    def test_entry_types_detected(self, docket_path: Path) -> None:
        from kaos_source.parsers.pacer import parse_docket

        html = docket_path.read_text(encoding="utf-8", errors="replace")
        docket = parse_docket(html)

        types = {e.entry_type for e in docket.docket_entries if e.entry_type}
        assert len(types) > 0


# ---------------------------------------------------------------------------
# PacerParseDocketTool
# ---------------------------------------------------------------------------


class TestParseTool:
    async def test_parse_docket(self, docket_path: Path) -> None:
        tool = PacerParseDocketTool()
        result = await tool.execute({"path": str(docket_path)})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["case_number"]
        assert result.structuredContent["entry_count"] > 0

    async def test_file_not_found(self) -> None:
        tool = PacerParseDocketTool()
        result = await tool.execute({"path": "/nonexistent/docket.html"})
        assert result.isError
        assert "not found" in (result.text or "").lower()


# ---------------------------------------------------------------------------
# PacerFilterEntriesTool
# ---------------------------------------------------------------------------


class TestFilterTool:
    async def test_filter_by_type(self, docket_path: Path) -> None:
        tool = PacerFilterEntriesTool()
        result = await tool.execute(
            {
                "path": str(docket_path),
                "entry_type": "Motion",
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        # All returned entries should be motions
        for entry in result.structuredContent["entries"]:
            assert entry["entry_type"] == "Motion"

    async def test_filter_by_text(self, docket_path: Path) -> None:
        tool = PacerFilterEntriesTool()
        result = await tool.execute(
            {
                "path": str(docket_path),
                "text_search": "complaint",
            }
        )
        assert not result.isError

    async def test_filter_has_documents(self, docket_path: Path) -> None:
        tool = PacerFilterEntriesTool()
        result = await tool.execute(
            {
                "path": str(docket_path),
                "has_documents": True,
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        for entry in result.structuredContent["entries"]:
            assert len(entry["document_links"]) > 0
