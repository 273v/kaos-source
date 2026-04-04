"""GovInfo API connector (Government Publishing Office).

Requires API key: ``KAOS_SOURCE_GOVINFO_API_KEY`` (or legacy ``GOVINFO_API_KEY``).
Get a free key at https://api.data.gov/signup/

Base URL: https://api.govinfo.gov

Provides:
- Search across all government publications
- Get package metadata and granule details
- List collections and collection updates by date
- Fetch document content (PDF, XML, HTML, text)

Configuration via ``KaosSourceGovInfoSettings`` (env prefix ``KAOS_SOURCE_GOVINFO_``).

Reference: https://api.govinfo.gov/docs/
Ported from kl3m-data/sources/us/govinfo/.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from kaos_core.config.module_settings import ModuleSettings
from kaos_core.logging import get_logger
from pydantic import SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

logger = get_logger(__name__)

_BASE_URL = "https://api.govinfo.gov"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class KaosSourceGovInfoSettings(ModuleSettings):
    """Typed settings for the GovInfo connector.

    Env vars use the ``KAOS_SOURCE_GOVINFO_`` prefix:
    - ``KAOS_SOURCE_GOVINFO_API_KEY`` — GovInfo API key (required)
    - ``KAOS_SOURCE_GOVINFO_TIMEOUT`` — API request timeout (seconds)
    - ``KAOS_SOURCE_GOVINFO_USER_AGENT`` — User-Agent header string

    Legacy env var: ``GOVINFO_API_KEY`` (backward compatible).
    """

    api_key: SecretStr | None = None
    timeout: float = 30.0
    user_agent: str = "kaos-source/0.1 (https://273ventures.com)"

    model_config = SettingsConfigDict(
        env_prefix="KAOS_SOURCE_GOVINFO_",
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_env_fallback(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Support legacy GOVINFO_API_KEY env var."""
        if not values.get("api_key"):
            legacy = os.environ.get("GOVINFO_API_KEY")
            if legacy:
                values["api_key"] = legacy
        return values

    def get_api_key(self) -> str:
        """Get the API key or raise a clear error."""
        if self.api_key is not None:
            return self.api_key.get_secret_value()
        msg = (
            "GovInfo API key not set. "
            "Set KAOS_SOURCE_GOVINFO_API_KEY or GOVINFO_API_KEY env var. "
            "Get a free key at https://api.data.gov/signup/"
        )
        raise ValueError(msg)


def _get_settings(settings: KaosSourceGovInfoSettings | None = None) -> KaosSourceGovInfoSettings:
    if settings is not None:
        return settings
    return KaosSourceGovInfoSettings()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GovInfoSearchResult:
    """A single search result from GovInfo."""

    title: str
    package_id: str
    collection_code: str = ""
    doc_class: str = ""
    date_issued: str = ""
    government_author: str = ""
    publisher: str = ""
    category: str = ""
    last_modified: str = ""
    detail_url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GovInfoSearchResponse:
    """Paginated search response."""

    results: list[GovInfoSearchResult]
    count: int
    offset: int
    next_offset: int | None = None


@dataclass(frozen=True, slots=True)
class GovInfoPackage:
    """GovInfo package metadata."""

    package_id: str
    title: str
    collection_code: str = ""
    date_issued: str = ""
    doc_class: str = ""
    pages: int = 0
    government_author: str = ""
    publisher: str = ""
    category: str = ""
    last_modified: str = ""
    download_url: str = ""
    detail_url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GovInfoCollection:
    """A GovInfo collection (e.g. BILLS, FR, CFR)."""

    collection_code: str
    collection_name: str
    package_count: int = 0
    granule_count: int = 0


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_search_result(data: dict[str, Any]) -> GovInfoSearchResult:
    return GovInfoSearchResult(
        title=data.get("title", ""),
        package_id=data.get("packageId", ""),
        collection_code=data.get("collectionCode", ""),
        doc_class=data.get("docClass", ""),
        date_issued=data.get("dateIssued", ""),
        government_author=data.get("governmentAuthor1", ""),
        publisher=data.get("publisher", ""),
        category=data.get("category", ""),
        last_modified=data.get("lastModified", ""),
        detail_url=data.get("detailsLink", ""),
        extra={
            k: v
            for k, v in data.items()
            if k
            not in {
                "title",
                "packageId",
                "collectionCode",
                "docClass",
                "dateIssued",
                "governmentAuthor1",
                "publisher",
                "category",
                "lastModified",
                "detailsLink",
            }
            and v
        },
    )


def _parse_package(data: dict[str, Any]) -> GovInfoPackage:
    return GovInfoPackage(
        package_id=data.get("packageId", ""),
        title=data.get("title", ""),
        collection_code=data.get("collectionCode", ""),
        date_issued=data.get("dateIssued", ""),
        doc_class=data.get("docClass", ""),
        pages=data.get("pages") or 0,
        government_author=data.get("governmentAuthor1", ""),
        publisher=data.get("publisher", ""),
        category=data.get("category", ""),
        last_modified=data.get("lastModified", ""),
        download_url=data.get("download", {}).get("pdfLink", ""),
        detail_url=data.get("detailsLink", ""),
        extra={
            k: v
            for k, v in data.items()
            if k
            not in {
                "packageId",
                "title",
                "collectionCode",
                "dateIssued",
                "docClass",
                "pages",
                "governmentAuthor1",
                "publisher",
                "category",
                "lastModified",
                "download",
                "detailsLink",
            }
            and v
        },
    )


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------


async def search(
    query: str,
    *,
    collection: str | None = None,
    page_size: int = 20,
    offset_mark: str = "*",
    settings: KaosSourceGovInfoSettings | None = None,
) -> GovInfoSearchResponse:
    """Search GovInfo across all government publications.

    Args:
        query: Search query string.
        collection: Optional collection code filter (e.g. "FR", "BILLS", "CFR").
        page_size: Results per page (max 100).
        offset_mark: Cursor-based pagination mark ("*" for first page).
        settings: Optional settings instance.

    Returns:
        GovInfoSearchResponse with results and pagination.
    """
    s = _get_settings(settings)
    api_key = s.get_api_key()

    body: dict[str, Any] = {
        "query": query,
        "pageSize": min(page_size, 100),
        "offsetMark": offset_mark,
    }
    if collection:
        body["collection"] = collection

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers={
            "User-Agent": s.user_agent,
            "Accept": "application/json",
            "X-Api-Key": api_key,
        },
    ) as client:
        resp = await client.post(f"{_BASE_URL}/search", json=body)
        resp.raise_for_status()
        data = resp.json()

    results = [_parse_search_result(r) for r in data.get("results", [])]
    count = data.get("count", 0)
    next_mark = data.get("nextOffsetMark")

    return GovInfoSearchResponse(
        results=results,
        count=count,
        offset=0,
        next_offset=1 if next_mark else None,
    )


async def get_package(
    package_id: str,
    *,
    settings: KaosSourceGovInfoSettings | None = None,
) -> GovInfoPackage:
    """Get metadata for a specific GovInfo package.

    Args:
        package_id: GovInfo package ID (e.g. "FR-2024-06-15").
        settings: Optional settings instance.

    Returns:
        GovInfoPackage with full metadata.
    """
    s = _get_settings(settings)
    api_key = s.get_api_key()

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers={
            "User-Agent": s.user_agent,
            "Accept": "application/json",
            "X-Api-Key": api_key,
        },
    ) as client:
        resp = await client.get(f"{_BASE_URL}/packages/{package_id}/summary")
        resp.raise_for_status()
        data = resp.json()

    return _parse_package(data)


async def get_collections(
    *,
    settings: KaosSourceGovInfoSettings | None = None,
) -> list[GovInfoCollection]:
    """List all GovInfo collections.

    Returns:
        List of GovInfoCollection objects.
    """
    s = _get_settings(settings)
    api_key = s.get_api_key()

    async with httpx.AsyncClient(
        timeout=s.timeout,
        headers={
            "User-Agent": s.user_agent,
            "Accept": "application/json",
            "X-Api-Key": api_key,
        },
    ) as client:
        resp = await client.get(f"{_BASE_URL}/collections")
        resp.raise_for_status()
        data = resp.json()

    return [
        GovInfoCollection(
            collection_code=c.get("collectionCode", ""),
            collection_name=c.get("collectionName", ""),
            package_count=c.get("packageCount", 0),
            granule_count=c.get("granuleCount", 0),
        )
        for c in data.get("collections", [])
    ]
