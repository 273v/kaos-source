"""Smoke test script for all kaos-source data connectors.

Run with: uv run python tests/e2e_smoke.py
"""

import asyncio
import os
import sys


async def main() -> None:
    passed = 0
    failed = 0

    # --- EDGAR ---
    print("=" * 60)
    print("EDGAR")
    print("=" * 60)
    try:
        from kaos_source.connectors.edgar import get_company, lookup_ticker, search_filings

        r = await lookup_ticker("AAPL")
        assert r is not None
        print(f"  lookup AAPL -> CIK {r['cik']}")

        co = await get_company(r["cik"], max_filings=3)
        print(f"  company: {co.name} ({co.ticker}), {len(co.filings)} filings")
        for f in co.filings:
            print(f"    {f.form} filed {f.filing_date}")

        sr = await search_filings(query="annual report", forms="10-K", size=2)
        print(f"  search '10-K annual report': {sr.total} results")
        passed += 3
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1

    # --- Federal Register ---
    print()
    print("=" * 60)
    print("FEDERAL REGISTER")
    print("=" * 60)
    try:
        from kaos_source.connectors.federal_register import get_agencies, get_document, search_documents

        fr = await search_documents(term="securities", doc_type="RULE", per_page=3)
        print(f"  search 'securities RULE': {fr.count} results")
        for d in fr.documents:
            print(f"    {d.document_number}: {d.title[:60]}")

        if fr.documents:
            doc = await get_document(fr.documents[0].document_number)
            print(f"  get_document: {doc.title[:60]}")

        agencies = await get_agencies()
        print(f"  agencies: {len(agencies)}")
        passed += 3
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1

    # --- eCFR ---
    print()
    print("=" * 60)
    print("eCFR")
    print("=" * 60)
    try:
        from kaos_source.connectors.ecfr import get_section_content, get_title_structure, get_titles

        titles = await get_titles()
        print(f"  titles: {len(titles)}")

        structure = await get_title_structure(1, "2024-01-01")
        parts = structure.find_parts()
        sections = structure.find_sections()
        print(f"  Title 1 structure: {len(parts)} parts, {len(sections)} sections")

        content = await get_section_content(1, "2024-01-01", part="1")
        print(f"  Title 1 Part 1 content: {len(content)} chars")
        passed += 3
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1

    # --- GovInfo ---
    print()
    print("=" * 60)
    print("GOVINFO")
    print("=" * 60)
    api_key = os.environ.get("GOVINFO_API_KEY") or os.environ.get("KAOS_SOURCE_GOVINFO_API_KEY")
    if not api_key:
        print("  SKIPPED (no GOVINFO_API_KEY)")
    else:
        try:
            from kaos_source.connectors.govinfo import get_collections, get_package, search

            cols = await get_collections()
            print(f"  collections: {len(cols)}")

            sr = await search("federal budget", page_size=2)
            print(f"  search 'federal budget': {sr.count} results")

            if sr.results:
                pkg = await get_package(sr.results[0].package_id)
                print(f"  package: {pkg.title[:60]}")
            passed += 3
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    # --- PACER ---
    print()
    print("=" * 60)
    print("PACER (local parser)")
    print("=" * 60)
    fixture = "tests/fixtures/pacer_docket1.html"
    if not os.path.exists(fixture):
        print("  SKIPPED (no fixture)")
    else:
        try:
            from kaos_source.parsers.pacer import parse_docket

            html = open(fixture, encoding="utf-8", errors="replace").read()
            docket = parse_docket(html)
            print(f"  case: {docket.case_number}")
            print(f"  parties: {docket.plaintiff} v. {docket.defendant}")
            print(f"  entries: {docket.entry_count}")
            types = {e.entry_type for e in docket.docket_entries if e.entry_type}
            print(f"  entry types: {', '.join(sorted(types))}")
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    # --- Summary ---
    print()
    print("=" * 60)
    total = passed + failed
    if failed == 0:
        print(f"ALL {passed} CHECKS PASSED")
    else:
        print(f"{passed}/{total} passed, {failed} FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
