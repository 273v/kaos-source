"""eCFR (Electronic Code of Federal Regulations) API connector.

Public REST API — no authentication required.
Base URL: https://www.ecfr.gov/api

Provides:
- List all CFR titles (1-50)
- Browse hierarchical structure (titles → chapters → parts → sections)
- Get HTML or XML content for specific sections
- List agencies with CFR references

Configuration via ``KaosSourceECFRSettings`` (env prefix ``KAOS_SOURCE_ECFR_``):
- ``KAOS_SOURCE_ECFR_TIMEOUT`` — metadata request timeout (default 30)
- ``KAOS_SOURCE_ECFR_CONTENT_TIMEOUT`` — content fetch timeout (default 300)
- ``KAOS_SOURCE_ECFR_USER_AGENT`` — User-Agent header

Reference: https://www.ecfr.gov/developers/documentation/api/v1
Ported from kl3m-data/sources/us/ecfr/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from kaos_core.config.module_settings import ModuleSettings
from kaos_core.logging import get_logger
from pydantic_settings import SettingsConfigDict

logger = get_logger(__name__)

_BASE_URL = "https://www.ecfr.gov/api"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class KaosSourceECFRSettings(ModuleSettings):
    """Typed settings for the eCFR connector.

    Env vars use the ``KAOS_SOURCE_ECFR_`` prefix:
    - ``KAOS_SOURCE_ECFR_TIMEOUT`` — Metadata API timeout (seconds)
    - ``KAOS_SOURCE_ECFR_CONTENT_TIMEOUT`` — Content download timeout (seconds)
    - ``KAOS_SOURCE_ECFR_USER_AGENT`` — User-Agent header string
    """

    timeout: float = 30.0
    content_timeout: float = 300.0  # Large titles (12, 26, 42) can be slow
    user_agent: str = "kaos-source/0.1 (https://273ventures.com)"

    model_config = SettingsConfigDict(
        env_prefix="KAOS_SOURCE_ECFR_",
        env_file=".env",
        extra="ignore",
    )


def _get_settings(settings: KaosSourceECFRSettings | None = None) -> KaosSourceECFRSettings:
    if settings is not None:
        return settings
    return KaosSourceECFRSettings()


def _api_headers(settings: KaosSourceECFRSettings) -> dict[str, str]:
    return {"User-Agent": settings.user_agent, "Accept": "application/json"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ECFRTitle:
    """A CFR title (e.g. Title 40 — Protection of Environment)."""

    number: int
    name: str
    latest_amended_on: str | None = None
    latest_issue_date: str | None = None
    up_to_date_as_of: str | None = None
    reserved: bool = False


@dataclass(frozen=True, slots=True)
class ECFRAgency:
    """A CFR agency with references to titles/chapters."""

    name: str
    short_name: str = ""
    slug: str = ""
    cfr_references: list[dict[str, Any]] = field(default_factory=list)
    children: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ECFRStructureNode:
    """A node in the CFR hierarchical structure.

    Hierarchy: title → subtitle → chapter → subchapter → part → subpart → section
    """

    identifier: str
    type: str
    label: str
    label_level: str = ""
    label_description: str = ""
    reserved: bool = False
    children: list[ECFRStructureNode] = field(default_factory=list)

    def flatten(self) -> list[ECFRStructureNode]:
        """Flatten the tree to a list of all nodes."""
        result: list[ECFRStructureNode] = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result

    def find_sections(self) -> list[ECFRStructureNode]:
        """Find all section-type nodes in the subtree."""
        return [n for n in self.flatten() if n.type == "section"]

    def find_parts(self) -> list[ECFRStructureNode]:
        """Find all part-type nodes in the subtree."""
        return [n for n in self.flatten() if n.type == "part"]


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
    s = _get_settings(settings)

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers=_api_headers(s),
    ) as client:
        resp = await client.get(f"{_BASE_URL}/versioner/v1/titles.json")
        resp.raise_for_status()
        data = resp.json()

    return [_parse_title(t) for t in data.get("titles", [])]


async def get_agencies(
    *,
    settings: KaosSourceECFRSettings | None = None,
) -> list[ECFRAgency]:
    """Get all agencies with their CFR references.

    Returns:
        List of ECFRAgency objects.
    """
    s = _get_settings(settings)

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
    s = _get_settings(settings)

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
    s = _get_settings(settings)

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
