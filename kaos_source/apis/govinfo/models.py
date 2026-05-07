"""Frozen value types for the GovInfo (US GPO) API.

These dataclasses describe records returned by the GovInfo public REST
API at ``api.govinfo.gov``. They are the structured output of
:mod:`kaos_source.apis.govinfo.client` functions and the input to
:mod:`kaos_source.apis.govinfo.tools` MCP tools.

All types are ``frozen=True, slots=True`` — they are pure value objects
intended for safe sharing across async boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


__all__ = [
    "GovInfoCollection",
    "GovInfoPackage",
    "GovInfoSearchResponse",
    "GovInfoSearchResult",
]
