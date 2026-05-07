"""Raw async client functions for the eCFR (Electronic Code of Federal
Regulations) public REST API.

Public REST API — no authentication required.
Base URL: https://www.ecfr.gov/api

Provides:
- List all CFR titles (1-50)
- Browse hierarchical structure (titles → chapters → parts → sections)
- Get HTML or XML content for specific sections
- List agencies with CFR references

Configuration via :class:`KaosSourceECFRSettings` (env prefix
``KAOS_SOURCE_ECFR_``):

- ``KAOS_SOURCE_ECFR_TIMEOUT`` — metadata request timeout (default 30)
- ``KAOS_SOURCE_ECFR_CONTENT_TIMEOUT`` — content fetch timeout (default 300)
- ``KAOS_SOURCE_ECFR_USER_AGENT`` — User-Agent header

Reference: https://www.ecfr.gov/developers/documentation/api/v1
Ported from kl3m-data/sources/us/ecfr/.
"""

from __future__ import annotations

from typing import Any

import httpx
from kaos_core.logging import get_logger

from kaos_source.apis.ecfr.models import ECFRAgency, ECFRStructureNode, ECFRTitle
from kaos_source.settings.ecfr import KaosSourceECFRSettings

logger = get_logger(__name__)

_BASE_URL = "https://www.ecfr.gov/api"


def _api_headers(settings: KaosSourceECFRSettings) -> dict[str, str]:
    return {"User-Agent": settings.user_agent, "Accept": "application/json"}


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_title(data: dict[str, Any]) -> ECFRTitle:
    return ECFRTitle(
        number=data.get("number", 0),
        name=data.get("name", ""),
        latest_amended_on=data.get("latest_amended_on"),
        latest_issue_date=data.get("latest_issue_date"),
        up_to_date_as_of=data.get("up_to_date_as_of"),
        reserved=data.get("reserved") or False,
    )


def _parse_agency(data: dict[str, Any]) -> ECFRAgency:
    return ECFRAgency(
        name=data.get("name", ""),
        short_name=data.get("short_name", ""),
        slug=data.get("slug", ""),
        cfr_references=data.get("cfr_references") or [],
        children=data.get("children") or [],
    )


def _parse_structure(data: dict[str, Any]) -> ECFRStructureNode:
    """Recursively parse a structure node and its children."""
    children = [_parse_structure(c) for c in data.get("children", [])]
    return ECFRStructureNode(
        identifier=data.get("identifier", ""),
        type=data.get("type", ""),
        label=data.get("label", ""),
        label_level=data.get("label_level", ""),
        label_description=data.get("label_description", ""),
        reserved=data.get("reserved") or False,
        children=children,
    )


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------


async def get_titles(
    *,
    settings: KaosSourceECFRSettings | None = None,
) -> list[ECFRTitle]:
    """Get all CFR titles (1-50).

    Returns:
        List of ECFRTitle objects.
    """
    s = KaosSourceECFRSettings.resolve(settings)

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers=_api_headers(s),
    ) as client:
        resp = await client.get(f"{_BASE_URL}/versioner/v1/titles.json")
        resp.raise_for_status()
        data = resp.json()

    return [_parse_title(t) for t in data.get("titles", [])]


async def get_latest_date(
    title: int,
    *,
    settings: KaosSourceECFRSettings | None = None,
) -> str | None:
    """Get the most recent available date for a CFR title.

    Returns the ``latest_issue_date`` from the eCFR titles API for the given
    title number, or ``None`` if the API call fails or the title has no date.

    Callers must handle the ``None`` case explicitly — this function never
    fabricates a synthetic date.
    """
    try:
        titles = await get_titles(settings=settings)
        for t in titles:
            if t.number == title and t.latest_issue_date:
                return t.latest_issue_date
    except Exception as exc:
        logger.warning(
            "eCFR titles lookup failed for title %s: %s",
            title,
            exc,
        )
        return None

    logger.debug(
        "No latest_issue_date available for eCFR title %s",
        title,
    )
    return None


async def get_agencies(
    *,
    settings: KaosSourceECFRSettings | None = None,
) -> list[ECFRAgency]:
    """Get all agencies with their CFR references.

    Returns:
        List of ECFRAgency objects.
    """
    s = KaosSourceECFRSettings.resolve(settings)

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers=_api_headers(s),
    ) as client:
        resp = await client.get(f"{_BASE_URL}/admin/v1/agencies.json")
        resp.raise_for_status()
        data = resp.json()

    return [_parse_agency(a) for a in data.get("agencies", [])]


async def get_title_structure(
    title: int,
    date: str,
    *,
    settings: KaosSourceECFRSettings | None = None,
) -> ECFRStructureNode:
    """Get the hierarchical structure of a CFR title on a specific date.

    Args:
        title: CFR title number (e.g. 40).
        date: Date in YYYY-MM-DD format.
        settings: Optional settings instance.

    Returns:
        Root ECFRStructureNode with children.
    """
    s = KaosSourceECFRSettings.resolve(settings)

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers=_api_headers(s),
    ) as client:
        resp = await client.get(f"{_BASE_URL}/versioner/v1/structure/{date}/title-{title}.json")
        resp.raise_for_status()
        data = resp.json()

    return _parse_structure(data)


async def get_section_content(
    title: int,
    date: str,
    *,
    section: str | None = None,
    part: str | None = None,
    format: str = "html",
    settings: KaosSourceECFRSettings | None = None,
) -> str:
    """Get the content of a CFR section or part.

    Args:
        title: CFR title number.
        date: Date in YYYY-MM-DD format.
        section: Section identifier (e.g. "62.2").
        part: Part number (e.g. "82").
        format: "html" or "xml".
        settings: Optional settings instance.

    Returns:
        Content string (HTML or XML).
    """
    s = KaosSourceECFRSettings.resolve(settings)

    if format == "xml":
        url = f"{_BASE_URL}/versioner/v1/full/{date}/title-{title}.xml"
    else:
        url = f"{_BASE_URL}/renderer/v1/content/enhanced/{date}/title-{title}"

    params: dict[str, str] = {}
    if section:
        params["section"] = section
    if part:
        params["part"] = part

    async with httpx.AsyncClient(
        timeout=s.content_timeout,
        follow_redirects=True,
        headers={"User-Agent": s.user_agent},
    ) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()

    return resp.text


__all__ = [
    "get_agencies",
    "get_latest_date",
    "get_section_content",
    "get_title_structure",
    "get_titles",
]
