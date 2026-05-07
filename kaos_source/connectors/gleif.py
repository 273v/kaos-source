"""Backwards-compatibility shim — GLEIF connector moved to :mod:`kaos_source.apis.gleif`.

The implementation now lives at :mod:`kaos_source.apis.gleif.client`
(async HTTP functions) and :mod:`kaos_source.apis.gleif.models` (frozen
dataclass value types). New code should import from those modules
directly. This shim re-exports the public names so existing
``from kaos_source.connectors.gleif import ...`` imports keep working.
"""

from __future__ import annotations

from kaos_source.apis.gleif.client import (
    get_lei,
    search_lei,
    search_lei_by_country,
)
from kaos_source.apis.gleif.models import LEIAddress, LEIEntity

__all__ = [
    "LEIAddress",
    "LEIEntity",
    "get_lei",
    "search_lei",
    "search_lei_by_country",
]
