"""GLEIF HTTP client — raw async functions.

Public REST API at ``api.gleif.org/api/v1`` — no authentication required.
This module is the implementation layer for the
:class:`GleifApiConnector` and the GLEIF MCP tools: bytes in, structured
records out.

Functions:

- :func:`search_lei` — paginated search by legal entity name
- :func:`search_lei_by_country` — paginated search filtered by ISO
  3166-1 alpha-2 country code (optionally combined with a name filter)
- :func:`get_lei` — fetch a single LEI record by 20-character code

Unlike the other ``apis/`` clients, GLEIF has *no* dedicated settings
class — the API is unauthenticated and the only knob is a per-call
``timeout`` parameter. Callers wanting to override the default 30 s
timeout pass ``timeout=...`` explicitly.

Reference: https://www.gleif.org/en/lei-data/gleif-api
Base URL: https://api.gleif.org/api/v1
"""

from __future__ import annotations

from typing import Any

import httpx

from kaos_source.apis._http import fetch_json, raise_api_status
from kaos_source.apis.gleif.models import LEIAddress, LEIEntity

_BASE_URL = "https://api.gleif.org/api/v1"
_TIMEOUT = 30.0


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
        # KSRC-02 + KSRC-07: streamed JSON read with size cap and typed
        # retryable errors (Retry-After honored).
        data = await fetch_json(
            client,
            f"{_BASE_URL}/lei-records",
            api="GLEIF",
            params={
                "filter[entity.legalName]": name,
                "page[number]": page,
                "page[size]": min(per_page, 200),
            },
        )

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
    url = f"{_BASE_URL}/lei-records/{lei}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        # KSRC-02 + KSRC-07: streamed read with size cap; raise typed
        # transient/access errors with Retry-After. 404 returns None
        # rather than propagating SourceNotFoundError because the
        # caller's contract is "lookup, may not exist".
        from kaos_core.security import read_capped_json

        async with client.stream("GET", url) as resp:
            if resp.status_code == 404:
                return None
            raise_api_status(resp, locator=url, api="GLEIF")
            data = await read_capped_json(resp)

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
        # KSRC-02 + KSRC-07.
        data = await fetch_json(client, f"{_BASE_URL}/lei-records", api="GLEIF", params=params)

    records = data.get("data", [])
    total = data.get("meta", {}).get("pagination", {}).get("total", len(records))
    entities = [_parse_entity(r) for r in records]
    return entities, total


__all__ = [
    "get_lei",
    "search_lei",
    "search_lei_by_country",
]
