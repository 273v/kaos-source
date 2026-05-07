"""Back-compat shim — moved to :mod:`kaos_source.apis.govinfo`.

The GovInfo connector code now lives in
:mod:`kaos_source.apis.govinfo.client` (functions),
:mod:`kaos_source.apis.govinfo.models` (dataclasses), and
:mod:`kaos_source.apis.govinfo.connector` (:class:`GovInfoApiConnector`).
Settings live in :mod:`kaos_source.settings.govinfo`.

Existing import paths under :mod:`kaos_source.connectors.govinfo` keep
resolving via this shim — prefer the new locations for new code.
"""

from __future__ import annotations

from kaos_source.apis.govinfo.client import (
    get_collections,
    get_package,
    search,
)
from kaos_source.apis.govinfo.models import (
    GovInfoCollection,
    GovInfoPackage,
    GovInfoSearchResponse,
    GovInfoSearchResult,
)
from kaos_source.settings.govinfo import KaosSourceGovInfoSettings

__all__ = [
    "GovInfoCollection",
    "GovInfoPackage",
    "GovInfoSearchResponse",
    "GovInfoSearchResult",
    "KaosSourceGovInfoSettings",
    "get_collections",
    "get_package",
    "search",
]
