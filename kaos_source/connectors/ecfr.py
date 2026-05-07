"""Back-compat shim for the eCFR connector.

The canonical implementation moved to :mod:`kaos_source.apis.ecfr` in
Track 1 chunk 5. This module preserves the legacy import path
``from kaos_source.connectors.ecfr import ...`` so existing callers
(integration tests, downstream consumers) keep resolving without
changes. Prefer the new locations for fresh code:

- :mod:`kaos_source.apis.ecfr.client` — async API functions
- :mod:`kaos_source.apis.ecfr.models` — dataclass types
- :mod:`kaos_source.apis.ecfr.tools` — MCP tool classes
- :mod:`kaos_source.settings.ecfr` — :class:`KaosSourceECFRSettings`
"""

from __future__ import annotations

from kaos_source.apis.ecfr.client import (
    _api_headers,
    _parse_agency,
    _parse_structure,
    _parse_title,
    get_agencies,
    get_latest_date,
    get_section_content,
    get_title_structure,
    get_titles,
)
from kaos_source.apis.ecfr.models import ECFRAgency, ECFRStructureNode, ECFRTitle
from kaos_source.settings.ecfr import KaosSourceECFRSettings

__all__ = [
    "ECFRAgency",
    "ECFRStructureNode",
    "ECFRTitle",
    "KaosSourceECFRSettings",
    "_api_headers",
    "_parse_agency",
    "_parse_structure",
    "_parse_title",
    "get_agencies",
    "get_latest_date",
    "get_section_content",
    "get_title_structure",
    "get_titles",
]
