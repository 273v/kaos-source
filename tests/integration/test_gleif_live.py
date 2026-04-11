"""Live E2E tests for GLEIF LEI lookup.

Tests against the real GLEIF API with known LEIs.

Run with: pytest tests/integration/test_gleif_live.py -v
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.integration


# ── Helpers ─────────────────────────────────────────────────────────


class _MockToolsRegistry:
    def __init__(self) -> None:
        self.tools: list = []

    def register_tool(self, tool: object) -> None:
        self.tools.append(tool)


class _MockRuntime:
    def __init__(self) -> None:
        self.tools = _MockToolsRegistry()


def _build_gleif_tools() -> dict:
    from kaos_source.tools_gleif import register_gleif_tools

    rt = _MockRuntime()
    count = register_gleif_tools(rt)
    assert count == 2
    return {t.metadata.name: t for t in rt.tools.tools}


TOOLS = _build_gleif_tools()
TOOL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,}$")

# Known LEIs
ALPHABET_LEI = "5493006MHB84DD0ZWV18"  # Alphabet Inc.
JPMORGAN_LEI = "8I5DZWZKVSZI1NUHU748"  # JPMorgan Chase


# ── Metadata tests ──────────────────────────────────────────────────


class TestGleifToolMetadata:
    def test_tool_count(self) -> None:
        assert len(TOOLS) == 2

    def test_expected_names(self) -> None:
        assert set(TOOLS.keys()) == {
            "kaos-source-gleif-search",
            "kaos-source-gleif-get",
        }

    @pytest.mark.parametrize("name", list(TOOLS.keys()))
    def test_name_pattern(self, name: str) -> None:
        assert TOOL_NAME_PATTERN.match(name)

    @pytest.mark.parametrize("name", list(TOOLS.keys()))
    def test_annotations_set(self, name: str) -> None:
        assert TOOLS[name].metadata.annotations is not None
        assert TOOLS[name].metadata.annotations.readOnlyHint is True


# ── Search tool tests ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestGleifSearchLive:
    async def test_search_alphabet(self) -> None:
        """Search for Alphabet — should find Alphabet Inc."""
        tool = TOOLS["kaos-source-gleif-search"]
        result = await tool.execute({"name": "Alphabet Inc"})
        assert not result.isError
        data = result.require_structured()
        assert data["total"] >= 1
        # At least one result should be Alphabet Inc.
        names = [r["legal_name"] for r in data["results"]]
        assert any("ALPHABET" in n.upper() for n in names)

    async def test_search_with_country(self) -> None:
        """Search for Goldman Sachs in US."""
        tool = TOOLS["kaos-source-gleif-search"]
        result = await tool.execute({"name": "Goldman Sachs", "country": "US"})
        assert not result.isError
        data = result.require_structured()
        assert data["total"] >= 1
        # All results should be US-based
        for r in data["results"]:
            addr = r.get("legal_address") or r.get("headquarters_address")
            if addr:
                assert addr.get("country") == "US"

    async def test_search_empty_name_error(self) -> None:
        tool = TOOLS["kaos-source-gleif-search"]
        result = await tool.execute({"name": ""})
        assert result.isError


# ── Get tool tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGleifGetLive:
    async def test_get_alphabet(self) -> None:
        """Look up Alphabet Inc by LEI."""
        tool = TOOLS["kaos-source-gleif-get"]
        result = await tool.execute({"lei": ALPHABET_LEI})
        assert not result.isError
        data = result.require_structured()
        assert data["lei"] == ALPHABET_LEI
        assert "ALPHABET" in data["legal_name"].upper()
        assert data["jurisdiction"] == "US-DE"  # Delaware
        assert data["entity_status"] == "ACTIVE"
        # Should have headquarters address
        hq = data.get("headquarters_address")
        assert hq is not None
        assert hq["country"] == "US"

    async def test_get_jpmorgan(self) -> None:
        """Look up JPMorgan Chase by LEI."""
        tool = TOOLS["kaos-source-gleif-get"]
        result = await tool.execute({"lei": JPMORGAN_LEI})
        assert not result.isError
        data = result.require_structured()
        assert "JPMORGAN" in data["legal_name"].upper()
        assert data["entity_status"] == "ACTIVE"

    async def test_get_invalid_lei_error(self) -> None:
        tool = TOOLS["kaos-source-gleif-get"]
        result = await tool.execute({"lei": "INVALID"})
        assert result.isError  # Too short

    async def test_get_nonexistent_lei(self) -> None:
        tool = TOOLS["kaos-source-gleif-get"]
        result = await tool.execute({"lei": "00000000000000000000"})
        assert result.isError  # Not found
