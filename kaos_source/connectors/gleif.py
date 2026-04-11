"""GLEIF (Global Legal Entity Identifier Foundation) API connector.

Provides LEI (Legal Entity Identifier) lookups against the public GLEIF
API.  No authentication required.  Returns structured entity data:
legal name, jurisdiction, registered address, headquarters, parent
entities, and registration status.

API reference: https://www.gleif.org/en/lei-data/gleif-api
Base URL: https://api.gleif.org/api/v1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_BASE_URL = "https://api.gleif.org/api/v1"
_TIMEOUT = 30.0


# ── Data models ─────────────────────────────────────────────────────


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


# ── Parsing ─────────────────────────────────────────────────────────


def _parse_address(data: dict[str, Any] | None) -> LEIAddress | None:
    if not data:
        return None
    return LEIAddress(
        lines=data.get("addressLines") or [],
        city=data.get("city"),
        region=data.get("region"),
        country=data.get("country"),
        postal_code=data.get("postalCode"),
    )


def _parse_entity(record: dict[str, Any]) -> LEIEntity:
    attrs = record.get("attributes", {})
    entity = attrs.get("entity", {})
    reg = attrs.get("registration", {})

    legal_name_data = entity.get("legalName", {})

    other_names: list[str] = []
    for on in entity.get("otherNames", []):
        name = on.get("name")
        if name:
            other_names.append(name)

    return LEIEntity(
        lei=attrs.get("lei", record.get("id", "")),
        legal_name=legal_name_data.get("name", ""),
        legal_name_language=legal_name_data.get("language"),
        other_names=other_names or None,
        jurisdiction=entity.get("jurisdiction"),
        legal_form=entity.get("legalForm", {}).get("id"),
        entity_status=entity.get("status"),
        entity_category=entity.get("category"),
        legal_address=_parse_address(entity.get("legalAddress")),
        headquarters_address=_parse_address(entity.get("headquartersAddress")),
        registration_authority_id=entity.get("registeredAt", {}).get("id"),
        registration_authority_entity_id=entity.get("registeredAs"),
        initial_registration_date=reg.get("initialRegistrationDate"),
        last_update_date=reg.get("lastUpdateDate"),
        next_renewal_date=reg.get("nextRenewalDate"),
        managing_lou=reg.get("managingLou"),
    )


# ── API functions ───────────────────────────────────────────────────


async def search_lei(
    name: str,
    *,
    page: int = 1,
    per_page: int = 10,
    timeout: float = _TIMEOUT,
) -> tuple[list[LEIEntity], int]:
    """Search GLEIF by legal entity name.

    Args:
        name: Entity name to search for.
        page: Page number (1-based).
        per_page: Results per page (max 200).
        timeout: Request timeout.

    Returns:
        Tuple of (entities, total_count).
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            f"{_BASE_URL}/lei-records",
            params={
                "filter[entity.legalName]": name,
                "page[number]": page,
                "page[size]": min(per_page, 200),
            },
        )
        resp.raise_for_status()
        data = resp.json()

    records = data.get("data", [])
    total = data.get("meta", {}).get("pagination", {}).get("total", len(records))
    entities = [_parse_entity(r) for r in records]
    return entities, total


async def get_lei(
    lei: str,
    *,
    timeout: float = _TIMEOUT,
) -> LEIEntity | None:
    """Look up a specific LEI.

    Args:
        lei: The 20-character LEI code.
        timeout: Request timeout.

    Returns:
        LEIEntity or None if not found.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{_BASE_URL}/lei-records/{lei}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

    record = data.get("data")
    if not record:
        return None
    return _parse_entity(record)


async def search_lei_by_country(
    country: str,
    *,
    name: str | None = None,
    page: int = 1,
    per_page: int = 10,
    timeout: float = _TIMEOUT,
) -> tuple[list[LEIEntity], int]:
    """Search GLEIF by country code, optionally filtered by name.

    Args:
        country: ISO 3166-1 alpha-2 country code (e.g., 'US', 'GB').
        name: Optional entity name filter.
        page: Page number.
        per_page: Results per page.
        timeout: Request timeout.

    Returns:
        Tuple of (entities, total_count).
    """
    params: dict[str, Any] = {
        "filter[entity.legalAddress.country]": country.upper(),
        "page[number]": page,
        "page[size]": min(per_page, 200),
    }
    if name:
        params["filter[entity.legalName]"] = name

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{_BASE_URL}/lei-records", params=params)
        resp.raise_for_status()
        data = resp.json()

    records = data.get("data", [])
    total = data.get("meta", {}).get("pagination", {}).get("total", len(records))
    entities = [_parse_entity(r) for r in records]
    return entities, total
