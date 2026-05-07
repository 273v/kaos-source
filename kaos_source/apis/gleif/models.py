"""Frozen value types for the GLEIF (Legal Entity Identifier) API.

These dataclasses describe records returned by the public GLEIF API at
``api.gleif.org/api/v1``. They are the structured output of
:mod:`kaos_source.apis.gleif.client` functions and the input to
:mod:`kaos_source.apis.gleif.tools` MCP tools.

All types are ``frozen=True, slots=True`` — they are pure value objects
intended for safe sharing across async boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LEIAddress:
    """Structured address from GLEIF."""

    lines: list[str]
    city: str | None = None
    region: str | None = None
    country: str | None = None
    postal_code: str | None = None


@dataclass(frozen=True, slots=True)
class LEIEntity:
    """Parsed GLEIF LEI record."""

    lei: str
    legal_name: str
    legal_name_language: str | None = None
    other_names: list[str] | None = None
    jurisdiction: str | None = None
    legal_form: str | None = None
    entity_status: str | None = None
    entity_category: str | None = None
    legal_address: LEIAddress | None = None
    headquarters_address: LEIAddress | None = None
    registration_authority_id: str | None = None
    registration_authority_entity_id: str | None = None
    initial_registration_date: str | None = None
    last_update_date: str | None = None
    next_renewal_date: str | None = None
    managing_lou: str | None = None


__all__ = ["LEIAddress", "LEIEntity"]
