"""Frozen value types for the Federal Register API.

These dataclasses describe records returned by the Federal Register
public API at ``federalregister.gov/api/v1``. They are the structured
output of :mod:`kaos_source.apis.federal_register.client` functions and
the input to :mod:`kaos_source.apis.federal_register.tools` MCP tools.

All types are ``frozen=True, slots=True`` — they are pure value objects
intended for safe sharing across async boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FRDocument:
    """A Federal Register document (metadata).

    Every string field defaults to ``""`` so callers that use the
    ``fields`` parameter to request a subset don't crash when the FR
    API omits unrequested keys. ``document_number`` stays first for
    ordering but is still optional to survive malformed API responses.
    """

    document_number: str = ""
    title: str = ""
    type: str = ""
    publication_date: str = ""
    citation: str = ""
    abstract: str = ""
    subtype: str = ""
    agencies: list[dict[str, Any]] = field(default_factory=list)
    agency_names: list[str] = field(default_factory=list)
    start_page: int = 0
    end_page: int = 0
    page_length: int = 0
    html_url: str = ""
    pdf_url: str = ""
    json_url: str = ""
    full_text_xml_url: str = ""
    raw_text_url: str = ""
    body_html_url: str = ""
    effective_on: str = ""
    comments_close_on: str = ""
    dates: str = ""
    action: str = ""
    docket_ids: list[str] = field(default_factory=list)
    cfr_references: list[dict[str, Any]] = field(default_factory=list)
    regulation_id_numbers: list[str] = field(default_factory=list)
    significant: bool = False
    topics: list[str] = field(default_factory=list)
    excerpts: str = ""
    comment_url: str = ""
    regulations_dot_gov_url: str = ""
    signing_date: str = ""
    president: dict[str, Any] = field(default_factory=dict)
    executive_order_number: str = ""
    proclamation_number: str = ""
    volume: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FRSearchResult:
    """Paginated search result from the Federal Register API."""

    documents: list[FRDocument]
    count: int
    total_pages: int
    next_page_url: str | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class FRAgency:
    """A Federal Register agency."""

    id: int
    name: str
    short_name: str = ""
    slug: str = ""
    url: str = ""
    parent_id: int | None = None
    child_ids: list[int] = field(default_factory=list)
    description: str = ""


__all__ = ["FRAgency", "FRDocument", "FRSearchResult"]
