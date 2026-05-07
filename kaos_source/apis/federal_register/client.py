"""Federal Register HTTP client — raw async functions.

Public REST API at ``federalregister.gov/api/v1`` — no authentication
required. This module is the implementation layer for the
:class:`FederalRegisterApiConnector` and the FR MCP tools: bytes in,
structured records out.

Functions:

- :func:`search_documents` — paginated search over rules / proposed
  rules / notices / presidential documents
- :func:`get_document` — fetch a single document by FR document number
- :func:`get_agencies` — list all FR agencies
- :func:`fetch_document_content` — download text/xml/html/pdf body

Configuration via :class:`KaosSourceFRSettings` (env prefix
``KAOS_SOURCE_FR_``):

- ``KAOS_SOURCE_FR_TIMEOUT`` — API request timeout in seconds (default 30)
- ``KAOS_SOURCE_FR_CONTENT_TIMEOUT`` — Content fetch timeout (default 120)
- ``KAOS_SOURCE_FR_USER_AGENT`` — User-Agent header

Reference: https://www.federalregister.gov/developers/documentation/api/v1
Ported from kl3m-data/sources/us/fr/.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
from kaos_core.logging import get_logger

from kaos_source.apis.federal_register.models import FRAgency, FRDocument, FRSearchResult
from kaos_source.settings.federal_register import KaosSourceFRSettings

logger = get_logger(__name__)

_BASE_URL = "https://www.federalregister.gov/api/v1"

# Document types in the Federal Register
DOCUMENT_TYPES = ("RULE", "PRORULE", "NOTICE", "PRESDOCU")

# Minimal fields for discovery/search (metadata only)
_DISCOVERY_FIELDS = [
    "document_number",
    "title",
    "type",
    "subtype",
    "publication_date",
    "agencies",
    "agency_names",
    "citation",
    "start_page",
    "end_page",
    "page_length",
    "abstract",
    "html_url",
    "pdf_url",
    "json_url",
]

# Full fields for detailed document fetch
_DETAIL_FIELDS = [
    *_DISCOVERY_FIELDS,
    "full_text_xml_url",
    "raw_text_url",
    "body_html_url",
    "effective_on",
    "comments_close_on",
    "dates",
    "action",
    "docket_ids",
    "cfr_references",
    "regulation_id_numbers",
    "significant",
    "topics",
    "excerpts",
    "comment_url",
    "regulations_dot_gov_url",
    "signing_date",
    "president",
    "executive_order_number",
    "proclamation_number",
    "volume",
]


def _api_headers(settings: KaosSourceFRSettings) -> dict[str, str]:
    """Standard headers for FR API requests."""
    return {"User-Agent": settings.user_agent, "Accept": "application/json"}


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_document(data: dict[str, Any]) -> FRDocument:
    """Parse a document from the API response."""
    known_fields = {f.name for f in FRDocument.__dataclass_fields__.values()}
    known: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for k, v in data.items():
        if k in known_fields:
            known[k] = v if v is not None else ""
        elif v is not None:
            extra[k] = v

    # Normalize types
    if isinstance(known.get("significant"), str):
        known["significant"] = known["significant"] == "1"
    elif known.get("significant") is None:
        known["significant"] = False

    for list_field in (
        "agencies",
        "agency_names",
        "docket_ids",
        "cfr_references",
        "regulation_id_numbers",
        "topics",
    ):
        if not isinstance(known.get(list_field), list):
            known[list_field] = []

    for int_field in ("start_page", "end_page", "page_length", "volume"):
        if known.get(int_field) is None or known.get(int_field) == "":
            known[int_field] = 0

    return FRDocument(**known, extra=extra)


def _parse_agency(data: dict[str, Any]) -> FRAgency:
    """Parse an agency from the API response."""
    return FRAgency(
        id=data.get("id", 0),
        name=data.get("name", ""),
        short_name=data.get("short_name", ""),
        slug=data.get("slug", ""),
        url=data.get("url", ""),
        parent_id=data.get("parent_id"),
        child_ids=data.get("child_ids") or [],
        description=data.get("description", ""),
    )


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------


async def search_documents(
    *,
    term: str = "",
    doc_type: str | list[str] | None = None,
    agencies: str | list[str] | None = None,
    date_gte: str | date | None = None,
    date_lte: str | date | None = None,
    significant: bool | None = None,
    cfr_title: int | None = None,
    cfr_part: int | None = None,
    docket_id: str | None = None,
    per_page: int = 20,
    page: int = 1,
    order: str = "newest",
    fields: list[str] | None = None,
    settings: KaosSourceFRSettings | None = None,
) -> FRSearchResult:
    """Search Federal Register documents.

    Args:
        term: Full-text search query.
        doc_type: Document type(s): RULE, PRORULE, NOTICE, PRESDOCU.
        agencies: Agency slug(s) (e.g. "environmental-protection-agency").
        date_gte: Published on or after (YYYY-MM-DD).
        date_lte: Published on or before (YYYY-MM-DD).
        significant: Filter to EO 12866 significant actions.
        cfr_title: CFR title number.
        cfr_part: CFR part number.
        docket_id: Agency docket ID.
        per_page: Results per page (max 2000).
        page: Page number (max 50).
        order: Sort order: newest, oldest, relevance.
        fields: Fields to return (defaults to discovery fields).
        settings: Optional settings instance. If None, created from env.

    Returns:
        FRSearchResult with documents and pagination info.
    """
    s = KaosSourceFRSettings.resolve(settings)
    params: list[tuple[str, str | int | float | None]] = []

    # Field selection
    for f in fields or _DISCOVERY_FIELDS:
        params.append(("fields[]", f))

    # Pagination
    params.append(("per_page", str(min(per_page, 2000))))
    params.append(("page", str(min(page, 50))))
    params.append(("order", order))

    # Search conditions
    if term:
        params.append(("conditions[term]", term))

    if doc_type:
        types = [doc_type] if isinstance(doc_type, str) else doc_type
        for t in types:
            params.append(("conditions[type][]", t))

    if agencies:
        slugs = [agencies] if isinstance(agencies, str) else agencies
        for slug in slugs:
            params.append(("conditions[agencies][]", slug))

    if date_gte:
        params.append(("conditions[publication_date][gte]", str(date_gte)))
    if date_lte:
        params.append(("conditions[publication_date][lte]", str(date_lte)))

    if significant is not None:
        params.append(("conditions[significant]", "1" if significant else "0"))

    if cfr_title is not None:
        params.append(("conditions[cfr][title]", str(cfr_title)))
    if cfr_part is not None:
        params.append(("conditions[cfr][part]", str(cfr_part)))

    if docket_id:
        params.append(("conditions[docket_id]", docket_id))

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers=_api_headers(s),
    ) as client:
        resp = await client.get(f"{_BASE_URL}/documents.json", params=params)
        resp.raise_for_status()
        data = resp.json()

    documents = [_parse_document(d) for d in data.get("results", [])]
    return FRSearchResult(
        documents=documents,
        count=data.get("count", 0),
        total_pages=data.get("total_pages", 0),
        next_page_url=data.get("next_page_url"),
        description=data.get("description", ""),
    )


async def get_document(
    document_number: str,
    *,
    settings: KaosSourceFRSettings | None = None,
) -> FRDocument:
    """Get a single document by its document number.

    Args:
        document_number: FR document number (e.g. "2024-12345").
        settings: Optional settings instance.

    Returns:
        FRDocument with full details.

    Raises:
        httpx.HTTPStatusError: If document not found (404).
    """
    s = KaosSourceFRSettings.resolve(settings)
    params: list[tuple[str, str | int | float | None]] = [("fields[]", f) for f in _DETAIL_FIELDS]

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers=_api_headers(s),
    ) as client:
        resp = await client.get(f"{_BASE_URL}/documents/{document_number}.json", params=params)
        resp.raise_for_status()
        data = resp.json()

    return _parse_document(data)


async def get_agencies(
    *,
    settings: KaosSourceFRSettings | None = None,
) -> list[FRAgency]:
    """Get all Federal Register agencies.

    Args:
        settings: Optional settings instance.

    Returns:
        List of FRAgency objects.
    """
    s = KaosSourceFRSettings.resolve(settings)

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers=_api_headers(s),
    ) as client:
        resp = await client.get(f"{_BASE_URL}/agencies.json")
        resp.raise_for_status()
        data = resp.json()

    return [_parse_agency(a) for a in data]


async def fetch_document_content(
    document: FRDocument,
    format: str = "text",
    *,
    settings: KaosSourceFRSettings | None = None,
) -> str | bytes:
    """Fetch the full content of a document in the specified format.

    Args:
        document: FRDocument with content URLs.
        format: One of "text", "xml", "html", "pdf".
        settings: Optional settings instance.

    Returns:
        Text content (str) for text/xml/html, binary (bytes) for pdf.

    Raises:
        ValueError: If format is unknown or URL not available.
    """
    s = KaosSourceFRSettings.resolve(settings)
    url_map = {
        "text": document.raw_text_url,
        "xml": document.full_text_xml_url,
        "html": document.body_html_url,
        "pdf": document.pdf_url,
    }
    url = url_map.get(format)
    if not url:
        available = [k for k, v in url_map.items() if v]
        msg = f"Format '{format}' not available. Available: {', '.join(available)}"
        raise ValueError(msg)

    async with httpx.AsyncClient(
        timeout=s.content_timeout,
        follow_redirects=True,
        headers={"User-Agent": s.user_agent},
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    if format == "pdf":
        return resp.content

    text = resp.text

    # The "text" format returns HTML-wrapped <pre> content — strip HTML tags
    if format == "text" and "<html" in text[:200].lower():
        import re

        # Extract content from <pre> tags if present
        pre_match = re.search(r"<pre[^>]*>(.*)</pre>", text, re.DOTALL)
        if pre_match:
            text = pre_match.group(1)
        # Strip remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'")

    return text


__all__ = [
    "DOCUMENT_TYPES",
    "fetch_document_content",
    "get_agencies",
    "get_document",
    "search_documents",
]
