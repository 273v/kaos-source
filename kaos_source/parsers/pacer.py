"""PACER docket HTML parser.

Parses saved PACER docket HTML files into structured data.
Uses lxml for HTML parsing — no network access, no authentication.

Ported from kelvin_research/pacer/docket_parser.py.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DocumentLink:
    """A link to a document in a docket entry."""

    text: str
    url: str


@dataclass(frozen=True, slots=True)
class FilingInfo:
    """Filing information extracted from docket text."""

    attorney: str | None = None
    filed_date: date | None = None
    entered_date: date | None = None
    filing_fee: float | None = None
    receipt_number: str | None = None


@dataclass(frozen=True, slots=True)
class DocketEntry:
    """A single docket entry from a PACER case."""

    date_filed: date
    docket_number: str
    docket_text: str
    entry_type: str | None = None
    document_links: list[DocumentLink] = field(default_factory=list)
    filing_info: FilingInfo | None = None


@dataclass(frozen=True, slots=True)
class DocketInfo:
    """Complete docket information for a PACER case."""

    case_number: str
    case_title: str
    plaintiff: str
    defendant: str
    date_filed: date
    assigned_judge: str
    nature_of_suit: str
    cause_of_action: str
    date_terminated: date | None = None
    jury_demand: str | None = None
    jurisdiction: str | None = None
    docket_entries: list[DocketEntry] = field(default_factory=list)
    entry_count: int = 0


# Entry type detection patterns
_ENTRY_TYPE_PREFIXES = {
    "COMPLAINT": "Complaint",
    "MOTION": "Motion",
    "ORDER": "Order",
    "NOTICE": "Notice",
    "MINUTE": "Minute Entry",
    "SUMMONS": "Summons",
    "ANSWER": "Answer",
    "STIPULATION": "Stipulation",
    "DECLARATION": "Declaration",
    "BRIEF": "Brief",
    "MEMORANDUM": "Memorandum",
    "AFFIDAVIT": "Affidavit",
    "REPORT": "Report",
    "Proposed": "Proposed Document",
}

_ENTRY_TYPE_CONTAINS = {
    "Certificate of Interested": "Certificate",
    "Case assigned to": "Case Assignment",
    "Electronic filing error": "Filing Error",
}


def _determine_entry_type(text: str) -> str | None:
    """Determine the type of docket entry from its text."""
    for prefix, entry_type in _ENTRY_TYPE_PREFIXES.items():
        if text.startswith(prefix):
            return entry_type
    for substring, entry_type in _ENTRY_TYPE_CONTAINS.items():
        if substring in text:
            return entry_type
    return None


def _extract_filing_info(text: str) -> FilingInfo | None:
    """Extract filing information from docket text."""
    info: dict[str, Any] = {}

    fee_match = re.search(r"Filing fee \$ ([0-9,]+), receipt number ([A-Z0-9-]+)", text)
    if fee_match:
        info["filing_fee"] = float(fee_match.group(1).replace(",", ""))
        info["receipt_number"] = fee_match.group(2)

    attorney_match = re.search(r"\(([^)]+)\) \(Filed on", text)
    if attorney_match:
        info["attorney"] = attorney_match.group(1).strip()

    filed_match = re.search(r"\(Filed on ([^)]+)\)", text)
    if filed_match:
        try:
            info["filed_date"] = datetime.strptime(filed_match.group(1).strip(), "%m/%d/%Y").date()
        except ValueError:
            with contextlib.suppress(ValueError):
                info["filed_date"] = datetime.strptime(
                    filed_match.group(1).strip(), "%m/%d/%y"
                ).date()

    entered_match = re.search(r"\(Entered: ([^)]+)\)", text)
    if entered_match:
        with contextlib.suppress(ValueError):
            info["entered_date"] = datetime.strptime(
                entered_match.group(1).strip(), "%m/%d/%Y"
            ).date()

    return FilingInfo(**info) if info else None


def parse_docket(html_content: str) -> DocketInfo:
    """Parse a PACER docket HTML file into structured data.

    Args:
        html_content: Raw HTML content from PACER.

    Returns:
        DocketInfo with case info and docket entries.

    Raises:
        ValueError: If the HTML cannot be parsed as a PACER docket.
    """
    from lxml import html

    # Decode quoted-printable encoding if present
    content = html_content.replace("=3D", "=").replace("=\n", "")
    doc = html.fromstring(content)

    # --- Case info ---
    case_info: dict[str, Any] = {
        "case_number": "",
        "case_title": "",
        "plaintiff": "",
        "defendant": "",
        "date_filed": date.today(),
        "assigned_judge": "",
        "nature_of_suit": "",
        "cause_of_action": "",
    }

    case_links = doc.xpath('//a[contains(@href, "DktRpt.pl")]')
    if case_links:
        case_info["case_number"] = case_links[0].text_content().strip()

    party_section = doc.xpath('//table[contains(., " v. ")]')
    if party_section:
        party_text = party_section[0].text_content()
        if " v. " in party_text:
            parts = party_text.split(" v. ")
            if len(parts) >= 2:
                plaintiff = parts[0].strip().split("\n")[-1].strip()
                defendant = parts[1].strip().split("\n")[0].strip()
                case_info["plaintiff"] = plaintiff
                case_info["defendant"] = defendant
                case_info["case_title"] = f"{plaintiff} v. {defendant}"

    metadata_table = doc.xpath(
        '//table[contains(., "Date Filed:") and contains(., "Nature of Suit:")]'
    )
    if metadata_table:
        text = metadata_table[0].text_content()

        date_match = re.search(r"Date Filed: ([^\n]+)", text)
        if date_match:
            case_info["date_filed"] = datetime.strptime(
                date_match.group(1).strip(), "%m/%d/%Y"
            ).date()

        term_match = re.search(r"Date Terminated: ([^\n]+)", text)
        if term_match:
            case_info["date_terminated"] = datetime.strptime(
                term_match.group(1).strip(), "%m/%d/%Y"
            ).date()

        for field_name, pattern in {
            "jury_demand": r"Jury Demand: ([^\n]+)",
            "nature_of_suit": r"Nature of Suit: ([^\n]+)",
            "cause_of_action": r"Cause: ([^\n]+)",
            "jurisdiction": r"Jurisdiction: ([^\n]+)",
        }.items():
            m = re.search(pattern, text)
            if m:
                case_info[field_name] = m.group(1).strip()

    judge_entries = doc.xpath('//*[contains(text(), "Case assigned to Judge")]')
    if judge_entries:
        judge_match = re.search(
            r"Case assigned to Judge ([^.\n]+)", judge_entries[0].text_content()
        )
        if judge_match:
            case_info["assigned_judge"] = judge_match.group(1).strip()

    # --- Docket entries ---
    entries: list[DocketEntry] = []
    docket_table = None
    for table in doc.xpath("//table"):
        tc = table.text_content()
        if "Date Filed" in tc and "Docket Text" in tc:
            docket_table = table
            break

    if docket_table is not None:
        for row in docket_table.xpath(".//tr")[1:]:
            cells = row.xpath(".//td")
            if len(cells) < 3:
                continue
            try:
                date_str = cells[0].text_content().strip()
                date_filed = datetime.strptime(date_str, "%m/%d/%Y").date()
                docket_number = cells[1].text_content().strip()
                docket_text = cells[2].text_content().strip()

                links = [
                    DocumentLink(
                        text=a.text_content().strip(),
                        url=a.get("href", ""),
                    )
                    for a in cells[2].xpath(".//a[@href]")
                ]

                entries.append(
                    DocketEntry(
                        date_filed=date_filed,
                        docket_number=docket_number,
                        docket_text=docket_text,
                        entry_type=_determine_entry_type(docket_text),
                        document_links=links,
                        filing_info=_extract_filing_info(docket_text),
                    )
                )
            except Exception:
                continue

    return DocketInfo(
        **case_info,
        docket_entries=entries,
        entry_count=len(entries),
    )
