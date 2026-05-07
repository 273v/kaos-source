"""Frozen value types for the SEC EDGAR API.

These dataclasses describe records returned by the SEC EDGAR public APIs
(EFTS full-text search, ``data.sec.gov`` submissions, ``sec.gov`` ticker
catalogue). They are the structured output of
:mod:`kaos_source.apis.edgar.client` functions and the input to
:mod:`kaos_source.apis.edgar.tools` MCP tools.

All types are ``frozen=True, slots=True`` — they are pure value objects
intended for safe sharing across async boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class EdgarFiling:
    """A single EDGAR filing (from EFTS search or submissions API)."""

    accession_number: str
    form: str
    filing_date: str
    company_name: str = ""
    cik: str = ""
    primary_document: str = ""
    description: str = ""
    report_date: str = ""
    file_url: str = ""
    index_url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EdgarSearchResponse:
    """EFTS search response."""

    filings: list[EdgarFiling]
    total: int
    offset: int
    has_more: bool = False


@dataclass(frozen=True, slots=True)
class EdgarCompany:
    """Company info from submissions API."""

    cik: str
    name: str
    ticker: str = ""
    exchange: str = ""
    sic: str = ""
    sic_description: str = ""
    state_of_incorporation: str = ""
    fiscal_year_end: str = ""
    category: str = ""
    filings: list[EdgarFiling] = field(default_factory=list)
    total_filings: int = 0


__all__ = [
    "EdgarCompany",
    "EdgarFiling",
    "EdgarSearchResponse",
]
