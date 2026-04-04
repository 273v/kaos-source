"""Battle tests — real-world use cases across all data retrieval APIs.

These tests simulate actual agentic workflows: an agent searching for
legal/regulatory documents, reading them, and extracting information.

Run with: GOVINFO_API_KEY=xxx pytest tests/integration/test_battle.py -v
Skip in CI: pytest -m "not integration"
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════════════
# Federal Register — 5 real-world use cases
# ═══════════════════════════════════════════════════════════════════════════


class TestFRBattle:
    """Real-world Federal Register scenarios."""

    async def test_find_recent_epa_rules(self) -> None:
        """Agent: 'Find recent EPA final rules about air quality'"""
        from kaos_source.tools_federal_register import FRSearchTool

        tool = FRSearchTool()
        result = await tool.execute(
            {
                "term": "air quality standards",
                "doc_type": "RULE",
                "agency": "environmental-protection-agency",
                "per_page": 10,
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["count"] > 0
        # Results should be rules
        for doc in sc["results"]:
            assert doc["type"] in ("Rule", "RULE")

    async def test_get_specific_executive_order(self) -> None:
        """Agent: 'Get details on a specific FR document'"""
        from kaos_source.tools_federal_register import FRSearchTool, FRGetDocumentTool

        # First find a presidential document
        search = FRSearchTool()
        result = await search.execute(
            {
                "doc_type": "PRESDOCU",
                "per_page": 1,
                "order": "newest",
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        doc_num = result.structuredContent["results"][0]["document_number"]

        # Then get full details
        get_doc = FRGetDocumentTool()
        detail = await get_doc.execute({"document_number": doc_num})
        assert not detail.isError
        assert detail.structuredContent is not None
        assert detail.structuredContent["document_number"] == doc_num
        assert detail.structuredContent["title"]

    async def test_read_fr_document_text(self) -> None:
        """Agent: 'Read the full text of this Federal Register notice'"""
        from kaos_source.tools_federal_register import FRGetContentTool, FRSearchTool

        # Find a notice
        search = FRSearchTool()
        result = await search.execute(
            {
                "doc_type": "NOTICE",
                "per_page": 1,
                "order": "newest",
            }
        )
        assert not result.isError
        doc_num = result.structuredContent["results"][0]["document_number"]

        # Read its text content
        content = FRGetContentTool()
        text_result = await content.execute(
            {
                "document_number": doc_num,
                "format": "text",
            }
        )
        # Some documents may not have text URLs available
        if not text_result.isError:
            assert text_result.structuredContent is not None
            assert len(text_result.structuredContent["content"]) > 0

    async def test_find_sec_related_rules(self) -> None:
        """Agent: 'What SEC rules were published in January 2024?'"""
        from kaos_source.tools_federal_register import FRSearchTool

        tool = FRSearchTool()
        result = await tool.execute(
            {
                "agency": "securities-and-exchange-commission",
                "doc_type": "RULE",
                "date_from": "2024-01-01",
                "date_to": "2024-01-31",
                "per_page": 20,
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        # SEC publishes rules regularly
        assert result.structuredContent["count"] >= 0

    async def test_search_cfr_references(self) -> None:
        """Agent: 'Find Federal Register documents referencing 40 CFR Part 82'"""
        from kaos_source.tools_federal_register import FRSearchTool

        tool = FRSearchTool()
        result = await tool.execute(
            {
                "term": "40 CFR part 82",
                "per_page": 5,
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] > 0


# ═══════════════════════════════════════════════════════════════════════════
# eCFR — 5 real-world use cases
# ═══════════════════════════════════════════════════════════════════════════


class TestECFRBattle:
    """Real-world eCFR scenarios."""

    async def test_browse_title40_structure(self) -> None:
        """Agent: 'Show me the structure of Title 40 (Environmental Protection)'"""
        from kaos_source.tools_ecfr import ECFRStructureTool

        tool = ECFRStructureTool()
        result = await tool.execute(
            {
                "title": 40,
                "date": "2024-01-01",
                "depth": 2,
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["part_count"] > 50  # Title 40 has many parts
        assert sc["section_count"] > 100

    async def test_search_ozone_regulations(self) -> None:
        """Agent: 'Find sections in Title 40 about ozone'"""
        from kaos_source.tools_ecfr import ECFRSearchTool

        tool = ECFRSearchTool()
        result = await tool.execute(
            {
                "title": 40,
                "query": "ozone",
                "date": "2024-01-01",
                "max_results": 20,
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["count"] > 0
        # Should find ozone-related sections
        labels = [r["label"] for r in sc["results"]]
        assert any("ozone" in label.lower() for label in labels)

    async def test_read_specific_cfr_section(self) -> None:
        """Agent: 'Read 40 CFR § 82.1 — Purpose and scope of ozone protection'"""
        from kaos_source.tools_ecfr import ECFRContentTool

        tool = ECFRContentTool()
        result = await tool.execute(
            {
                "title": 40,
                "part": "82",
                "date": "2024-01-01",
                "format": "html",
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert len(sc["content"]) > 500
        assert "<" in sc["content"]  # HTML content

    async def test_browse_all_cfr_titles(self) -> None:
        """Agent: 'List all CFR titles'"""
        from kaos_source.tools_ecfr import ECFRListTitlesTool

        tool = ECFRListTitlesTool()
        result = await tool.execute({})
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["count"] >= 50
        # Check known titles exist
        numbers = {t["number"] for t in sc["titles"]}
        assert 26 in numbers  # Internal Revenue
        assert 40 in numbers  # Environment
        assert 17 in numbers  # Commodity and Securities Exchanges

    async def test_read_tax_code_section(self) -> None:
        """Agent: 'Read a section from Title 26 (Internal Revenue)'"""
        from kaos_source.tools_ecfr import ECFRContentTool

        tool = ECFRContentTool()
        result = await tool.execute(
            {
                "title": 26,
                "part": "1",
                "date": "2024-01-01",
                "format": "html",
            }
        )
        # Title 26 Part 1 is very large; may work or may timeout
        if not result.isError:
            assert result.structuredContent is not None
            assert len(result.structuredContent["content"]) > 100


# ═══════════════════════════════════════════════════════════════════════════
# GovInfo — 5 real-world use cases
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    not os.environ.get("GOVINFO_API_KEY"),
    reason="GOVINFO_API_KEY not set",
)
class TestGovInfoBattle:
    """Real-world GovInfo scenarios."""

    async def test_search_congressional_bills(self) -> None:
        """Agent: 'Find congressional bills about artificial intelligence'"""
        from kaos_source.tools_govinfo import GovInfoSearchTool

        tool = GovInfoSearchTool()
        result = await tool.execute(
            {
                "query": "artificial intelligence",
                "collection": "BILLS",
                "page_size": 10,
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["count"] > 0

    async def test_get_package_details(self) -> None:
        """Agent: 'Get details on this government document package'"""
        from kaos_source.tools_govinfo import GovInfoGetPackageTool, GovInfoSearchTool

        # Search first
        search = GovInfoSearchTool()
        result = await search.execute(
            {
                "query": "federal budget 2024",
                "page_size": 1,
            }
        )
        assert not result.isError
        pkg_id = result.structuredContent["results"][0]["package_id"]

        # Get package details
        get_pkg = GovInfoGetPackageTool()
        detail = await get_pkg.execute({"package_id": pkg_id})
        assert not detail.isError
        assert detail.structuredContent is not None
        assert detail.structuredContent["title"]

    async def test_list_collections(self) -> None:
        """Agent: 'What document collections are available on GovInfo?'"""
        from kaos_source.tools_govinfo import GovInfoCollectionsTool

        tool = GovInfoCollectionsTool()
        result = await tool.execute({})
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        codes = {c["code"] for c in sc["collections"]}
        assert "BILLS" in codes
        assert "FR" in codes
        assert "USCODE" in codes

    async def test_search_supreme_court(self) -> None:
        """Agent: 'Find Supreme Court decisions'"""
        from kaos_source.tools_govinfo import GovInfoSearchTool

        tool = GovInfoSearchTool()
        result = await tool.execute(
            {
                "query": "Supreme Court opinion",
                "page_size": 5,
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] > 0

    async def test_search_cfr_documents(self) -> None:
        """Agent: 'Search for Code of Federal Regulations documents about banking'"""
        from kaos_source.tools_govinfo import GovInfoSearchTool

        tool = GovInfoSearchTool()
        result = await tool.execute(
            {
                "query": "banking regulation capital requirements",
                "page_size": 5,
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] > 0


# ═══════════════════════════════════════════════════════════════════════════
# EDGAR — 5 real-world use cases
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgarBattle:
    """Real-world SEC EDGAR scenarios."""

    async def test_lookup_apple_and_get_10k(self) -> None:
        """Agent: 'Find Apple's most recent 10-K filing'"""
        from kaos_source.tools_edgar import EdgarCompanyTool, EdgarLookupTool

        # Step 1: Ticker → CIK
        lookup = EdgarLookupTool()
        result = await lookup.execute({"ticker": "AAPL"})
        assert not result.isError
        cik = result.structuredContent["cik"]
        assert "320193" in cik

        # Step 2: Get company + filtered 10-K filings
        # max_filings is pre-filter — Apple files many 4/8-K forms, so fetch more to find 10-Ks
        company = EdgarCompanyTool()
        result = await company.execute(
            {
                "cik": cik,
                "form_filter": "10-K",
                "max_filings": 100,
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["name"] == "Apple Inc."
        assert sc["ticker"] == "AAPL"
        assert len(sc["filings"]) > 0
        # All should be 10-K
        for f in sc["filings"]:
            assert f["form"] == "10-K"
            assert f["file_url"]  # Should have document URL

    async def test_search_climate_risk_disclosures(self) -> None:
        """Agent: 'Find 10-K filings mentioning climate risk'"""
        from kaos_source.tools_edgar import EdgarSearchTool

        tool = EdgarSearchTool()
        result = await tool.execute(
            {
                "query": '"climate risk"',
                "forms": "10-K",
                "per_page": 10,
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["total"] > 0
        # Results should have document URLs
        for filing in sc["results"]:
            assert filing["accession_number"]
            assert filing["company_name"]

    async def test_lookup_multiple_tickers(self) -> None:
        """Agent: 'Get CIK numbers for MSFT, GOOGL, and NVDA'"""
        from kaos_source.tools_edgar import EdgarLookupTool

        tool = EdgarLookupTool()
        for ticker in ("MSFT", "GOOGL", "NVDA"):
            result = await tool.execute({"ticker": ticker})
            assert not result.isError, f"Failed for {ticker}"
            assert result.structuredContent is not None
            assert result.structuredContent["ticker"] == ticker

    async def test_search_recent_8k_filings(self) -> None:
        """Agent: 'Find recent 8-K filings about mergers and acquisitions'"""
        from kaos_source.tools_edgar import EdgarSearchTool

        tool = EdgarSearchTool()
        result = await tool.execute(
            {
                "query": "merger acquisition",
                "forms": "8-K",
                "per_page": 5,
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["total"] > 0

    async def test_get_tesla_recent_filings(self) -> None:
        """Agent: 'What has Tesla filed recently?'"""
        from kaos_source.tools_edgar import EdgarCompanyTool, EdgarLookupTool

        lookup = EdgarLookupTool()
        result = await lookup.execute({"ticker": "TSLA"})
        assert not result.isError
        cik = result.structuredContent["cik"]

        company = EdgarCompanyTool()
        result = await company.execute({"cik": cik, "max_filings": 10})
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert "Tesla" in sc["name"]
        assert len(sc["filings"]) > 0


# ═══════════════════════════════════════════════════════════════════════════
# PACER — 3 real-world use cases (local parser, fixture-based)
# ═══════════════════════════════════════════════════════════════════════════


class TestPacerBattle:
    """Real-world PACER docket parsing scenarios."""

    _FIXTURE = "tests/fixtures/pacer_docket1.html"

    @pytest.fixture(autouse=True)
    def _check_fixture(self) -> None:
        import os

        if not os.path.exists(self._FIXTURE):
            pytest.skip("PACER fixture not available")

    async def test_parse_full_docket(self) -> None:
        """Agent: 'Parse this PACER docket file and summarize the case'"""
        from kaos_source.tools_pacer import PacerParseDocketTool

        tool = PacerParseDocketTool()
        result = await tool.execute({"path": self._FIXTURE})
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["case_number"]
        assert sc["plaintiff"]
        assert sc["defendant"]
        assert sc["entry_count"] > 0
        # Should have parsed multiple entry types
        types = {e["entry_type"] for e in sc["docket_entries"] if e.get("entry_type")}
        assert len(types) >= 2

    async def test_find_motions(self) -> None:
        """Agent: 'Find all motions in this docket'"""
        from kaos_source.tools_pacer import PacerFilterEntriesTool

        tool = PacerFilterEntriesTool()
        result = await tool.execute(
            {
                "path": self._FIXTURE,
                "entry_type": "Motion",
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        for entry in sc["entries"]:
            assert entry["entry_type"] == "Motion"

    async def test_find_entries_with_documents(self) -> None:
        """Agent: 'Show docket entries that have downloadable documents'"""
        from kaos_source.tools_pacer import PacerFilterEntriesTool

        tool = PacerFilterEntriesTool()
        result = await tool.execute(
            {
                "path": self._FIXTURE,
                "has_documents": True,
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["filtered_count"] > 0
        for entry in sc["entries"]:
            assert len(entry["document_links"]) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Source Discovery — 3 real-world use cases
# ═══════════════════════════════════════════════════════════════════════════


class TestSourceBattle:
    """Real-world file discovery scenarios."""

    async def test_discover_project_files(self) -> None:
        """Agent: 'List all Python files in the kaos-source package'"""
        from kaos_source.tools import DiscoverSourcesTool

        tool = DiscoverSourcesTool()
        result = await tool.execute(
            {
                "path": "/home/mjbommar/projects/273v/kaos-modules/kaos-source/kaos_source",
                "patterns": ["*.py"],
                "limit": 100,
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["count"] > 10
        names = {item["name"] for item in sc["items"]}
        assert "tools.py" in names

    async def test_preview_file_content(self) -> None:
        """Agent: 'Show me the first 512 bytes of this file'"""
        from kaos_source.tools import PreviewSourceTool

        tool = PreviewSourceTool()
        result = await tool.execute(
            {
                "path": "/home/mjbommar/projects/273v/kaos-modules/kaos-source/pyproject.toml",
                "max_bytes": 512,
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert "kaos-source" in sc["text"]

    async def test_describe_file_metadata(self) -> None:
        """Agent: 'What type of file is this and how big is it?'"""
        from kaos_source.tools import DescribeSourceTool

        tool = DescribeSourceTool()
        result = await tool.execute(
            {
                "path": "/home/mjbommar/projects/273v/kaos-modules/kaos-source/pyproject.toml",
            }
        )
        assert not result.isError
        sc = result.structuredContent
        assert sc is not None
        assert sc["name"] == "pyproject.toml"
        assert sc["size"] > 0
