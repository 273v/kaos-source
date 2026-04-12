"""SEC EDGAR API connector.

No API key required — but a User-Agent with company/email is mandatory.
Rate limit: 10 requests/second.

APIs used:
- EFTS search: https://efts.sec.gov/LATEST/search-index
- Submissions: https://data.sec.gov/submissions/CIK{CIK}.json
- Ticker lookup: https://www.sec.gov/files/company_tickers.json

Configuration via ``KaosSourceEdgarSettings`` (env prefix ``KAOS_SOURCE_EDGAR_``):
- ``KAOS_SOURCE_EDGAR_USER_AGENT`` — Required User-Agent (format: "Company email@co.com")
- ``KAOS_SOURCE_EDGAR_TIMEOUT`` — Request timeout (default 30)

Ported from kl3m-data/sources/us/edgar/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kaos_content.model.document import ContentDocument

import httpx
from kaos_core.config.module_settings import ModuleSettings
from kaos_core.logging import get_logger
from pydantic_settings import SettingsConfigDict

logger = get_logger(__name__)

_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

# Common form types
FORM_TYPES = (
    "10-K",
    "10-Q",
    "8-K",
    "S-1",
    "DEF 14A",
    "4",
    "SC 13D",
    "13F-HR",
    "20-F",
)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class KaosSourceEdgarSettings(ModuleSettings):
    """Typed settings for the EDGAR connector.

    The SEC requires a descriptive User-Agent header on all requests.
    Set ``KAOS_SOURCE_EDGAR_USER_AGENT`` to "YourCompany email@company.com".
    """

    user_agent: str = "273Ventures research@273ventures.com"
    timeout: float = 30.0

    model_config = SettingsConfigDict(
        env_prefix="KAOS_SOURCE_EDGAR_",
        env_file=".env",
        extra="ignore",
    )


def _get_settings(settings: KaosSourceEdgarSettings | None = None) -> KaosSourceEdgarSettings:
    if settings is not None:
        return settings
    return KaosSourceEdgarSettings()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_efts_hit(hit: dict[str, Any]) -> EdgarFiling:
    """Parse an EFTS search hit into an EdgarFiling."""
    src = hit.get("_source", {})
    ciks = src.get("ciks", [])
    cik = ciks[0].lstrip("0") if ciks else ""
    names = src.get("display_names", [])
    name = names[0] if names else ""
    accession = src.get("adsh", "")

    # Extract filename from _id (format: accession:filename)
    hit_id = hit.get("_id", "")
    filename = hit_id.split(":", 1)[1] if ":" in hit_id else ""

    # Build URLs
    accession_nodash = accession.replace("-", "")
    file_url = f"{_ARCHIVES_URL}/{cik}/{accession_nodash}/{filename}" if cik and filename else ""
    index_url = f"{_ARCHIVES_URL}/{cik}/{accession_nodash}/index.json" if cik else ""

    return EdgarFiling(
        accession_number=accession,
        form=src.get("form", ""),
        filing_date=src.get("file_date", ""),
        company_name=name,
        cik=cik,
        primary_document=filename,
        report_date=src.get("period_ending", ""),
        file_url=file_url,
        index_url=index_url,
        extra={
            k: v
            for k, v in src.items()
            if k
            not in {
                "ciks",
                "display_names",
                "adsh",
                "form",
                "file_date",
                "period_ending",
                "root_forms",
            }
            and v
        },
    )


def _parse_submission_filings(
    data: dict[str, Any], cik: str, max_filings: int = 50
) -> list[EdgarFiling]:
    """Parse recent filings from submissions API parallel arrays."""
    recent = data.get("filings", {}).get("recent", {})
    if not recent:
        return []

    accessions = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    primary_docs = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])

    filings = []
    cik_stripped = cik.lstrip("0")
    for i in range(min(len(accessions), max_filings)):
        accession = accessions[i]
        accession_nodash = accession.replace("-", "")
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""
        file_url = (
            f"{_ARCHIVES_URL}/{cik_stripped}/{accession_nodash}/{primary_doc}"
            if primary_doc
            else ""
        )

        filings.append(
            EdgarFiling(
                accession_number=accession,
                form=forms[i] if i < len(forms) else "",
                filing_date=dates[i] if i < len(dates) else "",
                cik=cik_stripped,
                primary_document=primary_doc,
                description=descriptions[i] if i < len(descriptions) else "",
                report_date=report_dates[i] if i < len(report_dates) else "",
                file_url=file_url,
            )
        )

    return filings


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------


async def search_filings(
    *,
    query: str = "",
    forms: str | None = None,
    cik: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    size: int = 20,
    offset: int = 0,
    settings: KaosSourceEdgarSettings | None = None,
) -> EdgarSearchResponse:
    """Search EDGAR filings via EFTS full-text search.

    Args:
        query: Full-text search query (Lucene syntax). Optional if cik provided.
        forms: Comma-separated form types (e.g. "10-K,10-Q").
        cik: 10-digit CIK number (with or without leading zeros).
        date_from: Filing date start (YYYY-MM-DD).
        date_to: Filing date end (YYYY-MM-DD).
        size: Results per page (max 100).
        offset: Pagination offset.
        settings: Optional settings instance.

    Returns:
        EdgarSearchResponse with filings and pagination.
    """
    s = _get_settings(settings)
    params: dict[str, str | int] = {
        "size": min(size, 100),
        "from": offset,
    }

    if query:
        params["q"] = query
    if forms:
        params["forms"] = forms
    if cik:
        # Pad to 10 digits
        params["ciks"] = cik.zfill(10)
    if date_from or date_to:
        params["dateRange"] = "custom"
        if date_from:
            params["startdt"] = date_from
        if date_to:
            params["enddt"] = date_to

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers={"User-Agent": s.user_agent, "Accept": "application/json"},
    ) as client:
        resp = await client.get(_EFTS_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    hits = data.get("hits", {})
    total_obj = hits.get("total", {})
    total = total_obj.get("value", 0) if isinstance(total_obj, dict) else 0

    filings = [_parse_efts_hit(h) for h in hits.get("hits", [])]
    has_more = (offset + len(filings)) < total

    return EdgarSearchResponse(
        filings=filings,
        total=total,
        offset=offset,
        has_more=has_more,
    )


async def get_company(
    cik: str,
    *,
    max_filings: int = 50,
    form_filter: str | None = None,
    settings: KaosSourceEdgarSettings | None = None,
) -> EdgarCompany:
    """Get company info and recent filings from submissions API.

    Args:
        cik: CIK number (with or without leading zeros).
        max_filings: Max recent filings to return.
        form_filter: Optional form type to filter (e.g. "10-K").
        settings: Optional settings instance.

    Returns:
        EdgarCompany with info and filings.
    """
    s = _get_settings(settings)
    cik_padded = cik.zfill(10)

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers={"User-Agent": s.user_agent, "Accept": "application/json"},
    ) as client:
        resp = await client.get(f"{_SUBMISSIONS_URL}/CIK{cik_padded}.json")
        resp.raise_for_status()
        data = resp.json()

    tickers = data.get("tickers", [])
    exchanges = data.get("exchanges", [])

    filings = _parse_submission_filings(data, cik_padded, max_filings=max_filings)

    if form_filter:
        filings = [f for f in filings if f.form == form_filter]

    name = data.get("name", "")
    return EdgarCompany(
        cik=cik_padded,
        name=name,
        ticker=tickers[0] if tickers else "",
        exchange=exchanges[0] if exchanges else "",
        sic=data.get("sic", ""),
        sic_description=data.get("sicDescription", ""),
        state_of_incorporation=data.get("stateOfIncorporation", ""),
        fiscal_year_end=data.get("fiscalYearEnd", ""),
        category=data.get("category", ""),
        filings=filings,
        total_filings=len(filings),
    )


async def lookup_ticker(
    ticker: str,
    *,
    settings: KaosSourceEdgarSettings | None = None,
) -> dict[str, Any] | None:
    """Look up a company by ticker symbol.

    Args:
        ticker: Stock ticker (e.g. "AAPL").
        settings: Optional settings instance.

    Returns:
        Dict with cik, ticker, title, or None if not found.
    """
    s = _get_settings(settings)
    ticker_upper = ticker.upper()

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers={"User-Agent": s.user_agent, "Accept": "application/json"},
    ) as client:
        resp = await client.get(_TICKERS_URL)
        resp.raise_for_status()
        data = resp.json()

    for entry in data.values():
        if entry.get("ticker") == ticker_upper:
            return {
                "cik": str(entry["cik_str"]).zfill(10),
                "ticker": entry["ticker"],
                "title": entry.get("title", ""),
            }
    return None


async def fetch_filing_document(
    filing: EdgarFiling,
    *,
    settings: KaosSourceEdgarSettings | None = None,
) -> str:
    """Fetch the primary document HTML of an EDGAR filing.

    Args:
        filing: An EdgarFiling from search_filings or get_company.
        settings: Optional settings instance.

    Returns:
        Raw HTML string of the filing's primary document.
    """
    s = _get_settings(settings)
    url = filing.file_url
    if not url:
        msg = f"Filing {filing.accession_number} has no file_url"
        raise ValueError(msg)

    async with httpx.AsyncClient(
        timeout=max(s.timeout, 120),
        headers={"User-Agent": s.user_agent},
        follow_redirects=True,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def filing_html_to_document(
    html: str,
    *,
    url: str = "",
) -> ContentDocument:
    """Convert an EDGAR filing's HTML to a ContentDocument.

    EDGAR filings use Inline XBRL (iXBRL) which wraps standard HTML
    in ``ix:`` namespace elements.  This function handles the XBRL
    stripping automatically and uses ``extract_content=False``
    because the entire filing body is content (there is no
    navigation/sidebar to filter).

    This is the correct entry point for parsing EDGAR filings.  Do
    NOT use ``kaos_web.html_to_document`` directly — its readability
    model will aggressively filter the filing's styled content.

    Args:
        html: Raw HTML string from EDGAR (may contain iXBRL).
        url: Source URL for provenance.

    Returns:
        ContentDocument with the filing's full content as AST blocks.
    """
    from kaos_web import html_to_document

    return html_to_document(
        html,
        url=url,
        strip_xbrl=True,
        extract_content=False,
    )
